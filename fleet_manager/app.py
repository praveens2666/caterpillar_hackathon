from flask import Flask, render_template, g, request, redirect, url_for, flash, jsonify, session
import sqlite3
import os
import threading
import random
import time
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'fleet_secret_key'
app.permanent_session_lifetime = timedelta(days=1)
# 1. Ensure the database path is correct and shared with the operator app
DATABASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cat_operator.db'))

FLEET_MANAGER_USERNAME = 'fleetadmin'
FLEET_MANAGER_PASSWORD = 'fleet123'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == FLEET_MANAGER_USERNAME and password == FLEET_MANAGER_PASSWORD:
            session['fleet_manager_logged_in'] = True
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('fleet_login.html')

@app.route('/logout')
def logout():
    session.pop('fleet_manager_logged_in', None)
    return redirect(url_for('login'))

from functools import wraps
def fleet_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('fleet_manager_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET', 'POST'])
@fleet_manager_required
def dashboard():
    conn = get_db()
    # Get all machines for dropdown
    machines = conn.execute('SELECT id, machine_id, model, latitude, longitude FROM machine').fetchall()
    # Handle task assignment
    if request.method == 'POST':
        operator_id = request.form['operator_id']
        description = request.form['description']
        scheduled_time = request.form['scheduled_time']
        machine_id = request.form['machine_id']
        conn.execute('INSERT INTO task (operator_id, description, scheduled_time, status, progress, machine_id) VALUES (?, ?, ?, ?, ?, ?)',
                     (operator_id, description, scheduled_time, 'pending', 0, machine_id))
        conn.commit()
        flash('Task assigned!')
        return redirect(url_for('dashboard'))
    # 2. Show raw work_session table for debugging
    sessions = conn.execute('SELECT * FROM work_session').fetchall()
    # 3. Get all operators
    operators = conn.execute('SELECT id, username FROM operator').fetchall()
    session_map = {s['operator_id']: s['on_break'] for s in sessions}
    operator_infos = []
    for op in operators:
        current_task = conn.execute('''SELECT t.description, m.machine_id, m.model FROM task t LEFT JOIN machine m ON t.machine_id = m.id WHERE t.operator_id=? AND t.status='in_progress' LIMIT 1''', (op['id'],)).fetchone()
        if op['id'] in session_map:
            if session_map[op['id']]:
                status = 'Break'
            else:
                status = 'Active'
        else:
            status = 'Inactive'
        operator_infos.append({
            'id': op['id'],
            'username': op['username'],
            'status': status,
            'current_task': current_task['description'] if current_task else None,
            'current_machine': f"{current_task['machine_id']} - {current_task['model']}" if current_task else None
        })
    # Pass machines to template for map markers
    return render_template('dashboard.html', operators=operator_infos, sessions=sessions, all_operators=operators, machines=machines)

@app.route('/debug_sessions')
def debug_sessions():
    conn = get_db()
    sessions = conn.execute('SELECT * FROM work_session').fetchall()
    return render_template('debug_sessions.html', sessions=sessions)

@app.route('/api/operator_status')
def api_operator_status():
    conn = get_db()
    # Get all operators
    operators = conn.execute('SELECT id, username FROM operator').fetchall()
    # Get all current sessions
    sessions = conn.execute('SELECT * FROM work_session').fetchall()
    session_map = {s['operator_id']: s for s in sessions}
    # Get last known times for all operators (including inactive)
    last_times = {}
    for s in sessions:
        last_times[s['operator_id']] = {
            'working_seconds': s['working_seconds'] if s['working_seconds'] is not None else 0,
            'break_seconds': s['break_seconds'] if s['break_seconds'] is not None else 0
        }
    # For operators with no session, try to get last times from a historical table if available (not implemented here)
    operator_infos = []
    for op in operators:
        if op['id'] in session_map:
            sess = session_map[op['id']]
            if sess['on_break']:
                status = 'Break'
            else:
                status = 'Active'
            working_seconds = sess['working_seconds'] if sess['working_seconds'] is not None else 0
            break_seconds = sess['break_seconds'] if sess['break_seconds'] is not None else 0
        else:
            status = 'Inactive'
            # Use last known times if available
            working_seconds = last_times.get(op['id'], {}).get('working_seconds', 0)
            break_seconds = last_times.get(op['id'], {}).get('break_seconds', 0)
        operator_infos.append({
            'id': op['id'],
            'username': op['username'],
            'status': status,
            'working_seconds': working_seconds,
            'break_seconds': break_seconds
        })
    return jsonify({'operators': operator_infos})

def init_fleet_db():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fleet_manager.db'))
    if not os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS fleet_manager (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        # Insert default fleet manager
        c.execute("INSERT INTO fleet_manager (username, password) VALUES (?, ?)", ("fleetadmin", "fleet123"))
        conn.commit()
        conn.close()
init_fleet_db()

# --- Machine Location Simulation ---
active_machine_locations = {}

# Helper: get current task and machine for each operator
def get_operator_current_task(conn, operator_id):
    row = conn.execute('''SELECT t.description, m.machine_id, m.model, m.latitude, m.longitude, m.id as machine_dbid
        FROM task t LEFT JOIN machine m ON t.machine_id = m.id
        WHERE t.operator_id=? AND t.status='in_progress' LIMIT 1''', (operator_id,)).fetchone()
    if row:
        return dict(row)
    return None

def move_active_machines():
    while True:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        # Find all active machines (linked to in-progress tasks)
        rows = conn.execute('''SELECT m.id, m.latitude, m.longitude FROM machine m
            JOIN task t ON t.machine_id = m.id WHERE t.status='in_progress' ''').fetchall()
        for row in rows:
            # Randomly move location within ~0.001 deg
            lat = row['latitude'] + random.uniform(-0.001, 0.001)
            lon = row['longitude'] + random.uniform(-0.001, 0.001)
            conn.execute('UPDATE machine SET latitude=?, longitude=? WHERE id=?', (lat, lon, row['id']))
        conn.commit()
        conn.close()
        time.sleep(3)  # Move every 3 seconds

threading.Thread(target=move_active_machines, daemon=True).start()

if __name__ == '__main__':
    app.run(port=5001, debug=True)
