import sqlite3
import os
import json
import uuid
from datetime import datetime, timedelta

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "data", "qingsong.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Therapists Table (Only specialties, no education)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS therapists (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        title TEXT NOT NULL,
        role_label TEXT NOT NULL,
        avatar TEXT,
        order_num INTEGER DEFAULT 1,
        specialties TEXT,
        education TEXT,
        certifications TEXT,
        is_active INTEGER DEFAULT 1
    );
    """)

    # 2. Clinic Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # 3. Schedule Overrides / Off days
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schedule_overrides (
        id TEXT PRIMARY KEY,
        therapist_id TEXT NOT NULL,
        date TEXT NOT NULL,
        time_slot TEXT,
        is_available INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 4. Patients Table (Stores memory of basic info by line_user_id)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        line_user_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        birthday TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    # 5. Appointments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id TEXT PRIMARY KEY,
        line_user_id TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        patient_phone TEXT NOT NULL,
        patient_birthday TEXT,
        therapist_id TEXT NOT NULL,
        therapist_name TEXT NOT NULL,
        visit_type TEXT NOT NULL,
        has_referral_slip INTEGER DEFAULT 0,
        appointment_date TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'RESERVED',
        patient_note TEXT,
        reminder_sent_at TEXT,
        confirmed_at TEXT,
        cancelled_at TEXT,
        cancel_reason TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 6. Reminder Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reminder_logs (
        id TEXT PRIMARY KEY,
        appointment_id TEXT NOT NULL,
        line_user_id TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        status TEXT NOT NULL,
        flex_payload TEXT
    );
    """)

    conn.commit()

    # Re-seed Therapists (Only specialties, no education)
    cursor.execute("DELETE FROM therapists")
    seed_data(cursor)
    conn.commit()
    conn.close()

def seed_data(cursor):
    # Therapist 1: 劉韋綸 院長 (只留專長，去除學經歷)
    cursor.execute("""
    INSERT INTO therapists (id, name, title, role_label, avatar, order_num, specialties, education, certifications, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "th_liu",
        "劉韋綸",
        "院長",
        "Physical Therapist",
        "/images/therapist_liu.svg",
        1,
        json.dumps([
            "骨骼肌肉徒手物理治療",
            "肌肉動作控制訓練",
            "銀髮族運動訓練",
            "肌筋膜疼痛問題處理",
            "運動傷害防護與修復"
        ], ensure_ascii=False),
        json.dumps([], ensure_ascii=False),  # 去除學經歷
        json.dumps([], ensure_ascii=False),
        1
    ))

    # Therapist 2: 洪嘉良 物理治療師 (只留專長，去除學經歷)
    cursor.execute("""
    INSERT INTO therapists (id, name, title, role_label, avatar, order_num, specialties, education, certifications, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "th_hong",
        "洪嘉良",
        "物理治療師",
        "Physical Therapist",
        "/images/therapist_hong.png",
        2,
        json.dumps([
            "肌肉骨骼物理治療",
            "術後物理治療",
            "肌筋膜沾黏處理",
            "動作控制訓練",
            "姿勢矯正與維持",
            "銀髮族肌力與平衡訓練"
        ], ensure_ascii=False),
        json.dumps([], ensure_ascii=False),  # 去除學經歷
        json.dumps([], ensure_ascii=False),
        1
    ))

    # Default clinic settings (Fixed 8 slots: 09:00, 10:00, 11:00, 15:00, 16:00, 17:00, 19:00, 20:00)
    settings = {
        "clinic_name": "青松物理治療所",
        "clinic_phone": "07-7353353",
        "clinic_address": "高雄市鳥松區華美路69號",
        "clinic_line_id": "@126cxeyj",
        "liff_id": "2012064889-uSjEJVic",
        "booking_window_days": "30",
        "cancel_lead_hours": "24",
        "reminder_lead_hours": "24",
        "default_slots": json.dumps([
            "09:00", "10:00", "11:00",
            "15:00", "16:00", "17:00",
            "19:00", "20:00"
        ])
    }
    for k, v in settings.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Sample Appointments on upcoming Weekdays (Mon-Fri)
    # Find next Monday
    now = datetime.now()
    days_ahead = (0 - now.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    next_monday = now + timedelta(days=days_ahead)
    next_tuesday = next_monday + timedelta(days=1)
    next_wednesday = next_monday + timedelta(days=2)

    sample_appointments = [
        (
            "APT" + next_monday.strftime("%Y%m%d") + "001",
            "U_DEMO_001",
            "陳雅婷",
            "0912-345-678",
            "1992-05-18",
            "th_liu",
            "劉韋綸",
            "FIRST_VISIT",
            1,
            next_monday.strftime("%Y-%m-%d"),
            "10:00",
            "CONFIRMED",
            "肩頸長期痠痛、右手舉起卡卡",
            (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            None,
            None,
            (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        ),
        (
            "APT" + next_monday.strftime("%Y%m%d") + "002",
            "U_DEMO_002",
            "林建宏",
            "0928-112-233",
            "1985-11-04",
            "th_hong",
            "洪嘉良",
            "FOLLOW_UP",
            0,
            next_monday.strftime("%Y-%m-%d"),
            "15:00",
            "PENDING_CONFIRM",
            "右膝前十字韌帶術後第二個月訓練",
            (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            None,
            None,
            None,
            (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        ),
        (
            "APT" + next_tuesday.strftime("%Y%m%d") + "003",
            "U_DEMO_003",
            "張淑芬",
            "0933-789-012",
            "1968-08-22",
            "th_hong",
            "洪嘉良",
            "FITNESS",
            0,
            next_tuesday.strftime("%Y-%m-%d"),
            "11:00",
            "RESERVED",
            "銀髮族肌力訓練與核心維持",
            None,
            None,
            None,
            None,
            (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        ),
        (
            "APT" + next_wednesday.strftime("%Y%m%d") + "004",
            "U_DEMO_004",
            "黃冠宇",
            "0987-654-321",
            "1998-03-15",
            "th_liu",
            "劉韋綸",
            "FIRST_VISIT",
            1,
            next_wednesday.strftime("%Y-%m-%d"),
            "19:00",
            "RESERVED",
            "打羽球腰部拉傷",
            None,
            None,
            None,
            None,
            now.strftime("%Y-%m-%d %H:%M:%S")
        )
    ]

    for apt in sample_appointments:
        cursor.execute("""
        INSERT OR REPLACE INTO appointments (
            id, line_user_id, patient_name, patient_phone, patient_birthday,
            therapist_id, therapist_name, visit_type, has_referral_slip,
            appointment_date, appointment_time, status, patient_note,
            reminder_sent_at, confirmed_at, cancelled_at, cancel_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, apt)

    # Seed Patient memory
    cursor.execute("""
    INSERT OR REPLACE INTO patients (line_user_id, name, phone, birthday, updated_at)
    VALUES (?, ?, ?, ?, ?)
    """, ("U_DEMO_001", "陳雅婷", "0912-345-678", "1992-05-18", now.strftime("%Y-%m-%d %H:%M:%S")))
    cursor.execute("""
    INSERT OR REPLACE INTO patients (line_user_id, name, phone, birthday, updated_at)
    VALUES (?, ?, ?, ?, ?)
    """, ("U_DEMO_002", "林建宏", "0928-112-233", "1985-11-04", now.strftime("%Y-%m-%d %H:%M:%S")))

if __name__ == "__main__":
    init_db()
    print("Database re-initialized with updated slots and therapist specs.")
