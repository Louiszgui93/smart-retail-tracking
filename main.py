import cv2
import time
import logging
import sys
import os
from datetime import datetime

# Adicionar caminho para imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configurar credenciais Google Vision API (se disponível)
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "config", "vision_service_account.json")
if os.path.exists(CREDENTIALS_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH
    print(f"[INFO] Google Vision credentials carregadas de: {CREDENTIALS_PATH}")
else:
    print("[WARN] Google Vision credentials nao encontradas - funcionalidade Vision API desabilitada")
    print(f"   Esperado em: {CREDENTIALS_PATH}")
from reid.id_manager import IdManager, make_signature
from capture.rtsp_reader import RTSPReader
from detection.detector import Detector
from detection.tracker import extract_tracks
from analytics.zones import ZoneManager
from analytics.heatmap import Heatmap
from analytics.metrics import Metrics
from alerts.behavior import BehaviorAnalyzer
from config.db_config import DB_CONFIG
from reid.db_manager import PersonDB
from alerts.behavior import register_alert_to_dashboard
from api.vision_integration import VisionAnalyzer

# =============================
# CONFIGURAÇÃO DE LOGGING
# =============================
log_dir = "./logs"
os.makedirs(log_dir, exist_ok=True)

log_file = f"{log_dir}/tracking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================
# CONFIGURAÇÕES
# =============================
RTSP_URL = os.getenv("RTSP_URL", "")
ZONES_PATH = "config/zones.json"
CAMERA_ID = "cam_entrada"  # ID da câmera para o banco

# =============================
# PARÂMETROS DO SISTEMA
# =============================
CONFIRMATION_FRAMES = 3      # Número de frames para confirmar uma pessoa
ALERT_DISPLAY_TIME = 5       # segundos
STATS_UPDATE_INTERVAL = 100  # frames
CACHE_TTL_MINUTES = 120      # 2 horas de cache
ZONE_ALERT_THRESHOLD = 60    # Segundos para alerta de zona (1 minuto)
TARGET_WIDTH = int(os.getenv("TARGET_WIDTH", 960))  # Largura alvo para processamento (0 para desativar)
SHOW_GUI = os.getenv("SHOW_GUI", "True").lower() == "true"  # Se False, roda em modo headless (sem exibir janela OpenCV)

# =============================
# INICIALIZAÇÃO
# =============================
logger.info("=" * 50)
logger.info("INICIANDO SISTEMA DE TRACKING COM REIDENTIFICAÇÃO")
logger.info("=" * 50)
id_manager = IdManager()

# Inicializar componentes
cam = RTSPReader(RTSP_URL)
detector = Detector()
zones = ZoneManager(ZONES_PATH)
metrics = Metrics()
behavior = BehaviorAnalyzer()

# Inicializar banco de dados
person_db = PersonDB(DB_CONFIG)
person_db.cache_ttl_minutes = CACHE_TTL_MINUTES  # Sobrescrever cache time
person_db.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", 0.55))

# Inicializar Vision Analyzer (opcional)
try:
    vision_analyzer = VisionAnalyzer()
    logger.info("✅ Vision Analyzer inicializado com sucesso")
except Exception as e:
    vision_analyzer = None
    logger.warning(f"⚠️  Vision Analyzer não disponível: {e}")
    logger.warning("   Sistema continuará funcionando sem análise de emoções")

logger.info("? Banco de dados de reidentificação conectado")
logger.info(f"?? Configuração: Cache={CACHE_TTL_MINUTES}min, Confirmação={CONFIRMATION_FRAMES}frames")
logger.info(f"?? Alerta zona: {ZONE_ALERT_THRESHOLD}s")

# =============================
# VARIÁVEIS DE CONTROLE
# =============================
heatmap = None
active_alerts = {}             # Alertas comportamentais (tid -> dados)
zone_alerts = {}               # Alertas de zona {alert_key: dados}
track_to_person = {}           # Mapeia track_id -> person_uuid persistente
track_to_logical_id = {}       # Mapeia track_id -> logical_id do id_manager (Bugfix)
last_db_log_time = {}             # Mapeia track_id -> timestamp da última escrita no banco (Performance)
DB_LOG_INTERVAL = 1.0             # Intervalo mínimo de gravações no banco (segundos)
pending_confirmations = {}     # Para confirmação em múltiplos frames
disappeared_tracks = {}        # Tracks que desapareceram (para limpeza)
zone_tracking = {}             # Track tempo por zona: {(tid, zone): start_time}
last_zone_position = {}        # Última zona de cada track
DISAPPEARED_TIMEOUT = 5.0       # Segundos antes de remover track desaparecido (tolerância para oclusões rápidas)
pending_screenshots = []  # Lista de screenshots pendentes para capturar


frame_count = 0
last_frame_id = -1
total_persons_today = 0
start_time = time.time()

# =============================
# FUNÇÕES AUXILIARES
# =============================
def cleanup_old_tracks():
    """Limpa tracks que desapareceram de fato após o tempo limite (grace period)"""
    current_time = time.time()
    tracks_to_remove = []
    
    for tid, disappearance_time in disappeared_tracks.items():
        if current_time - disappearance_time > DISAPPEARED_TIMEOUT:
            tracks_to_remove.append(tid)
    
    for tid in tracks_to_remove:
        if tid in track_to_person:
            person_uuid = track_to_person[tid]
            log_person_event("disappeared", tid, person_uuid)
            
            # Remover ID lógico do id_manager ao expirar de fato
            logical_id = track_to_logical_id.get(tid)
            if logical_id is not None:
                id_manager.remove(logical_id)
            
            logger.info(f"??? Removendo track {tid} (desaparecido há >{DISAPPEARED_TIMEOUT}s)")
            del track_to_person[tid]
        
        if tid in pending_confirmations:
            logger.info(f"??? Cancelando confirmação do track {tid}")
            del pending_confirmations[tid]
        
        if tid in disappeared_tracks:
            del disappeared_tracks[tid]
            
        if tid in track_to_logical_id:
            del track_to_logical_id[tid]
        
        # Limpar tracking de zona
        keys_to_remove = [k for k in zone_tracking.keys() if k[0] == tid]
        for key in keys_to_remove:
            del zone_tracking[key]
        
        # Limpar alertas de zona deste track
        zone_alert_keys = [k for k in zone_alerts.keys() if f"_{tid}_" in k]
        for key in zone_alert_keys:
            del zone_alerts[key]

# Adicione essa função auxiliar para captura de screenshots
def capture_zone_alert_screenshot(frame, tid, tracks, screenshot_data):
    """Captura screenshot de alerta de zona"""
    logger.debug(f"🔍 Tentando capturar screenshot para track {tid}")
    
    if tid is None or frame is None:
        logger.error("❌ tid ou frame é None")
        return None
    
    # Encontrar o track atual para obter bbox
    current_track = next((t for t in tracks if t["id"] == tid), None)
    
    if not current_track:
        logger.warning(f"❌ Track {tid} não encontrado em tracks atuais")
        return None
    
    bbox = current_track["bbox"]
    x1, y1, x2, y2 = map(int, bbox)
    logger.debug(f"📐 BBox encontrada: {x1},{y1},{x2},{y2}")
    
    # Verificar se a bbox é válida
    h, w = frame.shape[:2]
    if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
        logger.warning(f"⚠️  BBox inválida: {bbox} (frame: {w}x{h})")
        return None
    
    try:
        logger.debug(f"📸 Chamando capture_alert_snapshot para pessoa {screenshot_data['person_uuid'][:8]}")
        
        # Capturar screenshot com dados de zona e tempo
        screenshot_path = person_db.capture_alert_snapshot(
            frame, 
            [x1, y1, x2, y2],
            screenshot_data['person_uuid'],
            alert_type="zona",
            camera_id=CAMERA_ID,
            zone=screenshot_data.get('zone'),
            time_in_zone=screenshot_data.get('time_in_zone', 0)
        )
        
        if screenshot_path:
            logger.info(f"✅ Screenshot capturado: {screenshot_data['person_uuid'][:8]} -> {screenshot_path}")
            return screenshot_path
        else:
            logger.warning(f"❌ capture_alert_snapshot retornou None para {screenshot_data['person_uuid'][:8]}")
            # Tentar método alternativo
            return simple_capture_screenshot(frame, [x1, y1, x2, y2], 
                                           screenshot_data['person_uuid'], "zona", CAMERA_ID)
            
    except Exception as e:
        logger.error(f"❌ Erro ao capturar screenshot: {e}", exc_info=True)
        # Fallback para método simples
        try:
            return simple_capture_screenshot(frame, [x1, y1, x2, y2], 
                                           screenshot_data['person_uuid'], "zona", CAMERA_ID)
        except Exception as e2:
            logger.error(f"❌ Fallback também falhou: {e2}")
    
    return None

# Atualize a função check_zone_alerts para capturar screenshot imediatamente:
def check_zone_alerts(tracks, frame):
    """Verifica se alguém está há muito tempo em uma zona - RETORNA LISTA de novos alertas"""
    alerts = []
    current_time = time.time()
    
    for (tid, zone), start_time in zone_tracking.items():
        time_in_zone = current_time - start_time
        
        if time_in_zone >= ZONE_ALERT_THRESHOLD:
            person_uuid = track_to_person.get(tid, "Desconhecido")
            
            # Verificar se já alertamos recentemente
            alert_key = f"zone_{tid}_{zone}"
            last_alert_time = zone_alerts.get(alert_key, {}).get("timestamp", 0)
            
            if current_time - last_alert_time > 10:
                # Capturar screenshot
                screenshot_path = capture_zone_alert_screenshot(
                    frame, tid, tracks, {
                        'track_id': tid,
                        'person_uuid': person_uuid,
                        'zone': zone,
                        'time_in_zone': int(time_in_zone)
                    }
                ) if person_uuid != "Desconhecido" else ""
                
                alert_data = {
                    'track_id': tid,
                    'person_uuid': person_uuid,
                    'zone': zone,
                    'time_in_zone': int(time_in_zone),
                    'alert_time': datetime.now().isoformat(),
                    'alert_key': alert_key,
                    'screenshot_path': screenshot_path
                }
                alerts.append(alert_data)
                
                zone_alerts[alert_key] = {
                    "timestamp": current_time,
                    "zone": zone,
                    "type": "zona",
                    "data": alert_data
                }
                
                # REGISTRAR NO BANCO (apenas se o screenshot_path estiver vazio para evitar duplicados)
                if person_uuid != "Desconhecido" and not screenshot_path:
                    register_alert_to_dashboard(
                        person_uuid=person_uuid,
                        alert_type="zona",
                        zone=zone,
                        time_in_zone=int(time_in_zone),
                        screenshot_path=screenshot_path
                    )
    
    return alerts

def check_saved_screenshots():
    """Verifica quantos screenshots foram salvos"""
    import glob
    screenshots = glob.glob("./alert_screenshots/*.jpg")
    logger.info(f"?? Screenshots salvos no total: {len(screenshots)}")
    
    # Listar os 5 mais recentes
    if screenshots:
        screenshots.sort(key=os.path.getmtime, reverse=True)
        logger.info("?? Últimos 5 screenshots:")
        for i, ss in enumerate(screenshots[:5]):
            mtime = os.path.getmtime(ss)
            age = time.time() - mtime
            logger.info(f"   {i+1}. {os.path.basename(ss)} ({age:.0f}s atrás)")

# Chame esta função periodicamente (a cada 600 frames)
if frame_count % 600 == 0:
    check_saved_screenshots()

def debug_zone_alerts():
    """Mostra informações de debug sobre alertas de zona"""
    now = time.time()
    logger.info("🔍 DEBUG DETALHADO DE ALERTAS DE ZONA:")
    
    if zone_tracking:
        logger.info("📊 Zone Tracking Ativo:")
        for (tid, zone), start_time in zone_tracking.items():
            time_in_zone = now - start_time
            person_uuid = track_to_person.get(tid, "Desconhecido")
            alert_status = "⚠️ ALERTA" if time_in_zone >= ZONE_ALERT_THRESHOLD else "✅ Normal"
            logger.info(f"   Track {tid} ({person_uuid[:8]}): {zone} há {time_in_zone:.1f}s - {alert_status}")
    else:
        logger.info("📊 Zone Tracking: VAZIO")
    
    if zone_alerts:
        logger.info("🚨 Alertas Registrados:")
        for key, alert_data in zone_alerts.items():
            timestamp = alert_data.get("timestamp", 0)
            age = now - timestamp
            logger.info(f"   - {key}: {age:.1f}s atrás")
    else:
        logger.info("🚨 Alertas Registrados: NENHUM")

# =============================
# TESTE DE CONEXÃO COM BANCO DE DADOS
# =============================
def test_database_connection():
    """Testa se a conexão com o banco está funcionando"""
    try:
        # Testar conexão básica
        conn = person_db.get_connection()
        if conn:
            logger.info("? Conexão com banco de dados OK")
            conn.close()
            
            # Testar inserção de alerta
            test_result = person_db.test_alert_insertion()
            if test_result:
                logger.info("? Inserção de alertas no banco OK")
            else:
                logger.warning("??  Possível problema com inserção de alertas")
            
            return True
        else:
            logger.error("? Não foi possível conectar ao banco de dados")
            return False
    except Exception as e:
        logger.error(f"? Erro ao testar conexão com banco: {e}")
        return False

# Adicione esta chamada após inicializar o person_db:
logger.info("?? Testando conexão com banco de dados...")
if not test_database_connection():
    logger.warning("??  Alertas podem não ser registrados no dashboard!")
else:
    logger.info("? Banco de dados pronto para receber alertas")


def verify_alert_table_exists():
    """Verifica se a tabela de alertas existe no banco e realiza migração de colunas se necessário"""
    conn = None
    try:
        conn = person_db.get_connection()
        cursor = conn.cursor()
        
        # Verificar se a tabela existe
        cursor.execute("SHOW TABLES LIKE 'alert_snapshots'")
        result = cursor.fetchone()
        
        if result:
            logger.info("[DB] Tabela 'alert_snapshots' encontrada. Verificando estrutura...")
            
            # Verificar estrutura da tabela
            cursor.execute("DESCRIBE alert_snapshots")
            columns = cursor.fetchall()
            
            existing_columns = {col['Field'].lower(): col for col in columns}
            
            # Colunas necessárias e suas definições
            required_columns = {
                'zone': "VARCHAR(100) DEFAULT NULL",
                'time_in_zone': "INT DEFAULT 0",
                'camera_id': "VARCHAR(50) DEFAULT NULL"
            }
            
            for col_name, col_def in required_columns.items():
                if col_name not in existing_columns:
                    logger.warning(f"[DB] Coluna '{col_name}' ausente na tabela alert_snapshots. Adicionando...")
                    cursor.execute(f"ALTER TABLE alert_snapshots ADD COLUMN {col_name} {col_def}")
                    conn.commit()
                    logger.info(f"[DB] Coluna '{col_name}' adicionada com sucesso.")
            
            return True
        else:
            logger.error("[DB] Tabela 'alert_snapshots' NÃO encontrada! Criando...")
            cursor.execute("""
                CREATE TABLE alert_snapshots (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    person_uuid VARCHAR(255),
                    alert_type VARCHAR(50),
                    zone VARCHAR(100) DEFAULT NULL,
                    time_in_zone INT DEFAULT 0,
                    file_path VARCHAR(500),
                    camera_id VARCHAR(50) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_person (person_uuid),
                    INDEX idx_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            logger.info("[DB] Tabela 'alert_snapshots' criada com sucesso.")
            return True
    except Exception as e:
        logger.error(f"[DB] Erro ao verificar tabela: {e}")
        return False
    finally:
        if conn:
            person_db.release_connection(conn)

# Chame esta função após inicializar o banco:
logger.info("?? Verificando tabela de alertas...")
verify_alert_table_exists()

def simple_capture_screenshot(frame, bbox, person_uuid, alert_type, camera_id):
    """Captura screenshot simples se o método do person_db não existir"""
    import cv2
    from datetime import datetime
    import os
    
    logger.debug(f"?? Usando simple_capture_screenshot para {person_uuid[:8]}")
    
    # Criar diretório para screenshots
    screenshot_dir = "./alert_screenshots"
    os.makedirs(screenshot_dir, exist_ok=True)
    
    # Nome do arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{screenshot_dir}/{person_uuid[:8]}_{alert_type}_{timestamp}.jpg"
    
    # Extrair ROI
    x1, y1, x2, y2 = map(int, bbox)
    
    # Adicionar margem
    margin = 20
    h, w = frame.shape[:2]
    x1 = max(0, x1 - margin)
    y1 = max(0, y1 - margin)
    x2 = min(w, x2 + margin)
    y2 = min(h, y2 + margin)
    
    # Verificar dimensões
    roi_width = x2 - x1
    roi_height = y2 - y1
    
    if roi_width <= 0 or roi_height <= 0:
        logger.error(f"? ROI inválida: {roi_width}x{roi_height}")
        return ""
    
    # Capturar screenshot
    roi = frame[y1:y2, x1:x2]
    
    if roi.size > 0:
        success = cv2.imwrite(filename, roi)
        if success:
            logger.info(f"? Screenshot salvo (simples): {filename}")
            return filename
        else:
            logger.error(f"? cv2.imwrite falhou para {filename}")
    else:
        logger.error(f"? ROI vazia: {x1},{y1},{x2},{y2}")
    
    return ""


def log_person_event(event_type, tid, person_uuid, confidence=0.0, zone=""):
    """Log padronizado para eventos de pessoas"""
    short_uuid = person_uuid[:8]
    
    if event_type == "new":
        logger.info(f"?? NOVA PESSOA: Track {tid} -> {short_uuid} (Zona: {zone})")
    elif event_type == "reid":
        logger.info(f"?? REIDENTIFICADO: Track {tid} -> {short_uuid} (Conf: {confidence:.2f})")
    elif event_type == "disappeared":
        logger.info(f"?? DESAPARECEU: {short_uuid} (Track {tid})")
    elif event_type == "confirmed":
        logger.info(f"? CONFIRMADO: Track {tid} -> {short_uuid}")
    elif event_type == "zone_alert":
        logger.warning(f"?? ALERTA ZONA: {short_uuid} há {confidence:.0f}s na zona {zone}")

# =============================
# LOOP PRINCIPAL
# =============================
logger.info("?? Iniciando loop principal de tracking...")

try:
    while True:
        # Ler frame
        frame = cam.read()
        if frame is None:
            logger.warning("?? Frame vazio recebido")
            time.sleep(0.1)
            continue
            
        # Evitar processar o mesmo frame repetidamente em modo headless
        frame_id = getattr(cam, "frame_id", 0)
        if not SHOW_GUI and frame_id == last_frame_id:
            time.sleep(0.005)
            continue
        last_frame_id = frame_id
        
        # Redimensionamento dinâmico
        original_h, original_w = frame.shape[:2]
        if TARGET_WIDTH > 0 and original_w > TARGET_WIDTH:
            scale = TARGET_WIDTH / original_w
            frame = cv2.resize(frame, (TARGET_WIDTH, int(original_h * scale)))
        else:
            scale = 1.0
        
        # Inicializar heatmap na primeira imagem
        if heatmap is None:
            if scale < 1.0:
                logger.info(f"?? Câmera em alta resolução ({original_w}x{original_h}). Redimensionando para {TARGET_WIDTH}x{int(original_h * scale)} (escala: {scale:.2f})")
                zones.scale_zones(scale)
            h, w = frame.shape[:2]
            heatmap = Heatmap((h, w))
            logger.info(f"?? Dimensões do frame para processamento: {w}x{h}")
        
        now = time.time()
        frame_count += 1
        
        # Tracking com BoT-SORT
        t_start = time.time()
        results = detector.track(frame)
        tracks = extract_tracks(results)
        t_yolo = time.time() - t_start
        
        # Limpar tracks antigos desaparecidos
        if frame_count % 30 == 0:  # A cada 30 frames
            cleanup_old_tracks()
        
        current_frame_persons = {}
        current_track_ids = [t["id"] for t in tracks]
        
        # ===========================================
        # PROCESSAMENTO DE CADA TRACK
        # ===========================================
        for t in tracks:
            tid = t["id"]
            bbox = t["bbox"]
            x1, y1, x2, y2 = map(int, bbox)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            
            # Remover de disappeared se reapareceu (recuperação de oscilação rápida / blink)
            if tid in disappeared_tracks:
                del disappeared_tracks[tid]
            
            # Verificar bbox válida
            if x1 < 0 or y1 < 0 or x2 > frame.shape[1] or y2 > frame.shape[0]:
                logger.warning(f"Track {tid}: Bbox fora do frame: {bbox}")
                continue  # Pula este track
            
            # Determinar zona atual
            current_zone = zones.get_zone((cx, cy))
            
            # -------------------------------------------------
            # TRACKING DE TEMPO POR ZONA
            # -------------------------------------------------
            if current_zone:
                zone_key = (tid, current_zone)
                
                # Se mudou de zona ou é primeira vez
                if zone_key not in zone_tracking:
                    zone_tracking[zone_key] = now
                    # Limpar tracking de zonas antigas deste track
                    old_keys = [k for k in zone_tracking.keys() if k[0] == tid and k[1] != current_zone]
                    for key in old_keys:
                        del zone_tracking[key]
            
            # -------------------------------------------------
            # 1. SE JÁ TEM MAPEAMENTO DIRETO
            # -------------------------------------------------
            if tid in track_to_person:
                person_uuid = track_to_person[tid]
                is_reid = False
                
                # Remover de pending se estiver lá
                if tid in pending_confirmations:
                    del pending_confirmations[tid]
            
            # -------------------------------------------------
            # 2. SISTEMA DE CONFIRMAÇÃO EM MÚLTIPLOS FRAMES (Extração sob demanda)
            # -------------------------------------------------
            elif tid in pending_confirmations:
                # Extrair características apenas durante o processo de confirmação
                current_features = person_db.extract_features(frame, [x1, y1, x2, y2])
                if current_features is None:
                    logger.debug(f"Track {tid}: Falha na extração de features para bbox {bbox}")
                    continue
                
                # Atualizar contador
                pending_confirmations[tid]['frames'] += 1
                pending_confirmations[tid]['features'].append(current_features)
                
                # Mostrar progresso a cada frame
                progress = pending_confirmations[tid]['frames']
                logger.debug(f"? Confirmando track {tid}: {progress}/{CONFIRMATION_FRAMES}")
                
                # Se atingiu número mínimo de frames, CONFIRMAR
                if pending_confirmations[tid]['frames'] >= CONFIRMATION_FRAMES:
                    # Calcular características médias
                    features_list = pending_confirmations[tid]['features']
                    
                    # Filtra features válidas (não None)
                    valid_features = [f for f in features_list if f is not None]
                    
                    if not valid_features:
                        logger.warning(f"?? Track {tid}: Nenhuma feature válida para confirmação")
                        del pending_confirmations[tid]
                        continue
                    
                    # Calcular média apenas se tiver features suficientes
                    if len(valid_features) >= CONFIRMATION_FRAMES:
                        avg_features = person_db.average_features(valid_features)
                        
                        if avg_features is None:
                            logger.warning(f"?? Track {tid}: Falha ao calcular média de features")
                            # Fallback: usar a última feature válida
                            avg_features = valid_features[-1]
                    else:
                        # Se não tiver frames suficientes, usar o que tem
                        avg_features = valid_features[-1]
                        logger.debug(f"?? Track {tid}: Usando {len(valid_features)} features (menos que {CONFIRMATION_FRAMES})")
                    
                    # Buscar/criar pessoa USANDO AS FEATURES MÉDIAS
                    person_uuid, is_reid = person_db.get_or_create_person_with_features(
                        avg_features, frame, bbox, CAMERA_ID
                    )
                    
                    # Salvar mapeamento definitivo
                    track_to_person[tid] = person_uuid
                    
                    # Log do evento
                    if is_reid:
                        confidence = 0.7  # Placeholder
                        log_person_event("reid", tid, person_uuid, confidence)
                    else:
                        log_person_event("new", tid, person_uuid, zone=current_zone)
                    
                    # Limpar pending
                    del pending_confirmations[tid]
                else:
                    # Ainda confirmando - pular registro no banco
                    continue
            
            # -------------------------------------------------
            # 3. PRIMEIRA VEZ VENDO ESTE TRACK
            # -------------------------------------------------
            else:
                # Extrair características para iniciar confirmação
                current_features = person_db.extract_features(frame, [x1, y1, x2, y2])
                if current_features is None:
                    logger.debug(f"Track {tid}: Não iniciando confirmação - features inválidas")
                    continue
                
                # Iniciar processo de confirmação
                pending_confirmations[tid] = {
                    'frames': 1,
                    'features': [current_features],
                    'possible_uuid': None,
                    'first_seen': now
                }
                logger.debug(f"?? Iniciando confirmação para track {tid}")
                continue  # Pular até ter frames suficientes
            
            # -------------------------------------------------
            # 4. REGISTRAR NO BANCO (com rate-limit de 1s para performance)
            # -------------------------------------------------
            last_log = last_db_log_time.get(tid, 0)
            if now - last_log >= DB_LOG_INTERVAL:
                detection_time = datetime.now()
                confidence = t.get("confidence", 0.8)
                
                person_db.log_detection(
                    person_uuid=person_uuid,
                    camera_id=CAMERA_ID,
                    bbox=[x1, y1, x2, y2],
                    detection_time=detection_time,
                    confidence=confidence
                )
                last_db_log_time[tid] = now
            
            # Registrar para verificação de desaparecimento
            current_frame_persons[tid] = {
                'uuid': person_uuid,
                'bbox': [x1, y1, x2, y2],
                'time': now,
                'zone': current_zone
            }
            
            # -------------------------------------------------
            # 4.1 ANÁLISE VISION API (Opcional/Periódica)
            # -------------------------------------------------
            # Analisar a cada 100 frames para não sobrecarregar a API
            if frame_count % 100 == 0:
                logger.info(f"🔍 Analisando pessoa {person_uuid[:8]} com Google Vision API...")
                vision_results = vision_analyzer.analyze_person(frame, [x1, y1, x2, y2])
                if vision_results:
                    logger.info(f"📊 Resultados Vision para {person_uuid[:8]}: {vision_results['emotions']}")
                    # Aqui poderíamos salvar no banco de dados em uma tabela de atributos
                    # Por agora, vamos apenas logar para demonstrar a integração
            
            # -------------------------------------------------
            # 5. LÓGICA EXISTENTE (heatmap, zones, etc)
            # -------------------------------------------------
            heatmap.update((cx, cy))
            metrics.update(tid, current_zone)
            behavior.update(tid, current_zone)
            
            # Alertas visuais
            color = (0, 255, 0)  # verde padrão
            
            # Obter ou calcular logical_id (reaproveita ID já computado para o track ativo)
            logical_id = track_to_logical_id.get(tid)
            if logical_id is None:
                sig = make_signature(bbox, frame)
                if sig is not None:
                    logical_id = id_manager.get_logical_id(sig)
                    if logical_id:
                        track_to_logical_id[tid] = logical_id
            
            if logical_id:
                label = f"ID {logical_id} | {person_uuid[:6]}"
            else:
                label = f"ID ? | {person_uuid[:6]}"
            
            # Verificar alerta de zona
            if current_zone:
                time_in_zone = now - zone_tracking.get((tid, current_zone), now)
                if time_in_zone >= ZONE_ALERT_THRESHOLD:
                    color = (0, 165, 255)  # laranja para alerta de zona
                    label = f"ZONA: {current_zone} ({int(time_in_zone)}s)"
            
            # Verificar outros alertas
            if current_zone:
                alert_key = f"zone_{tid}_{current_zone}"
                if alert_key in zone_alerts:
                    alert = zone_alerts[alert_key]
                    if now - alert["timestamp"] < ALERT_DISPLAY_TIME:
                        color = (0, 0, 255)  # vermelho para alerta
                        label = f"ALERTA: {alert['zone']}"
            
            # Desenhar bounding box e label
            if SHOW_GUI:
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    frame,
                    label,
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2
                )
                
                # Desenhar ponto central
                cv2.circle(frame, (cx, cy), 3, color, -1)
        
        # ===========================================
        # 6. CAPTURAR SCREENSHOTS DE ALERTAS PENDENTES
        # ===========================================
        if pending_screenshots:
            for screenshot_data in pending_screenshots[:]:  # Usar cópia para remover itens
                tid = screenshot_data['track_id']
                
                # Encontrar o track atual para obter bbox
                current_track = next((t for t in tracks if t["id"] == tid), None)
                
                if current_track and screenshot_data.get('needs_bbox', True):
                    bbox = current_track["bbox"]
                    x1, y1, x2, y2 = map(int, bbox)
                    
                    # Capturar screenshot
                    screenshot_path = person_db.capture_alert_snapshot(
                        frame, 
                        [x1, y1, x2, y2],
                        screenshot_data['person_uuid'],
                        alert_type="zona",
                        camera_id=CAMERA_ID
                    )
                    
                    screenshot_data['screenshot_path'] = screenshot_path
                    screenshot_data['needs_bbox'] = False
                    
                    logger.info(f"?? Screenshot de alerta capturado: {screenshot_data['person_uuid'][:8]}")
                    
                    # Remover da lista pendente
                    pending_screenshots.remove(screenshot_data)
                    
                    # Atualizar alerta com caminho do screenshot
                    alert_key = f"zone_{tid}_{screenshot_data.get('zone', 'unknown')}"
                    if alert_key in zone_alerts:
                        zone_alerts[alert_key]['screenshot_path'] = screenshot_path
        
        # ===========================================
        # 7. VERIFICAR ALERTAS DE ZONA
        # ===========================================
        new_zone_alerts = []  # ? INICIALIZE AQUI (SOLUÇÃO 2)

        if frame_count % 30 == 0:  # Verificar a cada 30 frames
            # Obter novos alertas
            new_zone_alerts = check_zone_alerts(tracks, frame)
            
            # Log dos novos alertas
            if new_zone_alerts:
                logger.warning(f"?? {len(new_zone_alerts)} NOVOS ALERTAS DE ZONA DETECTADOS:")
                
                for alert_data in new_zone_alerts:
                    person_uuid = alert_data.get('person_uuid', 'Desconhecido')
                    zone = alert_data.get('zone', 'Desconhecida')
                    time_in_zone = alert_data.get('time_in_zone', 0)
                    
                    logger.warning(f"   ?? {person_uuid[:8]} há {time_in_zone}s em {zone}")
                    
                    # Verificar se screenshot foi capturado
                    if alert_data.get('screenshot_path'):
                        logger.info(f"   ?? Screenshot: {alert_data['screenshot_path']}")
                    else:
                        logger.warning(f"   ??  Screenshot NÃO capturado")
            
            # Debug periódico (a cada 300 frames)
            if frame_count % 300 == 0:
                debug_zone_alerts()

        # OU se você quiser debug independente da verificação de alertas:
        elif frame_count % 300 == 0:  # else if para debug em frames diferentes
            debug_zone_alerts()

        # ===========================================
        # 8. VERIFICAR TRACKS QUE DESAPARECERAM
        # ===========================================
        current_track_ids_set = set(current_track_ids)
        active_track_ids_set = set(track_to_person.keys())
        
        disappeared_now = active_track_ids_set - current_track_ids_set
        
        for tid in disappeared_now:
            if tid in track_to_person:
                # Apenas marca o timestamp inicial do desaparecimento (sem limpar ID ou disparar evento ainda)
                if tid not in disappeared_tracks:
                    disappeared_tracks[tid] = now
        
        # Remover do pending tracks que desapareceram antes de confirmar
        pending_to_remove = []
        for tid in pending_confirmations.keys():
            if tid not in current_track_ids_set:
                pending_to_remove.append(tid)
        
        for tid in pending_to_remove:
            logger.debug(f"? Track {tid} desapareceu durante confirmação")
            del pending_confirmations[tid]
        
        # ===========================================
        # 9. ALERTAS COMPORTAMENTAIS
        # ===========================================
        try:
            alerts = behavior.get_alerts()
            for alert in alerts:
                alert_time, alert_tid, alert_msg = alert
                logger.warning(f"?? ALERTA: ID {alert_tid} - {alert_msg}")
                
                # Adicionar para overlay visual
                if alert_tid not in active_alerts:
                    active_alerts[alert_tid] = {
                        "zone": alert_msg.split()[-1] if "em" in alert_msg else "comportamento",
                        "timestamp": now
                    }
        except AttributeError:
            pass
        
        # ===========================================
        # 10. OVERLAYS VISUAIS
        # ===========================================
        # Heatmap e Overlays
        # ===========================================
        if SHOW_GUI:
            frame = heatmap.render(frame)
            
            # Zonas
            zones.draw(frame)
            
            # Métricas
            metrics.draw(frame)
            
            # Comportamento
            try:
                behavior.draw(frame)
            except:
                pass
        
        # ===========================================
        # 11. ESTATÍSTICAS NA TELA
        # ===========================================
        # Contagem de pessoas
        active_count = len(current_frame_persons)
        unique_ids = len(set([p['uuid'] for p in current_frame_persons.values()]))
        pending_count = len(pending_confirmations)
        elapsed_time = time.time() - start_time
        fps = frame_count / elapsed_time if elapsed_time > 0 else 0
        zone_alerts_count = len(zone_alerts)
        
        if SHOW_GUI:
            # Linha 1: Pessoas ativas
            cv2.putText(
                frame,
                f"Ativas: {active_count} | Únicos: {unique_ids} | Pendentes: {pending_count}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )
            
            # Linha 2: FPS e tempo
            cv2.putText(
                frame,
                f"FPS: {fps:.1f} | Frame: {frame_count} | Tempo: {elapsed_time:.0f}s",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 0),
                2
            )
            
            # Linha 3: Alertas de zona
            if zone_alerts_count > 0:
                cv2.putText(
                    frame,
                    f"Alertas zona: {zone_alerts_count}",
                    (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 165, 255),
                    2
                )
        
        # Telemetria de desempenho
        t_loop = time.time() - t_start
        if frame_count % 30 == 0:
            logger.info(f"[PERF] Frame {frame_count}: YOLO={t_yolo*1000:.1f}ms, Total Loop={t_loop*1000:.1f}ms")

        # ===========================================
        # 12. LOG DE ESTATÍSTICAS PERIÓDICO
        # ===========================================
        if frame_count % STATS_UPDATE_INTERVAL == 0:
            # Obter estatísticas do banco
            stats = person_db.get_stats()
            
            # Log detalhado
            logger.info(f"?? ESTATÍSTICAS:")
            logger.info(f"   Frame: {frame_count}, FPS: {fps:.1f}")
            logger.info(f"   Pessoas ativas: {active_count}, Únicas: {unique_ids}")
            logger.info(f"   Pendentes confirmação: {pending_count}")
            logger.info(f"   Banco: {stats['total_persons']} pessoas, {stats['total_detections_today']} detecções hoje")
            logger.info(f"   Tracks mapeados: {len(track_to_person)}, Desaparecidos: {len(disappeared_tracks)}")
            logger.info(f"   Alertas zona ativos: {zone_alerts_count}")
            
            # Mostrar no frame (linha 4)
            if SHOW_GUI:
                cv2.putText(
                    frame,
                    f"Banco: {stats['total_persons']} pessoas | Hoje: {stats['total_detections_today']} detecções",
                    (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2
                )
        
        # ===========================================
        # 13. EXIBIÇÃO
        # ===========================================
        if SHOW_GUI:
            cv2.imshow("Seg.Ai - Tracking com ReID Persistente - Luiz Guilherme", frame)
            
            # Tecla ESC para sair
            if cv2.waitKey(1) & 0xFF == 27:
                logger.info("? Tecla ESC pressionada - Encerrando...")
                break
                
            # Tecla 'R' para reset stats (debug)
            if cv2.waitKey(1) & 0xFF == ord('r'):
                logger.info("?? Reset de estatísticas solicitado")
                track_to_person.clear()
                pending_confirmations.clear()
                disappeared_tracks.clear()
                zone_tracking.clear()
                active_alerts.clear()
                
            # Tecla 'S' para mostrar status detalhado
            if cv2.waitKey(1) & 0xFF == ord('s'):
                logger.info("?? STATUS DETALHADO:")
                logger.info(f"   Tracks->Person: {len(track_to_person)} mapeamentos")
                logger.info(f"   Pendentes: {len(pending_confirmations)}")
                for tid, data in pending_confirmations.items():
                    logger.info(f"     Track {tid}: {data['frames']}/{CONFIRMATION_FRAMES} frames")
                logger.info(f"   Desaparecidos: {len(disappeared_tracks)}")
                logger.info(f"   Zone tracking: {len(zone_tracking)} zonas ativas")
                
            # Tecla 'Z' para ver status de zonas
            if cv2.waitKey(1) & 0xFF == ord('z'):
                logger.info("?? STATUS ZONAS:")
                for (tid, zone), start_time in zone_tracking.items():
                    time_in_zone = now - start_time
                    person_uuid = track_to_person.get(tid, "Desconhecido")
                    short_uuid = person_uuid[:8] if person_uuid != "Desconhecido" else "Desconhecido"
                    logger.info(f"   Track {tid} ({short_uuid}): {zone} há {time_in_zone:.0f}s")
        else:
            # Em modo headless, pequena pausa para liberar a CPU
            time.sleep(0.002)

except KeyboardInterrupt:
    logger.info("?? Interrupção pelo usuário (Ctrl+C)")
except Exception as e:
    logger.error(f"?? ERRO CRÍTICO: {str(e)}", exc_info=True)
finally:
    # =============================
    # FINALIZAÇÃO
    # =============================
    logger.info("=" * 50)
    logger.info("FINALIZANDO SISTEMA...")
    logger.info("=" * 50)
    
    # Estatísticas finais
    elapsed_time = time.time() - start_time
    stats = person_db.get_stats()
    
    logger.info("?? ESTATÍSTICAS FINAIS:")
    logger.info(f"   Tempo total: {elapsed_time:.1f} segundos")
    logger.info(f"   Frames processados: {frame_count}")
    logger.info(f"   FPS médio: {frame_count/elapsed_time:.1f}" if elapsed_time > 0 else "   FPS médio: N/A")
    logger.info(f"   Pessoas únicas no banco: {stats['total_persons']}")
    logger.info(f"   Detecções totais: {stats['total_detections']}")
    logger.info(f"   Detecções hoje: {stats['total_detections_today']}")
    
    # Marcar pessoas ativas como inativas
    logger.info("???  Marcando pessoas ativas como inativas...")
    active_person_uuids = set(track_to_person.values())
    for person_uuid in active_person_uuids:
        try:
            person_db.mark_person_inactive(person_uuid)
            logger.debug(f"   Pessoa {person_uuid[:8]} marcada como inativa")
        except Exception as e:
            logger.error(f"   Erro ao marcar pessoa {person_uuid[:8]}: {e}")
    
    # Fechar conexões
    logger.info("?? Fechando conexões...")
    try:
        cam.release()
    except:
        pass
    
    try:
        person_db.close()
    except:
        pass
    
    cv2.destroyAllWindows()
    
    logger.info("=" * 50)
    logger.info("? SISTEMA FINALIZADO COM SUCESSO")
    logger.info(f"?? Log salvo em: {log_file}")
    logger.info("=" * 50)
    
    # Manter console aberto por 5 segundos
    time.sleep(5)