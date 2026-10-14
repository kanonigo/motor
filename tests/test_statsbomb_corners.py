import pandas as pd
import pytest

from motor.ingest.statsbomb import corners_from_events, shots_from_events
from motor.priors.corners import conversion_by_funnel, other_corners


def _ev(i, typ, team, minute, second=0, period=1, **kw):
    e = {"id": f"e{i}", "type": {"name": typ}, "team": {"id": team, "name": f"T{team}"},
         "minute": minute, "second": second, "period": period, "player": {"name": f"p{i}"}}
    e.update(kw)
    return e


def _shot(i, team, minute, outcome, related=()):
    return _ev(i, "Shot", team, minute, related_events=list(related), shot={
        "outcome": {"name": outcome}, "type": {"name": "Open Play"},
        "body_part": {"name": "Right Foot"}, "statsbomb_xg": 0.1})


def _pass(i, team, minute, second=0, corner=False, period=1):
    p = {"type": {"name": "Corner"}} if corner else {}
    return _ev(i, "Pass", team, minute, second, period, **{"pass": p})


EVENTS = [
    _shot(1, 1, 10, "Blocked"), _ev(2, "Clearance", 2, 10, 2), _pass(3, 1, 10, 40, corner=True),   # bloqueo -> córner
    _shot(4, 1, 20, "Saved"), _pass(5, 2, 20, 10),                                                   # parada -> saca el portero
    _shot(6, 2, 30, "Blocked", related=["e7"]),
    _ev(7, "Block", 1, 30, block={"save_block": True}), _pass(8, 2, 31, 50, corner=True),           # bloqueo en línea, córner a los 80 s
    _shot(9, 1, 40, "Goal"), _pass(10, 2, 41),
    _shot(11, 1, 50, "Off T"), _pass(12, 1, 50, 30, period=2, corner=True),                          # cambia de parte: no cuenta
    _shot(13, 1, 120, "Saved", ), _ev(14, "Shot", 1, 0, period=5),                                   # tanda de penaltis: fuera
]


def test_funnel_mapping_and_corner_attribution():
    df = pd.DataFrame(shots_from_events(EVENTS, 99))
    assert df["funnel"].tolist() == ["blocked", "saved", "on_target_dl", "goal", "off", "saved"]
    assert df["corner_next"].tolist() == [True, False, False, False, False, False]  # 80 s > ventana de 60 s


def test_shootout_and_corner_list():
    assert len(shots_from_events(EVENTS, 99)) == 6
    cs = corners_from_events(EVENTS, 99)
    assert [c["team"] for c in cs] == ["T1", "T2", "T1"]


def test_other_corners_never_negative_and_adds_up():
    shots = pd.DataFrame(shots_from_events(EVENTS, 99))
    corners = pd.DataFrame(corners_from_events(EVENTS, 99))
    oc = other_corners(shots, corners).set_index("team")
    assert (oc["corners"] == oc["from_shots"] + oc["other"]).all()
    assert oc.loc["T1", "from_shots"] == 1 and oc.loc["T1", "other"] == 1


def test_conversion_posterior_bounds():
    shots = pd.DataFrame({"funnel": ["blocked"] * 100 + ["saved"] * 50,
                          "corner_next": [True] * 25 + [False] * 75 + [True] * 10 + [False] * 40})
    g = conversion_by_funnel(shots).set_index("funnel")
    assert g.loc["blocked", "p"] == pytest.approx(26 / 102)
    assert g.loc["blocked", "ci90_low"] < 0.25 < g.loc["blocked", "ci90_high"]
