import os
import io
import logging
from google.cloud import vision

logger = logging.getLogger(__name__)

class VisionAnalyzer:
    def __init__(self):
        """
        Inicializa o cliente da Google Cloud Vision API.
        Certifique-se de que a variável de ambiente GOOGLE_APPLICATION_CREDENTIALS está configurada.
        """
        try:
            self.client = vision.ImageAnnotatorClient()
            logger.info("✅ Google Cloud Vision API Client inicializado.")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Google Cloud Vision Client: {e}")
            self.client = None

    def analyze_person(self, frame, bbox):
        """
        Analisa uma pessoa específica no frame usando a Vision API.
        
        Args:
            frame: O frame completo da imagem (numpy array).
            bbox: A bounding box da pessoa [x1, y1, x2, y2].
            
        Returns:
            dict: Resultados da análise (emoções, atributos, etc.)
        """
        if self.client is None:
            return None

        try:
            x1, y1, x2, y2 = map(int, bbox)
            # Garantir que a bbox está dentro dos limites do frame
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                return None

            # Converter ROI para bytes
            import cv2
            _, buffer = cv2.imencode('.jpg', roi)
            content = buffer.tobytes()
            image = vision.Image(content=content)

            # Realizar detecção facial e de objetos
            # Nota: FACE_DETECTION fornece emoções e atributos
            response = self.client.face_detection(image=image)
            faces = response.face_annotations

            results = {
                'emotions': [],
                'attributes': [],
                'raw_response': response
            }

            if faces:
                face = faces[0]  # Pegamos a face principal detectada no recorte
                
                # Mapeamento de probabilidades
                likelihood_name = ('UNKNOWN', 'VERY_UNLIKELY', 'UNLIKELY', 'POSSIBLE', 'LIKELY', 'VERY_LIKELY')
                
                results['emotions'] = {
                    'joy': likelihood_name[face.joy_likelihood],
                    'sorrow': likelihood_name[face.sorrow_likelihood],
                    'anger': likelihood_name[face.anger_likelihood],
                    'surprise': likelihood_name[face.surprise_likelihood]
                }
                
                results['attributes'] = {
                    'headwear': likelihood_name[face.headwear_likelihood],
                    'blurred': likelihood_name[face.blurred_likelihood],
                    'under_exposed': likelihood_name[face.under_exposed_likelihood]
                }

            return results

        except Exception as e:
            logger.error(f"❌ Erro na análise da Vision API: {e}")
            return None

    def detect_objects(self, frame):
        """
        Detecta múltiplos objetos no frame para enriquecer o contexto do varejo.
        """
        if self.client is None:
            return None

        try:
            import cv2
            _, buffer = cv2.imencode('.jpg', frame)
            content = buffer.tobytes()
            image = vision.Image(content=content)

            objects = self.client.object_localization(image=image).localized_object_annotations
            
            detected_objects = []
            for obj in objects:
                detected_objects.append({
                    'name': obj.name,
                    'score': obj.score,
                    'bounds': [(v.x, v.y) for v in obj.bounding_poly.normalized_vertices]
                })
            
            return detected_objects
        except Exception as e:
            logger.error(f"❌ Erro na detecção de objetos da Vision API: {e}")
            return None
