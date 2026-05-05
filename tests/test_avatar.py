"""アバター URL 解決ロジックのテスト。"""
from types import SimpleNamespace

from utils.avatar import (
    discord_avatar_url,
    resolve_avatar_url,
    twitter_avatar_url,
)


def _member(url: str | None) -> SimpleNamespace | None:
    if url is None:
        return None
    return SimpleNamespace(display_avatar=SimpleNamespace(url=url))


def test_twitter_avatar_url():
    assert twitter_avatar_url("@foo") == "https://unavatar.io/x/foo"
    assert twitter_avatar_url("foo") == "https://unavatar.io/x/foo"
    assert twitter_avatar_url(None) is None
    assert twitter_avatar_url("") is None


def test_discord_avatar_url():
    assert discord_avatar_url(_member("https://cdn.example/x.png")) == "https://cdn.example/x.png"
    assert discord_avatar_url(None) is None


def test_resolve_twitter_priority_uses_twitter():
    url = resolve_avatar_url(
        source="twitter",
        twitter_id="@foo",
        member=_member("https://cdn.example/x.png"),
    )
    assert url == "https://unavatar.io/x/foo"


def test_resolve_twitter_priority_falls_back_to_discord():
    url = resolve_avatar_url(
        source="twitter",
        twitter_id=None,
        member=_member("https://cdn.example/x.png"),
    )
    assert url == "https://cdn.example/x.png"


def test_resolve_discord_priority_uses_discord():
    url = resolve_avatar_url(
        source="discord",
        twitter_id="@foo",
        member=_member("https://cdn.example/x.png"),
    )
    assert url == "https://cdn.example/x.png"


def test_resolve_discord_priority_falls_back_to_twitter():
    url = resolve_avatar_url(source="discord", twitter_id="@foo", member=None)
    assert url == "https://unavatar.io/x/foo"


def test_resolve_returns_none_when_nothing_available():
    assert resolve_avatar_url(source="twitter", twitter_id=None, member=None) is None
    assert resolve_avatar_url(source="discord", twitter_id=None, member=None) is None
