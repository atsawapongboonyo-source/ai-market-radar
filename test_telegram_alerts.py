from telegram_alerts import build_entry_message


def test_entry_message_contains_core_fields():
    msg = build_entry_message({
        "ticker": "MU",
        "entry": 1038.2,
        "buy_low": 1036.27,
        "buy_high": 1051.24,
        "score": 78,
        "opening": "ENTRY1",
        "market": "bull",
        "group": "bull",
    })
    assert "AI RADAR" in msg
    assert "MU" in msg
    assert "$1,038.20" in msg
    assert "$1,036.27" in msg
    assert "$1,051.24" in msg
    assert "78/100" in msg
