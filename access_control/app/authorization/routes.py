from flask import render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required
from app.authorization import authz_bp
from app.models.models import Personnel, Role, Zone, AccessLog, Alert
from app import db
from app.face_recognition.engine import enroll_person_image, capture_and_recognize, DEFAULT_TIMEOUT, DEFAULT_VOTES, DEFAULT_TOLERANCE
from app.face_recognition.camera import camera_manager
from app.face_recognition.engine import recognize_from_frames
import numpy as np
import cv2
from threading import Thread, Event
from flask import current_app


@authz_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


@authz_bp.route('/personnel')
@login_required
def personnel_list():
    people = Personnel.query.all()
    return render_template('personnel_list.html', personnel=people)


@authz_bp.route('/personnel/add', methods=['GET', 'POST'])
@login_required
def add_personnel():
    roles = Role.query.all()
    if request.method == 'POST':
        name = request.form.get('full_name')
        role_id = request.form.get('role_id')
        file = request.files.get('face_image')
        filename = file.filename
        try:
            enroll_person_image(file.stream, filename, name, role_id)
            flash('Personnel added', 'success')
            return redirect(url_for('authorization.personnel_list'))
        except Exception as e:
            flash(str(e), 'danger')
    return render_template('add_personnel.html', roles=roles)


@authz_bp.route('/personnel/edit/<int:person_id>', methods=['GET', 'POST'])
@login_required
def edit_personnel(person_id):
    person = Personnel.query.get_or_404(person_id)
    roles = Role.query.all()
    if request.method == 'POST':
        person.full_name = request.form.get('full_name')
        person.role_id = request.form.get('role_id')
        person.active = bool(request.form.get('active'))
        db.session.commit()
        flash('Personnel updated', 'success')
        return redirect(url_for('authorization.personnel_list'))
    return render_template('add_personnel.html', roles=roles, person=person)


@authz_bp.route('/personnel/delete/<int:person_id>', methods=['POST'])
@login_required
def delete_personnel(person_id):
    person = Personnel.query.get_or_404(person_id)
    db.session.delete(person)
    db.session.commit()
    flash('Personnel deleted', 'success')
    return redirect(url_for('authorization.personnel_list'))


@authz_bp.route('/roles')
@login_required
def roles():
    r = Role.query.all()
    return render_template('roles.html', roles=r)


@authz_bp.route('/roles/add', methods=['GET', 'POST'])
@login_required
def add_role():
    if request.method == 'POST':
        name = request.form.get('role_name')
        desc = request.form.get('description')
        role = Role(role_name=name, description=desc)
        db.session.add(role)
        db.session.commit()
        flash('Role added', 'success')
        return redirect(url_for('authorization.roles'))
    return render_template('role_form.html', action='Add')


@authz_bp.route('/roles/edit/<int:role_id>', methods=['GET', 'POST'])
@login_required
def edit_role(role_id):
    role = Role.query.get_or_404(role_id)
    if request.method == 'POST':
        role.role_name = request.form.get('role_name')
        role.description = request.form.get('description')
        db.session.commit()
        flash('Role updated', 'success')
        return redirect(url_for('authorization.roles'))
    return render_template('role_form.html', action='Edit', role=role)


@authz_bp.route('/roles/delete/<int:role_id>', methods=['POST'])
@login_required
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash('Role deleted', 'success')
    return redirect(url_for('authorization.roles'))


@authz_bp.route('/zones')
@login_required
def zones():
    z = Zone.query.all()
    return render_template('zones.html', zones=z)


@authz_bp.route('/zones/add', methods=['GET', 'POST'])
@login_required
def add_zone():
    if request.method == 'POST':
        name = request.form.get('zone_name')
        desc = request.form.get('description')
        zone = Zone(zone_name=name, description=desc)
        db.session.add(zone)
        db.session.commit()
        flash('Zone added', 'success')
        return redirect(url_for('authorization.zones'))
    return render_template('zone_form.html', action='Add')


@authz_bp.route('/zones/edit/<int:zone_id>', methods=['GET', 'POST'])
@login_required
def edit_zone(zone_id):
    zone = Zone.query.get_or_404(zone_id)
    if request.method == 'POST':
        zone.zone_name = request.form.get('zone_name')
        zone.description = request.form.get('description')
        db.session.commit()
        flash('Zone updated', 'success')
        return redirect(url_for('authorization.zones'))
    return render_template('zone_form.html', action='Edit', zone=zone)


@authz_bp.route('/zones/delete/<int:zone_id>', methods=['POST'])
@login_required
def delete_zone(zone_id):
    zone = Zone.query.get_or_404(zone_id)
    db.session.delete(zone)
    db.session.commit()
    flash('Zone deleted', 'success')
    return redirect(url_for('authorization.zones'))


@authz_bp.route('/role_zone', methods=['GET', 'POST'])
@login_required
def role_zone():
    roles = Role.query.all()
    zones = Zone.query.all()
    if request.method == 'POST':
        role_id = request.form.get('role_id')
        zone_ids = request.form.getlist('zone_ids')
        role = Role.query.get(role_id)
        role.zones = [Zone.query.get(int(zid)) for zid in zone_ids]
        db.session.commit()
        flash('Role-zone assignments updated', 'success')
        return redirect(url_for('authorization.role_zone'))
    return render_template('role_zone.html', roles=roles, zones=zones)


@authz_bp.route('/access_logs')
@login_required
def access_logs():
    logs = AccessLog.query.order_by(AccessLog.timestamp.desc()).all()
    return render_template('access_logs.html', logs=logs)


@authz_bp.route('/access_logs/delete/<int:log_id>', methods=['POST'])
@login_required
def delete_access_log(log_id):
    log_entry = AccessLog.query.get_or_404(log_id)
    db.session.delete(log_entry)
    db.session.commit()
    flash('Log deleted', 'success')
    return redirect(url_for('authorization.access_logs'))


@authz_bp.route('/alerts')
@login_required
def alerts():
    alerts = Alert.query.order_by(Alert.timestamp.desc()).all()
    return render_template('alerts.html', alerts=alerts)


@authz_bp.route('/alerts/resolve/<int:alert_id>', methods=['POST'])
@login_required
def resolve_alert(alert_id):
    alert = Alert.query.get(alert_id)
    if alert:
        alert.resolved = True
        db.session.commit()
    return redirect(url_for('authorization.alerts'))


@authz_bp.route('/alerts/delete/<int:alert_id>', methods=['POST'])
@login_required
def delete_alert(alert_id):
    a = Alert.query.get_or_404(alert_id)
    db.session.delete(a)
    db.session.commit()
    flash('Alert deleted', 'success')
    return redirect(url_for('authorization.alerts'))


@authz_bp.route('/simulate/recognize', methods=['POST'])
@login_required
def simulate_recognize():
    zone = request.form.get('zone')
    # Recognition is automatic/adaptive; ignore manual timeout/votes/tolerance from UI
    timeout = DEFAULT_TIMEOUT
    votes = DEFAULT_VOTES
    tolerance = DEFAULT_TOLERANCE
    show_window = request.form.get('show_window', 'true').lower() in ('1', 'true', 'yes')

    # If an image file is provided, run recognition against that image (useful for simulation/testing)
    img_file = request.files.get('image')
    if img_file:
        # read image bytes and decode to BGR frame
        data = img_file.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({'status': 'error', 'error': 'invalid_image'})

        # Provide the same frame repeatedly so adaptive detection has multiple samples
        frames_to_send = max(3, int(votes))
        calls = {'n': 0}
        def get_frame_callable():
            if calls['n'] < frames_to_send:
                calls['n'] += 1
                return frame
            return None

        result = recognize_from_frames(get_frame_callable, zone, timeout_seconds=timeout, required_votes=votes, tolerance=tolerance)
        return jsonify(result)

    # otherwise use live camera capture
    result = capture_and_recognize(zone, timeout_seconds=timeout, required_votes=votes, tolerance=tolerance, show_window=show_window)
    return jsonify(result)


# MJPEG stream
@authz_bp.route('/camera/stream')
@login_required
def camera_stream():
    return Response(camera_manager.stream_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')


# Recognition control endpoints
RECOG_STATE = {
    'thread': None,
    'stop_event': None,
    'result': None
}


def _run_recognition(app, zone, timeout, votes, tolerance):
    stop_ev = RECOG_STATE['stop_event']
    try:
        with app.app_context():
            result = recognize_from_frames(camera_manager.get_frame, zone, timeout_seconds=timeout, required_votes=votes, tolerance=tolerance, stop_event=stop_ev)
            RECOG_STATE['result'] = result
    except Exception as e:
        RECOG_STATE['result'] = {'status': 'error', 'error': str(e)}
    finally:
        RECOG_STATE['thread'] = None


@authz_bp.route('/recognize/start', methods=['POST'])
@login_required
def recognize_start():
    zone = request.form.get('zone')
    # Ignore client-supplied timeout/votes/tolerance; use adaptive defaults
    timeout = DEFAULT_TIMEOUT
    votes = DEFAULT_VOTES
    tolerance = DEFAULT_TOLERANCE

    # ensure camera running
    camera_manager.start()

    if RECOG_STATE['thread'] and RECOG_STATE['thread'].is_alive():
        return jsonify({'status': 'running'})

    stop_ev = Event()
    RECOG_STATE['stop_event'] = stop_ev
    RECOG_STATE['result'] = None
    # capture app object to use in background thread
    app_ctx = current_app._get_current_object()
    t = Thread(target=_run_recognition, args=(app_ctx, zone, timeout or 3600, votes, tolerance), daemon=True)
    RECOG_STATE['thread'] = t
    t.start()
    return jsonify({'status': 'started'})


@authz_bp.route('/recognize/stop', methods=['POST'])
@login_required
def recognize_stop():
    if RECOG_STATE.get('stop_event'):
        RECOG_STATE['stop_event'].set()
    return jsonify({'status': 'stopping'})


@authz_bp.route('/recognize/status')
@login_required
def recognize_status():
    if RECOG_STATE.get('result'):
        return jsonify({'status': 'finished', 'result': RECOG_STATE['result']})
    if RECOG_STATE.get('thread') and RECOG_STATE['thread'].is_alive():
        return jsonify({'status': 'running'})
    return jsonify({'status': 'idle'})
