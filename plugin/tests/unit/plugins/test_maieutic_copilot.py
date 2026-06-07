from plugin.plugins.maieutic_copilot.engine import (
    build_co_learn_draft,
    detect_trigger,
    extract_message_text,
)


def test_manual_entry_builds_full_learning_loop() -> None:
    draft = build_co_learn_draft(
        "我想理解 N.E.K.O 插件机制，但不知道从哪开始。",
        knowledge_base_root="D:/AIGC工作站/知识库",
    )

    assert draft.triggered is True
    assert draft.trigger_kind == "creative_learning"
    assert draft.path == "structure"
    assert "我陪你一起拆开看" in draft.message
    assert "Insight" in draft.insight
    assert "Beacon" in draft.beacon
    assert "24 小时" in draft.beacon


def test_judgment_trigger_uses_challenge_path() -> None:
    draft = build_co_learn_draft("我把 Maieutic 做进猫娘里，这个方向有价值吗？")

    assert draft.trigger_kind == "judgment"
    assert draft.path == "challenge"
    assert "轻轻挑战" in draft.guidance


def test_creative_transfer_points_to_creative_judgment() -> None:
    draft = build_co_learn_draft("我想把这个概念用到我的 AIGC 视频创作里。")

    assert draft.trigger_kind == "creative_learning"
    assert "作品时的一个判断维度" in draft.insight
    assert "小项目" in draft.beacon


def test_non_trigger_does_not_force_when_message_listener_path() -> None:
    draft = build_co_learn_draft("早上好，谢谢你。", force=False)

    assert draft.triggered is False
    assert draft.message == ""


def test_extract_message_text_reads_parts() -> None:
    assert extract_message_text({"parts": [{"type": "text", "text": "我卡住了"}]}) == "我卡住了"


def test_trigger_detection_for_confusion() -> None:
    assert detect_trigger("我卡住了，AI Native 游戏到底和普通 AI NPC 有什么区别？") == "confusion"
