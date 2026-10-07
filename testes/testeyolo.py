import cv2, os
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(os.getenv("RTSP_URL", 0))

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    results = model(frame, conf=0.4, verbose=False)

    for r in results:
        for box in r.boxes:
            if int(box.cls[0]) == 0:
                x1,y1,x2,y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)

    cv2.imshow("YOLO Pessoas", frame)
    if cv2.waitKey(1)==27:
        break