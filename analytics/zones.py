import cv2
import json
import numpy as np


class ZoneManager:
    def __init__(self, zones_path):
        with open(zones_path, "r") as f:
            raw = json.load(f)

        self.polygons = {}

        for name, zone in raw.items():

            # Caso 1: formato simples
            if isinstance(zone, list):
                points = zone

            # Caso 2: formato estruturado { type, points }
            elif isinstance(zone, dict) and "points" in zone:
                points = zone["points"]

            else:
                raise ValueError(f"Zona inválida: {name}")

            parsed = []
            for p in points:
                if isinstance(p, (list, tuple)):
                    parsed.append([int(p[0]), int(p[1])])
                elif isinstance(p, dict):
                    parsed.append([int(p["x"]), int(p["y"])])
                else:
                    raise ValueError(f"Ponto inválido na zona {name}: {p}")

            self.polygons[name] = np.array(parsed, dtype=np.int32)

    def scale_zones(self, scale_factor: float):
        """Redimensiona os polígonos das zonas pela escala"""
        for name in self.polygons:
            self.polygons[name] = (self.polygons[name] * scale_factor).astype(np.int32)

    def get_zone(self, point):
        for name, poly in self.polygons.items():
            if cv2.pointPolygonTest(poly, point, False) >= 0:
                return name
        return None

    def draw(self, frame):
        for name, poly in self.polygons.items():
            cv2.polylines(frame, [poly], True, (255, 0, 0), 2)
            x, y = poly[0]
            cv2.putText(
                frame,
                name,
                (x, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 0),
                2
            )
