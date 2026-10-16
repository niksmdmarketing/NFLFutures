import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import trust as T  # noqa: E402

SC = {"gain": 0.03, "base": 0.10}            # 30% skill
SL = {"slope": 1.0, "ll": 0.07, "ll_recal": 0.069}


def test_rules():
    assert T.rate(SC, SL, 14, "playoff", "third quarter")[0] == "Reliable"
    assert T.rate(SC, SL, 4, "playoff", "third quarter")[0] == "Mixed"                      # thin evidence
    assert T.rate(SC, SL, 14, "title", "third quarter")[0] == "Mixed"                       # few winners, no interval
    assert T.rate(SC, SL, 14, "title", "third quarter", ci={("third quarter", "title"): (0.8, 1.3)})[0] == "Reliable"
    assert T.rate({"gain": 0.005, "base": 0.1}, SL, 14, "div", "preseason")[0] == "Weak"
    assert T.rate(SC, {"slope": 1.6, "ll": 0.08, "ll_recal": 0.07}, 14, "div", "preseason")[0] == "Mixed"   # miscalibrated
    assert T.rate(SC, SL, 14, "div", "preseason", market_note="x.")[0] == "Market usually better"
    assert T.rate(None, None, 0, None, "preseason")[0] == "Not tested"
    assert [T.stage_of(x) for x in (0, 0.1, 0.3, 0.6, 0.9, 1.2)] == ["preseason", "first quarter", "second quarter", "third quarter", "last quarter", "last quarter"]
