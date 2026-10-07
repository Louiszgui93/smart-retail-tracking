# detection/tracker.py
# detection/tracker.py
def extract_tracks(results):
    """Extrai tracks do formato do YOLO/BoT-SORT"""
    tracks = []
    
    for r in results:
        if r.boxes.id is None:
            continue
        
        for box, tid, conf in zip(r.boxes.xyxy, r.boxes.id, r.boxes.conf):
            x1, y1, x2, y2 = map(int, box.cpu().numpy())
            tracks.append({
                "id": int(tid),
                "bbox": [x1, y1, x2, y2],
                "conf": float(conf)
            })
    
    return tracks