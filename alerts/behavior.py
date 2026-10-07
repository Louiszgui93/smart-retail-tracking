import time
import os
from collections import defaultdict
from datetime import datetime
import logging
import pymysql

logger = logging.getLogger("alerts")


def get_db_connection():
    """Obtém conexão com o banco usando o pool global"""
    try:
        from config.db_config import DB_POOL
        return DB_POOL.get_connection()
    except Exception as e:
        logger.error(f"[ERROR] Erro ao obter conexão do pool: {e}")
        return None

def release_db_connection(conn):
    """Libera a conexão de volta ao pool global"""
    try:
        from config.db_config import DB_POOL
        DB_POOL.release_connection(conn)
    except Exception as e:
        logger.error(f"[ERROR] Erro ao liberar conexão: {e}")

def register_alert_to_dashboard(
    person_uuid,
    alert_type,
    zone=None,
    time_in_zone=0,
    screenshot_path=""
):
    """Registra alerta no banco para o dashboard acessar"""
    conn = get_db_connection()
    if conn is None:
        logger.error("[ERROR] Não foi possível conectar ao banco para registrar alerta")
        return
        
    try:
        with conn.cursor() as cursor:
            # Verificar se a tabela tem coluna zone
            cursor.execute("SHOW COLUMNS FROM alert_snapshots LIKE 'zone'")
            has_zone_column = cursor.fetchone() is not None
            
            if has_zone_column:
                query = """
                INSERT INTO alert_snapshots 
                (person_uuid, alert_type, zone, time_in_zone, file_path, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(query, (
                    person_uuid,
                    alert_type,
                    zone or "",
                    int(time_in_zone),
                    screenshot_path
                ))
            else:
                # Fallback para tabela antiga
                query = """
                INSERT INTO alert_snapshots 
                (person_uuid, alert_type, file_path, created_at)
                VALUES (%s, %s, %s, NOW())
                """
                cursor.execute(query, (
                    person_uuid,
                    alert_type,
                    screenshot_path
                ))
            
            conn.commit()
        logger.info(f"[ALERT] Alerta registrado no dashboard: {person_uuid[:8]} - {alert_type}")
        
    except Exception as e:
        logger.error(f"[ERROR] Erro ao registrar alerta no dashboard: {e}")
    finally:
        release_db_connection(conn)



class BehaviorAnalyzer:
    def __init__(self):
        # tempo de entrada por zona
        self.zone_entry_time = defaultdict(dict)

        # última zona conhecida por track
        self.last_zone = {}

        # alertas pendentes (para overlay)
        self.alerts = []

        # controle de cooldown de alertas
        self.last_alert_time = {}  # (track_id, alert_type, zone) -> timestamp

        # parâmetros (ajustáveis via variáveis de ambiente)
        self.MAX_TIME_IN_ZONE = int(os.getenv('MAX_TIME_IN_ZONE', 25))  # segundos
        self.EXIT_AFTER_ISLAND = int(os.getenv('EXIT_AFTER_ISLAND', 5))  # segundos
        self.ALERT_COOLDOWN = int(os.getenv('ALERT_COOLDOWN', 10))       # segundos (anti-spam)

    def _can_alert(self, track_id, alert_type, zone):
        """Evita spam de alertas"""
        key = (track_id, alert_type, zone)
        now = time.time()

        last = self.last_alert_time.get(key, 0)
        if now - last >= self.ALERT_COOLDOWN:
            self.last_alert_time[key] = now
            return True
        return False

    def update(self, track_id, zone):
        now = time.time()

        # primeira vez vendo o track
        if track_id not in self.last_zone:
            self.last_zone[track_id] = zone
            if zone:
                self.zone_entry_time[zone][track_id] = now
            return

        last_zone = self.last_zone[track_id]

        # ===============================
        # TROCA DE ZONA
        # ===============================
        if zone != last_zone:
            # saiu da ilha direto para saída
            if (
                last_zone == "ilhas_promocionais"
                and zone == "entrada_saida"
            ):
                if self._can_alert(track_id, "saida_pos_ilha", last_zone):
                    self.alerts.append(
                        (now, track_id, "Ilha → Saída")
                    )

            # registrar nova zona
            self.last_zone[track_id] = zone
            if zone:
                self.zone_entry_time[zone][track_id] = now

        # ===============================
        # TEMPO EXCESSIVO EM ZONA
        # ===============================
        if zone and track_id in self.zone_entry_time[zone]:
            duration = now - self.zone_entry_time[zone][track_id]

            if duration >= self.MAX_TIME_IN_ZONE:
                if self._can_alert(track_id, "tempo_excessivo", zone):
                    self.alerts.append(
                        (now, track_id, f"Tempo excessivo em {zone}")
                    )

                # reset parcial para evitar spam contínuo
                self.zone_entry_time[zone][track_id] = now

    def draw(self, frame):
        import cv2

        if not self.alerts:
            return

        y = frame.shape[0] - 60
        for alert in self.alerts[-3:]:
            text = f"ALERTA ID {alert[1]}: {alert[2]}"
            cv2.putText(
                frame,
                text,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2
            )
            y += 20

    def get_alerts(self):
        """
        Retorna e limpa a lista de alertas pendentes.
        Formato:
        (timestamp, track_id, mensagem)
        """
        alerts = self.alerts.copy()
        self.alerts.clear()
        return alerts