import cv2
import os
import time
from flask import Flask, Response, redirect
from deepface import DeepFace
import numpy as np
import glob
import threading, queue, time

app = Flask(__name__)

ESP32_STREAM_URL = os.getenv("ESP32_STREAM_URL", "http://10.144.208.145:81/stream")

frame_count = 0

# Precompute embeddings for known faces
DB_PATH = os.getenv("KNOWN_FACES_PATH", "known_faces")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "VGG-Face")
EMBEDDING_THRESHOLD = float(os.getenv("EMBEDDING_THRESHOLD", "0.4"))

def load_known_embeddings(db_path=DB_PATH, model_name=EMBEDDING_MODEL):
    entries = []
    embeddings = []
    if not os.path.isdir(db_path):
        print(f"Known faces directory not found: {db_path}")
        return entries, None

    # iterate over person folders
    for person_dir in sorted(os.listdir(db_path)):
        person_path = os.path.join(db_path, person_dir)
        if not os.path.isdir(person_path):
            continue
        # find image files
        pattern = os.path.join(person_path, "*.*")
        for img_path in glob.glob(pattern):
            if not img_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            try:
                vec = DeepFace.represent(img_path=img_path, model_name=model_name, enforce_detection=False, detector_backend='opencv')
                vec = np.array(vec).reshape(-1)
                entries.append({
                    'name': person_dir,
                    'path': img_path,
                })
                embeddings.append(vec)
            except Exception as e:
                print(f"Failed to represent {img_path}: {e}")
    if len(embeddings) == 0:
        return entries, None
    emb_matrix = np.vstack(embeddings)
    # precompute norms for cosine similarity
    emb_norms = np.linalg.norm(emb_matrix, axis=1)
    return entries, (emb_matrix, emb_norms)

# load embeddings at startup
KNOWN_ENTRIES, KNOWN_EMBEDDINGS = load_known_embeddings()

# load Haar cascade for face detection (for drawing bounding boxes)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

proc_q = queue.Queue(maxsize=1)
latest_annots = None  # escribe worker, lee main thread (reemplazo atómico)

def worker():
    # cargar modelo aquí si hace falta
    while True:
        frame_small = proc_q.get()  # bloquea hasta un frame
        # detectar caras, representar, comparar embeddings...
        annots = [ {'rect':(x,y,w,h),'name':name}, ... ]
        # actualizar última anotación (asignación atómica)
        global latest_annots
        latest_annots = {'t': time.time(), 'annots': annots}
        proc_q.task_done()

# arrancar worker
threading.Thread(target=worker, daemon=True).start()

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
                # detect faces in the small frame to draw rectangles
                gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray_small, scaleFactor=1.1, minNeighbors=5)

                # scale factors to map small->original frame
                sx = frame.shape[1] / small.shape[1]
                sy = frame.shape[0] / small.shape[0]

                if len(faces) > 0:
                    # for each detected face, compute embedding and try to ID
                    for (x, y, w, h) in faces:
                        # crop face region on small image
                        face_crop = small[y:y+h, x:x+w]

                        name = None

                        # If we have precomputed embeddings, use fast compare
                        if KNOWN_EMBEDDINGS is not None and len(KNOWN_ENTRIES) > 0:
                            qvec = DeepFace.represent(img=face_crop, model_name=EMBEDDING_MODEL, enforce_detection=False, detector_backend='opencv')
                            qvec = np.array(qvec).reshape(-1)
                            emb_matrix, emb_norms = KNOWN_EMBEDDINGS
                            qnorm = np.linalg.norm(qvec)
                            if qnorm != 0 and not np.any(emb_norms == 0):
                                sims = (emb_matrix @ qvec) / (emb_norms * qnorm)
                                best_idx = int(np.argmax(sims))
                                best_sim = float(sims[best_idx])
                                if best_sim >= EMBEDDING_THRESHOLD:
                                    name = KNOWN_ENTRIES[best_idx]['name']
                        else:
                            result = DeepFace.find(
                                img=face_crop,
                                db_path="known_faces",
                                enforce_detection=False,
                                detector_backend="opencv"
                            )
                            if len(result) > 0 and len(result[0]) > 0:
                                identity = result[0].iloc[0]["identity"]
                                name = identity.split("/")[-2]
                        # draw rectangle on original-size frame with color based on recognition
                        rx = int(x * sx)
                        ry = int(y * sy)
                        rw = int(w * sx)
                        rh = int(h * sy)
                        if name:
                            box_color = (0, 255, 0)  # green for recognized
                            label = name
                        else:
                            box_color = (0, 0, 255)  # red for unknown
                            label = "Unknown"

                        cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), box_color, 2)
                        # draw label background
                        label_y = ry + rh + 20
                        # ensure label is within frame
                        if label_y + 20 > frame.shape[0]:
                            label_y = ry - 10
                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                        lx = rx
                        ly = label_y
                        cv2.rectangle(frame, (lx - 2, ly - th - 4), (lx + tw + 2, ly + 4), box_color, -1)
                        cv2.putText(frame, label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

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


@app.route('/view')
def view():
    # simple page that shows the processed stream with detection boxes
    html = (
        '<!doctype html>'
        '<html><head><meta charset="utf-8"><title>Camera - Detections</title></head>'
        '<body style="margin:0; background:#000;">'
        '<img src="/video" style="width:100%;height:auto;display:block;"/>'
        '</body></html>'
    )
    return html


@app.route('/esp_redirect')
def esp_redirect():
    # redirects to the configured ESP32 stream URL (set ESP32_STREAM_URL to include path/port)
    return redirect(ESP32_STREAM_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)