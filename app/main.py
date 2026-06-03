import cv2
import os
import time
from flask import Flask, Response, redirect
from deepface import DeepFace
import numpy as np
import glob

app = Flask(__name__)

ESP32_STREAM_URL = os.getenv("ESP32_STREAM_URL", "http://10.144.208.145/stream")

frame_count = 0

# Precompute embeddings for known faces
DB_PATH = os.getenv("KNOWN_FACES_PATH", "known_faces")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "VGG-Face")
EMBEDDING_THRESHOLD = float(os.getenv("EMBEDDING_THRESHOLD", "0.4"))


def extract_embedding(result):
    if isinstance(result, list):
        if len(result) == 0:
            raise ValueError("Empty embedding result")
        result = result[0]
    if isinstance(result, dict):
        if "embedding" in result:
            return np.array(result["embedding"], dtype=np.float32).reshape(-1)
        if "face_embedding" in result:
            return np.array(result["face_embedding"], dtype=np.float32).reshape(-1)
        raise ValueError(f"Unsupported embedding dict keys: {list(result.keys())}")
    return np.array(result, dtype=np.float32).reshape(-1)


def load_known_embeddings(db_path=DB_PATH, model_name=EMBEDDING_MODEL):
    metadata = []
    embedding_vectors = []
    if not os.path.isdir(db_path):
        print(f"Known faces directory not found: {db_path}")
        return metadata, None

    # Iterate over person folders and keep metadata separate from vectors.
    for person_dir in sorted(os.listdir(db_path)):
        person_path = os.path.join(db_path, person_dir)
        if not os.path.isdir(person_path):
            continue
        pattern = os.path.join(person_path, "*.*")
        for img_path in glob.glob(pattern):
            if not img_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            try:
                vec = DeepFace.represent(img_path=img_path, model_name=model_name, enforce_detection=False, detector_backend='opencv')
                vec = extract_embedding(vec)
                metadata.append({
                    'name': person_dir,
                    'path': img_path,
                })
                embedding_vectors.append(vec)
            except Exception as e:
                print(f"Failed to represent {img_path}: {e}")
    if len(embedding_vectors) == 0:
        return metadata, None
    emb_matrix = np.vstack(embedding_vectors) ## shape (N, D) where N=number of known faces, D=embedding dimension
    emb_norms = np.linalg.norm(emb_matrix, axis=1) ## precompute norms for cosine similarity
    print(f"Loaded {len(metadata)} known face embeddings from {db_path}", flush=True)
    return metadata, (emb_matrix, emb_norms)

# load embeddings at startup
KNOWN_METADATA, KNOWN_EMBEDDINGS = load_known_embeddings()

# load Haar cascade for face detection (for drawing bounding boxes)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

def generate_frames():

    global frame_count

    cap = None

    while True:

        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(ESP32_STREAM_URL)
            if not cap.isOpened():
                print(f"No se pudo abrir el stream: {ESP32_STREAM_URL}", flush=True)
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
                # detect faces using DeepFace so we get the facial area directly
                faces = []
                try:
                    faces = DeepFace.extract_faces(
                        img_path=small,
                        detector_backend="opencv",
                        enforce_detection=False,
                        align=False
                    )
                    print(f"[FACE_DETECT] frame={frame_count} deepface_faces={len(faces)}", flush=True)
                except Exception as detect_error:
                    print(f"[FACE_DETECT] frame={frame_count} deepface_error={detect_error}", flush=True)

                if len(faces) == 0:
                    gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    haar_faces = face_cascade.detectMultiScale(gray_small, scaleFactor=1.1, minNeighbors=5)
                    print(f"[FACE_DETECT] frame={frame_count} haar_faces={len(haar_faces)}", flush=True)
                    for (x, y, w, h) in haar_faces:
                        faces.append({
                            "face": small[y:y + h, x:x + w],
                            "facial_area": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
                        })

                # scale factors to map small->original frame
                sx = frame.shape[1] / small.shape[1]
                sy = frame.shape[0] / small.shape[0]

                if len(faces) > 0:
                    # for each detected face, compute embedding and try to ID
                    for face_item in faces:
                        facial_area = face_item.get("facial_area", {})
                        x = int(facial_area.get("x", 0))
                        y = int(facial_area.get("y", 0))
                        w = int(facial_area.get("w", 0))
                        h = int(facial_area.get("h", 0))
                        face_crop = face_item.get("face")
                        if face_crop is None or w <= 0 or h <= 0:
                            print(f"[FACE_SKIP] frame={frame_count} invalid_face_area={facial_area}", flush=True)
                            continue

                        name = None

                        # If we have precomputed embeddings, use fast compare
                        if KNOWN_EMBEDDINGS is not None and len(KNOWN_METADATA) > 0:
                            print(f"[FACE_RECOGNIZE] frame={frame_count} faces={len(faces)}", flush=True)
                            qvec = DeepFace.represent(img_path=face_crop, model_name=EMBEDDING_MODEL, enforce_detection=False, detector_backend='opencv')
                            qvec = extract_embedding(qvec)
                            emb_matrix, emb_norms = KNOWN_EMBEDDINGS
                            qnorm = np.linalg.norm(qvec)
                            if qnorm != 0 and not np.any(emb_norms == 0):
                                sims = (emb_matrix @ qvec) / (emb_norms * qnorm)
                                best_idx = int(np.argmax(sims))
                                best_sim = float(sims[best_idx])
                                if best_sim >= EMBEDDING_THRESHOLD:
                                    name = KNOWN_METADATA[best_idx]['name']
                                    print(f"[FACE_MATCH] frame={frame_count} detected=1 status=registered name={name} sim={best_sim:.4f}", flush=True)
                                else:
                                    print(f"[FACE_MATCH] frame={frame_count} detected=1 status=unknown sim={best_sim:.4f}", flush=True)
                            else:
                                print(f"[FACE_MATCH] frame={frame_count} detected=1 status=unknown reason=zero_norm", flush=True)
                        else:
                            result = DeepFace.find(
                                img_path=face_crop,
                                db_path="known_faces",
                                enforce_detection=False,
                                detector_backend="opencv"
                            )
                            if len(result) > 0 and len(result[0]) > 0:
                                identity = result[0].iloc[0]["identity"]
                                name = identity.split("/")[-2]
                                print(f"[FACE_MATCH] frame={frame_count} detected=1 status=registered name={name}", flush=True)
                            else:
                                print(f"[FACE_MATCH] frame={frame_count} detected=1 status=unknown", flush=True)
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

                        # Drawing overlays disabled: keep recognition logic and console output only
                        print(f"[FACE_RECOG] frame={frame_count} rect=({rx},{ry},{rw},{rh}) label={label}", flush=True)

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