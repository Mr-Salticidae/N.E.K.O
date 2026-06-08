from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from config import USER_PLUGIN_BASE
from utils.logger_config import get_module_logger

logger = get_module_logger(__name__, "UserPluginMessageBridge")

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="plugin-message-bridge")
_LAST_ERROR_AT = 0.0
_ERROR_LOG_INTERVAL_SECONDS = 30.0


def _resolve_user_plugin_base() -> str:
    raw_port = os.getenv("NEKO_USER_PLUGIN_SERVER_PORT", "").strip()
    if raw_port:
        try:
            port = int(raw_port)
            if 0 < port <= 65535:
                return f"http://127.0.0.1:{port}"
        except ValueError:
            pass
    return USER_PLUGIN_BASE.rstrip("/")


def _post_text_message(lanlan_name: str, text: str) -> None:
    global _LAST_ERROR_AT

    body = json.dumps(
        {
            "args": {
                "text": text,
                "content": text,
                "message": {"type": "text", "text": text},
                "lanlan_name": lanlan_name,
                "source": "main_chat",
            },
            "timeout": 3.0,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{_resolve_user_plugin_base()}/plugins/messages/dispatch",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3.5) as response:
            response.read(256)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        now = time.time()
        if now - _LAST_ERROR_AT >= _ERROR_LOG_INTERVAL_SECONDS:
            _LAST_ERROR_AT = now
            logger.debug("failed to dispatch user text to plugin message consumers: %s", exc)


def dispatch_user_text_to_plugin_messages(lanlan_name: str, text: str) -> dict[str, Any] | None:
    clean_text = str(text or "").strip()
    if not clean_text:
        return None
    try:
        _EXECUTOR.submit(_post_text_message, str(lanlan_name or ""), clean_text)
    except RuntimeError as exc:
        logger.debug("plugin message bridge executor unavailable: %s", exc)
    return None


def shutdown_user_plugin_message_bridge() -> None:
    if threading.current_thread() is threading.main_thread():
        _EXECUTOR.shutdown(wait=False, cancel_futures=True)
