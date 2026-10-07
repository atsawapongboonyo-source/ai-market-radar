from trigger_monitor import classify_trigger


def test_trigger_below_resets_hits():
    x = classify_trigger(99, 100, 105, 1)
    assert x["state"] == "BELOW_TRIGGER"
    assert x["hits"] == 0


def test_trigger_requires_two_consecutive_hits():
    first = classify_trigger(100.5, 100, 105, 0)
    assert first["state"] == "TRIGGER_TOUCHED"
    second = classify_trigger(101, 100, 105, first["hits"])
    assert second["state"] == "TRIGGER_CONFIRMED"


def test_trigger_blocks_chasing():
    x = classify_trigger(106, 100, 105, 1)
    assert x["state"] == "DONT_CHASE"
