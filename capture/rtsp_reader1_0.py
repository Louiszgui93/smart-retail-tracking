import cv2


class RTSPReader:
    def __init__(self, rtsp_url):
        self.cap = cv2.VideoCapture(rtsp_url)

    def read(self):
        ret, frame = self.cap.read()
        if not ret:
            return None
        return frame

    def release(self):
        self.cap.release()
