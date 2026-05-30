import cv2
import sys
from threading import Thread, Event, Lock
import time
import logging


class CameraManager:
    def __init__(self, device=0):
        self.device = device
        self.cap = None
        self.thread = None
        self.running = Event()
        self.frame_lock = Lock()
        self.latest_frame = None
        self.stop_recog = Event()
        self.recog_thread = None
        self.recog_result = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        # attempt to open capture; may fail if device busy
        try:
            # On Windows prefer DirectShow backend which is often more reliable than MSMF
            if sys.platform.startswith('win'):
                try:
                    self.cap = cv2.VideoCapture(self.device, cv2.CAP_DSHOW)
                    logging.getLogger('face_recog').debug('Opened camera with CAP_DSHOW')
                except Exception:
                    self.cap = cv2.VideoCapture(self.device)
                    logging.getLogger('face_recog').debug('Opened camera with default backend after CAP_DSHOW failed')
            else:
                self.cap = cv2.VideoCapture(self.device)
        except Exception as e:
            logging.getLogger('face_recog').exception('Failed to open VideoCapture: %s', e)
            self.cap = None
        self.running.set()
        self.thread = Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        while self.running.is_set():
            try:
                if self.cap is None:
                    # try to reopen (prefer DirectShow on Windows)
                    try:
                        if sys.platform.startswith('win'):
                            try:
                                self.cap = cv2.VideoCapture(self.device, cv2.CAP_DSHOW)
                            except Exception:
                                self.cap = cv2.VideoCapture(self.device)
                        else:
                            self.cap = cv2.VideoCapture(self.device)
                    except Exception as e:
                        logging.getLogger('face_recog').exception('Reopen VideoCapture failed: %s', e)
                        time.sleep(0.5)
                        continue

                ret, frame = self.cap.read()
                if not ret:
                    # frame read failed; release and try reopen later
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self.cap = None
                    time.sleep(0.05)
                    continue

                with self.frame_lock:
                    self.latest_frame = frame
                time.sleep(0.01)
            except cv2.error as e:
                logging.getLogger('face_recog').exception('OpenCV error in capture loop: %s', e)
                try:
                    if self.cap:
                        self.cap.release()
                except Exception:
                    pass
                self.cap = None
                time.sleep(0.5)
            except Exception as e:
                logging.getLogger('face_recog').exception('Unexpected error in capture loop: %s', e)
                time.sleep(0.5)

    def stop(self):
        self.running.clear()
        if self.thread:
            self.thread.join(timeout=1)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        self.thread = None
        self.cap = None

    def get_frame(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return None
            # return a copy to avoid races
            return self.latest_frame.copy()

    def stream_generator(self):
        # Ensure capture loop is running
        self.start()
        while True:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            chunk = jpeg.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + chunk + b'\r\n')


camera_manager = CameraManager()
