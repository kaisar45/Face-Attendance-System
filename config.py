"""Configuration for the local face-attendance application."""
from __future__ import annotations

import os
from pathlib import Path
import secrets

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE_DIR = BASE_DIR / "database"
FACES_DIR = BASE_DIR / "faces"
REPORTS_DIR = BASE_DIR / "reports"
ASSETS_DIR = BASE_DIR / "assets"
DATABASE_PATH = Path(os.getenv("ATTENDANCE_DATABASE", DATABASE_DIR / "attendance.sqlite3"))
MODEL_PATH = FACES_DIR / "lbph_model.yml"
MODEL_LABELS_PATH = FACES_DIR / "model_labels.json"

SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeThis-123!")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}

# OpenCV LBPH distance is lower for closer matches; 
# tune using real enrollment data.
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "65"))
MIN_FACE_SAMPLES = int(os.getenv("MIN_FACE_SAMPLES", "20"))
CAMERA_FRAME_MAX_BYTES = 2_000_000
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "local")

for directory in (DATABASE_DIR, FACES_DIR, REPORTS_DIR, ASSETS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
