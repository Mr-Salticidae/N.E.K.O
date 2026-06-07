from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Literal


TriggerKind = Literal["confusion", "judgment", "creative_learning", "none"]
PathKind = Literal["structure", "challenge"]


CONFUSION_KEYWORDS = (
    "没懂",
    "不懂",
    "卡住",
    "迷茫",
    "困惑",
    "不知道从哪",
    "从哪开始",
    "怎么理解",
    "怎么学",
    "学不会",
    "解释一下",
    "what is",
    "how to understand",
)

JUDGMENT_KEYWORDS = (
    "对不对",
    "该选哪个",
    "选哪个",
    "有价值吗",
    "值不值得",
    "行不行",
    "方向",
    "判断",
    "要不要",
    "worth",
    "should i",
)

CREATIVE_KEYWORDS = (
    "作品",
    "创作",
    "AIGC",
    "视频",
    "prompt",
    "提示词",
    "复盘",
    "工作流",
    "项目",
    "插件",
    "skill",
    "知识库",
    "方法论",
    "怎么用到",
    "应用到",
)

CASUAL_KEYWORDS = (
    "早上好",
    "晚上好",
    "你好",
    "哈哈",
    "谢谢",
    "辛苦",
    "天气",
)


@dataclass(frozen=True)
class KnowledgeBaseContext:
    root: str
    available: bool
    readme_seen: bool
    skill_index_seen: bool
    markdown_count: int
    principle: str


@dataclass(frozen=True)
class CoLearnDraft:
    triggered: bool
    trigger_kind: TriggerKind
    path: PathKind | None
    summary: str
    opening: str
    guidance: str
    insight: str
    beacon: str
    message: str
    knowledge_base: KnowledgeBaseContext

    def as_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "trigger_kind": self.trigger_kind,
            "path": self.path,
            "summary": self.summary,
            "opening": self.opening,
            "guidance": self.guidance,
            "insight": self.insight,
            "beacon": self.beacon,
            "message": self.message,
            "knowledge_base": {
                "root": self.knowledge_base.root,
                "available": self.knowledge_base.available,
                "readme_seen": self.knowledge_base.readme_seen,
                "skill_index_seen": self.knowledge_base.skill_index_seen,
                "markdown_count": self.knowledge_base.markdown_count,
                "principle": self.knowledge_base.principle,
            },
        }


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def detect_trigger(text: str) -> TriggerKind:
    normalized = normalize_text(text)
    lower = normalized.lower()
    if not normalized:
        return "none"
    if len(normalized) <= 12 and any(keyword in normalized for keyword in CASUAL_KEYWORDS):
        return "none"
    if any(keyword.lower() in lower for keyword in CREATIVE_KEYWORDS) and any(
        keyword.lower() in lower for keyword in CONFUSION_KEYWORDS + JUDGMENT_KEYWORDS
    ):
        return "creative_learning"
    if any(keyword.lower() in lower for keyword in JUDGMENT_KEYWORDS):
        return "judgment"
    if any(keyword.lower() in lower for keyword in CONFUSION_KEYWORDS):
        return "confusion"
    if any(keyword.lower() in lower for keyword in CREATIVE_KEYWORDS) and any(
        marker in lower for marker in ("学习", "理解", "learn", "study", "用到", "应用")
    ):
        return "creative_learning"
    return "none"


def choose_path(trigger_kind: TriggerKind, text: str) -> PathKind | None:
    if trigger_kind == "none":
        return None
    lower = normalize_text(text).lower()
    if trigger_kind == "judgment" or any(marker in lower for marker in ("目标", "程度", "够用", "要不要")):
        return "challenge"
    return "structure"


def load_knowledge_base_context(root: str | Path | None) -> KnowledgeBaseContext:
    root_text = str(root or "").strip()
    if not root_text:
        return KnowledgeBaseContext(
            root="",
            available=False,
            readme_seen=False,
            skill_index_seen=False,
            markdown_count=0,
            principle="知识库原则未配置；按 Maieutic v0 的共学规则运行。",
        )

    root_path = Path(root_text)
    available = root_path.exists() and root_path.is_dir()
    readme_seen = (root_path / "README.md").exists() if available else False
    skill_index_seen = (root_path / "SKILL_INDEX.md").exists() if available else False
    markdown_count = 0
    if available:
        try:
            markdown_count = sum(1 for _ in root_path.rglob("*.md"))
        except OSError:
            markdown_count = 0

    if readme_seen:
        principle = "知识库是 insight 归档，不是素材包；学习结果应沉淀为可复用判断、流程或规则。"
    else:
        principle = "未读取到知识库 README；按 Maieutic v0 的共学规则运行。"

    return KnowledgeBaseContext(
        root=root_text,
        available=available,
        readme_seen=readme_seen,
        skill_index_seen=skill_index_seen,
        markdown_count=markdown_count,
        principle=principle,
    )


def build_co_learn_draft(
    question: Any,
    *,
    knowledge_base_root: str | Path | None = None,
    force: bool = True,
) -> CoLearnDraft:
    text = normalize_text(question)
    trigger_kind = detect_trigger(text)
    if force and trigger_kind == "none":
        trigger_kind = "confusion"
    path = choose_path(trigger_kind, text)
    kb = load_knowledge_base_context(knowledge_base_root)

    if trigger_kind == "none":
        return CoLearnDraft(
            triggered=False,
            trigger_kind="none",
            path=None,
            summary="未触发 Maieutic 共学闭环。",
            opening="",
            guidance="",
            insight="",
            beacon="",
            message="",
            knowledge_base=kb,
        )

    subject = _derive_subject(text)
    opening = f"嗯，我陪你一起拆开看。先别急着找答案，我们先把「{subject}」这个问题摆正。"
    if path == "challenge":
        guidance = (
            "这里先轻轻挑战一下：你现在问的表面上是方向判断，真正要确认的是"
            "「它要服务什么学习结果或创作判断」。如果目标只是知道概念，答案会很散；"
            "如果目标是用它做项目，我们就要看它能不能改变你的下一步选择。"
        )
    else:
        guidance = (
            "我们把它拆成三层：第一层是概念本身是什么，第二层是它解决什么问题，"
            "第三层是它在你的作品或工作流里能变成什么判断动作。先分层，后面才不会越学越乱。"
        )

    if trigger_kind == "judgment":
        insight = f"Insight：这个问题的关键不是先判定「{subject}」好不好，而是看它能不能产生一个更清晰的创作取舍标准。"
    elif trigger_kind == "confusion":
        insight = f"Insight：你卡住的不是「{subject}」这个词本身，而是还没把定义、用途和可操作动作分开。"
    else:
        insight = f"Insight：这个知识点真正有用的地方，是把「{subject}」变成你做作品时的一个判断维度，而不只是会解释它。"

    beacon = (
        "Beacon：24 小时内拿一个正在做或想做的小项目，写下三行："
        "这个概念帮我判断什么、它会改变哪个创作选择、这次理解能沉淀成哪条可复用规则。"
    )

    message = "\n\n".join((opening, guidance, insight, beacon))
    return CoLearnDraft(
        triggered=True,
        trigger_kind=trigger_kind,
        path=path,
        summary=f"已生成 Maieutic 共学建议：{trigger_kind}/{path}。",
        opening=opening,
        guidance=guidance,
        insight=insight,
        beacon=beacon,
        message=message,
        knowledge_base=kb,
    )


def extract_message_text(payload: dict[str, Any]) -> str:
    for key in ("text", "content", "message", "query", "question", "user_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    parts = payload.get("parts")
    if isinstance(parts, list):
        texts = [
            str(part.get("text", "")).strip()
            for part in parts
            if isinstance(part, dict) and str(part.get("type", "text")) == "text"
        ]
        return "\n".join(text for text in texts if text)
    return ""


def _derive_subject(text: str) -> str:
    cleaned = normalize_text(text)
    if not cleaned:
        return "这个学习点"
    cleaned = re.sub(r"^(我想|我在|我把|帮我|请你|想要|想)\s*", "", cleaned)
    cleaned = re.sub(r"(但|但是|不过|可是).*?$", "", cleaned)
    cleaned = re.sub(r"(到底|怎么理解|怎么学|从哪开始|有价值吗|对不对|值不值得|行不行)", "", cleaned)
    cleaned = cleaned.strip(" ，。？！?!.")
    if not cleaned:
        return "这个学习点"
    return cleaned[:32]
