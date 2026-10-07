# dashboard.py - Dashboard completo com alertas em tempo real
from flask import Flask, render_template, jsonify, send_file
from flask_socketio import SocketIO
import pymysql
from datetime import datetime, timedelta
import json
import os
import time
import threading

app = Flask(__name__, 
           template_folder='templates',
           static_folder='static')

socketio = SocketIO(app, cors_allowed_origins="*")

def get_db_connection():
    """Obtém uma conexão do pool global"""
    try:
        from config.db_config import DB_POOL
        return DB_POOL.get_connection()
    except Exception as e:
        print(f"Erro ao obter conexão do pool: {e}")
        return None

def release_db_connection(conn):
    """Libera a conexão de volta ao pool global"""
    try:
        from config.db_config import DB_POOL
        DB_POOL.release_connection(conn)
    except Exception as e:
        print(f"Erro ao liberar conexão: {e}")


# Rota principal
@app.route('/')
def index():
    """Página principal do dashboard"""
    return render_template('dashboard.html')

# API: Estatísticas gerais
@app.route('/api/stats')
def get_stats():
    """API: Retorna estatísticas gerais"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        with conn.cursor() as cursor:
            stats = {}
            
            # Pessoas ativas
            cursor.execute("SELECT COUNT(*) as count FROM person_cache WHERE is_active = 1")
            stats['active_persons'] = cursor.fetchone()['count']
            
            # Detecções hoje
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM person_occurrences 
                WHERE DATE(detection_time) = CURDATE()
            """)
            stats['today_detections'] = cursor.fetchone()['count']
            
            # Pessoas únicas hoje
            cursor.execute("""
                SELECT COUNT(DISTINCT person_uuid) as count 
                FROM person_occurrences 
                WHERE DATE(detection_time) = CURDATE()
            """)
            stats['unique_today'] = cursor.fetchone()['count']
            
            # Alertas hoje
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM alert_snapshots 
                WHERE DATE(created_at) = CURDATE()
            """)
            stats['today_alerts'] = cursor.fetchone()['count']
            
            # Alertas ativos (última hora)
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM alert_snapshots 
                WHERE created_at >= NOW() - INTERVAL 1 HOUR
            """)
            stats['active_alerts'] = cursor.fetchone()['count']
            
            # Últimos alertas
            cursor.execute("""
                SELECT * FROM alert_snapshots 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            recent_alerts = cursor.fetchall()
            
            # Detecções por hora (últimas 6 horas)
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(detection_time, '%%H:00') as hour,
                    COUNT(*) as count
                FROM person_occurrences 
                WHERE detection_time >= NOW() - INTERVAL 6 HOUR
                GROUP BY DATE_FORMAT(detection_time, '%%H')
                ORDER BY hour
            """)
            hourly_data = cursor.fetchall()
            
        return jsonify({
            'success': True,
            'stats': stats,
            'recent_alerts': recent_alerts,
            'hourly': hourly_data,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Erro na API stats: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)

# API: Alertas com screenshots
@app.route('/api/alerts')
def get_alerts():
    """API: Retorna alertas ativos com screenshots"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'alerts': [], 'count': 0})
    
    try:
        with conn.cursor() as cursor:
            # Primeiro verificar a estrutura da tabela
            cursor.execute("SHOW COLUMNS FROM alert_snapshots")
            columns = [col['Field'] for col in cursor.fetchall()]
            
            # Construir query dinâmica baseada nas colunas existentes
            select_fields = [
                "a.id",
                "a.person_uuid",
                "a.alert_type"
            ]
            
            # Adicionar colunas condicionalmente
            if 'zone' in columns:
                select_fields.append("a.zone")
            else:
                select_fields.append("NULL as zone")
                
            if 'time_in_zone' in columns:
                select_fields.append("a.time_in_zone")
            else:
                select_fields.append("0 as time_in_zone")
                
            select_fields.extend([
                "a.file_path",
                "a.created_at",
                "p.confidence_score"
            ])
            
            select_clause = ", ".join(select_fields)
            
            query = f"""
                SELECT {select_clause}
                FROM alert_snapshots a
                LEFT JOIN person_cache p ON a.person_uuid = p.person_uuid
                WHERE a.created_at >= NOW() - INTERVAL 2 HOUR
                ORDER BY a.created_at DESC
                LIMIT 20
            """
            
            cursor.execute(query)
            alerts = cursor.fetchall()
            
            # Processar caminhos das imagens
            alerts_list = []
            for alert in alerts:
                screenshot_url = ""
                has_screenshot = False
                
                if alert['file_path']:
                    # Verificar se o arquivo existe
                    if os.path.exists(alert['file_path']):
                        filename = os.path.basename(alert['file_path'])
                        screenshot_url = f"/api/alert_image/{filename}"
                        has_screenshot = True
                    else:
                        # Tentar encontrar em diretórios comuns
                        common_dirs = [
                            "./alerts",
                            "alerts",
                            "../alerts",
                            os.path.join(os.getcwd(), "alerts"),
                            os.path.dirname(os.path.abspath(__file__)) + "/alerts"
                        ]
                        
                        filename = os.path.basename(alert['file_path'])
                        for dir_path in common_dirs:
                            possible_path = os.path.join(dir_path, filename)
                            if os.path.exists(possible_path):
                                screenshot_url = f"/api/alert_image/{filename}"
                                has_screenshot = True
                                break
                
                alerts_list.append({
                    'id': alert['id'],
                    'person_uuid': alert['person_uuid'],
                    'short_uuid': alert['person_uuid'][:8] if alert['person_uuid'] else 'Unknown',
                    'alert_type': alert['alert_type'],
                    'zone': alert.get('zone', 'Desconhecida'),
                    'time_in_zone': alert.get('time_in_zone', 0),
                    'screenshot_url': screenshot_url,
                    'created_at': alert['created_at'].isoformat() if alert['created_at'] else None,
                    'confidence': float(alert['confidence_score']) if alert['confidence_score'] else 0.0,
                    'has_screenshot': has_screenshot
                })
            
        return jsonify({
            'success': True,
            'alerts': alerts_list,
            'count': len(alerts_list),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Erro na API alerts: {e}")
        return jsonify({'alerts': [], 'count': 0, 'error': str(e)})
    finally:
        if conn:
            release_db_connection(conn)

# API: Serve imagens de alertas
@app.route('/api/alert_image/<path:filename>')
def get_alert_image(filename):
    """Serve imagens de alertas"""
    try:
        import mimetypes
        
        # Segurança: prevenir directory traversal
        safe_filename = os.path.basename(filename)
        
        # Lista de diretórios para buscar
        search_dirs = [
            "alerts",
            "./alerts",
            "../alerts",
            os.path.join(os.getcwd(), "alerts"),
            os.path.dirname(os.path.abspath(__file__)) + "/alerts"
        ]
        
        # Tentar encontrar o arquivo
        found_path = None
        for dir_path in search_dirs:
            possible_path = os.path.join(dir_path, safe_filename)
            if os.path.exists(possible_path):
                found_path = possible_path
                break
        
        if found_path:
            # Determinar tipo MIME
            mime_type, _ = mimetypes.guess_type(found_path)
            if not mime_type:
                mime_type = 'image/jpeg'
            
            return send_file(found_path, mimetype=mime_type)
        else:
            # Criar imagem placeholder personalizada
            from PIL import Image, ImageDraw, ImageFont
            import tempfile
            
            img = Image.new('RGB', (400, 300), color='#2c3e50')
            d = ImageDraw.Draw(img)
            
            try:
                font = ImageFont.truetype("arial.ttf", 24)
            except:
                font = ImageFont.load_default()
            
            # Desenhar texto
            d.text((200, 120), "?? ALERTA", fill='#e74c3c', font=font, anchor='mm')
            d.text((200, 160), "Imagem não disponível", fill='white', font=font, anchor='mm')
            d.text((200, 200), safe_filename[:20], fill='#bdc3c7', font=font, anchor='mm')
            
            # Salvar em arquivo temporário
            temp_path = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg').name
            img.save(temp_path, 'JPEG', quality=85)
            
            return send_file(temp_path, mimetype='image/jpeg')
            
    except Exception as e:
        print(f"Erro ao servir imagem {filename}: {e}")
        return jsonify({'error': str(e)}), 500

# API: Últimas detecções
@app.route('/api/recent')
def get_recent():
    """API: Apenas detecções recentes"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'recent': []})
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    person_uuid,
                    camera_id,
                    detection_time,
                    bbox
                FROM person_occurrences 
                ORDER BY detection_time DESC 
                LIMIT 10
            """)
            recent = cursor.fetchall()
            
            # Processar dados
            recent_list = []
            for item in recent:
                recent_list.append({
                    'person_uuid': item['person_uuid'],
                    'short_uuid': item['person_uuid'][:8] if item['person_uuid'] else 'Unknown',
                    'camera_id': item['camera_id'],
                    'detection_time': item['detection_time'].isoformat() if item['detection_time'] else None
                })
            
        return jsonify({'recent': recent_list})
        
    finally:
        if conn:
            release_db_connection(conn)

# API: Detalhes da pessoa
@app.route('/api/person/<uuid>')
def get_person_details(uuid):
    """API: Detalhes de uma pessoa específica"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        with conn.cursor() as cursor:
            # Informações da pessoa
            cursor.execute("""
                SELECT * FROM person_cache 
                WHERE person_uuid = %s
            """, (uuid,))
            person = cursor.fetchone()
            
            if not person:
                return jsonify({'error': 'Pessoa não encontrada'}), 404
            
            # Histórico de detecções
            cursor.execute("""
                SELECT * FROM person_occurrences 
                WHERE person_uuid = %s
                ORDER BY detection_time DESC
                LIMIT 50
            """, (uuid,))
            history = cursor.fetchall()
            
            # Alertas desta pessoa
            cursor.execute("""
                SELECT * FROM alert_snapshots 
                WHERE person_uuid = %s
                ORDER BY created_at DESC
                LIMIT 10
            """, (uuid,))
            alerts = cursor.fetchall()
            
        return jsonify({
            'success': True,
            'person': person,
            'history': history,
            'alerts': alerts
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)

# WebSocket: Atualizações em tempo real
@socketio.on('connect')
def handle_connect():
    print('Cliente conectado via WebSocket')

def background_alerts_check():
    """Thread para verificar novos alertas periodicamente"""
    while True:
        try:
            time.sleep(5)  # Verificar a cada 5 segundos
            
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cursor:
                    # Verificar alertas muito recentes (últimos 10 segundos)
                    cursor.execute("""
                        SELECT COUNT(*) as count 
                        FROM alert_snapshots 
                        WHERE created_at >= NOW() - INTERVAL 10 SECOND
                    """)
                    new_alerts = cursor.fetchone()['count']
                    
                    if new_alerts > 0:
                        # Emitir evento para todos os clientes
                        socketio.emit('new_alert', {
                            'count': new_alerts,
                            'timestamp': datetime.now().isoformat()
                        })
                        print(f"📢 Novo alerta detectado: {new_alerts}")
                
                release_db_connection(conn)
                
        except Exception as e:
            print(f"Erro no background check: {e}")

# Iniciar thread de verificação de alertas
threading.Thread(target=background_alerts_check, daemon=True).start()

if __name__ == '__main__':
    print("=" * 50)
    print("[INFO] Dashboard web iniciando...")
    print("[INFO] Acesse: http://localhost:5050")
    print("[INFO] WebSocket ativo para atualizacoes em tempo real")
    print("=" * 50)
    
    # Criar diretórios necessários
    os.makedirs("alerts", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    
    socketio.run(app, host='0.0.0.0', port=5050, debug=True, allow_unsafe_werkzeug=True)