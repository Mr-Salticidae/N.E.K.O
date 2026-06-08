from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugin.server.application.plugins import dispatch_service as module
from plugin.server.application.plugins.dispatch_service import PluginDispatchService


class _Host:
    alive = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object], float]] = []

    def health_check(self) -> SimpleNamespace:
        return SimpleNamespace(alive=True)

    async def trigger_custom_event(
        self,
        *,
        event_type: str,
        event_id: str,
        args: dict[str, object],
        timeout: float,
    ) -> dict[str, object]:
        self.calls.append((event_type, event_id, args, timeout))
        return {"handled": True}


@pytest.mark.plugin_unit
@pytest.mark.asyncio
async def test_dispatch_message_fans_out_to_message_consumers_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _Host()
    monkeypatch.setattr(
        module.state,
        "get_event_handlers_snapshot_cached",
        lambda timeout=1.0: {
            "maieutic_copilot:message:maieutic_message_listener": object(),
            "maieutic_copilot:plugin_entry:co_learn": object(),
            "other_plugin:timer:tick": object(),
        },
    )
    monkeypatch.setattr(
        module.state,
        "get_plugin_hosts_snapshot_cached",
        lambda timeout=1.0: {"maieutic_copilot": host},
    )

    response = await PluginDispatchService().dispatch_message(
        args={"text": "我卡住了"},
        timeout=2.5,
    )

    assert response["success"] is True
    assert response["consumer_count"] == 1
    assert response["delivered_count"] == 1
    assert host.calls == [
        ("message", "maieutic_message_listener", {"text": "我卡住了"}, 2.5)
    ]
