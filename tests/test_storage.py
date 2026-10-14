import pandas as pd
import pytest

from motor import storage


def _df(n: int, ts: str = "2026-10-14T16:00:00Z") -> pd.DataFrame:
    return pd.DataFrame({"league": "laliga", "x": range(n), "captured_at": pd.Timestamp(ts)})


def test_append_never_overwrites_and_duckdb_reads(tmp_path):
    storage.append(_df(3), "demo", ["league"], root=tmp_path)
    storage.append(_df(2, "2026-10-15T16:00:00Z"), "demo", ["league"], root=tmp_path)
    con = storage.connect(tmp_path)
    assert con.execute("SELECT count(*) FROM demo").fetchone()[0] == 5
    assert con.execute("SELECT count(DISTINCT captured_at) FROM demo").fetchone()[0] == 2


def test_requires_timezone_aware_capture_time(tmp_path):
    df = _df(1)
    df["captured_at"] = df["captured_at"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="zona horaria"):
        storage.append(df, "demo", root=tmp_path)


def test_requires_capture_time(tmp_path):
    with pytest.raises(ValueError, match="captured_at"):
        storage.append(_df(1).drop(columns="captured_at"), "demo", root=tmp_path)
