from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from plugin.core.state import state
from plugin.logging_config import get_logger
from plugin.server.domain import RUNTIME_ERRORS
from plugin.server.domain.errors import ServerDomainError

logger = get_logger("server.application.plugins.dispatch")


@runtime_checkable
class HostHealthContract(Protocol):
    alive: bool


@runtime_checkable
class PluginDispatchHostContract(Protocol):
    def health_check(self) -> HostHealthContract: ...

    async def trigger_custom_event(
        self,
        *,
        event_type: str,
        event_id: str,
        args: dict[str, object],
        timeout: float,
    ) -> object: ...


def _iter_message_consumers() -> list[tuple[str, str]]:
    handlers_snapshot = state.get_event_handlers_snapshot_cached(timeout=1.0)
    consumers: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for event_key_obj in handlers_snapshot:
        if not isinstance(event_key_obj, str):
            continue
        parts = event_key_obj.split(":", 2)
        if len(parts) != 3:
            continue
        plugin_id, event_type, event_id = parts
        if not plugin_id or event_type != "message" or not event_id:
            continue
        item = (plugin_id, event_id)
        if item in seen:
            continue
        seen.add(item)
        consumers.append(item)
    return consumers


def _resolve_host(plugin_id: str) -> PluginDispatchHostContract:
    hosts_snapshot = state.get_plugin_hosts_snapshot_cached(timeout=1.0)
    host_obj = hosts_snapshot.get(plugin_id)
    if not isinstance(host_obj, PluginDispatchHostContract):
        raise ServerDomainError(
            code="PLUGIN_NOT_FOUND",
            message=f"Plugin '{plugin_id}' not found",
            status_code=404,
            details={"plugin_id": plugin_id},
        )
    return host_obj


def _normalize_args(raw_args: object) -> dict[str, object]:
    if raw_args is None:
        return {}
    if not isinstance(raw_args, Mapping):
        raise ServerDomainError(
            code="INVALID_ARGUMENT",
            message="args must be an object",
            status_code=400,
            details={},
        )
    normalized: dict[str, object] = {}
    for key, value in raw_args.items():
        if not isinstance(key, str):
            raise ServerDomainError(
                code="INVALID_ARGUMENT",
                message="args keys must be strings",
                status_code=400,
                details={"key_type": type(key).__name__},
            )
        normalized[key] = value
    return normalized


class PluginDispatchService:
    async def dispatch_message(
        self,
        *,
        args: object,
        timeout: float,
    ) -> dict[str, object]:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or float(timeout) <= 0
        ):
            raise ServerDomainError(
                code="INVALID_ARGUMENT",
                message="timeout must be a positive finite number",
                status_code=400,
                details={},
            )

        consumers = await asyncio.to_thread(_iter_message_consumers)
        normalized_args = _normalize_args(args)
        results: list[dict[str, object]] = []

        async def _dispatch_one(plugin_id: str, event_id: str) -> None:
            try:
                host = await asyncio.to_thread(_resolve_host, plugin_id)
                health = await asyncio.to_thread(host.health_check)
                if not bool(health.alive):
                    results.append(
                        {
                            "plugin_id": plugin_id,
                            "event_id": event_id,
                            "success": False,
                            "error": "plugin process is not alive",
                        }
                    )
                    return
                data = await host.trigger_custom_event(
                    event_type="message",
                    event_id=event_id,
                    args=normalized_args,
                    timeout=float(timeout),
                )
                results.append(
                    {
                        "plugin_id": plugin_id,
                        "event_id": event_id,
                        "success": True,
                        "data": data,
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive fanout
                logger.debug(
                    "dispatch_message consumer failed: plugin_id={}, event_id={}, err_type={}, err={}",
                    plugin_id,
                    event_id,
                    type(exc).__name__,
                    str(exc),
                )
                results.append(
                    {
                        "plugin_id": plugin_id,
                        "event_id": event_id,
                        "success": False,
                        "error": str(exc),
                    }
                )

        await asyncio.gather(*(_dispatch_one(plugin_id, event_id) for plugin_id, event_id in consumers))
        delivered = sum(1 for item in results if item.get("success"))
        return {
            "success": True,
            "consumer_count": len(consumers),
            "delivered_count": delivered,
            "results": results,
        }

    async def trigger_custom_event(
        self,
        *,
        to_plugin: str,
        event_type: str,
        event_id: str,
        args: object,
        timeout: float,
    ) -> object:
        if not to_plugin:
            raise ServerDomainError(
                code="INVALID_ARGUMENT",
                message="to_plugin is required",
                status_code=400,
                details={},
            )
        if not event_type:
            raise ServerDomainError(
                code="INVALID_ARGUMENT",
                message="event_type is required",
                status_code=400,
                details={},
            )
        if not event_id:
            raise ServerDomainError(
                code="INVALID_ARGUMENT",
                message="event_id is required",
                status_code=400,
                details={},
            )
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or float(timeout) <= 0
        ):
            raise ServerDomainError(
                code="INVALID_ARGUMENT",
                message="timeout must be a positive finite number",
                status_code=400,
                details={},
            )

        try:
            host = await asyncio.to_thread(_resolve_host, to_plugin)
            health = await asyncio.to_thread(host.health_check)
            if not bool(health.alive):
                raise ServerDomainError(
                    code="PLUGIN_NOT_READY",
                    message=f"Plugin '{to_plugin}' process is not alive",
                    status_code=409,
                    details={"plugin_id": to_plugin},
                )
            normalized_args = _normalize_args(args)
            return await host.trigger_custom_event(
                event_type=event_type,
                event_id=event_id,
                args=normalized_args,
                timeout=timeout,
            )
        except ServerDomainError:
            raise
        except RUNTIME_ERRORS as exc:
            logger.error(
                "trigger_custom_event failed: to_plugin={}, event_type={}, event_id={}, err_type={}, err={}",
                to_plugin,
                event_type,
                event_id,
                type(exc).__name__,
                str(exc),
            )
            raise ServerDomainError(
                code="PLUGIN_EVENT_DISPATCH_FAILED",
                message="Failed to dispatch plugin event",
                status_code=500,
                details={"error_type": type(exc).__name__, "to_plugin": to_plugin},
            ) from exc
