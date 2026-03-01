#!/usr/bin/env python3
import json
import os
import sqlite3
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data.db")
INDEX_PATH = os.path.join(ROOT, "index.html")


def now_ms() -> int:
    return int(time.time() * 1000)


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          sport TEXT NOT NULL,
          location TEXT NOT NULL,
          start_ms INTEGER NOT NULL,
          lock_ms INTEGER,
          max_players INTEGER NOT NULL,
          duration_minutes INTEGER NOT NULL DEFAULT 90,
          created_at_ms INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS participants (
          id TEXT PRIMARY KEY,
          match_id TEXT NOT NULL,
          name TEXT NOT NULL,
          email TEXT NOT NULL,
          phone TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('joined','waitlist','left')),
          created_at_ms INTEGER NOT NULL,
          FOREIGN KEY(match_id) REFERENCES matches(id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_participants_match ON participants(match_id)")
    conn.commit()
    conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def match_with_participants(conn, match_id):
    m = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not m:
        return None
    match = row_to_dict(m)
    parts = conn.execute(
        """
        SELECT id, match_id, name, email, phone, status, created_at_ms
        FROM participants
        WHERE match_id = ? AND status != 'left'
        ORDER BY created_at_ms ASC
        """,
        (match_id,),
    ).fetchall()
    match["participants"] = [row_to_dict(p) for p in parts]
    return match


def joined_count(conn, match_id):
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM participants WHERE match_id=? AND status='joined'",
        (match_id,),
    ).fetchone()
    return int(row["c"])


class Handler(BaseHTTPRequestHandler):
    def _send(self, status=200, data=None, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if data is not None:
            if isinstance(data, (dict, list)):
                self.wfile.write(json.dumps(data).encode("utf-8"))
            elif isinstance(data, str):
                self.wfile.write(data.encode("utf-8"))
            else:
                self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            if not os.path.exists(INDEX_PATH):
                return self._send(404, "index.html not found", "text/plain")
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")

        if path == "/api/health":
            return self._send(200, {"ok": True, "ts": now_ms()})

        if path == "/api/matches":
            running = query.get("running", ["0"])[0] == "1"
            conn = db_conn()
            if running:
                ms = now_ms()
                rows = conn.execute(
                    """
                    SELECT * FROM matches
                    WHERE start_ms <= ?
                      AND (start_ms + duration_minutes * 60000) >= ?
                    ORDER BY start_ms DESC
                    """,
                    (ms, ms),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM matches ORDER BY created_at_ms DESC").fetchall()
            out = [row_to_dict(r) for r in rows]
            conn.close()
            return self._send(200, out)

        if path.startswith("/api/matches/"):
            match_id = path.split("/")[-1]
            conn = db_conn()
            m = match_with_participants(conn, match_id)
            conn.close()
            if not m:
                return self._send(404, {"error": "match not found"})
            return self._send(200, m)

        return self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._body()

        if path == "/api/matches":
            try:
                mid = body.get("id") or f"m{now_ms()}"
                title = (body.get("title") or "Weekend Match").strip()
                sport = (body.get("sport") or "Badminton").strip()
                location = (body.get("location") or "TBD").strip()
                start_ms = int(body.get("start_ms"))
                lock_ms = body.get("lock_ms")
                lock_ms = int(lock_ms) if lock_ms else None
                max_players = max(2, int(body.get("max_players") or 6))
                duration_minutes = max(30, int(body.get("duration_minutes") or 90))
            except Exception:
                return self._send(400, {"error": "invalid payload"})

            conn = db_conn()
            conn.execute(
                """
                INSERT INTO matches(id,title,sport,location,start_ms,lock_ms,max_players,duration_minutes,created_at_ms)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (mid, title, sport, location, start_ms, lock_ms, max_players, duration_minutes, now_ms()),
            )
            conn.commit()
            m = match_with_participants(conn, mid)
            conn.close()
            return self._send(201, m)

        if path.endswith("/join") and path.startswith("/api/matches/"):
            match_id = path.split("/")[-2]
            name = (body.get("name") or "").strip()
            email = (body.get("email") or "").strip().lower()
            phone = (body.get("phone") or "").strip()
            if not (name and email and phone):
                return self._send(400, {"error": "name, email, phone are required"})

            conn = db_conn()
            m = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
            if not m:
                conn.close()
                return self._send(404, {"error": "match not found"})

            if m["lock_ms"] and now_ms() > int(m["lock_ms"]):
                conn.close()
                return self._send(400, {"error": "roster is locked"})

            existing = conn.execute(
                """
                SELECT * FROM participants
                WHERE match_id=? AND (LOWER(email)=LOWER(?) OR phone=?) AND status != 'left'
                LIMIT 1
                """,
                (match_id, email, phone),
            ).fetchone()
            if existing:
                conn.close()
                return self._send(409, {"error": "participant already joined/waitlisted"})

            jc = joined_count(conn, match_id)
            status = "joined" if jc < int(m["max_players"]) else "waitlist"
            pid = f"p{now_ms()}{int(time.time_ns()%1000)}"
            conn.execute(
                """
                INSERT INTO participants(id,match_id,name,email,phone,status,created_at_ms)
                VALUES(?,?,?,?,?,?,?)
                """,
                (pid, match_id, name, email, phone, status, now_ms()),
            )
            conn.commit()
            out = match_with_participants(conn, match_id)
            conn.close()
            return self._send(200, out)

        if path.endswith("/leave") and path.startswith("/api/matches/"):
            match_id = path.split("/")[-2]
            email = (body.get("email") or "").strip().lower()
            phone = (body.get("phone") or "").strip()
            if not (email or phone):
                return self._send(400, {"error": "email or phone required"})

            conn = db_conn()
            m = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
            if not m:
                conn.close()
                return self._send(404, {"error": "match not found"})

            if email:
                target = conn.execute(
                    """
                    SELECT * FROM participants
                    WHERE match_id=? AND LOWER(email)=LOWER(?) AND status != 'left'
                    ORDER BY created_at_ms DESC LIMIT 1
                    """,
                    (match_id, email),
                ).fetchone()
            else:
                target = conn.execute(
                    """
                    SELECT * FROM participants
                    WHERE match_id=? AND phone=? AND status != 'left'
                    ORDER BY created_at_ms DESC LIMIT 1
                    """,
                    (match_id, phone),
                ).fetchone()

            if not target:
                conn.close()
                return self._send(404, {"error": "participant not found"})

            conn.execute("UPDATE participants SET status='left' WHERE id=?", (target["id"],))

            jc = joined_count(conn, match_id)
            if jc < int(m["max_players"]):
                nxt = conn.execute(
                    """
                    SELECT * FROM participants
                    WHERE match_id=? AND status='waitlist'
                    ORDER BY created_at_ms ASC LIMIT 1
                    """,
                    (match_id,),
                ).fetchone()
                if nxt:
                    conn.execute("UPDATE participants SET status='joined' WHERE id=?", (nxt["id"],))

            conn.commit()
            out = match_with_participants(conn, match_id)
            conn.close()
            return self._send(200, out)

        return self._send(404, {"error": "not found"})


def main():
    init_db()
    port = int(os.environ.get("PORT", "8081"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"No-Drama Sports Slot running at http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
