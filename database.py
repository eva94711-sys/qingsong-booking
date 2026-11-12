import sqlite3
import os
import json
import ssl
import urllib.parse
from datetime import datetime, timedelta

try:
    import pg8000.dbapi
    HAS_PG8000 = True
except ImportError:
    HAS_PG8000 = False

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "data", "qingsong.db")

DEFAULT_SLOTS = [
    "09:00", "10:00", "11:00",
    "15:00", "16:00", "17:00",
    "19:00", "20:00"
]

_LAST_PG_ERROR = None


class PGCursorWrapper:
    """Wraps a pg8000 DB-API cursor to accept SQLite-style `?` placeholders and return dict rows."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        stripped = sql.strip().upper()
        if stripped == "BEGIN IMMEDIATE":
            self._cursor.execute("LOCK TABLE appointments IN SHARE ROW EXCLUSIVE MODE")
            return self

        pg_sql = sql.replace("?", "%s")
        if params is not None:
            self._cursor.execute(pg_sql, tuple(params))
        else:
            self._cursor.execute(pg_sql)
        return self

    def fetchone(self):
        if not self._cursor.description:
            return None
        row = self._cursor.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in self._cursor.description]
        return dict(zip(cols, row))

    def fetchall(self):
        if not self._cursor.description:
            return []
        cols = [desc[0] for desc in self._cursor.description]
        return [dict(zip(cols, row)) for row in self._cursor.fetchall()]

    def close(self):
        self._cursor.close()


class PGConnectionWrapper:
    """Wraps a pg8000 DB-API connection to match sqlite3 connection usage in server.py."""

    def __init__(self, conn):
        self._conn = conn
        self.is_postgres = True

    def cursor(self):
        return PGCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _parse_pg_params(database_url):
    parsed = urllib.parse.urlparse(database_url)
    query = urllib.parse.parse_qs(parsed.query)
    sslmode = query.get("sslmode", [""])[0].lower()
    host = parsed.hostname or ""

    kwargs = {
        "user": urllib.parse.unquote(parsed.username or ""),
        "password": urllib.parse.unquote(parsed.password or ""),
        "host": host,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
        "timeout": 15,
    }
    if sslmode != "disable":
        kwargs["ssl_context"] = ssl.create_default_context()
    return kwargs


def get_db_info():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        if not HAS_PG8000:
            return {
                "mode": "sqlite",
                "persistent": False,
                "label": "本機暫存 SQLite（缺少 pg8000 套件）",
                "warning": "已設定 DATABASE_URL，但尚未安裝 pg8000 套件。請至 Render Settings 將 Build Command 改為 pip install -r requirements.txt 並重新部署。"
            }
        if _LAST_PG_ERROR:
            return {
                "mode": "sqlite",
                "persistent": False,
                "label": "本機暫存 SQLite（雲端連線失敗）",
                "warning": f"DATABASE_URL 連線失敗，已暫時退回本機模式：{_LAST_PG_ERROR}"
            }
        return {
            "mode": "postgresql",
            "persistent": True,
            "label": "Neon PostgreSQL 雲端資料庫（永久保存）",
            "warning": None
        }

    is_render = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))
    return {
        "mode": "sqlite",
        "persistent": False,
        "label": "本機暫存 SQLite（重啟會清空）" if is_render else "本機 SQLite 資料庫",
        "warning": "目前伺服器使用暫存硬碟，Render 休眠喚醒或更新部署時資料會歸零。請設定免費 Neon 雲端資料庫 (DATABASE_URL) 以永久保存所有預約！" if is_render else "本機測試模式：若部署至 Render 請務必設定 DATABASE_URL 環境變數以永久保存資料。"
    }


def get_connection():
    global _LAST_PG_ERROR
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url and HAS_PG8000:
        try:
            kwargs = _parse_pg_params(database_url)
            pg_conn = pg8000.dbapi.connect(**kwargs)
            _LAST_PG_ERROR = None
            return PGConnectionWrapper(pg_conn)
        except Exception as e:
            _LAST_PG_ERROR = str(e)
            print(f"⚠️ PostgreSQL 連線失敗，退回本機 SQLite: {e}")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Therapists Table
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

    # 3. Schedule Overrides / Off days / Special openings
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

    # 4. Patients Table
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
    seed_data(cursor)
    conn.commit()
    conn.close()


def get_default_weekly_schedule(slots=None):
    base_slots = slots or list(DEFAULT_SLOTS)
    return {
        "0": list(base_slots),  # 週一
        "1": list(base_slots),  # 週二
        "2": list(base_slots),  # 週三
        "3": list(base_slots),  # 週四
        "4": list(base_slots),  # 週五
        "5": [],                # 週六休診
        "6": []                 # 週日休診
    }


def seed_data(cursor):
    # Therapist 1: 劉韋綸 院長
    cursor.execute("""
    INSERT INTO therapists (id, name, title, role_label, avatar, order_num, specialties, education, certifications, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        title = EXCLUDED.title,
        role_label = EXCLUDED.role_label,
        avatar = EXCLUDED.avatar,
        order_num = EXCLUDED.order_num,
        specialties = EXCLUDED.specialties,
        education = EXCLUDED.education,
        certifications = EXCLUDED.certifications,
        is_active = EXCLUDED.is_active
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
        json.dumps([], ensure_ascii=False),
        json.dumps([], ensure_ascii=False),
        1
    ))

    # Therapist 2: 洪嘉良 物理治療師
    cursor.execute("""
    INSERT INTO therapists (id, name, title, role_label, avatar, order_num, specialties, education, certifications, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        title = EXCLUDED.title,
        role_label = EXCLUDED.role_label,
        avatar = EXCLUDED.avatar,
        order_num = EXCLUDED.order_num,
        specialties = EXCLUDED.specialties,
        education = EXCLUDED.education,
        certifications = EXCLUDED.certifications,
        is_active = EXCLUDED.is_active
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
        json.dumps([], ensure_ascii=False),
        json.dumps([], ensure_ascii=False),
        1
    ))

    # Default clinic settings (ON CONFLICT DO NOTHING so admin edits persist!)
    default_weekly = {
        "th_liu": get_default_weekly_schedule(DEFAULT_SLOTS),
        "th_hong": get_default_weekly_schedule(DEFAULT_SLOTS)
    }
    settings = {
        "clinic_name": "青松物理治療所",
        "clinic_phone": "07-7353353",
        "clinic_address": "高雄市鳥松區華美路69號",
        "clinic_line_id": "@557fabgw",
        "liff_id": "2012458374-x8h6v4Dh",
        "booking_window_days": "30",
        "cancel_lead_hours": "24",
        "reminder_lead_hours": "24",
        "default_slots": json.dumps(DEFAULT_SLOTS),
        "weekly_schedules": json.dumps(default_weekly, ensure_ascii=False)
    }
    for k, v in settings.items():
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING",
            (k, v)
        )


if __name__ == "__main__":
    init_db()
    print("Database initialized:", get_db_info())
