# Face Recognition Attendance System

A local-first attendance web application using **Flask**, **SQLite**, and OpenCV's **LBPH face recognizer**. Administrators manage a student roster, enroll face samples from a webcam, mark attendance during a live session, and export filtered CSV reports.

> Face matching is probabilistic and this demo has **no liveness detection**. Do not use recognition alone to make consequential decisions. Tell participants what is collected, obtain appropriate permission, limit access and retention, and provide a practical non-biometric way to record attendance.

## Features

- Administrator sign-in with hashed password storage and CSRF protection.
- Student registration and activation/deactivation (historical records remain intact).
- Webcam enrollment with one-face validation and multiple cropped grayscale samples per student.
- OpenCV LBPH training and threshold-based matching; recognition occurs on the same machine as the Flask server.
- At most one attendance record per active student per local calendar day.
- Manual roll call when a student opts out or face recognition is unavailable; reports distinguish manual records from camera matches.
- Overview dashboard, searchable roster, date/student report filters, and CSV export.
- SQLite database with foreign keys and WAL; sample images and generated model stay in `faces/`.

## Requirements

- Python 3.10+ (tested with Python 3.12).
- A webcam connected to the computer running the app.
- Modern browser with camera permission. Browser camera APIs require `localhost` or HTTPS; open the app on the same machine at `http://127.0.0.1:5000`.
- `opencv-contrib-python-headless` is required because LBPH is part of OpenCV's contrib modules. Do **not** install `opencv-python` alongside it.

## Install and run

```bash
cd Face-Recognition-Attendance-System
python3 -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set a unique strong `ADMIN_PASSWORD` and a private, stable `SECRET_KEY` before using real data. Then start:

```bash
python main.py
```

Open `http://127.0.0.1:5000` and sign in using the values in `.env` (`admin` / `ChangeThis-123!` only if unchanged). The SQLite database and first admin account are initialized on first startup. Existing account passwords are not reset when environment values change; changing credentials for a pre-existing database requires an admin-password reset (see below).

Camera selection and access are controlled by the browser. Allow the browser camera prompt and close other applications using the webcam.

## First use

1. Sign in as administrator.
2. Open **Students → Add student** and create the roster entry.
3. Choose **Enroll face**. Allow camera access, capture several varied samples (frontal and slight left/right views, neutral expressions, consistent lighting), then save. The default minimum is 8 usable samples. Enrollment only stores cropped grayscale faces, not full camera frames.
4. Open **Live attendance → Start camera**. A recognized active student is recorded on the first successful match for that local date. Later matches show as already marked.
5. Students who opt out or cannot be recognized can be marked from **Manual roll call** on the same page. Manual and camera records share the once-per-day rule.
6. Use **Reports** to filter by date/student and download a CSV.

If some captures fail validation, the interface reports which images did not contain exactly one detectable face. Capture replacements with the face well-lit, centered, and large enough in the preview.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ADMIN_USERNAME` | `admin` | Initial administrator name |
| `ADMIN_PASSWORD` | `ChangeThis-123!` | Initial password only; stored as a hash when the account is created |
| `SECRET_KEY` | Random on each start | Flask session signing key; set a stable random value in `.env` |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Local server address |
| `APP_TIMEZONE` | `local` | Local system time or an IANA timezone such as `Asia/Kolkata` |
| `FACE_MATCH_THRESHOLD` | `65` | Maximum LBPH distance to accept as a match (lower is stricter) |
| `MIN_FACE_SAMPLES` | `8` | Suggested sample minimum before training |
| `ATTENDANCE_DATABASE` | `database/attendance.sqlite3` | Optional custom DB path |

Run the regression tests with `.venv/bin/python -m unittest discover -s tests -v`.

LBPH distance depends on the camera, lighting, and enrollment images. The default is only a starting point: test with consented data, inspect false matches and missed matches, and tune conservatively. A threshold cannot make this system resistant to spoofing or demographic performance differences. Re-enroll in representative lighting if matching is unreliable.

## Data and maintenance

- SQLite file: `database/attendance.sqlite3`.
- Cropped face samples, trained model and labels: `faces/`.
- CSV files are downloaded by the browser; `reports/` is reserved for optional exports/backups.
- `.gitignore` excludes databases, models, sample images, and `.env`. Keep it that way when using version control.
- Back up the database and face/model data together only to an access-controlled, encrypted location. Set an explicit retention policy. Deactivating a student preserves historical attendance and face samples; it removes them from recognition after model retraining.
- To reset local data, stop the server, make a backup if needed, and remove `database/attendance.sqlite3*`, the contents of `faces/`, and any downloaded CSV reports. This permanently removes records and should be done only when intended.

### Reset an administrator password

A small Python command can update the existing admin password hash; substitute a new password locally and do not share it:

```bash
python - <<'PY'
from werkzeug.security import generate_password_hash
from database import transaction
with transaction() as conn:
    conn.execute("UPDATE admins SET password_hash=? WHERE username=?",
                 (generate_password_hash("YOUR-NEW-STRONG-PASSWORD"), "admin"))
PY
```

## Security and scope

This is intended for a controlled, single-machine classroom/demo setup, not a public internet service. Keep `HOST=127.0.0.1`; do not expose it to a network without a security review, HTTPS, hardened secret management, backup/retention procedures, access controls, abuse protection, and institution-specific privacy/legal review. Cookies are HttpOnly and SameSite=Lax; camera and API routes require administrator authentication, and state-changing requests are CSRF-protected. The manual attendance form offers a non-biometric alternative.

The app implements face **recognition** only: no liveness detection, no identity proof, no anti-spoofing, no unattended auto-deletion, and no guarantee of accuracy. It uses Haar cascade face detection plus LBPH, which is a lightweight baseline rather than a modern high-accuracy face embedding model. Maintain a manual fallback and audit attendance records.

## Troubleshooting

- **`OpenCV face module is missing`**: reinstall into the active virtual environment using `pip install --force-reinstall opencv-contrib-python-headless`; uninstall conflicting `opencv-python` packages first.
- **Camera blocked**: use `http://127.0.0.1:5000`, allow camera access in the browser, check OS permissions, and close other apps using the camera.
- **No face found / too many faces**: ensure exactly one face is clearly visible, improve lighting, and capture at a closer distance.
- **False matches or missed matches**: gather more varied enrollment samples and lower `FACE_MATCH_THRESHOLD` to be stricter. After editing the value, restart the app. The model retrains as sample batches are saved and when a student is activated/deactivated.
- **Stale model**: enroll samples again to retrain. If needed, stop the server, remove `faces/lbph_model.yml` and `faces/model_labels.json`, then save fresh samples to trigger training.

## Project layout

```text
Face-Recognition-Attendance-System/
├── main.py                     # Flask app, routes, authentication
├── config.py                   # Paths and environment-backed settings
├── database.py                 # SQLite helpers and initialization
├── student.py                  # Roster validation and queries
├── face_capture.py             # Webcam capture utility
├── face_recognition.py         # Enrollment, training, matching
├── attendance.py               # Attendance and dashboard queries
├── report.py                   # CSV and date validation
├── database/database.sql       # Database schema
├── templates/                  # Jinja pages
├── static/                     # CSS and browser camera logic
├── faces/                      # Local face samples/model (git-ignored)
└── reports/                    # Optional local report exports
```
