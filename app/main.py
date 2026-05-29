import cv2
import os
import time
from flask import Flask, Response
from deepface import DeepFace

app = Flask(__name__)

ESP32_STREAM_URL = os.getenv("ESP32_STREAM_URL", "http://10.144.208.145")

frame_count = 0

def generate_frames():

    global frame_count

    cap = None

    while True:

        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(ESP32_STREAM_URL)
            if not cap.isOpened():
                print(f"No se pudo abrir el stream: {ESP32_STREAM_URL}")
                time.sleep(2)
                continue

        success, frame = cap.read()

        if not success:
            cap.release()
            cap = None
            time.sleep(1)
            continue

        frame_count += 1

        if frame_count % 15 == 0:

            small = cv2.resize(frame, (320,240))

            try:

                result = DeepFace.find(
                    img_path=small,
                    db_path="known_faces",
                    enforce_detection=False,
                    detector_backend="opencv",
                    silent=True
                )

                if len(result) > 0 and len(result[0]) > 0:

                    identity = result[0].iloc[0]["identity"]

                    name = identity.split("/")[-2]

                    cv2.putText(
                        frame,
                        f"{name}",
                        (20,40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0,255,0),
                        2
                    )

            except Exception as e:
                print(e)

        ret, buffer = cv2.imencode('.jpg', frame)

        frame_bytes = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame_bytes +
            b'\r\n'
        )

    if cap is not None:
        cap.release()

@app.route('/video')

def video():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)