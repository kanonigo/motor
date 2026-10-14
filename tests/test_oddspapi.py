import json
from pathlib import Path

import pandas as pd
import pytest

from motor.ingest.oddspapi import OddsPapiClient, flatten_historical, price_at

FIX = Path(__file__).parent / "fixtures" / "oddspapi_historical_sample.json"
NOW = pd.Timestamp("2026-10-14T16:00:00Z")


@pytest.fixture
def odds() -> pd.DataFrame:
    return flatten_historical(json.loads(FIX.read_text()), NOW)


def test_flatten_one_row_per_price_change(odds):
    assert len(odds) == 5
    assert set(odds["bookmaker"]) == {"pinnacle", "winamax.es"}
    assert odds["created_at"].dt.tz is not None
    assert (odds["fixture_id"] == "id1000001").all()


def test_flatten_accepts_unwrapped_payload():
    payload = json.loads(FIX.read_text())["id1000001"] | {"fixtureId": "id1000001"}
    assert len(flatten_historical(payload, NOW)) == 5


def test_price_at_uses_only_past_prices(odds):
    # alineaciones a las 18:00 -> la cuota tomable es la anterior, no la de las 18:10
    snap = price_at(odds, pd.Timestamp("2025-08-15T18:00:00Z"))
    wmx = snap[snap["bookmaker"] == "winamax.es"].iloc[0]
    pin = snap[snap["bookmaker"] == "pinnacle"].iloc[0]
    assert wmx["price"] == pytest.approx(1.80)
    assert pin["price"] == pytest.approx(2.05)
    assert (snap["created_at"] <= pd.Timestamp("2025-08-15T18:00:00Z")).all()


def test_price_at_before_any_quote_is_empty(odds):
    assert price_at(odds, pd.Timestamp("2025-08-14T00:00:00Z")).empty


def test_client_requires_key(monkeypatch):
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ODDSPAPI_API_KEY"):
        OddsPapiClient()


def test_historical_rejects_too_many_books(monkeypatch):
    c = OddsPapiClient(api_key="x")
    with pytest.raises(ValueError):
        c.historical_odds("id1", ["a", "b", "c", "d"])
