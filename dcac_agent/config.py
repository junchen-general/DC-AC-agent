from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
WORK = ROOT / "work"


def load_config() -> dict:
    config = {
        "host": "127.0.0.1", "port": 7862,
        "matlab_executable": shutil.which("matlab") or "",
        "matlab_timeout_seconds": 300,
        "llm": {"enabled": False, "base_url": "https://api.openai.com/v1",
                "model": "", "api_key": "", "max_iterations": 8},
    }
    path = ROOT / "config.json"
    if path.exists():
        values = json.loads(path.read_text(encoding="utf-8-sig"))
        config.update({k: v for k, v in values.items() if k != "llm"})
        config["llm"].update(values.get("llm", {}))
    for key, env in (("api_key", "LLM_API_KEY"), ("base_url", "LLM_BASE_URL"), ("model", "LLM_MODEL")):
        if os.getenv(env):
            config["llm"][key] = os.environ[env]
    if os.getenv("LLM_API_KEY"):
        config["llm"]["enabled"] = True
    if os.getenv("DCAC_MATLAB"):
        config["matlab_executable"] = os.environ["DCAC_MATLAB"]
    config["port"] = int(os.getenv("DCAC_PORT", config["port"]))
    return config


def public_config(config: dict) -> dict:
    result = copy.deepcopy(config)
    result["llm"]["api_key"] = ""
    result["llm"]["has_api_key"] = bool(config["llm"].get("api_key"))
    return result
