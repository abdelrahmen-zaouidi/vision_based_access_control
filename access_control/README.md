# Sensitive Facility Access Control System (Simulated)

This project is a PC-only simulation of a role-based facial recognition access control system.

Quick start

1. Create a Python 3 virtual environment and install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2. Run the app:

```powershell
python run.py
```

3. Open `http://localhost:5000` and login with the default admin (created on first run):
- username: `admin`
- password: `adminpass`

Notes
- Uploads are stored at `C:\Users\Administrator\app\uploads` per spec.
- Database: SQLite (file `app.db`) but schema is MySQL-ready.

Security considerations and next steps are in code comments.
