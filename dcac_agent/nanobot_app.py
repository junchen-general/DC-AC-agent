"""Optional Nanobot runtime. One isolated runtime per job; Store owns history."""
from __future__ import annotations

import asyncio
import json
from importlib.metadata import version, PackageNotFoundError

from .config import WORK
from .nanobot_tools import build_tools


def runtime_status():
    try:
        installed = version("nanobot-ai")
        return {"installed": True, "version": installed, "supported": installed == "0.3.5"}
    except PackageNotFoundError:
        return {"installed": False, "version": None, "supported": False}


def run_nanobot(service, job, text, settings):
    status = runtime_status()
    if not status["supported"]:
        raise RuntimeError("请使用项目虚拟环境并安装 nanobot-ai==0.3.5；也可切换为规则或兼容接口模式。")
    return asyncio.run(_run(service, job, text, settings))


async def _run(service, job, text, settings):
    from nanobot import Nanobot
    from .agent import SYSTEM, TOOLS

    workspace = WORK / "nanobot" / job["session_id"] / job["id"] / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text(SYSTEM, encoding="utf-8")
    from nanobot.config.schema import Config
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.tools.registry import ToolRegistry
    config = Config(**{
        "agents": {"defaults": {"workspace": str(workspace), "model": settings["model"],
            "provider": "openai", "max_tool_iterations": min(12, max(1, int(settings.get("max_iterations", 8)))),
            "temperature": 0.0}},
        "providers": {"openai": {"api_key": settings["api_key"], "api_base": settings["base_url"], "api_type": "chat_completions"}},
        "tools": {"restrict_to_workspace": True},
    })
    config.bind_source_path(workspace.parent / "runtime.json")
    bot = Nanobot(AgentLoop.from_config(config, tool_registry=ToolRegistry()), config=config)
    registry = bot._loop.tools
    for name in list(registry.tool_names):
        registry.unregister(name)
    for tool in build_tools(service, job, TOOLS):
        registry.register(tool)
    session = service.store.snapshot(job["session_id"])
    context = json.dumps({"spec": session["spec"], "revision": session["revision"],
                          "history": session["messages"][-16:]}, ensure_ascii=False)
    service._emit(job, "mode", "Nanobot 0.3.5 工具调用", {"tools": registry.tool_names})
    task = asyncio.create_task(bot.run(SYSTEM + "\n当前上下文：" + context + "\n本次需求：" + text,
        session_key=job["id"], channel="dcac", chat_id=job["session_id"], sender_id="user", ephemeral=True))
    try:
        started = asyncio.get_running_loop().time()
        while not task.done():
            if asyncio.get_running_loop().time() - started > 1200:
                job["cancel"].set()
            if job["cancel"].is_set():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise InterruptedError("任务已取消。")
            await asyncio.sleep(.1)
        try:
            reply = await task
        except asyncio.CancelledError:
            raise InterruptedError("Nanobot任务已取消。") from None
        if getattr(reply, "error", None):
            raise RuntimeError(reply.error)
        return getattr(reply, "content", "") or "本轮没有文本回复，请查看执行记录。"
    finally:
        if not task.done():
            task.cancel()
        await bot._loop.aclose()
