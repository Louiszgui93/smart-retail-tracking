import time

class AlertEngine:
    def __init__(self):
        self.triggered = set()

        # Limites de tempo por zona (segundos)
        self.max_time_zone = {
            "corredor": 120,
            "caixa": 180
        }

    def evaluate(self, metrics):
        alerts = []

        for tid, zones in metrics.zone_time.items():
            for zone, seconds in zones.items():
                key = (tid, zone)

                if zone in self.max_time_zone:
                    if seconds > self.max_time_zone[zone] and key not in self.triggered:
                        alert = {
                            "type": "tempo_excessivo",
                            "id": tid,
                            "zone": zone,
                            "seconds": int(seconds)
                        }
                        alerts.append(alert)
                        self.triggered.add(key)

        return alerts
