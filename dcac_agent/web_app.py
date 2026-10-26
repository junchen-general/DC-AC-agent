from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .agent import AgentService
from .config import OUTPUTS, ROOT, WORK, load_config, public_config
from .design import DesignSpec, MODEL_STAGES, BASELINE
from .runtime import MatlabRuntime
from .store import Store, now
from .contracts import write_manifest, read_multiphysics
from .nanobot_app import runtime_status


class Application:
    def __init__(self, config=None, store=None):
        self.config = config or load_config()
        self.store = store or Store(WORK)
        self.runtime = MatlabRuntime(self.config)
        self.agent = AgentService(self.config, self.store, self.runtime)
        self.csrf = secrets.token_urlsafe(32)
        self.settings_lock = threading.Lock()

    def state(self, sid=None):
        sessions = self.store.listing()
        if not sid:
            sid = sessions[0]["id"] if sessions else self.store.create()["id"]
        self.sync_manual_runs(sid)
        session = self.store.snapshot(sid)
        physics = []
        for run in session["runs"]:
            try:
                item = read_multiphysics(OUTPUTS / sid / run["id"], session, run)
                if item.get("status") != "not_run":
                    physics.append(item)
            except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
                physics.append({"status": "invalid", "run_id": run["id"], "message": str(exc)})
        return {"model_stages": MODEL_STAGES, "nanobot": runtime_status(), "multiphysics": physics, "session": session, "sessions": self.store.listing(), "csrf": self.csrf,
                "derived": DesignSpec(**session["spec"]).derived(), "config": public_config(self.config),
                "environment": self.runtime.status(), "job": self.agent.session_job(sid) or session.get("last_job")}

    def sync_manual_runs(self, sid):
        """Pick up results produced by the exported script in its original run folder."""
        changed = False
        with self.store.lock:
            for run in self.store.get(sid)["runs"]:
                if run["status"] not in {"exported", "failed", "cancelled"}:
                    continue
                folder = OUTPUTS / sid / run["id"]
                path = folder / "result.json"
                if not path.exists():
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                    if not data.get("ok") or data.get("source") != "MATLAB/Simulink" or data.get("spec") != run["spec"]:
                        continue
                    if data.get("action", run["action"]) != run["action"]:
                        continue
                    # New exports carry identity; legacy exports had only a spec.
                    if "run_context" in data:
                        context = data["run_context"]
                        if not isinstance(context, dict) or any(context.get(key) != value for key, value in
                            (("session_id", sid), ("run_id", run["id"]), ("design_revision", run["revision"]))):
                            continue
                    if data.get("electrical_v1", {}).get("model_fidelity", BASELINE) != run["spec"].get("model_fidelity", BASELINE):
                        continue
                    if run["action"] == "simulate" and not data.get("metrics"):
                        continue
                    run.update(status="completed", metrics=data.get("metrics"), checks=data.get("checks"),
                               execution="manual_matlab", finished_at=now(),
                               files=self.agent._artifacts(sid, run["id"], folder))
                    run.pop("error", None)
                    write_manifest(folder, sid, run, data.get("source"))
                    run["files"] = self.agent._artifacts(sid, run["id"], folder)
                    (folder / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
                    changed = True
                except (OSError, ValueError, TypeError):
                    continue
            if changed:
                self.store.save()

    def update_settings(self, payload):
        with self.settings_lock:
            llm = dict(self.config["llm"])
            for key in ("enabled", "backend", "base_url", "model"):
                if key in payload:
                    llm[key] = payload[key]
            if not isinstance(llm["enabled"], bool):
                raise ValueError("enabled必须为布尔值。")
            if llm.get("backend", "legacy") not in {"legacy", "nanobot"}:
                raise ValueError("不支持的Agent运行时。")
            if not isinstance(llm["model"], str) or len(llm["model"]) > 200:
                raise ValueError("模型名称格式无效。")
            url = urlparse(str(llm["base_url"]))
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("服务地址须是无账号、查询参数的HTTP(S)基础地址。")
            if payload.get("clear_api_key"):
                llm["api_key"] = ""
            elif payload.get("api_key"):
                if not isinstance(payload["api_key"], str) or len(payload["api_key"]) > 2000:
                    raise ValueError("API Key格式无效。")
                llm["api_key"] = payload["api_key"].strip()
            executable = str(payload.get("matlab_executable", self.config["matlab_executable"])).strip()
            if executable and (not Path(executable).is_file() or Path(executable).name.lower() not in {"matlab", "matlab.exe"}):
                raise ValueError("请填写真实的matlab.exe完整路径。")
            new = {**self.config, "llm": llm, "matlab_executable": executable}
            temp = ROOT / "config.json.tmp"
            temp.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(ROOT / "config.json")
            self.config.update(new)
            return public_config(self.config)


def make_handler(app: Application):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DCACAgent/0.1"

        def log_message(self, fmt, *args):
            # Keep request content, credentials and conversation text out of logs.
            pass

        def _json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _host_allowed(self):
            host = self.headers.get("Host", "").lower()
            return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def _guard(self, write=False):
            if not self._host_allowed():
                self._json({"error": "仅允许通过本机localhost访问。"}, 403)
                return False
            if write:
                if self.headers.get("X-CSRF-Token", "") != app.csrf:
                    self._json({"error": "会话令牌无效，请刷新网页。"}, 403)
                    return False
                origin = self.headers.get("Origin")
                if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
                    self._json({"error": "拒绝跨来源操作。"}, 403)
                    return False
            return True

        def _body(self):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 1_000_000:
                raise ValueError("请求体过大。")
            if "application/json" not in self.headers.get("Content-Type", ""):
                raise ValueError("请求必须采用JSON格式。")
            result = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(result, dict):
                raise ValueError("JSON请求必须为对象。")
            return result

        def do_GET(self):
            if not self._guard():
                return
            try:
                parsed = urlparse(self.path)
                path = unquote(parsed.path)
                query = parse_qs(parsed.query)
                if path == "/api/state":
                    self._json(app.state(query.get("session_id", [None])[0]))
                elif path.startswith("/api/jobs/"):
                    self._json(app.agent.snapshot(path.rsplit("/", 1)[-1]))
                elif path.startswith("/api/results/"):
                    parts = path.split("/")
                    if len(parts) != 5 or not all(re.fullmatch(r"[a-f0-9]{12}", p) for p in parts[3:]):
                        raise ValueError("运行标识无效。")
                    target = OUTPUTS / parts[3] / parts[4] / "result.json"
                    if not target.is_file():
                        raise FileNotFoundError("没有结果文件。")
                    self._json(json.loads(target.read_text(encoding="utf-8-sig")))
                elif path.startswith("/artifacts/"):
                    target = (OUTPUTS / path.removeprefix("/artifacts/")).resolve()
                    if not target.is_relative_to(OUTPUTS.resolve()) or not target.is_file():
                        raise FileNotFoundError("工件不存在。")
                    self._file(target, download=target.suffix not in {".png", ".json"})
                elif path in {"/", "/index.html", "/styles.css", "/app.js"}:
                    self._file(ROOT / "dcac_agent" / "web" / ("index.html" if path == "/" else path[1:]))
                else:
                    self._json({"error": "接口不存在。"}, 404)
            except (KeyError, FileNotFoundError) as exc:
                self._json({"error": str(exc)}, 404)
            except (ValueError, TypeError) as exc:
                self._json({"error": str(exc)}, 400)
            except Exception:
                self._json({"error": "服务端错误，请检查本机控制台。"}, 500)

        def _file(self, target: Path, download=False):
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix in {".html", ".css", ".js", ".json"}:
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
            self.end_headers()
            with target.open("rb") as stream:
                while chunk := stream.read(128 * 1024):
                    self.wfile.write(chunk)

        def do_POST(self):
            if not self._guard(write=True):
                return
            try:
                body = self._body()
                if self.path == "/api/sessions":
                    self._json(app.store.create(), 201)
                elif self.path == "/api/chat":
                    self._json(app.agent.submit(str(body.get("session_id", "")), body.get("message", ""),
                                               str(body.get("action", "chat")), body.get("updates"), body.get("run_id")), 202)
                elif self.path == "/api/cancel":
                    self._json(app.agent.cancel(str(body.get("job_id", ""))))
                elif self.path == "/api/settings":
                    self._json(app.update_settings(body))
                else:
                    self._json({"error": "接口不存在。"}, 404)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, 400)
            except KeyError as exc:
                self._json({"error": str(exc)}, 404)
            except Exception:
                self._json({"error": "服务端错误，请检查本机控制台。"}, 500)
    return Handler


def main():
    app = Application()
    if app.config["host"] not in {"127.0.0.1", "localhost"}:
        raise ValueError("首版只支持本机运行，请将host设为127.0.0.1。")
    server = ThreadingHTTPServer((app.config["host"], int(app.config["port"])), make_handler(app))
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"DC/AC Agent v0.1\nLocal: {url}\nMATLAB: {app.runtime.status()['executable'] or 'not found'}\nCtrl+C to stop.", flush=True)
    if os.getenv("DCAC_OPEN_BROWSER") == "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with app.agent.lock:
            for job in app.agent.jobs.values():
                job["cancel"].set()
        server.server_close()
        app.agent.pool.shutdown(wait=True, cancel_futures=True)


if __name__ == "__main__":
    main()
