# detection/detector.py
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ultralytics import YOLO

logger = logging.getLogger(__name__)


class Detector:
    """
    Detector YOLO com tracking (BoT-SORT) e configuração por env/parametros.
    """

    def __init__(self, model_path: Optional[str] = None, conf_threshold: Optional[float] = None, iou_threshold: Optional[float] = None) -> None:
        # Determinar modelo a usar
        if model_path is None:
            model_path = os.getenv("YOLO_MODEL", "yolov8m.pt")

        # Thresholds (validação/clamp)
        if conf_threshold is None:
            conf_threshold = float(os.getenv("YOLO_CONF", 0.5))
        if iou_threshold is None:
            iou_threshold = float(os.getenv("YOLO_IOU", 0.5))

        self.conf_threshold = self._clamp(float(conf_threshold))
        self.iou_threshold = self._clamp(float(iou_threshold))
        self.model_path = str(model_path)

        model_names = {
            "yolov8n.pt": "YOLOv8n (Nano)",
            "yolov8s.pt": "YOLOv8s (Small)",
            "yolov8m.pt": "YOLOv8m (Medium)",
            "yolov8l.pt": "YOLOv8l (Large)",
            "yolov8x.pt": "YOLOv8x (Extra Large)",
        }
        model_desc = model_names.get(self.model_path, self.model_path)

        logger.info("Carregando modelo: %s", model_desc)
        logger.info("  Confidence threshold: %s", self.conf_threshold)
        logger.info("  IoU threshold: %s", self.iou_threshold)

        # Tentar carregar modelo; se falhar, tentar fallback uma vez; se falhar de novo -> raise
        try:
            self.model = YOLO(self.model_path, task="detect")
            logger.info("Detector %s inicializado", model_desc)
        except Exception as e:
            logger.warning("Erro ao carregar modelo %s: %s", self.model_path, e)
            fallback = "yolov8n.pt"
            logger.info("Tentando modelo fallback: %s", fallback)
            try:
                self.model = YOLO(fallback, task="detect")
                self.model_path = fallback
                logger.info("Detector %s inicializado (fallback)", fallback)
            except Exception as e2:
                logger.error("Falha ao carregar modelo fallback: %s", e2)
                raise RuntimeError(f"Não foi possível carregar nenhum modelo YOLO: {e2}") from e2

        # Resolver caminho do tracker relativo ao projeto
        tracker_name = os.getenv("TRACKER_CONFIG", "config/bytetrack.yaml")
        possible_tracker = Path(tracker_name)
        if possible_tracker.exists():
            self.tracker_path = str(possible_tracker)
        else:
            logger.warning("Arquivo tracker %s não encontrado; usando padrão 'bytetrack.yaml'", tracker_name)
            self.tracker_path = "bytetrack.yaml"

    @staticmethod
    def _clamp(value: float) -> float:
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    def track(self, frame: Any, persist: bool = True, classes: Optional[list] = None):
        """
        Executa detecção + tracking.
        """
        if classes is None:
            classes = [0]  # pessoas por padrão
        return self.model.track(
            frame,
            persist=persist,
            tracker=self.tracker_path,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            classes=classes,
            verbose=False,
        )

    def detect(self, frame: Any, classes: Optional[list] = None):
        """
        Executa apenas detecção.
        """
        if classes is None:
            classes = [0]
        return self.model.predict(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            classes=classes,
            verbose=False,
        )

    def get_model_info(self) -> Dict[str, Any]:
        device = getattr(self.model, "device", None)
        return {
            "model_path": self.model_path,
            "confidence_threshold": self.conf_threshold,
            "iou_threshold": self.iou_threshold,
            "device": str(device),
        }

    def set_confidence(self, conf: float) -> None:
        self.conf_threshold = self._clamp(float(conf))
        logger.info("Confidence threshold atualizado para: %s", self.conf_threshold)

    def set_iou(self, iou: float) -> None:
        self.iou_threshold = self._clamp(float(iou))
        logger.info("IoU threshold atualizado para: %s", self.iou_threshold)

    def close(self) -> None:
        """
        Liberar recursos do modelo quando aplicável.
        """
        try:
            close_fn = getattr(self.model, "close", None)
            if callable(close_fn):
                close_fn()
        finally:
            try:
                del self.model
            except Exception:
                pass