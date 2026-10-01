"""Headless-compatible OpenCV utility for collecting face sample stills.

The web app's main enrollment flow uses the browser webcam. This optional
utility is useful when the webcam is physically attached to the server: press
Enter in the terminal to capture a still, then it saves only a validated face

crop. It works with opencv-contrib-python-headless and requires no GUI window.
"""
from __future__ import annotations

from pathlib import Path
import argparse

import cv2

from face_recognition import FaceError, detect_single_face


def capture_samples(output_dir: str | Path, count: int = 8, camera_index: int = 0) -> list[Path]:
    """Capture `count` face crops from a webcam, pressing Enter for each still."""
    if count < 1:
        raise ValueError("count must be positive")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        raise RuntimeError(f"Could not open camera {camera_index}.")
    saved: list[Path] = []
    try:
        while len(saved) < count:
            input(f"Position one face in frame; press Enter to capture ({len(saved)}/{count}, or Ctrl+C to cancel)… ")
            ok, frame = camera.read()
            if not ok:
                print("Could not read from camera; try again.")
                continue
            try:
                crop = detect_single_face(frame)
            except FaceError as exc:
                print(f"Capture rejected: {exc}")
                continue
            path = destination / f"sample_{len(saved)+1:03d}.png"
            if not cv2.imwrite(str(path), crop):
                raise RuntimeError(f"Could not save {path}.")
            saved.append(path)
            print(f"Saved sample {len(saved)}/{count}.")
        return saved
    finally:
        camera.release()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", help="Directory where cropped face samples will be saved")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()
    try:
        paths = capture_samples(args.output_dir, args.count, args.camera)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Saved {len(paths)} face sample(s) to {args.output_dir}")
    return 0 if len(paths) == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
