from pathlib import Path

import pandas as pd
import pytest

from motor.ingest.football_data import parse

FIX = Path(__file__).parent / "fixtures" / "fd_sp1_sample.csv"
NOW = pd.Timestamp("2026-10-14T16:00:00Z")


@pytest.fixture
def df() -> pd.DataFrame:
    return parse(FIX.read_text(), "laliga", "2526", NOW)


def test_one_row_per_match_and_stable_id(df):
    assert len(df) == 3
    assert df["match_id"].is_unique
    assert df.loc[0, "match_id"] == "laliga_2025-08-15_Girona_Vallecano"


def test_columns_normalised(df):
    row = df.iloc[1]
    assert (row["home_shots"], row["home_sot"], row["away_reds"]) == (22, 9, 1)
    assert row["ps_close_home"] == pytest.approx(1.18)
    assert row["ah_line_close"] == pytest.approx(-2.25)


def test_odds_flagged_without_capture_time(df):
    # sin hora de captura: no vale como cuota "a T-60" en el backtest
    assert not df["odds_time_known"].any()
    assert (df["captured_at"] == NOW).all()


def test_quality_flags(df):
    # Sevilla: 2 goles con 1 a puerta -> posible gol en propia, se marca, no se borra
    assert df.loc[2, "flag_home_goals_gt_sot"]
    assert not df["flag_home_sot_gt_shots"].any()
    assert df["flag_missing_pinnacle_close"].tolist() == [False, False, True]


def test_missing_required_column_fails():
    text = FIX.read_text().replace("HST", "XXX", 1)
    with pytest.raises(ValueError, match="HST"):
        parse(text, "laliga", "2526", NOW)


def test_mirror_format_real_rows():
    # primeras filas reales del espejo de GitHub: fechas ISO, sin cuotas
    text = (Path(__file__).parent / "fixtures" / "fd_mirror_sp1_2324_head.csv").read_text()
    df = parse(text, "laliga", "2324", NOW, source="mirror")
    assert len(df) == 5
    assert str(df.loc[0, "match_date"]) == "2023-08-11"
    assert df["ps_close_home"].isna().all()
    assert df["flag_missing_pinnacle_close"].all()
