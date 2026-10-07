import cv2, os
from ultralytics import YOLO

model = YOLO("yolov8n.pt")

cap = cv2.VideoCapture(os.getenv("RTSP_URL", 0))

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    results = model.track(
        frame,
        persist=True,
        tracker="bytetrack.yaml",
        conf=0.4,
        verbose=False
    )

    for r in results:
        if r.boxes.id is None:
            continue

        for box, tid in zip(r.boxes.xyxy, r.boxes.id):
            x1,y1,x2,y2 = map(int, box)
            cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
            cv2.putText(
                frame,
                f"ID {int(tid)}",
                (x1,y1-10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,(0,0,255),2
            )

    cv2.imshow("Tracking", frame)
    if cv2.waitKey(1) == 27:
        break
