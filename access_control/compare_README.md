# Photo vs Webcam Face Comparison

Quick utility to compare a reference photo with a face captured from a webcam using `face_recognition` and `opencv-python`.

## Install
This project already includes `opencv-python` and `face_recognition` in `requirements.txt`.

On Windows you may need additional build tools for `dlib` (used by `face_recognition`). If installation fails, see the `face_recognition` docs and consider using a prebuilt wheel for `dlib`.

Example:
```bash
python -m pip install -r requirements.txt
```

## Usage
```bash
python compare_photo_webcam.py --photo path/to/person.jpg --tolerance 0.6 --output result.jpg
```

- `--photo`: path to the reference image containing one face
- `--tolerance`: matching tolerance (default 0.6). Lower = stricter
- `--camera`: camera index (default 0)

Controls: run the script, a live window opens; press SPACE to capture the frame.

## Improvements & Upgrades (ideas)

- **Liveness detection**: integrate eye-blink or challenge-response or an infrared camera to prevent presentation attacks.
- **Use stronger embeddings**: swap to ArcFace / InsightFace for more accurate matching under pose/lighting variations.
- **Store known encodings**: persist known embeddings in a small database for fast multi-person matching.
- **Batch enrollment**: allow enrolling multiple photos per person and averaging embeddings.
- **Real-time streaming mode**: process continuous frames and send alerts on match/unknown.
- **GUI / web UI**: wrap in a Flask/Streamlit app for easier use and audit logs.
- **Threshold calibration**: add an interactive tool to tune `--tolerance` for your camera/environment.
- **Privacy & security**: encrypt stored embeddings, audit access, and log events securely.

If you'd like, I can integrate this into the existing app structure, add a web endpoint, or implement one of the improvements above.
