"""HN Graph — polls the Hacker News front page and serves a live scoreboard chart."""

import json
import logging
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

DB_PATH = os.environ.get("DB_PATH", "data/hn.db")
PORT = int(os.environ.get("PORT", "8000"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))  # seconds
TOP_N = int(os.environ.get("TOP_N", "30"))  # front page size
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "7"))

HN_API = "https://hacker-news.firebaseio.com/v0"
STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hn-graph")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                author TEXT,
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                ts INTEGER NOT NULL,
                story_id INTEGER NOT NULL REFERENCES stories(id),
                rank INTEGER NOT NULL,
                score INTEGER NOT NULL,
                comments INTEGER NOT NULL,
                PRIMARY KEY (ts, story_id)
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
            """
        )


def fetch_json(url):
    req = Request(url, headers={"User-Agent": "hn-graph/1.0"})
    with urlopen(req, timeout=15) as resp:
        return json.load(resp)


def poll_once():
    ids = fetch_json(f"{HN_API}/topstories.json")[:TOP_N]
    with ThreadPoolExecutor(max_workers=10) as pool:
        items = list(pool.map(lambda i: fetch_json(f"{HN_API}/item/{i}.json"), ids))

    ts = int(time.time())
    with db() as conn:
        for rank, item in enumerate(items, start=1):
            if not item or item.get("deleted") or item.get("dead"):
                continue
            conn.execute(
                """INSERT INTO stories (id, title, url, author, created_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET title = excluded.title, url = excluded.url""",
                (item["id"], item.get("title", ""), item.get("url"), item.get("by"), item.get("time")),
            )
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (ts, story_id, rank, score, comments) VALUES (?, ?, ?, ?, ?)",
                (ts, item["id"], rank, item.get("score", 0), item.get("descendants", 0)),
            )
        purged = conn.execute("DELETE FROM snapshots WHERE ts < ?", (ts - RETENTION_DAYS * 86400,)).rowcount
        if purged:
            conn.execute("DELETE FROM stories WHERE id NOT IN (SELECT DISTINCT story_id FROM snapshots)")
    log.info("Snapshot saved: %d stories%s", len(items), f", purged {purged} old points" if purged else "")


def poller():
    while True:
        try:
            poll_once()
        except Exception:
            log.exception("Polling failed")
        time.sleep(POLL_INTERVAL)


def get_data(hours):
    since = int(time.time()) - hours * 3600
    with db() as conn:
        rows = conn.execute(
            """SELECT s.ts, s.story_id, s.rank, s.score, s.comments
               FROM snapshots s WHERE s.ts >= ? ORDER BY s.ts""",
            (since,),
        ).fetchall()
        story_ids = {r["story_id"] for r in rows}
        stories = {}
        if story_ids:
            placeholders = ",".join("?" * len(story_ids))
            for s in conn.execute(
                f"SELECT id, title, url, author, created_at FROM stories WHERE id IN ({placeholders})",
                tuple(story_ids),
            ):
                stories[s["id"]] = {**dict(s), "points": []}

    for r in rows:
        stories[r["story_id"]]["points"].append([r["ts"], r["score"], r["rank"], r["comments"]])

    last_ts = rows[-1]["ts"] if rows else None
    return {
        "updated_at": last_ts,
        "poll_interval": POLL_INTERVAL,
        "stories": list(stories.values()),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            try:
                hours = int(parse_qs(parsed.query).get("hours", ["24"])[0])
            except ValueError:
                hours = 24
            hours = max(1, min(hours, RETENTION_DAYS * 24))
            body = json.dumps(get_data(hours)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


def main():
    init_db()
    threading.Thread(target=poller, daemon=True).start()
    log.info("Listening on http://0.0.0.0:%d (poll every %ds)", PORT, POLL_INTERVAL)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
