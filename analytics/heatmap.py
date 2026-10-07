import cv2
import numpy as np


class Heatmap:
    def __init__(self, shape): # shape é (height, width)
        self.map = np.zeros(shape, dtype=np.float32)

    def update(self, point):
        x, y = point
        if 0 <= y < self.map.shape[0] and 0 <= x < self.map.shape[1]:
            self.map[y, x] += 1

    def render(self, frame):
        normalized = cv2.normalize(self.map, None, 0, 255, cv2.NORM_MINMAX)
        heat = cv2.applyColorMap(normalized.astype(np.uint8), cv2.COLORMAP_JET)
        return cv2.addWeighted(frame, 0.6, heat, 0.4, 0)
