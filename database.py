import json
import sqlite3
from pathlib import Path
from typing import Any

def _connect(db_path: str):
    path = Path(db_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(db_path: str):
    with _connect(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            requests INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            invite_url TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            action TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

def touch_user(db_path: str, user_id: int):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users(user_id) VALUES(?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP",
            (int(user_id),)
        )
        conn.execute("INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)", (int(user_id),))

def is_admin(db_path: str, user_id: int) -> bool:
    with _connect(db_path) as conn:
        return conn.execute("SELECT 1 FROM admins WHERE user_id=?", (int(user_id),)).fetchone() is not None

def get_channels(db_path: str):
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT channel_id, title, invite_url FROM channels ORDER BY title").fetchall()
        return [dict(row) for row in rows]

def get_admin_ids(db_path: str):
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT user_id FROM admins ORDER BY user_id").fetchall()
        return [int(row["user_id"]) for row in rows]

def get_stats(db_path: str):
    with _connect(db_path) as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        requests = conn.execute("SELECT COALESCE(SUM(requests),0) FROM user_stats").fetchone()[0]
        channels = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        admins = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
        return {"users": int(users), "requests": int(requests), "channels": int(channels), "admins": int(admins)}

def increment_requests(db_path: str, user_id: int):
    touch_user(db_path, user_id)
    with _connect(db_path) as conn:
        conn.execute("UPDATE user_stats SET requests=requests+1 WHERE user_id=?", (int(user_id),))

def set_state(db_path: str, user_id: int, action: str):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO user_states(user_id, action) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET action=excluded.action, updated_at=CURRENT_TIMESTAMP",
            (int(user_id), str(action))
        )

def get_state(db_path: str, user_id: int):
    with _connect(db_path) as conn:
        row = conn.execute("SELECT action FROM user_states WHERE user_id=?", (int(user_id),)).fetchone()
        return {"action": row["action"]} if row else None

def clear_state(db_path: str, user_id: int):
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM user_states WHERE user_id=?", (int(user_id),))

def create_pending(db_path: str, requester_id: int, action: str, payload: Any) -> int:
    payload_json = json.dumps(payload, ensure_ascii=False)
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO pending_actions(requester_id, action, payload) VALUES(?, ?, ?)",
            (int(requester_id), str(action), payload_json)
        )
        return int(cur.lastrowid)

def get_pending(db_path: str, pending_id: int):
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM pending_actions WHERE id=?", (int(pending_id),)).fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "user_id": int(row["requester_id"]),
            "action": row["action"],
            "payload": json.loads(row["payload"])
        }

def delete_pending(db_path: str, pending_id: int):
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM pending_actions WHERE id=?", (int(pending_id),))

def _valid_channel_id(value: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError("د چینل ID یا username تش دی.")
    if value.startswith("@"):
        if len(value) < 2:
            raise ValueError("د چینل username ناسم دی.")
        return value
    try:
        int(value)
    except ValueError:
        raise ValueError("د چینل ID باید عددي وي یا د @username په بڼه وي.")
    return value

def parse_admin_input(action: str, text: str, owner_id: int):
    text = text.strip()
    if action == "add_channel":
        parts = [p.strip() for p in text.split("|")]
        if len(parts) != 3:
            raise ValueError("درې برخې د | په نښه جلا کړئ: @channelusername | نوم | https://t.me/channelusername")
        channel_id, title, invite_url = parts
        channel_id = _valid_channel_id(channel_id)
        if not title:
            raise ValueError("د چینل نوم تش دی.")
        if not invite_url.startswith(("https://t.me/", "http://t.me/")):
            raise ValueError("د چینل لینک باید د https://t.me/ په بڼه وي.")
        return "add_channel", {"channel_id": channel_id, "title": title, "invite_url": invite_url}
    if action == "edit_channel":
        parts = [p.strip() for p in text.split("|")]
        if len(parts) != 4:
            raise ValueError("څلور برخې ولیکئ: اوسنی_ID | نوی_ID | نوی نوم | نوی لینک")
        old_id, new_id, title, invite_url = parts
        old_id = _valid_channel_id(old_id)
        new_id = _valid_channel_id(new_id)
        if not title or not invite_url.startswith(("https://t.me/", "http://t.me/")):
            raise ValueError("نوی نوم او معتبر t.me لینک ورکړئ.")
        return "edit_channel", {"old_id": old_id, "channel_id": new_id, "title": title, "invite_url": invite_url}
    if action == "delete_channel":
        return "delete_channel", {"channel_id": _valid_channel_id(text)}
    if action in ("add_admin", "delete_admin"):
        try:
            user_id = int(text)
        except ValueError:
            raise ValueError("د اډمین عددي Telegram ID ولیکئ.")
        if user_id <= 0:
            raise ValueError("Telegram ID باید مثبت عدد وي.")
        if user_id == int(owner_id):
            raise ValueError("د اصلي مالک ID د اضافي اډمین په توګه مه ثبتوئ.")
        return action, {"user_id": user_id}
    raise ValueError("دا عملیات نه پېژندل کېږي.")

def describe_pending(action: str, payload: dict):
    if action == "add_channel":
        return f"چینل اضافه کول\nID: {payload['channel_id']}\nنوم: {payload['title']}\nلینک: {payload['invite_url']}"
    if action == "edit_channel":
        return f"د چینل معلومات بدلول\nزوړ ID: {payload['old_id']}\nنوی ID: {payload['channel_id']}\nنوم: {payload['title']}\nلینک: {payload['invite_url']}"
    if action == "delete_channel":
        return f"چینل حذف کول\nID: {payload['channel_id']}"
    if action == "add_admin":
        return f"اډمین اضافه کول\nTelegram ID: {payload['user_id']}"
    if action == "delete_admin":
        return f"اډمین حذف کول\nTelegram ID: {payload['user_id']}"
    return "نامعلوم عملیات"

def apply_pending(db_path: str, pending_id: int, acting_user_id: int, owner_id: int):
    item = get_pending(db_path, pending_id)
    if not item:
        raise ValueError("دا عملیات نه موندل کېږي.")
    if item["user_id"] != int(acting_user_id):
        raise ValueError("یوازې د غوښتنې جوړوونکی یې تاییدولای شي.")
    action, payload = item["action"], item["payload"]
    with _connect(db_path) as conn:
        if action == "add_channel":
            conn.execute(
                "INSERT INTO channels(channel_id,title,invite_url) VALUES(?,?,?)",
                (payload["channel_id"], payload["title"], payload["invite_url"])
            )
        elif action == "edit_channel":
            cur = conn.execute(
                "UPDATE channels SET channel_id=?, title=?, invite_url=? WHERE channel_id=?",
                (payload["channel_id"], payload["title"], payload["invite_url"], payload["old_id"])
            )
            if cur.rowcount == 0:
                raise ValueError("زوړ چینل ونه موندل شو.")
        elif action == "delete_channel":
            cur = conn.execute("DELETE FROM channels WHERE channel_id=?", (payload["channel_id"],))
            if cur.rowcount == 0:
                raise ValueError("چینل ونه موندل شو.")
        elif action == "add_admin":
            uid = int(payload["user_id"])
            if uid == int(owner_id):
                raise ValueError("اصلي مالک اضافي اډمین ته اړتیا نه لري.")
            conn.execute("INSERT INTO admins(user_id) VALUES(?)", (uid,))
        elif action == "delete_admin":
            uid = int(payload["user_id"])
            if uid == int(owner_id):
                raise ValueError("د اصلي مالک واکونه نه شي حذف کېدای.")
            conn.execute("DELETE FROM admins WHERE user_id=?", (uid,))
        else:
            raise ValueError("دا عملیات نه پېژندل کېږي.")
        conn.execute("DELETE FROM pending_actions WHERE id=?", (int(pending_id),))
