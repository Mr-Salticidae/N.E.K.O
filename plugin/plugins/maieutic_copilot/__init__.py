from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plugin.sdk.plugin import NekoPluginBase, Ok, lifecycle, message, neko_plugin, plugin_entry

from .engine import build_co_learn_draft, detect_trigger, extract_message_text


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@neko_plugin
class MaieuticCopilotPlugin(NekoPluginBase):
    def __init__(self, ctx: Any) -> None:
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._cfg: dict[str, Any] = {}

    @lifecycle(id="startup")
    async def startup(self, **_: Any):
        raw = _as_mapping(await self.config.dump(timeout=5.0))
        self._cfg = _as_mapping(raw.get("maieutic"))
        return Ok(
            {
                "status": "ready",
                "summary": "Maieutic Copilot ready. It will stay hidden until a learning, judgment, or creative-transfer question appears.",
                "push_on_message": self._push_on_message,
                "knowledge_base_root": self._knowledge_base_root,
            }
        )

    @property
    def _knowledge_base_root(self) -> str:
        return str(self._cfg.get("knowledge_base_root") or "D:/AIGC工作站/知识库")

    @property
    def _push_on_message(self) -> bool:
        return bool(self._cfg.get("push_on_message", True))

    @plugin_entry(
        id="co_learn",
        name="共学澄清",
        description="为学习困惑、方向判断或创作迁移问题生成隐性的 Maieutic 共学建议，供猫娘转述。",
        llm_result_fields=["summary", "message", "insight", "beacon"],
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "用户当前想学习、澄清或迁移到创作中的问题。"},
                "force": {"type": "boolean", "description": "是否即使没有触发关键词也生成共学闭环。", "default": True},
                "push": {"type": "boolean", "description": "是否把建议推入 LLM 上下文，让猫娘自然回应。", "default": False},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
        metadata={"agent_auto": False},
    )
    async def co_learn(self, question: str, force: bool = True, push: bool = False, **_: Any):
        draft = build_co_learn_draft(
            question,
            knowledge_base_root=self._knowledge_base_root,
            force=force,
        )
        payload = draft.as_dict()
        if push and draft.triggered:
            self._push_draft(draft.message, entry_id="co_learn", trigger_kind=draft.trigger_kind)
        return Ok(payload)

    @message(
        id="maieutic_message_listener",
        name="Maieutic message listener",
        description="Listens for learning confusion, judgment, and creative-learning messages without taking over ordinary chat.",
        metadata={"agent_auto": False},
    )
    async def on_message(self, **payload: Any):
        text = extract_message_text(payload)
        trigger_kind = detect_trigger(text)
        if trigger_kind == "none":
            return Ok({"triggered": False, "summary": "未触发 Maieutic 共学闭环。"})

        draft = build_co_learn_draft(
            text,
            knowledge_base_root=self._knowledge_base_root,
            force=False,
        )
        if self._push_on_message and draft.triggered:
            self._push_draft(
                draft.message,
                entry_id="maieutic_message_listener",
                trigger_kind=draft.trigger_kind,
            )
        return Ok(draft.as_dict())

    def _push_draft(self, text: str, *, entry_id: str, trigger_kind: str) -> None:
        self.push_message(
            visibility=[],
            ai_behavior="respond",
            parts=[{"type": "text", "text": text}],
            source="maieutic_copilot",
            metadata={
                "entry_id": entry_id,
                "trigger_kind": trigger_kind,
                "delivery_semantics": "passive",
                "persona_policy": "hidden_maieutic_catgirl",
            },
        )
