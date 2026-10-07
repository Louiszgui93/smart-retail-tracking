import cv2, math, os
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(os.getenv("RTSP_URL", 0))

objects = {}
next_id = 1

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    results = model(frame, conf=0.4, verbose=False)
    centers = []

    for r in results:
        for box in r.boxes:
            if int(box.cls[0]) == 0:
                x1,y1,x2,y2 = map(int, box.xyxy[0])
                cx,cy = (x1+x2)//2, (y1+y2)//2
                centers.append((cx,cy))
                cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)

    updated = {}
    for c in centers:
        assigned = False
        for oid,(ox,oy) in objects.items():
            if math.hypot(c[0]-ox,c[1]-oy) < 50:
                updated[oid] = c
                assigned = True
                break
        if not assigned:
            updated[next_id] = c
            next_id += 1

    objects = updated

    for oid,(x,y) in objects.items():
        cv2.putText(frame,f"ID {oid}",(x,y),
            cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,0,255),2)

    cv2.imshow("Tracking Simples", frame)
    if cv2.waitKey(1)==27:
        break
