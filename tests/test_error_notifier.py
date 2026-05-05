"""ErrorNotifier ペイロードのスキーマテスト。"""
from utils.error_notifier import build_payload


def test_payload_minimum():
    p = build_payload(level="ERROR", message="hello")
    assert p["bot"] == "AnniversaryBot"
    assert p["level"] == "ERROR"
    assert p["message"] == "hello"
    assert p["exception"] is None
    assert p["context"] == {}
    assert p["timestamp"].endswith("Z")


def test_payload_with_exception():
    try:
        raise ValueError("boom")
    except ValueError as e:
        p = build_payload(level="ERROR", message="oops", exception=e)
    assert p["exception"]["type"] == "ValueError"
    assert p["exception"]["message"] == "boom"
    assert "ValueError: boom" in p["exception"]["traceback"]


def test_payload_with_context():
    p = build_payload(
        level="CRITICAL",
        message="x",
        context={"guild_id": 1, "user_id": 2, "command": "show"},
    )
    assert p["level"] == "CRITICAL"
    assert p["context"]["guild_id"] == 1
    assert p["context"]["command"] == "show"


def test_payload_truncates_huge_traceback(monkeypatch):
    from utils import error_notifier

    monkeypatch.setattr(error_notifier, "_MAX_TRACEBACK_CHARS", 100)
    try:
        raise RuntimeError("x" * 500)
    except RuntimeError as e:
        p = error_notifier.build_payload(level="ERROR", message="m", exception=e)
    assert len(p["exception"]["traceback"]) <= 100 + len("\n... (truncated)")
    assert p["exception"]["traceback"].endswith("(truncated)")
