"""Ingesta de football-data.co.uk: totales por equipo y cuotas Pinnacle (apertura y cierre).

Uso:
    python -m motor.ingest.football_data --league laliga
    python -m motor.ingest.football_data --league laliga --seasons 2324 2425
    python -m motor.ingest.football_data --league laliga --mirror   # sin cuotas, accesible desde GitHub

Limitaciones (anotadas en cada fila):
- Las cuotas no traen hora de captura: `odds_time_known = False`. Sirven para
  calibrar F1 y medir CLV, nunca como entrada "a T-60" en un backtest.
- El proveedor de las estadísticas de equipo no es necesariamente Opta.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import pandas as pd
import requests
import yaml

from motor import storage

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
# Espejo en GitHub (datasets/football-datasets): mismas estadísticas, sin cuotas
MIRROR_URL = "https://raw.githubusercontent.com/datasets/football-datasets/main/datasets/{slug}/season-{season}.csv"
MIRROR_SLUGS = {"SP1": "la-liga", "E0": "premier-league"}
CONFIG = Path(__file__).resolve().parents[3] / "config" / "ligas.yaml"

# columna original -> columna normalizada
STATS = {
    "FTHG": "home_goals", "FTAG": "away_goals",
    "HTHG": "home_goals_ht", "HTAG": "away_goals_ht",
    "HS": "home_shots", "AS": "away_shots",
    "HST": "home_sot", "AST": "away_sot",
    "HF": "home_fouls", "AF": "away_fouls",
    "HC": "home_corners", "AC": "away_corners",
    "HY": "home_yellows", "AY": "away_yellows",
    "HR": "home_reds", "AR": "away_reds",
}
PINNACLE = {
    "PSH": "ps_open_home", "PSD": "ps_open_draw", "PSA": "ps_open_away",
    "PSCH": "ps_close_home", "PSCD": "ps_close_draw", "PSCA": "ps_close_away",
    "P>2.5": "ps_open_over25", "P<2.5": "ps_open_under25",
    "PC>2.5": "ps_close_over25", "PC<2.5": "ps_close_under25",
    "AHh": "ah_line_open", "PAHH": "ps_open_ah_home", "PAHA": "ps_open_ah_away",
    "AHCh": "ah_line_close", "PCAHH": "ps_close_ah_home", "PCAHA": "ps_close_ah_away",
}
OPTIONAL = {"Referee": "referee", "Time": "kickoff_time"}


def download(code: str, season: str, timeout: float = 30.0, mirror: bool = False) -> str:
    url = (MIRROR_URL.format(slug=MIRROR_SLUGS[code], season=season) if mirror
           else BASE_URL.format(season=season, code=code))
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    # los CSV a veces vienen en latin-1 o con BOM
    try:
        return r.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return r.content.decode("latin-1")


def _parse_dates(col: pd.Series) -> pd.Series:
    """El original usa dd/mm/aa(aa); el espejo usa ISO aaaa-mm-dd."""
    iso = col.str.match(r"^\d{4}-\d{2}-\d{2}$")
    out = pd.Series(pd.NaT, index=col.index, dtype="datetime64[ns]")
    out[iso] = pd.to_datetime(col[iso], format="%Y-%m-%d")
    out[~iso] = pd.to_datetime(col[~iso], dayfirst=True, format="mixed")
    if out.isna().any():
        raise ValueError(f"Fechas no reconocidas: {col[out.isna()].head().tolist()}")
    return out.dt.date


def parse(csv_text: str, league: str, season: str, captured_at: pd.Timestamp,
          source: str = "football-data.co.uk") -> pd.DataFrame:
    """CSV crudo -> una fila por partido con nombres normalizados y flags de calidad."""
    raw = pd.read_csv(io.StringIO(csv_text))
    raw = raw.dropna(subset=["HomeTeam", "AwayTeam"])
    missing = [c for c in ("Date", "HomeTeam", "AwayTeam", *STATS) if c not in raw.columns]
    if missing:
        raise ValueError(f"{league} {season}: faltan columnas {missing}")

    df = pd.DataFrame({
        "league": league,
        "season": season,
        "match_date": _parse_dates(raw["Date"].astype(str).str.strip()),
        "home": raw["HomeTeam"].str.strip(),
        "away": raw["AwayTeam"].str.strip(),
    })
    for src, dst in OPTIONAL.items():
        df[dst] = raw[src].astype("string") if src in raw.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    for src, dst in STATS.items():
        df[dst] = pd.to_numeric(raw[src], errors="coerce").astype("Int64")
    for src, dst in PINNACLE.items():
        df[dst] = pd.to_numeric(raw[src], errors="coerce") if src in raw.columns else float("nan")

    df.insert(0, "match_id", league + "_" + df["match_date"].astype(str) + "_" + df["home"] + "_" + df["away"])
    df["odds_time_known"] = False
    df["source"] = source
    df["captured_at"] = captured_at
    return add_quality_flags(df)


def add_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Flags, no filtros: la decisión de excluir se toma aguas abajo."""
    out = df.copy()
    for side in ("home", "away"):
        # embudo (Ley 2): a puerta ≤ remates
        out[f"flag_{side}_sot_gt_shots"] = out[f"{side}_sot"] > out[f"{side}_shots"]
        # goles > a puerta solo es posible con goles en propia (no pasan por el embudo)
        out[f"flag_{side}_goals_gt_sot"] = out[f"{side}_goals"] > out[f"{side}_sot"]
    out["flag_missing_pinnacle_close"] = out[["ps_close_home", "ps_close_draw", "ps_close_away"]].isna().any(axis=1)
    return out


def load_league(league: str) -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))[league]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--league", default="laliga")
    ap.add_argument("--seasons", nargs="*")
    ap.add_argument("--mirror", action="store_true",
                    help="usar el espejo de GitHub (solo estadísticas, sin cuotas)")
    args = ap.parse_args(argv)
    source = "datasets/football-datasets (espejo de football-data.co.uk)" if args.mirror else "football-data.co.uk"

    cfg = load_league(args.league)
    for season in args.seasons or cfg["seasons"]:
        now = storage.utcnow()
        text = download(cfg["football_data_code"], season, mirror=args.mirror)
        raw_dir = storage.DATA_ROOT / "raw" / "football_data" / args.league
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"{season}_{'mirror_' if args.mirror else ''}{now:%Y%m%dT%H%M%SZ}.csv").write_text(text, encoding="utf-8")
        df = parse(text, args.league, season, now, source)
        storage.append(df, "fd_matches", partition_cols=["league", "season"])
        flags = [c for c in df.columns if c.startswith("flag_")]
        print(f"{season}: {len(df)} partidos; " + ", ".join(f"{c}={int(df[c].sum())}" for c in flags))


if __name__ == "__main__":
    main()
