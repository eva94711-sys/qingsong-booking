#!/usr/bin/env python3
import http.server
import socketserver
import os
import json
import urllib.parse
import urllib.request
import sqlite3
import uuid
import csv
import io
from datetime import datetime, timedelta
import database

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DEFAULT_LINE_TOKEN = "yp6wkNJuQGfj9VJJwTWxAsZF9+uzK96hfuioq5jxJ8k0uSBhBGsrN8iiNOujlptTeWBbBe0xqDhmVXYbwTVDeo0NFFqQMe23nIvMMMg+UHc7khN6AchbB43a1rsaqTzQEi4S19/7ZGismZ/suDGUrwdB04t89/1O/w1cDnyilFU="

class QingsongRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Route matching
        if path == "/" or path == "/index.html":
            self.serve_file(os.path.join(PUBLIC_DIR, "index.html"), "text/html")
        elif path == "/admin" or path == "/admin.html":
            self.serve_file(os.path.join(PUBLIC_DIR, "admin.html"), "text/html")
        elif path == "/api/therapists":
            self.api_get_therapists()
        elif path == "/api/services":
            self.api_get_services()
        elif path == "/api/settings":
            self.api_get_settings()
        elif path == "/api/patient":
            self.api_get_patient(query)
        elif path == "/api/slots":
            self.api_get_slots(query)
        elif path == "/api/appointments":
            self.api_get_appointments(query)
        elif path == "/api/admin/appointments":
            self.api_admin_get_appointments(query)
        elif path == "/api/admin/stats":
            self.api_admin_get_stats()
        elif path == "/api/admin/export":
            self.api_admin_export_csv(query)
        elif path == "/api/reminders/check-and-send":
            self.api_trigger_reminders({})
        else:
            # Fallback to static file serving
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()

        if path == "/api/appointments":
            self.api_create_appointment(body)
        elif path.startswith("/api/appointments/") and path.endswith("/cancel"):
            apt_id = path.split("/")[3]
            self.api_cancel_appointment(apt_id, body)
        elif path.startswith("/api/appointments/") and path.endswith("/confirm"):
            apt_id = path.split("/")[3]
            self.api_confirm_appointment(apt_id, body)
        elif path.startswith("/api/admin/appointments/") and path.endswith("/status"):
            apt_id = path.split("/")[4]
            self.api_admin_update_status(apt_id, body)
        elif path == "/api/reminders/check-and-send":
            self.api_trigger_reminders(body)
        elif path == "/api/line/webhook":
            self.api_line_webhook(body)
        else:
            self.send_json({"error": "Endpoint not found"}, status=404)

    # --- Helper methods ---
    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            raw_data = self.rfile.read(content_length).decode("utf-8")
            try:
                return json.loads(raw_data)
            except Exception:
                return {}
        return {}

    def send_json(self, data, status=200):
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_bytes)

    def serve_file(self, filepath, content_type):
        if not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        # 停用快取，強制瀏覽器每次都取最新檔案
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(content)

    # --- API Handlers ---
    def api_get_therapists(self):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM therapists WHERE is_active = 1 ORDER BY order_num ASC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "name": r["name"],
                "title": r["title"],
                "role_label": r["role_label"],
                "avatar": r["avatar"],
                "order_num": r["order_num"],
                "specialties": json.loads(r["specialties"]) if r["specialties"] else [],
                "education": json.loads(r["education"]) if r["education"] else [],
                "certifications": json.loads(r["certifications"]) if r["certifications"] else []
            })
        conn.close()
        self.send_json(result)

    def api_get_services(self):
        services = [
            {
                "id": "srv_overall",
                "name": "整體評估治療",
                "duration": "約 40 - 60 分鐘",
                "price": 1500,
                "price_label": "NT$ 1,500 / 次",
                "category": "物理治療",
                "needs_referral": True,
                "description": "全身生物力學全面性檢測評估、骨骼肌肉關節徒手調整、動作控制矯正與個別化居家運動指導。",
                "popular": True
            },
            {
                "id": "srv_local",
                "name": "局部評估治療",
                "duration": "約 20 - 30 分鐘",
                "price": 800,
                "price_label": "NT$ 600 - 800 / 次",
                "category": "物理治療",
                "needs_referral": True,
                "description": "針對單一關節或局部特定肌群（如落枕、腳踝扭傷、手腕媽媽手）之局部疼痛緩解與徒手處置。",
                "popular": False
            },
            {
                "id": "srv_director",
                "name": "院長指定特別治療",
                "duration": "約 50 - 60 分鐘",
                "price": 2000,
                "price_label": "NT$ 2,000 / 次",
                "category": "指定門診",
                "needs_referral": True,
                "description": "由劉韋綸所長親自整體評估，深度探究頑固性疼痛成因，結合呼吸整合、進階肌筋膜與動作鏈重塑。",
                "popular": False
            },
            {
                "id": "srv_shockwave",
                "name": "高端體外震波治療",
                "duration": "約 15 - 20 分鐘",
                "price": 1000,
                "price_label": "NT$ 1,000 / 1,500發",
                "category": "儀器輔助",
                "needs_referral": True,
                "description": "利用非侵入性震波直達深層組織，促進微血管新生與修復，適用於足底筋膜炎、五十肩、網球肘、鈣化性肌腱炎。",
                "popular": False
            },
            {
                "id": "srv_fitness",
                "name": "銀髮族肌力與體適能指導",
                "duration": "約 50 - 60 分鐘",
                "price": 3000,
                "price_label": "NT$ 3,000 / 次",
                "category": "健康促進",
                "needs_referral": False,
                "description": "依物理治療法規免照會單。針對長輩與特殊族群設計防跌倒平衡訓練、核心強化與高齡功能性體適能。",
                "popular": False
            }
        ]
        self.send_json(services)

    def api_get_settings(self):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings")
        rows = cursor.fetchall()
        settings = {r["key"]: r["value"] for r in rows}
        if "default_slots" in settings:
            try:
                settings["default_slots"] = json.loads(settings["default_slots"])
            except Exception:
                pass
        conn.close()
        self.send_json(settings)

    def api_get_patient(self, query):
        line_user_id = query.get("line_user_id", [""])[0]
        if not line_user_id:
            self.send_json({"found": False})
            return
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE line_user_id = ?", (line_user_id,))
        patient = cursor.fetchone()
        conn.close()
        if patient:
            self.send_json({
                "found": True,
                "patient": {
                    "line_user_id": patient["line_user_id"],
                    "name": patient["name"],
                    "phone": patient["phone"],
                    "birthday": patient["birthday"]
                }
            })
        else:
            self.send_json({"found": False})

    def api_get_slots(self, query):
        target_date = query.get("date", [""])[0]
        therapist_id = query.get("therapist_id", ["any"])[0]

        if not target_date:
            self.send_json({"error": "Date parameter is required"}, status=400)
            return

        # Parse date and check weekday (Saturday=5, Sunday=6 are closed)
        try:
            date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            self.send_json({"error": "Invalid date format"}, status=400)
            return

        if date_obj.weekday() in (5, 6):  # Saturday and Sunday closed
            self.send_json({
                "date": target_date,
                "is_closed": True,
                "reason": "週六、週日為固定休診日（僅週一至週五開放預約）",
                "slots": []
            })
            return

        conn = database.get_connection()
        cursor = conn.cursor()

        # Get all active therapists
        cursor.execute("SELECT id, name FROM therapists WHERE is_active = 1")
        all_therapists = cursor.fetchall()
        total_therapist_count = len(all_therapists)

        # Standard slots (8 slots: 09:00, 10:00, 11:00, 15:00, 16:00, 17:00, 19:00, 20:00)
        standard_slots = [
            "09:00", "10:00", "11:00",
            "15:00", "16:00", "17:00",
            "19:00", "20:00"
        ]

        # Query booked appointments for that date (status not CANCELLED)
        if therapist_id and therapist_id != "any":
            # 指定特定治療師：只要該治療師被預約就算額滿
            cursor.execute("""
                SELECT appointment_time 
                FROM appointments 
                WHERE appointment_date = ? AND therapist_id = ? AND status != 'CANCELLED'
            """, (target_date, therapist_id))
            booked_times = {row["appointment_time"] for row in cursor.fetchall()}
        else:
            # 不指定治療師：若所有治療師皆被約滿才算額滿（或只要有空檔即可）
            cursor.execute("""
                SELECT appointment_time, COUNT(DISTINCT therapist_id) as count 
                FROM appointments 
                WHERE appointment_date = ? AND status != 'CANCELLED'
                GROUP BY appointment_time
            """, (target_date,))
            booked_rows = cursor.fetchall()
            booked_times = {row["appointment_time"] for row in booked_rows if row["count"] >= total_therapist_count}

        # Build response slots
        slots_result = []
        for slot in standard_slots:
            is_available = slot not in booked_times
            slots_result.append({
                "time": slot,
                "available": is_available,
                "remaining_capacity": 0 if not is_available else 1
            })

        conn.close()
        self.send_json({
            "date": target_date,
            "is_closed": False,
            "therapist_id": therapist_id,
            "slots": slots_result
        })

    def api_create_appointment(self, body):
        line_user_id = body.get("line_user_id", "").strip() or f"U_GUEST_{uuid.uuid4().hex[:8]}"
        patient_name = body.get("patient_name", "").strip()
        patient_phone = body.get("patient_phone", "").strip()
        patient_birthday = body.get("patient_birthday", "").strip()
        therapist_id = body.get("therapist_id", "any").strip()
        visit_type = body.get("visit_type", "FIRST_VISIT").strip()
        has_referral_slip = 1 if body.get("has_referral_slip") else 0
        appointment_date = body.get("appointment_date", "").strip()
        appointment_time = body.get("appointment_time", "").strip()
        patient_note = body.get("patient_note", "").strip()

        if not patient_name or not patient_phone or not appointment_date or not appointment_time:
            self.send_json({"error": "請完整填寫姓名、電話、預約日期與時段"}, status=400)
            return

        # 法規硬性檢查：初診必須有照會單方可看診
        if visit_type == "FIRST_VISIT" and not has_referral_slip:
            self.send_json({"error": "依物理治療法規規定，初診病患必須持有醫師照會單或轉診單方可預約看診。"}, status=400)
            return

        conn = database.get_connection()
        cursor = conn.cursor()

        try:
            # Conflict prevention inside transaction
            cursor.execute("BEGIN IMMEDIATE")

            # Resolve therapist if "any"
            cursor.execute("SELECT id, name FROM therapists WHERE is_active = 1 ORDER BY order_num ASC")
            all_therapists = cursor.fetchall()
            assigned_therapist_id = None
            assigned_therapist_name = None

            if therapist_id != "any":
                # Check if chosen therapist is booked
                cursor.execute("""
                    SELECT id FROM appointments 
                    WHERE appointment_date = ? AND appointment_time = ? AND therapist_id = ? AND status != 'CANCELLED'
                """, (appointment_date, appointment_time, therapist_id))
                if cursor.fetchone():
                    conn.rollback()
                    self.send_json({"error": "很抱歉，該治療師此時段剛被他人預約，請選擇其他時段"}, status=409)
                    return
                for t in all_therapists:
                    if t["id"] == therapist_id:
                        assigned_therapist_id = t["id"]
                        assigned_therapist_name = t["name"]
                        break
            else:
                # 不指定治療師：自動指派該時段空閒的治療師
                cursor.execute("""
                    SELECT therapist_id FROM appointments 
                    WHERE appointment_date = ? AND appointment_time = ? AND status != 'CANCELLED'
                """, (appointment_date, appointment_time))
                busy_ids = {r["therapist_id"] for r in cursor.fetchall()}
                for t in all_therapists:
                    if t["id"] not in busy_ids:
                        assigned_therapist_id = t["id"]
                        assigned_therapist_name = t["name"]
                        break

                if not assigned_therapist_id:
                    conn.rollback()
                    self.send_json({"error": "很抱歉，該時段所有治療師已全數額滿，請選擇其他時段"}, status=409)
                    return

            apt_id = "APT" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4].upper()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO appointments (
                    id, line_user_id, patient_name, patient_phone, patient_birthday,
                    therapist_id, therapist_name, visit_type, has_referral_slip,
                    appointment_date, appointment_time, status, patient_note,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RESERVED', ?, ?)
            """, (
                apt_id, line_user_id, patient_name, patient_phone, patient_birthday,
                assigned_therapist_id, assigned_therapist_name, visit_type, has_referral_slip,
                appointment_date, appointment_time, patient_note, now_str
            ))

            # Remember patient details
            cursor.execute("""
                INSERT OR REPLACE INTO patients (line_user_id, name, phone, birthday, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (line_user_id, patient_name, patient_phone, patient_birthday, now_str))

            conn.commit()

            # Generate Flex Message payload
            flex_receipt = self.generate_flex_receipt(apt_id, patient_name, assigned_therapist_name, appointment_date, appointment_time, visit_type, has_referral_slip)

            # Push instant receipt to patient's LINE chat
            if line_user_id and not line_user_id.startswith("U_GUEST_"):
                self.send_line_push_flex(line_user_id, "【青松物理治療所】預約掛號成功憑證", flex_receipt)

            self.send_json({
                "success": True,
                "appointment_id": apt_id,
                "therapist_name": assigned_therapist_name,
                "appointment_date": appointment_date,
                "appointment_time": appointment_time,
                "flex_receipt": flex_receipt
            })

        except Exception as e:
            conn.rollback()
            self.send_json({"error": f"預約失敗: {str(e)}"}, status=500)
        finally:
            conn.close()

    def api_get_appointments(self, query):
        line_user_id = query.get("line_user_id", [""])[0]
        if not line_user_id:
            self.send_json([])
            return

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM appointments 
            WHERE line_user_id = ? 
            ORDER BY appointment_date DESC, appointment_time DESC
        """, (line_user_id,))
        rows = cursor.fetchall()
        result = [dict(r) for r in rows]
        conn.close()
        self.send_json(result)

    def api_cancel_appointment(self, apt_id, body):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appointments WHERE id = ?", (apt_id,))
        apt = cursor.fetchone()
        if not apt:
            conn.close()
            self.send_json({"error": "找不到此筆預約"}, status=404)
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reason = body.get("reason", "病患主動線上取消")

        cursor.execute("""
            UPDATE appointments 
            SET status = 'CANCELLED', cancelled_at = ?, cancel_reason = ? 
            WHERE id = ?
        """, (now_str, reason, apt_id))
        conn.commit()
        conn.close()

        self.send_json({
            "success": True,
            "message": "預約已成功取消，該時段已釋出",
            "appointment_id": apt_id
        })

    def api_confirm_appointment(self, apt_id, body):
        conn = database.get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE appointments 
            SET status = 'CONFIRMED', confirmed_at = ? 
            WHERE id = ? AND status != 'CANCELLED'
        """, (now_str, apt_id))
        conn.commit()
        conn.close()

        self.send_json({
            "success": True,
            "message": "已確認明天準時出席，青松物理治療所期待為您服務！"
        })

    def api_admin_get_appointments(self, query):
        target_date = query.get("date", [""])[0]
        therapist_id = query.get("therapist_id", [""])[0]
        status = query.get("status", [""])[0]

        sql = "SELECT * FROM appointments WHERE 1=1"
        params = []
        if target_date:
            sql += " AND appointment_date = ?"
            params.append(target_date)
        if therapist_id and therapist_id != "all":
            sql += " AND therapist_id = ?"
            params.append(therapist_id)
        if status and status != "all":
            sql += " AND status = ?"
            params.append(status)

        sql += " ORDER BY appointment_date ASC, appointment_time ASC"

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        result = [dict(r) for r in rows]
        conn.close()
        self.send_json(result)

    def api_admin_get_stats(self):
        conn = database.get_connection()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        cursor.execute("SELECT COUNT(*) as total FROM appointments WHERE status != 'CANCELLED'")
        total = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as today_count FROM appointments WHERE appointment_date = ? AND status != 'CANCELLED'", (today,))
        today_count = cursor.fetchone()["today_count"]

        cursor.execute("SELECT COUNT(*) as tomorrow_pending FROM appointments WHERE appointment_date = ? AND status = 'PENDING_CONFIRM'", (tomorrow,))
        tomorrow_pending = cursor.fetchone()["tomorrow_pending"]

        cursor.execute("SELECT COUNT(*) as confirmed FROM appointments WHERE status = 'CONFIRMED'")
        confirmed = cursor.fetchone()["confirmed"]

        cursor.execute("SELECT COUNT(*) as cancelled FROM appointments WHERE status = 'CANCELLED'")
        cancelled = cursor.fetchone()["cancelled"]

        conn.close()
        self.send_json({
            "total_active": total,
            "today_count": today_count,
            "tomorrow_pending": tomorrow_pending,
            "confirmed_count": confirmed,
            "cancelled_count": cancelled
        })

    def api_admin_update_status(self, apt_id, body):
        new_status = body.get("status")
        note = body.get("note")

        if not new_status:
            self.send_json({"error": "Missing status"}, status=400)
            return

        conn = database.get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if new_status == "CONFIRMED":
            cursor.execute("UPDATE appointments SET status = ?, confirmed_at = ? WHERE id = ?", (new_status, now_str, apt_id))
        elif new_status == "CANCELLED":
            cursor.execute("UPDATE appointments SET status = ?, cancelled_at = ? WHERE id = ?", (new_status, now_str, apt_id))
        else:
            cursor.execute("UPDATE appointments SET status = ? WHERE id = ?", (new_status, apt_id))

        if note is not None:
            cursor.execute("UPDATE appointments SET patient_note = ? WHERE id = ?", (note, apt_id))

        conn.commit()
        conn.close()
        self.send_json({"success": True, "updated_id": apt_id, "status": new_status})

    def api_admin_export_csv(self, query):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, appointment_date, appointment_time, therapist_name, 
                   patient_name, patient_phone, patient_birthday, visit_type,
                   has_referral_slip, status, patient_note, created_at
            FROM appointments
            ORDER BY appointment_date DESC, appointment_time DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "預約編號", "看診日期", "時段", "物理治療師",
            "病患姓名", "聯絡電話", "生日", "就診類型",
            "照會轉診單", "出席狀態", "備註說明", "掛號時間"
        ])
        for r in rows:
            type_label = "初診" if r["visit_type"] == "FIRST_VISIT" else ("肌力訓練" if r["visit_type"] == "FITNESS" else "複診")
            slip_label = "有" if r["has_referral_slip"] else "無"
            status_map = {
                "RESERVED": "已預約(待排程)",
                "PENDING_CONFIRM": "待確認(已發送24H提醒)",
                "CONFIRMED": "已確認出席",
                "CANCELLED": "已取消",
                "COMPLETED": "已完診"
            }
            writer.writerow([
                r["id"], r["appointment_date"], r["appointment_time"], r["therapist_name"],
                r["patient_name"], r["patient_phone"], r["patient_birthday"], type_label,
                slip_label, status_map.get(r["status"], r["status"]), r["patient_note"], r["created_at"]
            ])

        csv_bytes = output.getvalue().encode("utf-8-sig")  # utf-8-sig for Excel compatibility
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename=qingsong_appointments_{datetime.now().strftime('%Y%m%d')}.csv")
        self.send_header("Content-Length", str(len(csv_bytes)))
        self.end_headers()
        self.wfile.write(csv_bytes)

    def get_line_token(self):
        return os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", DEFAULT_LINE_TOKEN)

    def send_line_push_flex(self, to_user_id, alt_text, flex_content):
        token = self.get_line_token()
        if not token or not to_user_id or to_user_id.startswith("U_GUEST_"):
            return False
        try:
            url = "https://api.line.me/v2/bot/message/push"
            payload = json.dumps({
                "to": to_user_id,
                "messages": [{
                    "type": "flex",
                    "altText": alt_text,
                    "contents": flex_content
                }]
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Failed to send LINE push: {e}")
            return False

    def send_line_reply_text(self, reply_token, text):
        token = self.get_line_token()
        if not token or not reply_token:
            return False
        try:
            url = "https://api.line.me/v2/bot/message/reply"
            payload = json.dumps({
                "replyToken": reply_token,
                "messages": [{
                    "type": "text",
                    "text": text
                }]
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Failed to reply LINE: {e}")
            return False

    def api_trigger_reminders(self, body):
        """Dynamic 24h Reminder check: finds upcoming appointments in the next 36 hours that are still RESERVED"""
        conn = database.get_connection()
        cursor = conn.cursor()
        
        # Calculate Taiwan Time (UTC+8)
        taiwan_now = datetime.utcnow() + timedelta(hours=8)
        
        # Look from now up to 36 hours ahead (covers all upcoming appointments within 36 hours)
        window_start = (taiwan_now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        window_end = (taiwan_now + timedelta(hours=36)).strftime("%Y-%m-%d %H:%M")

        cursor.execute("""
            SELECT * FROM appointments 
            WHERE (status = 'RESERVED' OR status = 'PENDING_CONFIRM')
              AND (appointment_date || ' ' || appointment_time) >= ?
              AND (appointment_date || ' ' || appointment_time) <= ?
        """, (window_start, window_end))

        eligible = cursor.fetchall()
        processed = []
        now_str = taiwan_now.strftime("%Y-%m-%d %H:%M:%S")

        for apt in eligible:
            flex_card = self.generate_flex_confirmation(apt)
            cursor.execute("""
                UPDATE appointments 
                SET status = 'PENDING_CONFIRM', reminder_sent_at = ? 
                WHERE id = ?
            """, (now_str, apt["id"]))

            cursor.execute("""
                INSERT INTO reminder_logs (id, appointment_id, line_user_id, sent_at, status, flex_payload)
                VALUES (?, ?, ?, ?, 'SENT', ?)
            """, (str(uuid.uuid4()), apt["id"], apt["line_user_id"], now_str, json.dumps(flex_card, ensure_ascii=False)))

            push_sent = False
            if apt["line_user_id"] and not apt["line_user_id"].startswith("U_GUEST_"):
                push_sent = self.send_line_push_flex(apt["line_user_id"], "【青松物理治療所】明日看診出席確認通知", flex_card)

            processed.append({
                "appointment_id": apt["id"],
                "patient_name": apt["patient_name"],
                "therapist_name": apt["therapist_name"],
                "date": apt["appointment_date"],
                "time": apt["appointment_time"],
                "push_sent": push_sent,
                "flex_preview": flex_card
            })

        conn.commit()
        conn.close()

        self.send_json({
            "success": True,
            "checked_at": now_str,
            "processed_count": len(processed),
            "processed_items": processed
        })

    def api_line_webhook(self, body):
        """Handles LINE Webhook callback from Flex button clicks"""
        events = body.get("events", [])
        results = []

        conn = database.get_connection()
        cursor = conn.cursor()

        for event in events:
            if event.get("type") == "postback":
                reply_token = event.get("replyToken")
                postback_data = event.get("postback", {}).get("data", "")
                parsed_data = urllib.parse.parse_qs(postback_data)
                action = parsed_data.get("action", [""])[0]
                apt_id = parsed_data.get("apt_id", [""])[0]
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if action == "confirm" and apt_id:
                    cursor.execute("UPDATE appointments SET status = 'CONFIRMED', confirmed_at = ? WHERE id = ?", (now_str, apt_id))
                    results.append({"apt_id": apt_id, "action": "confirmed"})
                    if reply_token:
                        self.send_line_reply_text(reply_token, "✅ 已為您確認明日預約！\n\n院長與物理治療師將專屬為您保留時段。\n📍 看診地點：高雄市鳥松區華美路69號\n請穿著寬鬆活動衣褲，提早 5-10 分鐘抵達報到，期待為您服務！🌲")
                elif action == "cancel" and apt_id:
                    cursor.execute("UPDATE appointments SET status = 'CANCELLED', cancelled_at = ?, cancel_reason = 'LINE確認卡片點擊無法前往' WHERE id = ?", (now_str, apt_id))
                    results.append({"apt_id": apt_id, "action": "cancelled"})
                    if reply_token:
                        self.send_line_reply_text(reply_token, "❌ 已為您取消明日預約，該時段已釋出。\n\n若日後需要重新安排看診或肌力訓練，隨時歡迎點擊下方選單再次預約，祝您早日康復、健康平安！🌲")

        conn.commit()
        conn.close()
        self.send_json({"success": True, "handled": results})

    # --- LINE Flex Message Generators ---
    def generate_flex_receipt(self, apt_id, name, therapist, date_str, time_str, v_type, slip):
        type_str = "初診評估" if v_type == "FIRST_VISIT" else ("肌力訓練" if v_type == "FITNESS" else "複診追蹤")
        slip_str = "當天請攜帶照會/轉診單正本" if slip else "免照會單"
        return {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#15803d",
                "contents": [
                    {"type": "text", "text": "🌲 青松物理治療所", "color": "#ffffff", "weight": "bold", "size": "md"},
                    {"type": "text", "text": "預約掛號成功憑證", "color": "#dcfce7", "weight": "bold", "size": "xl", "margin": "xs"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"您好，{name}：您的預約已成立！", "weight": "bold", "size": "md"},
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "spacing": "sm",
                        "contents": [
                            {"type": "text", "text": f"🗓 預約日期：{date_str} ({time_str})", "size": "sm", "color": "#334155"},
                            {"type": "text", "text": f"👨‍⚕️ 物理治療師：{therapist}", "size": "sm", "color": "#334155"},
                            {"type": "text", "text": f"📋 就診類別：{type_str}", "size": "sm", "color": "#334155"},
                            {"type": "text", "text": f"📄 轉診叮嚀：{slip_str}", "size": "sm", "color": "#15803d"},
                            {"type": "text", "text": f"📍 地點：高雄市鳥松區華美路69號", "size": "sm", "color": "#64748b"}
                        ]
                    },
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": "🔔 我們將於看診前 24 小時發送確認訊息，屆時請留意 LINE 通知點擊確認！", "size": "xs", "color": "#059669", "margin": "md", "wrap": True}
                ]
            }
        }

    def generate_flex_confirmation(self, apt):
        """Day-before 24H confirmation Flex Message with interactive buttons"""
        return {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#047857",
                "contents": [
                    {"type": "text", "text": "🌲 青松物理治療所", "color": "#ffffff", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "明日看診出席確認通知", "color": "#ffffff", "weight": "bold", "size": "lg", "margin": "xs"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"親愛的 {apt['patient_name']} 您好：", "weight": "bold", "size": "md"},
                    {"type": "text", "text": "提醒您明日有安排物理治療預約，為確保治療師專屬為您保留時段，請協助點擊下方按鈕確認：", "size": "sm", "color": "#475569", "margin": "sm", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "spacing": "xs",
                        "contents": [
                            {"type": "text", "text": f"🗓 預約時間：{apt['appointment_date']} {apt['appointment_time']}", "size": "sm", "weight": "bold", "color": "#065f46"},
                            {"type": "text", "text": f"👨‍⚕️ 負責治療師：{apt['therapist_name']}", "size": "sm", "color": "#334155"},
                            {"type": "text", "text": "👕 建議穿著：寬鬆活動運動衣褲", "size": "xs", "color": "#64748b"},
                            {"type": "text", "text": "📍 地點：高雄市鳥松區華美路69號 (07-7353353)", "size": "xs", "color": "#64748b"}
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "horizontal",
                "spacing": "md",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#15803d",
                        "action": {
                            "type": "postback",
                            "label": "✅ 會準時前往",
                            "data": f"action=confirm&apt_id={apt['id']}",
                            "displayText": "我會準時前往青松物理治療所！"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "color": "#fee2e2",
                        "action": {
                            "type": "postback",
                            "label": "❌ 無法前往/取消",
                            "data": f"action=cancel&apt_id={apt['id']}",
                            "displayText": "很抱歉，明日臨時有事需取消預約。"
                        }
                    }
                ]
            }
        }

if __name__ == "__main__":
    database.init_db()
    with socketserver.TCPServer(("", PORT), QingsongRequestHandler) as httpd:
        print(f"🌲 青松物理治療所預約系統伺服器已啟動: http://localhost:{PORT}")
        print(f"📱 病患端 LINE LIFF 體驗: http://localhost:{PORT}/")
        print(f"🖥 診所端管理後台: http://localhost:{PORT}/admin")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n伺服器已安全停止")
