import cv2
import face_recognition
from app.models.models import Personnel
from app import db
from config import UPLOAD_FOLDER
import numpy as np
from datetime import datetime, timedelta
from app.models.models import AccessLog, Alert, Role, Zone
import time
from collections import Counter, deque
import logging
import os
import math
from pathlib import Path
from werkzeug.utils import secure_filename


def _normalize_locations(locs):
    """Convert various dlib/face_recognition location types to (top,right,bottom,left) tuples."""
    out = []
    for l in locs:
        # full_object_detection (has rect)
        if hasattr(l, 'rect'):
            r = l.rect
            out.append((r.top(), r.right(), r.bottom(), r.left()))
        # dlib.rectangle
        elif hasattr(l, 'top') and hasattr(l, 'right'):
            out.append((l.top(), l.right(), l.bottom(), l.left()))
        else:
            out.append(tuple(l))
    return out


# Configuration (safe defaults)
DEFAULT_TIMEOUT = 10
MAX_TIMEOUT = 15
DEFAULT_VOTES = 1
DEFAULT_TOLERANCE = 0.6
POLL_INTERVAL = 0.1
ALERT_SUPPRESSION_MIN_FRAMES = 3  # don't alert if only brief/no frames seen
UNKNOWN_ALERT_THRESHOLD = 3
DECAY_FACTOR = 0.96  # per-frame soft decay for previous counts
# Performance tuning
# Use a slightly higher width and don't skip frames by default to avoid missing faces
DEFAULT_TARGET_WIDTH = 640
# Process every 2nd frame by default to reduce CPU and speed up throughput on slow webcams
FRAME_SKIP = 2  # only run detection on every Nth captured frame (1 = process every frame)
# Idle/dark detection
CAMERA_IDLE_VARIANCE_THRESHOLD = 15.0  # low variance => likely static/dark scene
CAMERA_IDLE_FRAMES = 40  # number of consecutive low-variance frames to consider camera idle

# Recognition stability
# Require only a single sustained frame for faster decisions in fast mode
STABILITY_REQUIRED_FRAMES = 1  # require sustained confidence over N frames
# Slightly lower acceptance thresholds for faster unlocks (can be tuned)
MIN_CONFIDENCE_PERCENT = 0.55  # base percent confidence required to accept
MIN_CONFIDENCE_PERCENT_EARLY = 0.40  # permissive early
MIN_TOLERANCE = 0.35  # don't get stricter than this
# Fast/simple mode tuning for low-light webcams
FAST_TARGET_WIDTH = 280    # smaller frame for detection (faster)
ENCODING_CROP_WIDTH = 120  # crop width for encoding to reduce work
EMA_DECAY = 0.60           # exponential moving average decay for per-id confidence (lower => faster response)
EMA_THRESHOLD = 0.55       # EMA threshold to accept identity


def _preprocess_frame(frame, target_width=None, enhance=True):
    """Apply basic preprocessing: optional resize, denoise, brightness normalization.

    Input: BGR frame (as from OpenCV). Returns BGR frame.
    """
    if frame is None:
        return None

    out = frame.copy()
    # Optionally resize to target_width for consistent detection scale
    if target_width:
        h, w = out.shape[:2]
        if w != target_width:
            scale = target_width / float(w)
            out = cv2.resize(out, (target_width, int(h * scale)))

    if enhance:
        # Convert to YCrCb and apply CLAHE to Y channel to normalize brightness/contrast
        try:
            ycrcb = cv2.cvtColor(out, cv2.COLOR_BGR2YCrCb)
            y, cr, cb = cv2.split(ycrcb)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            y = clahe.apply(y)
            ycrcb = cv2.merge([y, cr, cb])
            out = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
        except Exception:
            # if conversion fails, continue with original
            pass

        # Denoise a little (fastNlMeansColored) - light parameters to avoid detail loss
        try:
            out = cv2.fastNlMeansDenoisingColored(out, None, h=3, hForColor=3, templateWindowSize=7, searchWindowSize=21)
        except Exception:
            pass

    return out


def _choose_locator(preferred='cnn'):
    """Return locator model: prefer cnn if available else hog."""
    # face_recognition supports 'cnn' and 'hog'. If cnn not available (no dlib compiled), fallback
    if preferred == 'cnn':
        try:
            # quick smoke call to check availability (may raise if not compiled)
            _ = face_recognition.api.cnn_face_detector
            return 'cnn'
        except Exception:
            return 'hog'
    return 'hog'


def _log_counts(logger, counts):
    try:
        logger.debug('Counts: %s', dict(counts))
    except Exception:
        logger.debug('Counts (unprintable)')


def enroll_person_image(file_stream, filename, full_name, role_id):
    # werkzeug.secure_filename strips path separators and unsafe characters,
    # blocking '../etc/passwd' style traversal and Windows reserved names.
    safe_name = secure_filename(filename or '')
    if not safe_name:
        raise ValueError('Invalid filename')

    save_path = Path(UPLOAD_FOLDER) / safe_name
    with open(save_path, 'wb') as f:
        f.write(file_stream.read())

    image = face_recognition.load_image_file(str(save_path))
    encodings = face_recognition.face_encodings(image)
    if len(encodings) != 1:
        raise ValueError('Image must contain exactly one clear face')
    encoding = encodings[0]

    person = Personnel(full_name=full_name, role_id=role_id)
    person.set_encoding(encoding)
    db.session.add(person)
    db.session.commit()
    return person


def capture_and_recognize(zone_name, timeout_seconds=DEFAULT_TIMEOUT, required_votes=DEFAULT_VOTES, tolerance=DEFAULT_TOLERANCE, show_window=True, camera_index=0, locator_preference='hog'):
    """Capture from local camera and run recognition using the shared core loop.

    This function preserves the original return contract.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return {'status': 'failure', 'reason': 'camera_error'}

    def get_frame():
        ret, frame = cap.read()
        if not ret:
            return None
        # show overlay window if desired
        if show_window and frame is not None:
            try:
                cv2.imshow('Recognition (press q to cancel)', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    return None
            except Exception:
                pass
        return frame

    try:
        result = _run_recognition_core(get_frame, zone_name, timeout_seconds=timeout_seconds, required_votes=required_votes, tolerance=tolerance, poll_interval=POLL_INTERVAL, locator_preference=locator_preference, show_window=show_window)
        return result
    finally:
        cap.release()
        cv2.destroyAllWindows()


def create_alert_if_needed(alert_type, zone_name, description):
    # Simple alert generation rules:
    #  - create alert on unknown face
    #  - create alert if 3+ denials for same name/Unknown in last 5 minutes
    now = datetime.utcnow()
    five_min_ago = now - timedelta(minutes=5)

    recent_denials = AccessLog.query.filter(AccessLog.timestamp >= five_min_ago, AccessLog.status == 'failure', AccessLog.zone == zone_name).count()
    if alert_type == 'Unknown Face':
        alert = Alert(zone=zone_name, alert_type=alert_type, description=description)
        db.session.add(alert)
        db.session.commit()
        return

    if recent_denials >= 3:
        alert = Alert(zone=zone_name, alert_type='Repeated Denial', description=f'{recent_denials} recent failures: {description}')
        db.session.add(alert)
        db.session.commit()


def _run_recognition_core(get_frame_callable, zone_name, timeout_seconds=DEFAULT_TIMEOUT, required_votes=DEFAULT_VOTES, tolerance=DEFAULT_TOLERANCE, poll_interval=POLL_INTERVAL, stop_event=None, locator_preference='hog', show_window=False):
    """Core recognition loop used by both camera capture and external frame sources.

    Returns the same dict shape as previous functions.
    """
    logger = logging.getLogger('face_recog')
    if not logger.handlers:
        log_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')), 'face_recog.log')
        fh = logging.FileHandler(log_path)
        fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(fh)
        logger.setLevel(logging.DEBUG)

    locator_model = _choose_locator(locator_preference)
    logger.info('Recognition start zone=%s locator=%s timeout=%s votes=%s tol=%s', zone_name, locator_model, timeout_seconds, required_votes, tolerance)

    # Load known encodings
    personnel = Personnel.query.filter(Personnel.face_encoding.isnot(None)).all()
    known_encodings = []
    names = []
    ids = []
    for p in personnel:
        enc = p.get_encoding()
        if enc is not None:
            known_encodings.append(enc)
            names.append(p.full_name)
            ids.append(p.id)

    logger.debug('Loaded %d known encodings', len(known_encodings))

    start = time.time()
    frames = 0
    capture_count = 0
    counts = Counter()
    # allow fractional counts for soft decay
    float_counts = { }
    last_seen = {}
    detection_state = 'searching'
    adaptive_timeout = timeout_seconds

    # runtime state for idle detection and stability
    idle_frame_count = 0
    camera_idle = False
    stable_counters = {}
    ema_confidences = {}  # exponential moving average per id for simple/faster decisions

    while True:
        if stop_event and stop_event.is_set():
            break
        frame = get_frame_callable()
        if frame is None:
            time.sleep(poll_interval)
            # timeout check
            if (time.time() - start) > adaptive_timeout:
                break
            continue

        frames += 1
        capture_count += 1

        # Skip some frames to reduce CPU load (still count frames for timing/alerts)
        if FRAME_SKIP > 1 and (capture_count % FRAME_SKIP) != 0:
            time.sleep(max(0.0, poll_interval))
            if (time.time() - start) > adaptive_timeout:
                break
            continue

        # Preprocess frame for more robust detection (enable enhancement for reliability)
        proc = _preprocess_frame(frame, target_width=DEFAULT_TARGET_WIDTH, enhance=True)
        rgb = proc[:, :, ::-1]

        # Camera idle / dark detection: compute simple frame variance on grayscale.
        try:
            gray = cv2.cvtColor(proc, cv2.COLOR_BGR2GRAY)
            var = float(np.var(gray))
        except Exception:
            var = 255.0

        if var < CAMERA_IDLE_VARIANCE_THRESHOLD:
            idle_frame_count += 1
        else:
            idle_frame_count = 0

        camera_idle = idle_frame_count >= CAMERA_IDLE_FRAMES
        if camera_idle:
            logger.debug('Camera idle detected (variance=%.2f) - suppressing recognition work', var)
            # show minimal overlay if window requested
            if show_window:
                try:
                    disp = proc.copy()
                    cv2.putText(disp, 'Camera idle', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    cv2.imshow('Recognition (press q to cancel)', disp)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                except Exception:
                    pass
            time.sleep(poll_interval)
            # do not update counts or raise no-face alerts while idle
            if (time.time() - start) > adaptive_timeout:
                break
            continue

        # Fast/simple detection pipeline optimized for low-light and speed:
        #  - detect on a small resized frame (hog) for speed
        #  - choose largest face when multiple are present
        #  - compute encoding on a small cropped face region to reduce work
        #  - use an EMA per-identity for simple, fast confidence aggregation
        try:
            # resize for fast detection
            h, w = rgb.shape[:2]
            if w > FAST_TARGET_WIDTH:
                scale = FAST_TARGET_WIDTH / float(w)
                small_rgb = cv2.resize(rgb, (FAST_TARGET_WIDTH, int(h * scale)))
            else:
                small_rgb = rgb
            # ensure contiguous memory layout for dlib/face_recognition
            small_rgb = np.ascontiguousarray(small_rgb)

            # prefer HOG for speed; fall back to locator_model if caller forced CNN
            fast_locator = 'hog' if locator_preference != 'cnn' else locator_model
            small_locs = face_recognition.face_locations(small_rgb, model=fast_locator)
            # normalize and scale locations back to original proc coordinates
            face_locations = []
            encodings = []
            if small_locs:
                small_locs = _normalize_locations(small_locs)
                # scale locations to proc size
                sx = float(w) / float(small_rgb.shape[1])
                sy = float(h) / float(small_rgb.shape[0])
                scaled_locs = []
                for (t, r, b, l) in small_locs:
                    scaled_locs.append((int(t * sy), int(r * sx), int(b * sy), int(l * sx)))
                # select largest face only
                areas = [ (b - t) * (r - l) for (t, r, b, l) in scaled_locs ]
                max_idx = int(np.argmax(areas)) if areas else None
                if max_idx is not None:
                    loc = scaled_locs[max_idx]
                    face_locations = [loc]
                    # crop from proc (BGR) and compute encoding on a small resized crop
                    t, r, b, l = loc
                    # ensure coords inside image
                    t = max(0, t); l = max(0, l); b = min(proc.shape[0], b); r = min(proc.shape[1], r)
                    crop = proc[t:b, l:r]
                    try:
                        crop_rgb = crop[:, :, ::-1]
                        crop_rgb = np.ascontiguousarray(crop_rgb)
                        # resize crop for faster encoding
                        ch, cw = crop_rgb.shape[:2]
                        if cw > ENCODING_CROP_WIDTH:
                            crop_rgb = cv2.resize(crop_rgb, (ENCODING_CROP_WIDTH, int(ch * (ENCODING_CROP_WIDTH / float(cw)))))
                        encs = face_recognition.face_encodings(crop_rgb)
                        if encs:
                            encodings = [encs[0]]
                    except Exception as e:
                        logger.debug('Encoding on crop failed: %s', e)
                        encodings = []
        except Exception as e:
            logger.exception('Fast detection error: %s', e)
            face_locations = []
            encodings = []

        # Soft-decay counts for logging purposes
        for k in list(float_counts.keys()):
            float_counts[k] = float_counts.get(k, 0.0) * DECAY_FACTOR
            if float_counts[k] < 0.01:
                del float_counts[k]

        # evaluate encodings (at most one) and update EMA confidences
        frame_ids = []
        if encodings and known_encodings:
            enc = encodings[0]
            dists = face_recognition.face_distance(known_encodings, enc)
            best_idx = int(np.argmin(dists))
            best_dist = float(dists[best_idx])
            # simple mapping from distance to per-frame confidence (0..1)
            frame_conf = max(0.0, 1.0 - (best_dist / 0.8))
            pid = ids[best_idx] if best_dist <= 0.9 else 'unknown'
            frame_ids.append((pid, frame_conf))
        else:
            # no clear encoding: treat as unknown presence (small confidence)
            if face_locations:
                frame_ids.append(('unknown', 0.15))

        # update EMA confidences and counts
        for k in list(ema_confidences.keys()):
            ema_confidences[k] = ema_confidences.get(k, 0.0) * EMA_DECAY
        for pid, conf in frame_ids:
            ema_confidences[pid] = ema_confidences.get(pid, 0.0) * EMA_DECAY + (1.0 - EMA_DECAY) * conf
            # also maintain a simple integer-like count for backward-compatible logs/alerts
            float_counts[pid] = float_counts.get(pid, 0.0) + conf
            counts[pid] = int(round(float_counts.get(pid, 0)))

        # top candidate by EMA
        if ema_confidences:
            top_pid = max(ema_confidences.items(), key=lambda iv: iv[1])[0]
            top_conf = ema_confidences.get(top_pid, 0.0)
        else:
            top_pid, top_conf = None, 0.0

        _log_counts(logger, counts)

        # Minimal debug overlay: show top identity and confidence on preview when enabled.
        if show_window:
            try:
                disp = proc.copy()
                if face_locations:
                    t, r, b, l = face_locations[0]
                    cv2.rectangle(disp, (l, t), (r, b), (0, 255, 0), 2)

                if top_pid:
                    if top_pid == 'unknown':
                        label = f'Unknown {top_conf*100:.0f}%'
                    else:
                        try:
                            name_idx = ids.index(top_pid)
                            person_name = names[name_idx]
                        except Exception:
                            person_name = str(top_pid)
                        label = f'{person_name} {top_conf*100:.0f}%'
                else:
                    label = 'No face'

                cv2.putText(disp, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                cv2.imshow('Recognition (press q to cancel)', disp)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            except Exception:
                pass

        # determine detection state using EMA confidence and sustained frames
        if not face_locations:
            if detection_state != 'searching':
                detection_state = 'searching'
            top_pid, top_conf = None, 0.0
        else:
            # adaptive required confidence: be permissive early in sequence
            required_conf = MIN_CONFIDENCE_PERCENT_EARLY if frames < 3 else MIN_CONFIDENCE_PERCENT

            # update stability counters based on EMA top candidate
            if top_pid:
                if top_conf >= required_conf:
                    stable_counters[top_pid] = stable_counters.get(top_pid, 0) + 1
                else:
                    stable_counters[top_pid] = 0

            # determine recognized state only when sustained over multiple frames
            if top_pid and stable_counters.get(top_pid, 0) >= STABILITY_REQUIRED_FRAMES and top_conf >= required_conf:
                detection_state = 'recognized'
            else:
                detection_state = 'detected_unstable'

        logger.debug('State=%s frames=%d top=%s', detection_state, frames, top_pid)

        # Finalize on recognized
        if detection_state == 'recognized' and top_pid is not None:
            pid = top_pid
            if pid == 'unknown':
                # log unknown series only if sustained
                if frames >= ALERT_SUPPRESSION_MIN_FRAMES and counts.get('unknown', 0) >= UNKNOWN_ALERT_THRESHOLD:
                    log = AccessLog(full_name='Unknown', zone=zone_name, status='failure', denial_reason='Unknown face (series)', action_taken='Simulated Lock Denial')
                    db.session.add(log)
                    db.session.commit()
                    create_alert_if_needed('Unknown Face', zone_name, 'Unknown face attempted access (series)')
                return {'status': 'failure', 'reason': 'unknown_face', 'frames': frames, 'counts': dict(counts)}

            person = Personnel.query.get(pid)
            if not person:
                # weird case, continue
                logger.warning('Matched id %s not found in DB', pid)
                continue
            if not person.active:
                log = AccessLog(full_name=person.full_name, zone=zone_name, status='failure', denial_reason='Personnel inactive', action_taken='Simulated Lock Denial')
                db.session.add(log)
                db.session.commit()
                create_alert_if_needed('Repeated Denial', zone_name, f'Inactive personnel {person.full_name} attempted access')
                return {'status': 'failure', 'reason': 'inactive', 'person': person.full_name, 'frames': frames, 'counts': dict(counts)}

            role = Role.query.get(person.role_id)
            zone = Zone.query.filter_by(zone_name=zone_name).first()
            allowed = False
            if role and zone and zone in role.zones:
                allowed = True

            if allowed:
                action = 'Simulated Door Unlock'
                log = AccessLog(full_name=person.full_name, zone=zone_name, status='success', denial_reason='', action_taken=action)
                db.session.add(log)
                db.session.commit()
                return {'status': 'success', 'person': person.full_name, 'action': action, 'frames': frames, 'counts': dict(counts)}
            else:
                action = 'Simulated Lock Denial'
                log = AccessLog(full_name=person.full_name, zone=zone_name, status='failure', denial_reason='No role permission', action_taken=action)
                db.session.add(log)
                db.session.commit()
                create_alert_if_needed('Repeated Denial', zone_name, f'Unauthorized access by {person.full_name}')
                return {'status': 'failure', 'reason': 'no_permission', 'person': person.full_name, 'frames': frames, 'counts': dict(counts)}

        # Timeout check
        if (time.time() - start) > adaptive_timeout:
            logger.debug('Timeout reached after %s seconds; final counts=%s', adaptive_timeout, dict(counts))
            break

    # After loop: decide outcome
    if counts:
        most_common = max(counts.items(), key=lambda iv: iv[1])
        pid, v = most_common
        if pid == 'unknown':
            # only create alert if sustained unknowns
            if frames >= ALERT_SUPPRESSION_MIN_FRAMES and counts.get('unknown', 0) >= UNKNOWN_ALERT_THRESHOLD:
                log = AccessLog(full_name='Unknown', zone=zone_name, status='failure', denial_reason='Unknown face (timeout)', action_taken='Simulated Lock Denial')
                db.session.add(log)
                db.session.commit()
                create_alert_if_needed('Unknown Face', zone_name, 'Unknown face attempted access (timeout)')
            return {'status': 'failure', 'reason': 'unknown_face', 'frames': frames, 'counts': dict(counts)}

        person = Personnel.query.get(pid)
        if person:
            role = Role.query.get(person.role_id)
            zone = Zone.query.filter_by(zone_name=zone_name).first()
            allowed = False
            if role and zone and zone in role.zones:
                allowed = True
            if allowed:
                action = 'Simulated Door Unlock'
                log = AccessLog(full_name=person.full_name, zone=zone_name, status='success', denial_reason='', action_taken=action)
                db.session.add(log)
                db.session.commit()
                return {'status': 'success', 'person': person.full_name, 'action': action, 'frames': frames, 'counts': dict(counts)}
            else:
                action = 'Simulated Lock Denial'
                log = AccessLog(full_name=person.full_name, zone=zone_name, status='failure', denial_reason='No role permission', action_taken=action)
                db.session.add(log)
                db.session.commit()
                create_alert_if_needed('Repeated Denial', zone_name, f'Unauthorized access by {person.full_name}')
                return {'status': 'failure', 'reason': 'no_permission', 'person': person.full_name, 'frames': frames, 'counts': dict(counts)}

    # Nothing detected - treat as denial (access denied when no face).
    # Always record an AccessLog entry for auditing (important for security).
    log = AccessLog(full_name='Unknown', zone=zone_name, status='failure', denial_reason='No face detected', action_taken='Simulated Lock Denial')
    db.session.add(log)
    db.session.commit()
    # Create an Unknown Face alert only when camera is not idle and sustained
    if not camera_idle and frames >= ALERT_SUPPRESSION_MIN_FRAMES:
        create_alert_if_needed('Unknown Face', zone_name, 'No face detected during recognition window')
    else:
        logger.debug('No-face recorded; alert suppressed (camera_idle=%s, frames=%s)', camera_idle, frames)
    return {'status': 'failure', 'reason': 'no_face', 'frames': frames, 'counts': dict(counts)}


def recognize_from_frames(get_frame_callable, zone_name, timeout_seconds=DEFAULT_TIMEOUT, required_votes=DEFAULT_VOTES, tolerance=DEFAULT_TOLERANCE, poll_interval=POLL_INTERVAL, stop_event=None, locator_model='cnn', show_window=False):
    # Wrapper that calls the core recognition loop. Keeps previous signature and return shape.
    return _run_recognition_core(get_frame_callable, zone_name, timeout_seconds=timeout_seconds, required_votes=required_votes, tolerance=tolerance, poll_interval=poll_interval, stop_event=stop_event, locator_preference=locator_model, show_window=show_window)
