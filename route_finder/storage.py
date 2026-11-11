"""Small SQLite persistence layer for route history."""
import json, os, sqlite3
from pathlib import Path

class RouteHistory:
    def __init__(self, path=None):
        path = path or os.getenv("DATABASE_PATH", "data/routes.db")
        self.path = str(path); Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS routes (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, source TEXT NOT NULL, target TEXT NOT NULL, metric TEXT NOT NULL, algorithm TEXT NOT NULL, distance_km REAL NOT NULL, duration_min REAL NOT NULL, elapsed_ms REAL NOT NULL, nodes_json TEXT NOT NULL)")
    def _connect(self): return sqlite3.connect(self.path)
    def save(self, source, target, metric, result):
        with self._connect() as db:
            cur = db.execute("INSERT INTO routes(source,target,metric,algorithm,distance_km,duration_min,elapsed_ms,nodes_json) VALUES(?,?,?,?,?,?,?,?)", (str(source),str(target),metric,result.algorithm,result.distance_km,result.duration_min,result.elapsed_ms,json.dumps(result.nodes)))
            return cur.lastrowid
    def recent(self, limit=100):
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM routes ORDER BY id DESC LIMIT ?", (int(limit),))]
