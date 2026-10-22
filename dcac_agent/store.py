from __future__ import annotations

import copy
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .design import DesignSpec


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "sessions.json"
        self.lock = threading.RLock()
        self.sessions = {}
        if self.path.exists():
            self.sessions = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self):
        with self.lock:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.sessions, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            temp.replace(self.path)

    def create(self) -> dict:
        with self.lock:
            sid = uuid.uuid4().hex[:12]
            row = {"id": sid, "title": "新的逆变器设计", "created_at": now(), "updated_at": now(),
                   "spec": DesignSpec().to_dict(), "messages": [], "runs": [], "revision": 0}
            self.sessions[sid] = row
            self.save()
            return copy.deepcopy(row)

    def get(self, sid: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{12}", sid or "") or sid not in self.sessions:
            raise KeyError("会话不存在。")
        return self.sessions[sid]

    def snapshot(self, sid: str) -> dict:
        with self.lock:
            return copy.deepcopy(self.get(sid))

    def listing(self) -> list:
        with self.lock:
            return [{k: row[k] for k in ("id", "title", "updated_at")} for row in
                    sorted(self.sessions.values(), key=lambda r: r["updated_at"], reverse=True)]

    def message(self, sid: str, role: str, content: str, **extras):
        with self.lock:
            session = self.get(sid)
            session["messages"].append({"role": role, "content": content, "created_at": now(), **extras})
            session["updated_at"] = now()
            self.save()

    def update_spec(self, sid: str, updates: dict) -> dict:
        with self.lock:
            session = self.get(sid)
            spec = DesignSpec(**session["spec"]).updated(updates)
            session["spec"] = spec.to_dict()
            session["revision"] += 1
            session["title"] = f"{spec.output_power:g} W · {spec.output_voltage:g} V 单相逆变器"
            session["updated_at"] = now()
            self.save()
            return {"spec": spec.to_dict(), "derived": spec.derived(), "revision": session["revision"]}

    def add_run(self, sid: str, run: dict):
        with self.lock:
            self.get(sid)["runs"].append(run)
            self.save()

    def save_job(self, sid: str, job: dict):
        with self.lock:
            self.get(sid)["last_job"] = copy.deepcopy(job)
            self.save()
