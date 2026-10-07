"""
Database Manager para Sistema de Reidentificação - VERSÃO COMPLETA CORRIGIDA
Inclui TODAS as funções necessárias
"""

import pymysql
import json
import cv2
import numpy as np
from datetime import datetime, timedelta
import uuid
import os
import logging
from typing import Dict, List, Optional, Tuple
import hashlib

# Configurar logger
logger = logging.getLogger(__name__)


class PersonDB:
    def __init__(self, db_config: Dict):
        """
        Inicializa o PersonDB usando pool de conexões
        """
        self.db_config = db_config
        
        # Configurações de reidentificação - AJUSTADAS
        self.similarity_threshold = 0.70  # AUMENTADO para evitar falsos positivos
        self.cache_ttl_minutes = 30
        
        # Cache local para evitar consultas desnecessárias
        self.feature_cache = {}
        self.uuid_cache = {}
        self.cache_max_size = 100
        
        logger.info(f"PersonDB inicializado com Pool de Conexões: threshold={self.similarity_threshold}")
    
    def get_connection(self):
        """Obtém uma conexão do pool global"""
        from config.db_config import DB_POOL
        return DB_POOL.get_connection()
        
    def release_connection(self, conn):
        """Libera a conexão de volta ao pool global"""
        from config.db_config import DB_POOL
        DB_POOL.release_connection(conn)
    
    def connect(self):
        """Mantido para compatibilidade"""
        pass
    
    def reconnect(self):
        """Mantido para compatibilidade"""
        pass

    
    def extract_features(self, frame: np.ndarray, bbox: List[int]) -> Optional[Dict]:
        """
        Extrai features robustas para reidentificação
        """
        try:
            x1, y1, x2, y2 = map(int, bbox)
            
            # Validar bbox
            if x1 >= x2 or y1 >= y2:
                logger.debug(f"Bbox inválida: {bbox}")
                return None
            
            bbox_width = x2 - x1
            bbox_height = y2 - y1
            
            if bbox_width < 20 or bbox_height < 40:
                logger.debug(f"Bbox muito pequena: {bbox_width}x{bbox_height}")
                return None
            
            # Garantir dentro dos limites
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(frame.shape[1] - 1, x2)
            y2 = min(frame.shape[0] - 1, y2)
            
            # Extrair ROI
            roi = frame[y1:y2, x1:x2]
            
            if roi.size == 0:
                return None
            
            # ==============================================
            # EXTRAÇÃO DE FEATURES
            # ==============================================
            
            # 1. Histograma de cores HSV
            if len(roi.shape) == 3:
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                hist_h = cv2.calcHist([hsv], [0], None, [18], [0, 180])
                hist_s = cv2.calcHist([hsv], [1], None, [12], [0, 256])
                hist_v = cv2.calcHist([hsv], [2], None, [8], [0, 256])
                
                cv2.normalize(hist_h, hist_h, 0, 1, cv2.NORM_MINMAX)
                cv2.normalize(hist_s, hist_s, 0, 1, cv2.NORM_MINMAX)
                cv2.normalize(hist_v, hist_v, 0, 1, cv2.NORM_MINMAX)
                
                histogram = np.concatenate([hist_h.flatten(), hist_s.flatten(), hist_v.flatten()]).tolist()
            else:
                histogram = cv2.calcHist([roi], [0], None, [32], [0, 256])
                cv2.normalize(histogram, histogram, 0, 1, cv2.NORM_MINMAX)
                histogram = histogram.flatten().tolist()
            
            # 2. Cor média
            if len(roi.shape) == 3:
                lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
                avg_color_lab = np.mean(lab, axis=(0, 1)).tolist()
                avg_color_bgr = np.mean(roi, axis=(0, 1)).tolist()
            else:
                avg_color_lab = [np.mean(roi), 128, 128]
                avg_color_bgr = [np.mean(roi), np.mean(roi), np.mean(roi)]
            
            # 3. Proporções e posição
            frame_height, frame_width = frame.shape[:2]
            height_ratio = bbox_height / frame_height
            width_ratio = bbox_width / frame_width
            aspect_ratio = bbox_width / max(1, bbox_height)
            
            center_x = (x1 + x2) / (2 * frame_width)
            center_y = (y1 + y2) / (2 * frame_height)
            
            # 4. Hash para debug
            roi_bytes = cv2.imencode('.jpg', roi)[1].tobytes()
            roi_hash = hashlib.md5(roi_bytes).hexdigest()[:8]
            
            features = {
                'histogram_hsv': histogram,
                'avg_color_lab': avg_color_lab,
                'avg_color_bgr': avg_color_bgr,
                'height_ratio': float(height_ratio),
                'width_ratio': float(width_ratio),
                'aspect_ratio': float(aspect_ratio),
                'center_x': float(center_x),
                'center_y': float(center_y),
                'roi_size': [bbox_height, bbox_width],
                'roi_hash': roi_hash,
                'timestamp': datetime.now().isoformat()
            }
            
            return features
            
        except Exception as e:
            logger.error(f"Erro em extract_features: {e}")
            return None
    
    def calculate_similarity(self, feat1: Dict, feat2: Dict) -> float:
        """
        Calcula similaridade entre duas pessoas
        """
        if feat1 is None or feat2 is None:
            return 0.0
        
        try:
            total_similarity = 0
            total_weight = 0
            
            # 1. Similaridade de histograma (40%)
            if 'histogram_hsv' in feat1 and 'histogram_hsv' in feat2:
                hist1 = np.array(feat1['histogram_hsv'], dtype=np.float32)
                hist2 = np.array(feat2['histogram_hsv'], dtype=np.float32)
                
                if len(hist1) == len(hist2) > 0:
                    hist_sim = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
                    hist_sim = max(0, (hist_sim + 1) / 2)
                    total_similarity += hist_sim * 0.4
                    total_weight += 0.4
            
            # 2. Similaridade de cor (30%)
            if 'avg_color_bgr' in feat1 and 'avg_color_bgr' in feat2:
                color1 = np.array(feat1['avg_color_bgr'])
                color2 = np.array(feat2['avg_color_bgr'])
                
                if len(color1) == len(color2) >= 3:
                    color_diff = np.linalg.norm(color1 - color2)
                    max_color_diff = np.sqrt(3 * 255**2)
                    color_sim = 1.0 - min(1.0, color_diff / max_color_diff)
                    total_similarity += color_sim * 0.3
                    total_weight += 0.3
            
            # 3. Similaridade de proporções (20%)
            ratio_keys = ['aspect_ratio', 'height_ratio', 'width_ratio']
            for key in ratio_keys:
                if key in feat1 and key in feat2:
                    val1 = float(feat1[key])
                    val2 = float(feat2[key])
                    
                    if val1 > 0 and val2 > 0:
                        ratio = min(val1, val2) / max(val1, val2)
                        total_similarity += ratio * (0.2 / len(ratio_keys))
                        total_weight += (0.2 / len(ratio_keys))
            
            # 4. Similaridade de posição (10%)
            if 'center_x' in feat1 and 'center_x' in feat2:
                pos_diff = abs(feat1['center_x'] - feat2['center_x']) + abs(feat1['center_y'] - feat2['center_y'])
                pos_sim = 1.0 - min(1.0, pos_diff * 2)
                total_similarity += pos_sim * 0.1
                total_weight += 0.1
            
            if total_weight > 0:
                return total_similarity / total_weight
            return 0.0
            
        except Exception as e:
            logger.error(f"Erro em calculate_similarity: {e}")
            return 0.0
    
    def find_similar_person(self, current_features: Dict, camera_id: str = None, 
                          min_confidence: float = 0.5) -> Optional[str]:
        """
        Busca pessoa similar no banco
        """
        if current_features is None:
            return None
        
        conn = self.get_connection()
        try:
            cutoff_time = datetime.now() - timedelta(minutes=self.cache_ttl_minutes)
            
            query = """
            SELECT 
                person_uuid, 
                embedding, 
                confidence_score,
                last_seen,
                total_appearances
            FROM person_cache 
            WHERE is_active = 1 
            AND last_seen > %s
            ORDER BY confidence_score DESC, last_seen DESC
            LIMIT 20
            """
            
            with conn.cursor() as cursor:
                cursor.execute(query, (cutoff_time,))
                candidates = cursor.fetchall()
            
            if not candidates:
                return None
            
            best_match = None
            best_score = 0.0
            
            for person in candidates:
                try:
                    # Desserializar embedding
                    db_features = {}
                    if person['embedding']:
                        db_features = json.loads(person['embedding'])
                    
                    # Calcular similaridade
                    similarity = self.calculate_similarity(current_features, db_features)
                    
                    # Usar similaridade visual diretamente (sem penalizar pela confiança de detecção do YOLO)
                    final_score = similarity
                    
                    if final_score > best_score and final_score >= self.similarity_threshold:
                        best_score = final_score
                        best_match = person['person_uuid']
                        
                except Exception as e:
                    logger.error(f"Erro ao processar candidato: {e}")
                    continue
            
            if best_match:
                logger.info(f"?? ReID encontrado: {best_match[:8]} (score={best_score:.3f})")
                return best_match
            
            return None
                
        except Exception as e:
            logger.error(f"Erro find_similar_person: {e}")
            return None
        finally:
            self.release_connection(conn)
    
    def get_or_create_person(self, frame: np.ndarray, bbox: List[int], camera_id: str = "default"):
        """Método original para compatibilidade"""
        return self.get_or_create_person_with_features(
            self.extract_features(frame, bbox), 
            frame, 
            bbox, 
            camera_id
        )
    
    def get_or_create_person_with_features(self, features: Dict, frame: np.ndarray, 
                                         bbox: List[int], camera_id: str = "default") -> Tuple[str, bool]:
        """
        Versão CORRIGIDA - Evita criar o mesmo UUID sempre
        """
        try:
            if features is None:
                logger.warning("Features inválidas - criando UUID temporário")
                return f"temp_{uuid.uuid4()}", False
            
            x1, y1, x2, y2 = map(int, bbox)
            if (x2 - x1) < 10 or (y2 - y1) < 20:
                logger.warning(f"Bbox muito pequena {bbox} - UUID temporário")
                return f"temp_{uuid.uuid4()}", False
            
            # ============================================
            # 1. TENTAR REIDENTIFICAÇÃO
            # ============================================
            person_uuid = self.find_similar_person(features, camera_id)
            
            if person_uuid and not person_uuid.startswith("temp_"):
                logger.info(f"? Reidentificado: {person_uuid[:8]}")
                return person_uuid, True
            
            # ============================================
            # 2. CRIAR NOVA PESSOA COM UUID ÚNICO
            # ============================================
            
            # GERAR UUID BASEADO EM FEATURES + TIMESTAMP (único para cada pessoa)
            feature_string = f"{features.get('roi_hash', '')}_{features.get('avg_color_bgr', [])}_{datetime.now().timestamp()}"
            feature_hash = hashlib.md5(feature_string.encode()).hexdigest()
            
            # UUID determinístico
            namespace_uuid = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
            new_uuid = str(uuid.uuid5(namespace_uuid, feature_hash))
            
            # Salvar snapshot
            snapshot_path = self.save_snapshot(frame, bbox, new_uuid, camera_id)
            
            # Preparar dados
            embedding_data = {
                'histogram_hsv': features.get('histogram_hsv', []),
                'avg_color_lab': features.get('avg_color_lab', [50, 128, 128]),
                'avg_color_bgr': features.get('avg_color_bgr', [128, 128, 128]),
                'height_ratio': features.get('height_ratio', 0.3),
                'width_ratio': features.get('width_ratio', 0.2),
                'aspect_ratio': features.get('aspect_ratio', 0.5)
            }
            
            color_profile = {
                'histogram': features.get('histogram_hsv', []),
                'avg_color': features.get('avg_color_bgr', [128, 128, 128]),
                'roi_size': features.get('roi_size', [0, 0])
            }
            
            conn = self.get_connection()
            try:
                # Inserir no banco
                query = """
                INSERT INTO person_cache 
                (person_uuid, embedding, color_profile, height_ratio, 
                 width_ratio, aspect_ratio, snapshot_path, confidence_score,
                 total_appearances, is_active, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    last_seen = VALUES(last_seen),
                    total_appearances = total_appearances + 1
                """
                
                with conn.cursor() as cursor:
                    cursor.execute(query, (
                        new_uuid,
                        json.dumps(embedding_data),
                        json.dumps(color_profile),
                        features.get('height_ratio', 0.3),
                        features.get('width_ratio', 0.2),
                        features.get('aspect_ratio', 0.5),
                        snapshot_path,
                        0.8,  # Confiança inicial
                        1,    # Primeira aparição
                        1,    # Ativa
                        datetime.now()
                    ))
                    conn.commit()
            finally:
                self.release_connection(conn)
            
            logger.info(f"?? NOVA PESSOA: {new_uuid[:8]}")
            return new_uuid, False
            
        except Exception as e:
            logger.error(f"? Erro em get_or_create_person: {e}")
            fallback_uuid = f"error_{uuid.uuid4()}"
            return fallback_uuid, False
    
    def save_snapshot(self, frame: np.ndarray, bbox: List[int], 
                     person_uuid: str, camera_id: str = None) -> str:
        """Salva snapshot da pessoa"""
        try:
            x1, y1, x2, y2 = map(int, bbox)
            
            if x1 >= x2 or y1 >= y2:
                return ""
            
            roi = frame[y1:y2, x1:x2]
            
            if roi.size == 0:
                return ""
            
            # Criar diretório
            snapshots_dir = "./snapshots"
            os.makedirs(snapshots_dir, exist_ok=True)
            
            # Nome do arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{person_uuid[:8]}_{timestamp}.jpg"
            filepath = os.path.join(snapshots_dir, filename)
            
            # Salvar
            cv2.imwrite(filepath, roi)
            
            # Registrar no banco
            self._register_snapshot(person_uuid, filepath, camera_id, (roi.shape[1], roi.shape[0]))
            
            return filepath
            
        except Exception as e:
            logger.error(f"Erro ao salvar snapshot: {e}")
            return ""
    
    def _register_snapshot(self, person_uuid: str, file_path: str, 
                          camera_id: str, resolution: Tuple[int, int]):
        """Registra snapshot no banco"""
        conn = self.get_connection()
        try:
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            resolution_str = f"{resolution[0]}x{resolution[1]}"
            
            query = """
            INSERT INTO person_snapshots 
            (person_uuid, file_path, camera_id, resolution, file_size)
            VALUES (%s, %s, %s, %s, %s)
            """
            
            with conn.cursor() as cursor:
                cursor.execute(query, (
                    person_uuid,
                    file_path,
                    camera_id,
                    resolution_str,
                    file_size
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Erro ao registrar snapshot: {e}")
        finally:
            self.release_connection(conn)
    
    def log_detection(self, person_uuid: str, camera_id: str, bbox: List[int], 
                     detection_time: datetime = None, confidence: float = 1.0):
        """Registra detecção de forma sequencial para evitar conflito com triggers"""
        conn = self.get_connection()
        try:
            if detection_time is None:
                detection_time = datetime.now()
            
            bbox_json = json.dumps(bbox)
            
            with conn.cursor() as cursor:
                # 1. Atualizar o cache de pessoas primeiro (evita Erro 1020 gerado pelo trigger do INSERT)
                try:
                    update_query = """
                    UPDATE person_cache 
                    SET last_seen = %s,
                        confidence_score = 
                            CASE 
                                WHEN total_appearances < 3 THEN %s
                                ELSE confidence_score * 0.9 + %s * 0.1
                            END
                    WHERE person_uuid = %s
                    """
                    cursor.execute(update_query, (
                        detection_time,
                        confidence,
                        confidence,
                        person_uuid
                    ))
                    conn.commit()
                except Exception as db_err:
                    # Se as colunas confidence_score/total_appearances não existirem no schema simplificado
                    logger.debug(f"Aviso ao atualizar person_cache: {db_err}. Tentando atualização simplificada...")
                    try:
                        cursor.execute(
                            "UPDATE person_cache SET last_seen = %s WHERE person_uuid = %s",
                            (detection_time, person_uuid)
                        )
                        conn.commit()
                    except Exception as fallback_err:
                        logger.warning(f"Falha na atualização simplificada do cache: {fallback_err}")
                
                # 2. Inserir ocorrência (isso dispara o trigger trg_after_occurrence_insert)
                query = """
                INSERT INTO person_occurrences 
                (person_uuid, camera_id, bbox, detection_time, detection_date)
                VALUES (%s, %s, %s, %s, DATE(%s))
                """
                cursor.execute(query, (
                    person_uuid, 
                    camera_id, 
                    bbox_json, 
                    detection_time,
                    detection_time
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Erro ao registrar detecção: {e}")
        finally:
            self.release_connection(conn)
    
    def get_stats(self) -> Dict:
        """Estatísticas do banco"""
        conn = self.get_connection()
        try:
            stats = {}
            
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as total FROM person_cache WHERE is_active = 1")
                stats['total_persons'] = cursor.fetchone()['total']
                
                today = datetime.now().date()
                cursor.execute("""
                    SELECT COUNT(*) as total 
                    FROM person_occurrences 
                    WHERE detection_date = %s
                """, (today,))
                stats['total_detections_today'] = cursor.fetchone()['total']
                
                cursor.execute("SELECT COUNT(*) as total FROM person_occurrences")
                stats['total_detections'] = cursor.fetchone()['total']
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT person_uuid) as total 
                    FROM person_occurrences 
                    WHERE detection_date = %s
                """, (today,))
                stats['persons_today'] = cursor.fetchone()['total']
                
                cursor.execute("""
                    SELECT person_uuid, last_seen, confidence_score, total_appearances
                    FROM person_cache 
                    WHERE is_active = 1 
                    ORDER BY last_seen DESC 
                    LIMIT 5
                """)
                stats['recent_persons'] = cursor.fetchall()
            
            return stats
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {
                'total_persons': 0,
                'total_detections': 0,
                'total_detections_today': 0,
                'persons_today': 0,
                'recent_persons': []
            }
        finally:
            self.release_connection(conn)
    
    def average_features(self, features_list: List[Dict]) -> Optional[Dict]:
        """
        Calcula média de features
        """
        if not features_list:
            return None
        
        valid_features = [f for f in features_list if f is not None]
        if not valid_features:
            return None
        
        if len(valid_features) == 1:
            return valid_features[0].copy()
        
        avg_features = valid_features[0].copy()
        count = len(valid_features)
        
        # Histograma
        if 'histogram_hsv' in avg_features:
            hist_sum = np.array(avg_features['histogram_hsv'])
            for f in valid_features[1:]:
                if 'histogram_hsv' in f:
                    hist_sum += np.array(f['histogram_hsv'])
            avg_features['histogram_hsv'] = (hist_sum / count).tolist()
        
        # Cor
        if 'avg_color_bgr' in avg_features:
            color_sum = np.array(avg_features['avg_color_bgr'])
            for f in valid_features[1:]:
                if 'avg_color_bgr' in f:
                    color_sum += np.array(f['avg_color_bgr'])
            avg_features['avg_color_bgr'] = (color_sum / count).tolist()
        
        # Valores numéricos
        numeric_keys = ['height_ratio', 'width_ratio', 'aspect_ratio', 'center_x', 'center_y']
        for key in numeric_keys:
            if key in avg_features:
                values = [f.get(key, avg_features[key]) for f in valid_features]
                avg_features[key] = sum(values) / count
        
        logger.debug(f"Média calculada de {count} frames")
        return avg_features
    
    def capture_alert_snapshot(self, frame: np.ndarray, bbox: List[int], 
                              person_uuid: str, alert_type: str = "zona", 
                              camera_id: str = None, zone: Optional[str] = None, 
                              time_in_zone: int = 0) -> str:
        """Captura screenshot para alertas e registra no banco com informações completas"""
        try:
            x1, y1, x2, y2 = map(int, bbox)
            
            # Expandir
            padding = 20
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(frame.shape[1], x2 + padding)
            y2 = min(frame.shape[0], y2 + padding)
            
            roi = frame[y1:y2, x1:x2]
            
            if roi.size == 0:
                return ""
            
            # Criar diretório
            alerts_dir = "./alerts"
            os.makedirs(alerts_dir, exist_ok=True)
            
            # Nome do arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{alert_type}_{person_uuid[:8]}_{timestamp}.jpg"
            filepath = os.path.join(alerts_dir, filename)
            
            # Salvar
            cv2.imwrite(filepath, roi)
            
            # REGISTRAR NO BANCO (CRÍTICO PARA DASHBOARD)
            self._register_alert_in_db(person_uuid, filepath, alert_type, camera_id, zone, time_in_zone)
            
            logger.info(f"?? Alerta salvo: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Erro ao capturar screenshot de alerta: {e}")
            return ""
    
    def _register_alert_in_db(self, person_uuid: str, file_path: str, alert_type: str, camera_id: str, 
                             zone: Optional[str] = None, time_in_zone: int = 0):
        """Registra alerta no banco para o dashboard"""
        conn = self.get_connection()
        try:
            query = """
            INSERT INTO alert_snapshots 
            (person_uuid, alert_type, zone, time_in_zone, file_path, camera_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """
            
            with conn.cursor() as cursor:
                cursor.execute(query, (person_uuid, alert_type, zone, time_in_zone, file_path, camera_id))
                conn.commit()
                
            logger.debug(f"Alerta registrado no banco: {person_uuid[:8]}")
            
        except Exception as e:
            logger.error(f"Erro ao registrar alerta no banco: {e}")
        finally:
            self.release_connection(conn)
    
    def _register_alert_snapshot(self, person_uuid: str, file_path: str, alert_type: str, 
                               camera_id: str = None, resolution: Tuple[int, int] = None):
        """Mantido para compatibilidade"""
        return self._register_alert_in_db(person_uuid, file_path, alert_type, camera_id)
    
    def mark_person_inactive(self, person_uuid: str):
        """Marca pessoa como inativa"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                query = "UPDATE person_cache SET is_active = 0 WHERE person_uuid = %s"
                cursor.execute(query, (person_uuid,))
                conn.commit()
        except Exception as e:
            logger.error(f"Erro ao marcar pessoa como inativa: {e}")
        finally:
            self.release_connection(conn)
    
    def close(self):
        """Mantido para compatibilidade, pool gerencia conexões"""
        pass
    
    def cleanup_old_data(self, days_to_keep: int = 90):
        """Limpa dados antigos"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cutoff = datetime.now() - timedelta(days=7)
                query = """
                UPDATE person_cache 
                SET is_active = 0 
                WHERE is_active = 1 
                AND last_seen < %s
                """
                cursor.execute(query, (cutoff,))
                
                date_cutoff = datetime.now() - timedelta(days=days_to_keep)
                query = "DELETE FROM person_occurrences WHERE detection_date < %s"
                cursor.execute(query, (date_cutoff.date(),))
                
                conn.commit()
            
        except Exception as e:
            logger.error(f"Erro no cleanup: {e}")
        finally:
            self.release_connection(conn)

    def test_alert_insertion(self) -> bool:
        """Testa se a inserção de alertas está funcionando (insere e remove um alerta de teste)"""
        test_uuid = "00000000-0000-0000-0000-000000000000"
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # Primeiro, garantir que a pessoa de teste existe no cache
                cursor.execute("""
                    INSERT INTO person_cache (person_uuid, is_active)
                    VALUES (%s, 1)
                    ON DUPLICATE KEY UPDATE is_active = 1
                """, (test_uuid,))
                
                # Inserir alerta de teste
                cursor.execute("""
                    INSERT INTO alert_snapshots (person_uuid, alert_type, zone, time_in_zone, file_path, camera_id)
                    VALUES (%s, 'teste', 'zona_teste', 0, 'caminho_teste', 'cam_teste')
                """, (test_uuid, ))
                alert_id = cursor.lastrowid
                
                # Limpar teste
                cursor.execute("DELETE FROM alert_snapshots WHERE id = %s", (alert_id,))
                cursor.execute("DELETE FROM person_cache WHERE person_uuid = %s", (test_uuid,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erro ao testar inserção de alerta: {e}")
            return False
        finally:
            self.release_connection(conn)


# Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    TEST_CONFIG = {
        'host': 'localhost',
        'user': 'root',
        'password': '800ppc',
        'database': 'person_tracking_db',
        'port': 3306
    }
    
    print("?? Testando Database Manager...")
    
    try:
        db = PersonDB(TEST_CONFIG)
        
        # Testar extração de features
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        test_bbox = [100, 100, 200, 300]
        
        features = db.extract_features(test_frame, test_bbox)
        print(f"? Features extraídas: {features is not None}")
        
        if features:
            print(f"   ROI hash: {features.get('roi_hash', 'N/A')}")
        
        stats = db.get_stats()
        print(f"?? Estatísticas: {stats}")
        
        db.close()
        print("? Teste concluído!")
        
    except Exception as e:
        print(f"? Falha no teste: {e}")
        import traceback
        traceback.print_exc()