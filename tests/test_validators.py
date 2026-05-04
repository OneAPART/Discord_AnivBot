import pytest

from utils.validators import normalize_twitter, parse_md, parse_ymd, twitter_url


# --- Twitter ---
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@example", "@example"),
        ("example", "@example"),
        ("  user_1  ", "@user_1"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_twitter_ok(raw, expected):
    assert normalize_twitter(raw) == expected


@pytest.mark.parametrize("raw", ["bad-name!", "a" * 16, "日本語"])
def test_normalize_twitter_ng(raw):
    with pytest.raises(ValueError):
        normalize_twitter(raw)


def test_twitter_url():
    assert twitter_url("@foo") == "https://x.com/foo"


# --- MM/DD ---
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("04/15", (4, 15)),
        ("4/1", (4, 1)),
        ("12-31", (12, 31)),
        ("2.29", (2, 29)),  # うるう日も MM/DD としては許可
    ],
)
def test_parse_md_ok(raw, expected):
    assert parse_md(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["13/01", "00/10", "04/31", "abc", "1", "2025/04/15"],
)
def test_parse_md_ng(raw):
    with pytest.raises(ValueError):
        parse_md(raw)


# --- YYYY/MM/DD ---
def test_parse_ymd_ok():
    assert parse_ymd("2018/04/15") == (2018, 4, 15)
    assert parse_ymd("2020-02-29") == (2020, 2, 29)  # うるう年


@pytest.mark.parametrize(
    "raw",
    [
        "2019/02/29",  # 平年に29日
        "1899/01/01",  # 古すぎる
        "2999/01/01",  # 未来
        "2020/13/01",
        "04/15",
    ],
)
def test_parse_ymd_ng(raw):
    with pytest.raises(ValueError):
        parse_ymd(raw)
