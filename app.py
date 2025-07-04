from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, jsonify
import sqlite3
import os
import datetime
import random
import threading
import time
import itertools
import requests
import json
from datetime import timedelta
from ultralytics import YOLO
import cv2
import numpy as np
import pyttsx3
import winsound
import queue
import base64
from flask import request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'cat_secret_key'
app.permanent_session_lifetime = timedelta(days=1)
# Ensure session cookies are robust
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
DATABASE = 'cat_operator.db'

# Initialize Text-to-Speech engine
engine = pyttsx3.init()
engine.setProperty('rate', 250)
engine.setProperty('volume', 1.0)

# TTS queue and worker
_tts_queue = queue.Queue()
def tts_worker():
    print("[TTS] Worker started")
    engine = pyttsx3.init()
    engine.setProperty('rate', 250)
    engine.setProperty('volume', 1.0)
    while True:
        try:
            text = _tts_queue.get(timeout=5)
        except queue.Empty:
            continue
        if text is None:
            print("[TTS] Worker exiting")
            break
        print(f"[TTS] Speaking: {text}")
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"[TTS] Error: {e}")
threading.Thread(target=tts_worker, daemon=True).start()

def speak_text(text):
    print(f"[TTS] Queued: {text}")
    _tts_queue.put(text)

allowed_classes = ['person', 'car', 'truck', 'bus', 'motorcycle']
model = YOLO("yolov8n.pt")

# --- DB SETUP ---
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db()
        c = conn.cursor()
        c.execute('''CREATE TABLE operator (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE incident (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER,
            desc TEXT,
            timestamp TEXT,
            FOREIGN KEY(operator_id) REFERENCES operator(id)
        )''')
        c.execute('''CREATE TABLE machine_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            machine_id TEXT,
            operator_id TEXT,
            engine_hours REAL,
            fuel_used REAL,
            lead_cycles INTEGER,
            idling_time INTEGER,
            seatbelt_status TEXT,
            safety_alert TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER,
            description TEXT,
            scheduled_time TEXT,
            status TEXT,
            progress INTEGER,
            started_at TEXT,
            completed_at TEXT,
            machine_id INTEGER,
            FOREIGN KEY(operator_id) REFERENCES operator(id),
            FOREIGN KEY(machine_id) REFERENCES machine(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS machine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT UNIQUE NOT NULL,
            model TEXT,
            fuel_level REAL,
            last_service_date TEXT,
            next_service_due TEXT,
            hours_used REAL,
            latitude REAL,
            longitude REAL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS work_session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER,
            login_time TEXT,
            working_seconds INTEGER DEFAULT 0,
            break_seconds INTEGER DEFAULT 0,
            on_break INTEGER DEFAULT 0,
            last_update TEXT,
            FOREIGN KEY(operator_id) REFERENCES operator(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS mentor_booking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mentor_id INTEGER,
            mentor_name TEXT,
            course TEXT,
            time TEXT,
            mentor_phone TEXT,
            user_name TEXT,
            user_phone TEXT,
            user_email TEXT,
            user_company TEXT
        )''')
        # Insert sample operator
        c.execute("INSERT INTO operator (username, password) VALUES (?, ?)", ("catop", "cat123"))
        # Insert 5 sample operators
        c.executemany("INSERT INTO operator (username, password) VALUES (?, ?)", [
            ("catop1", "cat123"),
            ("catop2", "cat123"),
            ("catop3", "cat123"),
            ("catop4", "cat123"),
            ("catop5", "cat123")
        ])
        # Insert sample machine logs
        logs = [
            ("2025-05-01", "EXC001", "OP1001", 1523.5, 5.2, 12, 30, "Fastened", "No"),
            ("2025-05-01", "EXC001", "OP1001", 1524.8, 3.8, 2, 55, "Unfastened", "Yes"),
            ("2025-05-01 14:00:00", "EXC001", "OP1001", 1526.5, 6.1, 10, 15, "Fastened", "No"),
            ("2025-05-02", "EXC001", "OP1001", 1530.2, 2, 60, 60, "Unfastened", "Yes")
        ]
        c.executemany("INSERT INTO machine_log (date, machine_id, operator_id, engine_hours, fuel_used, lead_cycles, idling_time, seatbelt_status, safety_alert) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", logs)
        # Insert sample incidents
        sample_incidents = [
            (1, "Unsafe operation: Seatbelt unfastened and safety alert triggered on 2025-05-01", "2025-05-01 10:00:00"),
            (1, "Excessive idling detected on 2025-05-02 (Idling: 60 min)", "2025-05-02 14:30:00")
        ]
        c.executemany("INSERT INTO incident (operator_id, desc, timestamp) VALUES (?, ?, ?)", sample_incidents)
        # Insert sample tasks
        sample_tasks = [
            (1, "Excavate trench at site A", "08:00", "pending", 0, None, None, 1),
            (1, "Load gravel at site B", "11:00", "pending", 0, None, None, 1),
            (1, "Refuel and maintenance", "15:00", "pending", 0, None, None, 1)
        ]
        c.executemany("INSERT INTO task (operator_id, description, scheduled_time, status, progress, started_at, completed_at, machine_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", sample_tasks)
        # Insert sample machines with lat/lon
        machines = [
            ("EXC001", "CAT 320D3", 65.5, "2025-06-15", "2025-09-15", 1530.2, 13.0827, 80.2707),
            ("BLD002", "CAT D6K2", 80.0, "2025-05-10", "2025-08-10", 2100.0, 13.0100, 80.2200),
            ("LDR003", "CAT 950GC", 55.0, "2025-04-20", "2025-07-20", 980.5, 13.1000, 80.2900),
            ("DMP004", "CAT 770G", 90.0, "2025-03-15", "2025-09-15", 500.0, 13.0600, 80.2000),
            ("EXC005", "CAT 336D2", 40.0, "2025-02-01", "2025-08-01", 3000.0, 13.1200, 80.2500)
        ]
        c.executemany("INSERT INTO machine (machine_id, model, fuel_level, last_service_date, next_service_due, hours_used, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", machines)
        conn.commit()
        conn.close()

init_db()

# --- AUTH ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM operator WHERE username=? AND password=?', (username, password))
        user = c.fetchone()
        if user:
            session.permanent = True  # Make session permanent
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['login_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # Start a new work session directly in DB
            now = session['login_time']
            c.execute('DELETE FROM work_session WHERE operator_id=?', (user['id'],))
            c.execute('INSERT INTO work_session (operator_id, login_time, last_update) VALUES (?, ?, ?)', (user['id'], now, now))
            conn.commit()
            conn.close()
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        # Reset work session timers and remove session row
        conn = get_db()
        conn.execute('DELETE FROM work_session WHERE operator_id=?', (session['user_id'],))
        conn.commit()
        conn.close()
    session.clear()
    return redirect(url_for('login'))

# --- WEATHER API ---
WEATHER_API_KEY = '8324b62d96dd4cdbfde4d34c40d77fa8'  # Replace with your real API key
WEATHER_CITY = 'Chennai'  # Or make this dynamic

def get_weather_status():
    try:
        # Chennai coordinates
        lat = 13.0827
        lon = 80.2707
        url = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation,windspeed_10m&current_weather=true'
        resp = requests.get(url, timeout=5)
        data = resp.json()
        # Use current weather if available, else fallback to hourly
        if 'current_weather' in data:
            temp = data['current_weather']['temperature']
            wind = data['current_weather']['windspeed']
            # Precipitation is not in current_weather, so fallback to hourly
            precip = data['hourly']['precipitation'][0] if 'hourly' in data and 'precipitation' in data['hourly'] else 0
        else:
            temp = data['hourly']['temperature_2m'][0]
            wind = data['hourly']['windspeed_10m'][0]
            precip = data['hourly']['precipitation'][0]
        # Simple safety logic: unsafe if precipitation > 5mm or wind > 15 m/s
        if precip > 5 or wind > 15:
            safe = False
        else:
            safe = True
        return {
            'temp': temp,
            'weather': f'Precip: {precip}mm',
            'wind': wind,
            'safe': safe
        }
    except Exception as e:
        return {'temp': 'N/A', 'weather': 'N/A', 'wind': 'N/A', 'safe': None}

# --- DASHBOARD ---
def get_machine_overview():
    conn = get_db()
    machine = conn.execute('SELECT * FROM machine LIMIT 1').fetchone()
    conn.close()
    return machine

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    session.permanent = True  # Ensure session is always refreshed on dashboard access
    # Get session info
    conn = get_db()
    row = conn.execute('SELECT * FROM work_session WHERE operator_id=?', (session['user_id'],)).fetchone()
    if row:
        login_time = row['login_time']
        working_seconds = row['working_seconds']
        break_seconds = row['break_seconds']
        on_break = bool(row['on_break'])
        print(f"[DEBUG] Loading session for user {session['user_id']}: working_seconds={working_seconds}, break_seconds={break_seconds}, on_break={on_break}")
    else:
        login_time = session.get('login_time')
        working_seconds = 0
        break_seconds = 0
        on_break = False
    if request.method == 'POST':
        task_id = request.form.get('task_id')
        action = request.form.get('action')
        result = {'success': False}
        if action == 'start':
        # Check if any task is already in progress
            in_progress = conn.execute('SELECT id FROM task WHERE status=?', ("in_progress",)).fetchone()
            if in_progress:
                flash('Another task is already in progress. Complete it before starting a new one.')
                result = {'success': False, 'error': 'Another task is already in progress.'}
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute('UPDATE task SET status=?, started_at=? WHERE id=?', ("in_progress", now, task_id))
                result = {'success': True, 'task_id': task_id, 'status': 'in_progress'}
        elif action == 'complete':
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute('UPDATE task SET status=?, completed_at=?, progress=100 WHERE id=?', ("completed", now, task_id))
            result = {'success': True, 'task_id': task_id, 'status': 'completed'}
        elif action == 'progress':
            progress = int(request.form.get('progress', 0))
        # Only allow increasing progress
            current = conn.execute('SELECT progress FROM task WHERE id=?', (task_id,)).fetchone()[0]
            if progress > current:
                conn.execute('UPDATE task SET progress=? WHERE id=?', (progress, task_id))
                result = {'success': True, 'task_id': task_id, 'progress': progress}
            else:
                result = {'success': False, 'error': 'Progress not increased'}
        else:
            result = {'success': False, 'error': 'Unknown action'}
        conn.commit()
        session.modified = True  # Ensure session cookie is updated after POST
    # If AJAX, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            conn.close()
            return jsonify(result)
    # Fetch tasks with machine info
    tasks = conn.execute('''SELECT t.*, m.machine_id as machine_code, m.model as machine_model, m.fuel_level, m.hours_used, m.last_service_date, m.next_service_due FROM task t LEFT JOIN machine m ON t.machine_id = m.id WHERE t.operator_id=? ORDER BY t.scheduled_time''', (session['user_id'],)).fetchall()
    # Find the in-progress task and its machine
    in_progress_task = None
    current_machine = None
    for t in tasks:
        if t['status'] == 'in_progress' and t['machine_code']:
            in_progress_task = t
            current_machine = {
                'machine_id': t['machine_code'],
                'model': t['machine_model'],
                'fuel_level': t['fuel_level'],
                'hours_used': t['hours_used'],
                'last_service_date': t['last_service_date'],
                'next_service_due': t['next_service_due']
            }
            break
    # Do not fallback to default machine
    conn.close()
    weather = get_weather_status()
    return render_template('dashboard.html', tasks=tasks, username=session['username'], weather=weather, machine=current_machine, login_time=login_time, working_seconds=working_seconds, break_seconds=break_seconds, on_break=on_break)

# --- SAFETY ---

# Global state for demo hazard simulation
hazard_state = {
    'seatbelt': 'Normal',
    'ppe': 'Normal',
    'other': 'Normal'
}
# For random alternation
hazard_cycle = {
    'seatbelt': itertools.cycle(['Normal', 'Seatbelt unfastened!']),
    'ppe': itertools.cycle(['Normal', 'PPE removed!']),
    'other': itertools.cycle(['Normal', 'Excessive idling!'])
}

def simulate_hazard_states():
    while True:
        # Alternate each hazard randomly every 10 seconds
        for key in hazard_state:
            if random.random() < 0.5:
                hazard_state[key] = next(hazard_cycle[key])
        time.sleep(10)

threading.Thread(target=simulate_hazard_states, daemon=True).start()

@app.route('/safety')
def safety():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Use simulated hazard state
    seatbelt_warning = hazard_state['seatbelt']
    ppe_warning = hazard_state['ppe']
    other_warning = hazard_state['other']
    # --- TIMER STATE ---
    conn = get_db()
    row = conn.execute('SELECT * FROM work_session WHERE operator_id=?', (session['user_id'],)).fetchone()
    conn.close()
    if row:
        login_time = row['login_time']
        working_seconds = row['working_seconds']
        break_seconds = row['break_seconds']
        on_break = bool(row['on_break'])
    else:
        login_time = session.get('login_time')
        working_seconds = 0
        break_seconds = 0
        on_break = False
    return render_template('safety.html', seatbelt_warning=seatbelt_warning, ppe_warning=ppe_warning, other_warning=other_warning, login_time=login_time, working_seconds=working_seconds, break_seconds=break_seconds, on_break=on_break)

# --- INCIDENT LOGGING ---
@app.route('/incident', methods=['GET', 'POST'])
def incident():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    # --- TIMER STATE ---
    row = conn.execute('SELECT * FROM work_session WHERE operator_id=?', (session['user_id'],)).fetchone()
    if row:
        login_time = row['login_time']
        working_seconds = row['working_seconds']
        break_seconds = row['break_seconds']
        on_break = bool(row['on_break'])
    else:
        login_time = session.get('login_time')
        working_seconds = 0
        break_seconds = 0
        on_break = False
    if request.method == 'POST':
        desc = request.form['desc']
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('INSERT INTO incident (operator_id, desc, timestamp) VALUES (?, ?, ?)', (session['user_id'], desc, now))
        conn.commit()
        flash('Incident logged!')
        return redirect(url_for('incident'))
    incidents = conn.execute('SELECT * FROM incident ORDER BY id DESC LIMIT 20').fetchall()
    conn.close()
    return render_template('incident.html', incidents=incidents, login_time=login_time, working_seconds=working_seconds, break_seconds=break_seconds, on_break=on_break)

# --- TRAINING HUB ---
@app.route('/training', methods=['GET', 'POST'])
def training():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    # --- TIMER STATE ---
    row = conn.execute('SELECT * FROM work_session WHERE operator_id=?', (session['user_id'],)).fetchone()
    if row:
        login_time = row['login_time']
        working_seconds = row['working_seconds']
        break_seconds = row['break_seconds']
        on_break = bool(row['on_break'])
    else:
        login_time = session.get('login_time')
        working_seconds = 0
        break_seconds = 0
        on_break = False
    result = None
    if request.method == 'POST':
        choice = request.form['choice']
        if choice == '1':
            result = "Playing e-learning video... (simulated)"
        elif choice == '2':
            result = "Instructor session booked for tomorrow at 10:00 AM."
        elif choice == '3':
            result = "Launching simulation module... (simulated)"
        else:
            result = "Invalid choice."
    videos = [
        { 'title': 'Basic Machine Operation', 'url': 'https://www.youtube.com/embed/1Q8fG0TtVAY', 'level': 'Beginner', 'importance': 'High' },
        { 'title': 'Advanced Excavator Controls', 'url': 'https://www.youtube.com/embed/2Xc9gXyf2G4', 'level': 'Advanced', 'importance': 'Medium' },
        { 'title': 'Safety Protocols', 'url': 'https://www.youtube.com/embed/3fumBcKC6RE', 'level': 'Intermediate', 'importance': 'Critical' },
        { 'title': 'Fuel Efficiency Tips', 'url': 'https://www.youtube.com/embed/4WJLlWpzpP0', 'level': 'Beginner', 'importance': 'Medium' },
        { 'title': 'Maintenance Checklist', 'url': 'https://www.youtube.com/embed/5MgBikgcWnY', 'level': 'Intermediate', 'importance': 'High' },
        { 'title': 'Emergency Procedures', 'url': 'https://www.youtube.com/embed/6ZfuNTqbHE8', 'level': 'Advanced', 'importance': 'Critical' }
    ]
    conn.close()
    return render_template('training.html', result=result, videos=videos, login_time=login_time, working_seconds=working_seconds, break_seconds=break_seconds, on_break=on_break)

# --- MACHINE BEHAVIOR ---
@app.route('/behavior')
def behavior():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    # --- TIMER STATE ---
    row = conn.execute('SELECT * FROM work_session WHERE operator_id=?', (session['user_id'],)).fetchone()
    if row:
        login_time = row['login_time']
        working_seconds = row['working_seconds']
        break_seconds = row['break_seconds']
        on_break = bool(row['on_break'])
    else:
        login_time = session.get('login_time')
        working_seconds = 0
        break_seconds = 0
        on_break = False
    logs = conn.execute('SELECT * FROM machine_log').fetchall()
    warnings = []
    for log in logs:
        if log["idling_time"] > 45:
            warnings.append(f"Warning: Excessive idling detected on {log['date']} (Idling: {log['idling_time']} min)")
        if log["seatbelt_status"] == "Unfastened" and log["safety_alert"] == "Yes":
            warnings.append(f"Unsafe operation: Seatbelt unfastened and safety alert triggered on {log['date']}")
    conn.close()
    return render_template('behavior.html', warnings=warnings, login_time=login_time, working_seconds=working_seconds, break_seconds=break_seconds, on_break=on_break)

# --- TASK TIME ESTIMATION ---
@app.route('/estimate', methods=['GET', 'POST'])
def estimate():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    # --- TIMER STATE ---
    row = conn.execute('SELECT * FROM work_session WHERE operator_id=?', (session['user_id'],)).fetchone()
    if row:
        login_time = row['login_time']
        working_seconds = row['working_seconds']
        break_seconds = row['break_seconds']
        on_break = bool(row['on_break'])
    else:
        login_time = session.get('login_time')
        working_seconds = 0
        break_seconds = 0
        on_break = False
    estimate_result = None
    if request.method == 'POST':
        task = request.form['task']
        base_time = random.randint(30, 90)
        weather_factor = random.choice([0.9, 1.0, 1.1])
        estimated_time = int(base_time * weather_factor)
        estimate_result = f"Estimated time to complete '{task}': {estimated_time} minutes (based on past data and conditions)"
    conn.close()
    return render_template('estimate.html', estimate=estimate_result, login_time=login_time, working_seconds=working_seconds, break_seconds=break_seconds, on_break=on_break)

def get_machine_logs():
    conn = get_db()
    logs = conn.execute('SELECT * FROM machine_log').fetchall()
    conn.close()
    return logs

# --- REAL-TIME INCIDENT SIMULATION ---
def simulate_and_log_incidents():
    while True:
        # Check for any active task
        conn = get_db()
        active_task = conn.execute('SELECT * FROM task WHERE status=?', ("in_progress",)).fetchone()
        conn.close()
        if active_task:
            operator_id = active_task[1]
            # Simulate a random safety violation (seatbelt or PPE removal)
            violation = random.choice([
                ("Seatbelt removed during operation", "seatbelt"),
                ("PPE removed during operation", "ppe"),
                (None, None),  # No violation
            ])
            desc, vtype = violation
            if desc:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn = get_db()
                conn.execute('INSERT INTO incident (operator_id, desc, timestamp) VALUES (?, ?, ?)', (operator_id, desc, now))
                conn.commit()
                conn.close()
        logs = get_machine_logs()
        if not logs:
            time.sleep(10)
            continue
        log = random.choice(logs)
        danger = False
        desc = None
        if log["idling_time"] > 45:
            danger = True
            desc = f"Excessive idling detected on {log['date']} (Idling: {log['idling_time']} min)"
        if log["seatbelt_status"] == "Unfastened" and log["safety_alert"] == "Yes":
            danger = True
            desc = f"Unsafe operation: Seatbelt unfastened and safety alert triggered on {log['date']}"
        if danger and desc:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = get_db()
            conn.execute('INSERT INTO incident (desc, timestamp) VALUES (?, ?)', (desc, now))
            conn.commit()
            conn.close()
        time.sleep(10)  # Simulate real-time interval

# Start background thread for real-time incident logging
threading.Thread(target=simulate_and_log_incidents, daemon=True).start()

@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    # Returns all tasks and their progress for all operators
    conn = get_db()
    tasks = conn.execute('SELECT * FROM task').fetchall()
    conn.close()
    return {
        "tasks": [
            {
                "id": t["id"],
                "operator_id": t["operator_id"],
                "description": t["description"],
                "scheduled_time": t["scheduled_time"],
                "status": t["status"],
                "progress": t["progress"],
                "started_at": t["started_at"],
                "completed_at": t["completed_at"]
            } for t in tasks
        ]
    }

@app.route('/api/task/<int:task_id>/progress', methods=['POST'])
def api_update_task_progress(task_id):
    data = request.get_json()
    progress = int(data.get('progress', 0))
    conn = get_db()
    conn.execute('UPDATE task SET progress=? WHERE id=?', (progress, task_id))
    conn.commit()
    conn.close()
    return {"success": True, "task_id": task_id, "progress": progress}

@app.route('/api/incidents')
def api_get_incidents():
    conn = get_db()
    # Only show incidents if a task is in progress
    active_task = conn.execute('SELECT * FROM task WHERE status=?', ("in_progress",)).fetchone()
    if not active_task:
        conn.close()
        return {"incidents": []}
    incidents = conn.execute('SELECT * FROM incident ORDER BY id DESC LIMIT 20').fetchall()
    conn.close()
    return {"incidents": [
        {"timestamp": i["timestamp"], "desc": i["desc"]} for i in incidents
    ]}

@app.route('/safety-check', methods=['GET', 'POST'])
def safety_carousel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    task_id = request.args.get('task_id')
    if request.method == 'POST':
        # Log the safety check completion
        operator_id = session['user_id']
        machine_id = 'EXC001'  # You can make this dynamic if needed
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db()
        conn.execute('INSERT INTO incident (operator_id, desc, timestamp) VALUES (?, ?, ?)',
                     (operator_id, f"Safety checklist completed for machine {machine_id}", now))
        # If task_id is present, start the task after checklist
        if task_id:
            conn.execute('UPDATE task SET status=?, started_at=? WHERE id=?', ("in_progress", now, task_id))
        conn.commit()
        conn.close()
        return '<script>window.parent.location.reload();</script>'
    return render_template('safety_carousel.html', task_id=task_id)

@app.route('/start_session', methods=['POST'])
def start_session():
    if 'user_id' not in session:
        return {'success': False, 'error': 'Not logged in'}, 401
    conn = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # End any previous session for this user
    conn.execute('DELETE FROM work_session WHERE operator_id=?', (session['user_id'],))
    conn.execute('INSERT INTO work_session (operator_id, login_time, last_update) VALUES (?, ?, ?)', (session['user_id'], now, now))
    conn.commit()
    conn.close()
    return {'success': True, 'login_time': now}

@app.route('/update_session', methods=['POST'])
def update_session():
    if 'user_id' not in session:
        return {'success': False, 'error': 'Not logged in'}, 401
    data = request.get_json()
    working_seconds = data.get('working_seconds', 0)
    break_seconds = data.get('break_seconds', 0)
    on_break = 1 if data.get('on_break', False) else 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[DEBUG] Saving session for user {session['user_id']}: working_seconds={working_seconds}, break_seconds={break_seconds}, on_break={on_break}")
    conn = get_db()
    conn.execute('UPDATE work_session SET working_seconds=?, break_seconds=?, on_break=?, last_update=? WHERE operator_id=?',
                 (working_seconds, break_seconds, on_break, now, session['user_id']))
    conn.commit()
    conn.close()
    return {'success': True}

@app.route('/get_session', methods=['GET'])
def get_session():
    if 'user_id' not in session:
        return {'success': False, 'error': 'Not logged in'}, 401
    conn = get_db()
    row = conn.execute('SELECT * FROM work_session WHERE operator_id=?', (session['user_id'],)).fetchone()
    conn.close()
    if not row:
        return {'success': False, 'error': 'No session'}, 404
    return {
        'success': True,
        'login_time': row['login_time'],
        'working_seconds': row['working_seconds'],
        'break_seconds': row['break_seconds'],
        'on_break': bool(row['on_break'])
    }

# --- DETECT OBJECT ---
@app.route('/detect', methods=['POST'])
def detect():
    data = request.json['image']
    image_bytes = base64.b64decode(data.split(',')[1])
    np_arr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    results = model.predict(source=frame, imgsz=640, conf=0.5, verbose=False)

    alerts = []
    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            class_name = model.names[cls]

            if class_name not in allowed_classes:
                continue

            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            bbox_width = x2 - x1
            bbox_ratio = bbox_width / frame.shape[1]

            label = f"{class_name} {conf:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            if bbox_ratio > 0.5:
                alert_message = f"Alert! {class_name} very near!"
                alerts.append(alert_message)

    _, buffer = cv2.imencode('.jpg', frame)
    frame_base64 = base64.b64encode(buffer).decode('utf-8')

    return {'alerts': alerts, 'image': f"data:image/jpeg;base64,{frame_base64}"}

@app.route('/simulation.html')
def simulation_html():
    return render_template('simulation.html')

# --- SMS sending using Twilio ---
from twilio.rest import Client
TWILIO_ACCOUNT_SID = 'YOUR_TWILIO_ACCOUNT_SID'
TWILIO_AUTH_TOKEN = 'YOUR_TWILIO_AUTH_TOKEN'
TWILIO_FROM_NUMBER = 'YOUR_TWILIO_PHONE_NUMBER'

def send_sms(phone, message):
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=phone
        )
        print(f"[SMS SENT to {phone}]: {message}")
    except Exception as e:
        print(f"[SMS ERROR]: {e}")

# --- Background scheduler for SMS reminders ---
def schedule_sms(phone, message, send_time):
    def worker():
        now = datetime.now()
        delay = (send_time - now).total_seconds()
        if delay > 0:
            time.sleep(delay)
        send_sms(phone, message)
    threading.Thread(target=worker, daemon=True).start()

@app.route('/api/book_course', methods=['POST'])
def api_book_course():
    data = request.get_json()
    bookings_db.append(data)
    mentor_time = data.get('time')
    user_phone = data.get('user', {}).get('phone')
    mentor_name = data.get('name')
    course = data.get('course')
    if mentor_time and user_phone:
        course_dt = datetime.fromisoformat(mentor_time)
        sms_time = course_dt - timedelta(hours=1)
        msg = f"Reminder: Your course '{course}' with {mentor_name} starts at {course_dt.strftime('%Y-%m-%d %H:%M')}."
        schedule_sms(user_phone, msg, sms_time)
    return jsonify({'status': 'ok'})

@app.route('/api/booked_mentors', methods=['GET', 'POST'])
def api_booked_mentors():
    conn = get_db()
    if request.method == 'POST':
        data = request.get_json()
        booked = data.get('booked', [])
        # Clear and re-insert for demo; in production, use proper upsert
        conn.execute('DELETE FROM mentor_booking')
        for b in booked:
            user = b.get('user', {})
            conn.execute('''INSERT INTO mentor_booking (mentor_id, mentor_name, course, time, mentor_phone, user_name, user_phone, user_email, user_company) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (b.get('id'), b.get('name'), b.get('course'), b.get('time'), b.get('phone'), user.get('name'), user.get('phone'), user.get('email'), user.get('company')))
        conn.commit()
        conn.close()
        return jsonify({'status': 'ok'})
    # GET: return all booked mentors
    rows = conn.execute('SELECT * FROM mentor_booking').fetchall()
    conn.close()
    booked = []
    for r in rows:
        booked.append({
            'id': r['mentor_id'],
            'name': r['mentor_name'],
            'course': r['course'],
            'time': r['time'],
            'phone': r['mentor_phone'],
            'user': {
                'name': r['user_name'],
                'phone': r['user_phone'],
                'email': r['user_email'],
                'company': r['user_company']
            }
        })
    return jsonify({'booked': booked})

@app.route('/api/my_tasks')
def api_my_tasks():
    print('[DEBUG] /api/my_tasks session:', dict(session))
    if 'user_id' not in session:
        print('[DEBUG] /api/my_tasks: user_id not in session!')
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    conn = get_db()
    tasks = conn.execute('''SELECT t.*, m.machine_id as machine_code, m.model as machine_model FROM task t LEFT JOIN machine m ON t.machine_id = m.id WHERE t.operator_id=? ORDER BY t.scheduled_time''', (session['user_id'],)).fetchall()
    conn.close()
    print(f'[DEBUG] /api/my_tasks: returning {len(tasks)} tasks for user_id', session['user_id'])
    return jsonify({
        'success': True,
        'tasks': [
            {
                'id': t['id'],
                'scheduled_time': t['scheduled_time'],
                'description': t['description'],
                'machine_code': t['machine_code'],
                'machine_model': t['machine_model'],
                'status': t['status'],
                'progress': t['progress']
            } for t in tasks
        ]
    })

if __name__ == '__main__':
    app.run(debug=True)
