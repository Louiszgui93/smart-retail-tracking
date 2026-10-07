import time
from collections import defaultdict


class Metrics:
    def __init__(self):
        self.zone_time = defaultdict(dict)
        self.zone_counts = defaultdict(int)

    def update(self, track_id, zone):
        now = time.time()

        if zone is None:
            return

        if track_id not in self.zone_time[zone]:
            self.zone_time[zone][track_id] = now
            self.zone_counts[zone] += 1

    def draw(self, frame):
        y = 30
        for zone, count in self.zone_counts.items():
            text = f"{zone}: {count} pessoas"
            frame = self._put(frame, text, y)
            y += 25
        return frame

    def _put(self, frame, text, y):
        import cv2
        cv2.putText(frame, text, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        return frame
