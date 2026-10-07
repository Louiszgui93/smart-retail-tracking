import cv2
import numpy as np


def make_signature(bbox, frame):
    """
    Cria assinatura visual baseada em aparência
    """
    x1, y1, x2, y2 = map(int, bbox)

    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    # Normalizar tamanho
    roi = cv2.resize(roi, (64, 128))

    # Histograma HSV (bem mais robusto)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv],
        [0, 1],
        None,
        [16, 16],
        [0, 180, 0, 256]
    )

    hist = cv2.normalize(hist, hist).flatten()

    return hist


class IdManager:
    def __init__(self):
        self.people = {}      # pid -> hist médio
        self.next_id = 1

        # parâmetros
        self.SIM_THRESHOLD = 0.75
        self.UPDATE_ALPHA = 0.2   # atualização suave

    def get_logical_id(self, signature):
        if signature is None:
            return None

        best_id = None
        best_score = 0

        for pid, stored_hist in self.people.items():
            score = cv2.compareHist(
                stored_hist, signature, cv2.HISTCMP_CORREL
            )

            if score > best_score:
                best_score = score
                best_id = pid

        # encontrou alguém parecido
        if best_id is not None and best_score >= self.SIM_THRESHOLD:
            # atualização suave (EMA)
            self.people[best_id] = (
                self.UPDATE_ALPHA * signature +
                (1 - self.UPDATE_ALPHA) * self.people[best_id]
            )
            return best_id

        # nova pessoa
        pid = self.next_id
        self.people[pid] = signature
        self.next_id += 1
        return pid

    def remove(self, pid):
        """Remove pessoa lógica (opcional, quando some por muito tempo)"""
        if pid in self.people:
            del self.people[pid]
