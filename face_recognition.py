"""Local face enrollment and recognition using OpenCV's LBPH recognizer.

This is a practical classroom/demo baseline, not a liveness detector or a
security-grade identity verification system. Enrollment images stay on-device.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

import cv2
import numpy as np

import config
from database import transaction

FACE_SIZE = (200, 200)
_FACE_CASCADE = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))


class FaceError(ValueError):
    pass


def _recognizer():
    if not hasattr(cv2, "face") or not hasattr(cv2.face, "LBPHFaceRecognizer_create"):
        raise RuntimeError("OpenCV face module is missing. Install opencv-contrib-python-headless (not opencv-python).")
    return cv2.face.LBPHFaceRecognizer_create()


def decode_image(data_url_or_b64: str) -> np.ndarray:
    import base64
    import binascii

    if not isinstance(data_url_or_b64, str):
        raise FaceError("Image must be base64 text.")
    encoded = data_url_or_b64.split(",", 1)[-1]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FaceError("Invalid image encoding.") from exc
    if not raw or len(raw) > config.CAMERA_FRAME_MAX_BYTES:
        raise FaceError("Image is empty or too large (maximum 2 MB).")
    try:
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise FaceError("Could not decode image.") from exc
    if image is None:
        raise FaceError("Could not decode image.")
    height, width = image.shape[:2]
    if width > 4000 or height > 4000 or width * height > 12_000_000:
        raise FaceError("Image dimensions are too large (maximum 12 megapixels).")
    return image


def _face_regions(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    if _FACE_CASCADE.empty():
        raise RuntimeError("OpenCV's frontal-face detector is unavailable.")
    faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(70, 70))
    return [tuple(map(int, item)) for item in faces]


def detect_single_face(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = _face_regions(image)
    if len(faces) != 1:
        raise FaceError("Show exactly one face in the camera frame.")
    x, y, w, h = faces[0]
    crop = gray[y:y + h, x:x + w]
    return cv2.resize(crop, FACE_SIZE, interpolation=cv2.INTER_AREA)


def save_sample(student_id: int, data: str) -> int:
    image = decode_image(data)
    face = detect_single_face(image)
    # Do not use a raw student-supplied identifier in a path.
    filename = f"student_{int(student_id)}_{os.urandom(8).hex()}.png"
    destination = config.FACES_DIR / filename
    if not cv2.imwrite(str(destination), face):
        raise OSError("Could not save face sample.")
    try:
        with transaction() as conn:
            cur = conn.execute("INSERT INTO face_samples(student_id, image_path) VALUES (?, ?)", (student_id, str(destination)))
            sample_id = int(cur.lastrowid)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return sample_id


def sample_count(student_id: int) -> int:
    with transaction() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM face_samples WHERE student_id=?", (student_id,)).fetchone()[0])


def train_model() -> dict[str, int]:
    """Train on active enrolled students, atomically replacing the model files."""
    with transaction() as conn:
        rows = conn.execute(
            "SELECT s.id, f.image_path FROM students s JOIN face_samples f ON f.student_id=s.id WHERE s.active=1 ORDER BY s.id"
        ).fetchall()
    faces: list[np.ndarray] = []
    labels: list[int] = []
    label_map: dict[str, int] = {}
    by_student: dict[int, list[np.ndarray]] = {}
    for row in rows:
        label = int(row["id"])
        image = cv2.imread(row["image_path"], cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        by_student.setdefault(label, []).append(cv2.resize(image, FACE_SIZE))
    for label, student_faces in by_student.items():
        if len(student_faces) < config.MIN_FACE_SAMPLES:
            continue
        faces.extend(student_faces)
        labels.extend([label] * len(student_faces))
        label_map[str(label)] = label
    if not faces:
        config.MODEL_PATH.unlink(missing_ok=True)
        config.MODEL_LABELS_PATH.unlink(missing_ok=True)
        return {"students": 0, "samples": 0}
    model = _recognizer()
    model.train(faces, np.asarray(labels, dtype=np.int32))
    config.FACES_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(suffix=".yml", dir=config.FACES_DIR)
    os.close(fd)
    try:
        model.write(temp_name)
        os.replace(temp_name, config.MODEL_PATH)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    tmp_labels = config.MODEL_LABELS_PATH.with_suffix(".json.tmp")
    tmp_labels.write_text(json.dumps(label_map), encoding="utf-8")
    os.replace(tmp_labels, config.MODEL_LABELS_PATH)
    return {"students": len(label_map), "samples": len(faces)}


def recognize(image: np.ndarray) -> list[dict[str, Any]]:
    """Return one prediction per detected face; unknown faces have student_id None."""
    regions = _face_regions(image)
    if not regions:
        return []
    if not config.MODEL_PATH.exists():
        return [{"box": [x, y, w, h], "student_id": None, "confidence": None} for x, y, w, h in regions]
    model = _recognizer()
    model.read(str(config.MODEL_PATH))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    predictions = []
    for x, y, w, h in regions:
        face = cv2.resize(gray[y:y + h, x:x + w], FACE_SIZE, interpolation=cv2.INTER_AREA)
        label, confidence = model.predict(face)
        matched = int(label) if float(confidence) <= config.FACE_MATCH_THRESHOLD else None
        predictions.append({"box": [x, y, w, h], "student_id": matched, "confidence": round(float(confidence), 2)})
    return predictions
