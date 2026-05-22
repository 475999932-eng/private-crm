import json
import os
import secrets
import sqlite3
import hashlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "crm_multiuser.db")
HTML_PATH = os.path.join(BASE_DIR, "crm_multiuser.html")
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8090"))


def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('boss','staff')),
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            wechat TEXT DEFAULT '',
            city TEXT DEFAULT '',
            owner TEXT DEFAULT '',
            channel TEXT DEFAULT '',
            level TEXT DEFAULT '',
            status TEXT DEFAULT '',
            source TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            next_date TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            note TEXT DEFAULT '',
            last_follow TEXT DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            date TEXT NOT NULL,
            content TEXT DEFAULT '',
            next_date TEXT DEFAULT '',
            result TEXT DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    def _send(self, status, data, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.end_headers()
        if content_type.startswith("application/json"):
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        else:
            self.wfile.write(data.encode("utf-8"))

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _auth_user(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:].strip()
        conn = db_conn()
        row = conn.execute(
            """
            SELECT u.id, u.username, u.role
            FROM sessions s JOIN users u ON s.user_id = u.id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row["id"], "username": row["username"], "role": row["role"], "token": token}

    def _require_auth(self):
        user = self._auth_user()
        if not user:
            self._send(401, {"error": "unauthorized"})
            return None
        return user

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/crm_multiuser.html":
            if not os.path.exists(HTML_PATH):
                self._send(404, "crm_multiuser.html not found", "text/plain; charset=utf-8")
                return
            with open(HTML_PATH, "r", encoding="utf-8") as f:
                html = f.read()
            self._send(200, html, "text/html; charset=utf-8")
            return

        if path == "/api/me":
            user = self._require_auth()
            if not user:
                return
            self._send(200, {"user": {"id": user["id"], "username": user["username"], "role": user["role"]}})
            return

        if path == "/api/customers":
            user = self._require_auth()
            if not user:
                return
            conn = db_conn()
            if user["role"] == "boss":
                rows = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM customers WHERE owner = ? ORDER BY id DESC", (user["username"],)).fetchall()
            customers = []
            for r in rows:
                customers.append(
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "phone": r["phone"],
                        "wechat": r["wechat"],
                        "city": r["city"],
                        "owner": r["owner"],
                        "channel": r["channel"],
                        "level": r["level"],
                        "status": r["status"],
                        "source": r["source"],
                        "tags": json.loads(r["tags"] or "[]"),
                        "nextDate": r["next_date"],
                        "amount": r["amount"] or 0,
                        "note": r["note"],
                        "lastFollow": r["last_follow"],
                    }
                )
            conn.close()
            self._send(200, {"customers": customers})
            return

        if path == "/api/follows":
            user = self._require_auth()
            if not user:
                return
            conn = db_conn()
            if user["role"] == "boss":
                rows = conn.execute("SELECT * FROM follows ORDER BY id DESC LIMIT 200").fetchall()
            else:
                rows = conn.execute("SELECT * FROM follows WHERE created_by = ? ORDER BY id DESC LIMIT 200", (user["id"],)).fetchall()
            follows = []
            for r in rows:
                follows.append(
                    {
                        "id": r["id"],
                        "customerId": r["customer_id"],
                        "customerName": r["customer_name"],
                        "date": r["date"],
                        "content": r["content"],
                        "nextDate": r["next_date"],
                        "result": r["result"],
                    }
                )
            conn.close()
            self._send(200, {"follows": follows})
            return

        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/register":
            body = self._read_json()
            username = (body.get("username") or "").strip()
            password = (body.get("password") or "").strip()
            role = (body.get("role") or "staff").strip()
            if not username or not password:
                self._send(400, {"error": "username and password required"})
                return
            if role not in ("boss", "staff"):
                role = "staff"
            conn = db_conn()
            try:
                conn.execute(
                    "INSERT INTO users(username, password_hash, role, created_at) VALUES(?,?,?,?)",
                    (username, sha256(password), role, now_iso()),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                self._send(409, {"error": "username exists"})
                return
            conn.close()
            self._send(200, {"ok": True})
            return

        if path == "/api/login":
            body = self._read_json()
            username = (body.get("username") or "").strip()
            password = (body.get("password") or "").strip()
            conn = db_conn()
            user = conn.execute(
                "SELECT id, username, role FROM users WHERE username = ? AND password_hash = ?",
                (username, sha256(password)),
            ).fetchone()
            if not user:
                conn.close()
                self._send(401, {"error": "invalid credentials"})
                return
            token = secrets.token_hex(24)
            conn.execute(
                "INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                (token, user["id"], now_iso()),
            )
            conn.commit()
            conn.close()
            self._send(200, {"token": token, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}})
            return

        if path == "/api/logout":
            user = self._require_auth()
            if not user:
                return
            conn = db_conn()
            conn.execute("DELETE FROM sessions WHERE token = ?", (user["token"],))
            conn.commit()
            conn.close()
            self._send(200, {"ok": True})
            return

        if path == "/api/customers":
            user = self._require_auth()
            if not user:
                return
            b = self._read_json()
            owner = (b.get("owner") or "").strip() or user["username"]
            if user["role"] != "boss":
                owner = user["username"]
            tags = b.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            conn = db_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO customers(name, phone, wechat, city, owner, channel, level, status, source, tags, next_date, amount, note, last_follow, created_by, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    (b.get("name") or "").strip(),
                    (b.get("phone") or "").strip(),
                    (b.get("wechat") or "").strip(),
                    (b.get("city") or "").strip(),
                    owner,
                    (b.get("channel") or "").strip(),
                    (b.get("level") or "").strip(),
                    (b.get("status") or "").strip(),
                    (b.get("source") or "").strip(),
                    json.dumps(tags, ensure_ascii=False),
                    (b.get("nextDate") or "").strip(),
                    float(b.get("amount") or 0),
                    (b.get("note") or "").strip(),
                    (b.get("lastFollow") or "").strip(),
                    user["id"],
                    now_iso(),
                    now_iso(),
                ),
            )
            conn.commit()
            cid = cur.lastrowid
            conn.close()
            self._send(200, {"ok": True, "id": cid})
            return

        if path == "/api/follows":
            user = self._require_auth()
            if not user:
                return
            b = self._read_json()
            cid = int(b.get("customerId") or 0)
            conn = db_conn()
            cust = conn.execute("SELECT id, name, owner FROM customers WHERE id = ?", (cid,)).fetchone()
            if not cust:
                conn.close()
                self._send(404, {"error": "customer not found"})
                return
            if user["role"] != "boss" and cust["owner"] != user["username"]:
                conn.close()
                self._send(403, {"error": "forbidden"})
                return
            conn.execute(
                """
                INSERT INTO follows(customer_id, customer_name, date, content, next_date, result, created_by, created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    cid,
                    cust["name"],
                    (b.get("date") or "").strip(),
                    (b.get("content") or "").strip(),
                    (b.get("nextDate") or "").strip(),
                    (b.get("result") or "").strip(),
                    user["id"],
                    now_iso(),
                ),
            )
            conn.execute(
                "UPDATE customers SET last_follow = ?, next_date = ?, status = ?, updated_at = ? WHERE id = ?",
                (
                    (b.get("date") or "").strip(),
                    (b.get("nextDate") or "").strip(),
                    (b.get("status") or "").strip() or "跟进中",
                    now_iso(),
                    cid,
                ),
            )
            conn.commit()
            conn.close()
            self._send(200, {"ok": True})
            return

        self._send(404, {"error": "not found"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/customers/"):
            self._send(404, {"error": "not found"})
            return
        user = self._require_auth()
        if not user:
            return
        try:
            cid = int(path.split("/")[-1])
        except Exception:
            self._send(400, {"error": "invalid id"})
            return
        conn = db_conn()
        c = conn.execute("SELECT id, owner FROM customers WHERE id = ?", (cid,)).fetchone()
        if not c:
            conn.close()
            self._send(404, {"error": "customer not found"})
            return
        if user["role"] != "boss" and c["owner"] != user["username"]:
            conn.close()
            self._send(403, {"error": "forbidden"})
            return
        conn.execute("DELETE FROM customers WHERE id = ?", (cid,))
        conn.commit()
        conn.close()
        self._send(200, {"ok": True})


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"CRM server running at http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
