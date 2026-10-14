"""StatsBomb Open Data: remates con su resultado en el embudo y si derivan en córner.

Uso:
    python -m motor.ingest.statsbomb --competition 11 --season 27   # LaLiga 2015/16 completa

Mapeo al embudo de la Ley 2 (definición StatsBomb, NO Opta):
- Blocked con bloqueo `save_block` (habría entrado) -> on_target_dl (despeje en línea).
  bet365/Opta cuentan como a puerta el bloqueo del último defensor; save_block es la
  aproximación más cercana disponible.
- Blocked restante -> blocked
- Goal -> goal; Saved, Saved to Post -> saved
- Off T, Post, Wayward, Saved Off Target -> off
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import requests

from motor import storage

RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CORNER_WINDOW_S = 60.0  # ventana máxima entre remate y córner para atribuirlo al remate

OUTCOME_MAP = {
    "Goal": "goal", "Saved": "saved", "Saved to Post": "saved",
    "Off T": "off", "Post": "off", "Wayward": "off", "Saved Off Target": "off",
    "Blocked": "blocked",
}


def _secs(e: dict) -> float:
    return e["minute"] * 60.0 + e["second"]


def _is_corner(e: dict) -> bool:
    return e["type"]["name"] == "Pass" and e.get("pass", {}).get("type", {}).get("name") == "Corner"


def shots_from_events(events: list[dict[str, Any]], match_id: int) -> list[dict[str, Any]]:
    """Una fila por remate (sin tandas de penaltis) con su resultado y córner derivado."""
    by_id = {e["id"]: e for e in events}
    rows = []
    for i, e in enumerate(events):
        if e["type"]["name"] != "Shot" or e["period"] > 4:
            continue
        shot = e["shot"]
        outcome = OUTCOME_MAP.get(shot["outcome"]["name"], "other")
        if outcome == "blocked":
            blocks = [by_id[r] for r in e.get("related_events", []) if r in by_id
                      and by_id[r]["type"]["name"] == "Block"]
            if any(b.get("block", {}).get("save_block") for b in blocks):
                outcome = "on_target_dl"
        # siguiente reinicio o acción con balón: pase (cualquier equipo) o remate
        corner = False
        for nxt in events[i + 1:]:
            if nxt["period"] != e["period"] or _secs(nxt) - _secs(e) > CORNER_WINDOW_S:
                break
            if nxt["type"]["name"] in ("Pass", "Shot"):
                corner = _is_corner(nxt) and nxt["team"]["id"] == e["team"]["id"]
                break
        rows.append({
            "match_id": match_id, "event_id": e["id"], "period": e["period"],
            "minute": e["minute"], "team": e["team"]["name"], "player": e["player"]["name"],
            "shot_type": shot["type"]["name"], "body_part": shot["body_part"]["name"],
            "xg": shot.get("statsbomb_xg"), "sb_outcome": shot["outcome"]["name"],
            "funnel": outcome, "corner_next": corner,
        })
    return rows


def corners_from_events(events: list[dict[str, Any]], match_id: int) -> list[dict[str, Any]]:
    return [{"match_id": match_id, "team": e["team"]["name"], "period": e["period"], "minute": e["minute"]}
            for e in events if _is_corner(e) and e["period"] <= 4]


def _fetch(url: str) -> Any:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def ingest(competition: int, season: int, workers: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = _fetch(f"{RAW}/matches/{competition}/{season}.json")

    def one(m: dict) -> tuple[list, list]:
        ev = _fetch(f"{RAW}/events/{m['match_id']}.json")
        return shots_from_events(ev, m["match_id"]), corners_from_events(ev, m["match_id"])

    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(one, matches))
    now = storage.utcnow()
    shots = pd.DataFrame([r for s, _ in results for r in s])
    corners = pd.DataFrame([r for _, c in results for r in c])
    for df in (shots, corners):
        df["competition_id"], df["season_id"], df["captured_at"] = competition, season, now
    return shots, corners


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competition", type=int, default=11)
    ap.add_argument("--season", type=int, default=27)
    args = ap.parse_args(argv)
    shots, corners = ingest(args.competition, args.season)
    storage.append(shots, "sb_shots", ["competition_id", "season_id"])
    storage.append(corners, "sb_corners", ["competition_id", "season_id"])
    print(f"{shots['match_id'].nunique()} partidos, {len(shots)} remates, {len(corners)} córners")
    print(shots["funnel"].value_counts().to_string())


if __name__ == "__main__":
    main()
