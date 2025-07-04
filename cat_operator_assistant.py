import datetime
import random
import sys
import threading
import time
import sqlite3
import os

DATABASE = 'cat_operator_logs.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS incident (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            desc TEXT,
            timestamp TEXT
        )''')
        conn.commit()
        conn.close()

init_db()

# Sample data for simulation
machine_ids = ["EXC001", "EXC002", "LD001"]
operator_ids = ["OP1001", "OP1002"]

def generate_synthetic_log():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log = {
        "date": now,
        "machine_id": random.choice(machine_ids),
        "operator_id": random.choice(operator_ids),
        "engine_hours": round(random.uniform(1500, 1600), 1),
        "fuel_used": round(random.uniform(2, 10), 1),
        "lead_cycles": random.randint(1, 60),
        "idling_time": random.randint(5, 70),
        "seatbelt_status": random.choice(["Fastened", "Unfastened"]),
        "safety_alert": random.choice(["No", "Yes"])
    }
    return log

def simulate_and_log_incidents():
    while True:
        log = generate_synthetic_log()
        danger = False
        desc = None
        if log["idling_time"] > 45:
            danger = True
            desc = f"Excessive idling detected on {log['date']} (Idling: {log['idling_time']} min)"
        if log["seatbelt_status"] == "Unfastened" and log["safety_alert"] == "Yes":
            danger = True
            desc = f"Unsafe operation: Seatbelt unfastened and safety alert triggered on {log['date']}"
        if danger and desc:
            conn = get_db()
            conn.execute('INSERT INTO incident (desc, timestamp) VALUES (?, ?)', (desc, log["date"]))
            conn.commit()
            conn.close()
        time.sleep(60)  # Log every minute

# Start background thread for real-time incident logging
t = threading.Thread(target=simulate_and_log_incidents, daemon=True)
t.start()

# Sample data
machine_logs = [
    {
        "date": "2025-05-01",
        "machine_id": "EXC001",
        "operator_id": "OP1001",
        "engine_hours": 1523.5,
        "fuel_used": 5.2,
        "lead_cycles": 12,
        "idling_time": 30,
        "seatbelt_status": "Fastened",
        "safety_alert": "No"
    },
    {
        "date": "2025-05-01",
        "machine_id": "EXC001",
        "operator_id": "OP1001",
        "engine_hours": 1524.8,
        "fuel_used": 3.8,
        "lead_cycles": 2,
        "idling_time": 55,
        "seatbelt_status": "Unfastened",
        "safety_alert": "Yes"
    },
    {
        "date": "2025-05-01 14:00:00",
        "machine_id": "EXC001",
        "operator_id": "OP1001",
        "engine_hours": 1526.5,
        "fuel_used": 6.1,
        "lead_cycles": 10,
        "idling_time": 15,
        "seatbelt_status": "Fastened",
        "safety_alert": "No"
    },
    {
        "date": "2025-05-02",
        "machine_id": "EXC001",
        "operator_id": "OP1001",
        "engine_hours": 1530.2,
        "fuel_used": 2,
        "lead_cycles": 60,
        "idling_time": 60,
        "seatbelt_status": "Unfastened",
        "safety_alert": "Yes"
    }
]

daily_tasks = [
    {"task": "Excavate trench at site A", "scheduled_time": "08:00"},
    {"task": "Load gravel at site B", "scheduled_time": "11:00"},
    {"task": "Refuel and maintenance", "scheduled_time": "15:00"}
]

def show_dashboard():
    print("\n--- Daily Task Dashboard ---")
    for t in daily_tasks:
        print(f"{t['scheduled_time']}: {t['task']}")

def show_safety_features():
    print("\n--- Safety Features ---")
    for log in machine_logs:
        print(f"Date: {log['date']}, Machine: {log['machine_id']}, Seatbelt: {log['seatbelt_status']}, Proximity Hazard: {log['safety_alert']}")

def show_incident_logs():
    print("\n--- Automatic Incident Logs (Dangerous Only) ---")
    conn = get_db()
    logs = conn.execute('SELECT * FROM incident ORDER BY id DESC LIMIT 10').fetchall()
    for log in logs:
        print(f"{log['timestamp']}: {log['desc']}")
    conn.close()

def training_hub():
    print("\n--- Operator Training Hub ---")
    print("1. Watch e-learning video")
    print("2. Book instructor session")
    print("3. Try simulation module")
    choice = input("Choose an option: ")
    if choice == "1":
        print("Playing e-learning video... (simulated)")
    elif choice == "2":
        print("Instructor session booked for tomorrow at 10:00 AM.")
    elif choice == "3":
        print("Launching simulation module... (simulated)")
    else:
        print("Invalid choice.")

def detect_unusual_behavior():
    print("\n--- Machine Behavior Analysis ---")
    for log in machine_logs:
        if log["idling_time"] > 45:
            print(f"Warning: Excessive idling detected on {log['date']} (Idling: {log['idling_time']} min)")
        if log["seatbelt_status"] == "Unfastened" and log["safety_alert"] == "Yes":
            print(f"Unsafe operation: Seatbelt unfastened and safety alert triggered on {log['date']}")

def estimate_task_time():
    print("\n--- Task Time Estimation ---")
    task = input("Enter task description: ")
    # Simulate estimation based on past data
    base_time = random.randint(30, 90)
    weather_factor = random.choice([0.9, 1.0, 1.1])
    estimated_time = int(base_time * weather_factor)
    print(f"Estimated time to complete '{task}': {estimated_time} minutes (based on past data and conditions)")

def main_menu():
    while True:
        print("\n==== Cat Smart Operator Assistant ====")
        print("1. View Daily Task Dashboard")
        print("2. Safety Features")
        print("3. View Automatic Incident Logs")
        print("4. Operator Training Hub")
        print("5. Analyze Machine Behavior")
        print("6. Estimate Task Completion Time")
        print("0. Exit")
        choice = input("Select an option: ")
        if choice == "1":
            show_dashboard()
        elif choice == "2":
            show_safety_features()
        elif choice == "3":
            show_incident_logs()
        elif choice == "4":
            training_hub()
        elif choice == "5":
            detect_unusual_behavior()
        elif choice == "6":
            estimate_task_time()
        elif choice == "0":
            print("Goodbye!")
            sys.exit()
        else:
            print("Invalid option. Try again.")

if __name__ == "__main__":
    main_menu()
