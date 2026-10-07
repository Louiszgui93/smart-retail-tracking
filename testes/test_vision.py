import cv2
import numpy as np
import sys
import os
import logging

# Adicionar caminho para imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.vision_integration import VisionAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_vision_integration():
    # 1. Inicializar Analyzer
    analyzer = VisionAnalyzer()
    
    if analyzer.client is None:
        logger.error("❌ Falha ao inicializar o cliente da Vision API. Verifique as credenciais.")
        return

    # 2. Criar uma imagem de teste (ou carregar uma)
    # Vamos criar uma imagem preta com um retângulo simulando uma pessoa
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(frame, (200, 100), (400, 400), (255, 255, 255), -1)
    
    bbox = [200, 100, 400, 400]
    
    logger.info("Testing analyze_person...")
    # Nota: Isso vai falhar se não houver uma face real na imagem, 
    # mas valida se a chamada à API está funcionando.
    results = analyzer.analyze_person(frame, bbox)
    
    if results:
        logger.info(f"✅ Resultados da análise: {results}")
    else:
        logger.info("ℹ️ Nenhum resultado (provavelmente nenhuma face detectada na imagem de teste).")

    logger.info("Testing detect_objects...")
    objects = analyzer.detect_objects(frame)
    if objects is not None:
        logger.info(f"✅ Objetos detectados: {len(objects)}")
    else:
        logger.info("❌ Falha na detecção de objetos.")

if __name__ == "__main__":
    test_vision_integration()
