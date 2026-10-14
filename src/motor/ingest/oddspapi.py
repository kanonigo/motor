"""Cliente mínimo de OddsPapi (v4): partidos, mercados y cuotas históricas con timestamp.

`/v4/historical-odds` no consume cuota según la documentación (2026-10-14), así que
la captura se hace después de cada jornada: un partido = 1 llamada con hasta 3 casas
(pinnacle, bet365, winamax.es). Cada cambio de precio trae su `createdAt`, lo que
permite reconstruir la cuota vigente a T-60 sin fuga de información.

Uso (clave en la variable de entorno ODDSPAPI_API_KEY):
    python -m motor.ingest.oddspapi tournaments            # para rellenar ligas.yaml
    python -m motor.ingest.oddspapi markets                # catálogo de mercados
    python -m motor.ingest.oddspapi historical --from 2026-10-01 --to 2026-10-08

TODO_VERIFICAR con la primera respuesta real: host base (v4 vs v5) y la forma exacta
del JSON histórico. `flatten_historical` acepta las dos formas vistas en la documentación.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml

from motor import storage

BASE_URL = os.environ.get("ODDSPAPI_BASE_URL", "https://api.oddspapi.io")  # TODO_VERIFICAR
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
COOLDOWN_S = {"/v4/historical-odds": 5.0, "/v4/fixtures": 2.0}
MAX_BOOKMAKERS_HISTORICAL = 3


class OddsPapiClient:
    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL,
                 session: requests.Session | None = None) -> None:
        self.api_key = api_key or os.environ.get("ODDSPAPI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Falta ODDSPAPI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self._last_call: dict[str, float] = {}

    def _get(self, path: str, **params: Any) -> Any:
        wait = COOLDOWN_S.get(path, 1.0) - (time.monotonic() - self._last_call.get(path, 0.0))
        if wait > 0:
            time.sleep(wait)
        params = {k: v for k, v in params.items() if v is not None}
        params["apiKey"] = self.api_key
        r = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        self._last_call[path] = time.monotonic()
        if r.status_code == 429:
            raise RuntimeError(f"Cuota agotada o límite de ritmo: {r.text[:200]}")
        r.raise_for_status()
        return r.json()

    def account(self) -> Any:
        return self._get("/v4/account")

    def tournaments(self, sport_id: int = 10) -> Any:
        return self._get("/v4/tournaments", sportId=sport_id)

    def markets(self) -> Any:
        return self._get("/v4/markets")

    def fixtures(self, tournament_id: int, start: str | None = None, end: str | None = None,
                 status_id: int | None = None) -> list[dict]:
        return self._get("/v4/fixtures", tournamentId=tournament_id, **{"from": start, "to": end},
                         statusId=status_id)

    def historical_odds(self, fixture_id: str, bookmakers: list[str]) -> Any:
        if len(bookmakers) > MAX_BOOKMAKERS_HISTORICAL:
            raise ValueError(f"Máximo {MAX_BOOKMAKERS_HISTORICAL} casas por llamada")
        return self._get("/v4/historical-odds", fixtureId=fixture_id, bookmakers=",".join(bookmakers))


def _iter_entries(payload: dict) -> Iterator[tuple[str, str, str, str, str, dict]]:
    """Recorre bookmakers -> markets -> outcomes -> players -> [entradas]."""
    if "bookmakers" not in payload:
        # forma {fixtureId: {"bookmakers": ...}}
        for fid, body in payload.items():
            if isinstance(body, dict) and "bookmakers" in body:
                yield from _iter_entries({**body, "fixtureId": fid})
        return
    fid = str(payload.get("fixtureId", ""))
    for bk, bk_body in (payload["bookmakers"] or {}).items():
        for mid, m_body in (bk_body.get("markets") or {}).items():
            for oid, o_body in (m_body.get("outcomes") or {}).items():
                for pid, entries in (o_body.get("players") or {}).items():
                    for e in entries if isinstance(entries, list) else [entries]:
                        yield fid, bk, str(mid), str(oid), str(pid), e


def flatten_historical(payload: dict, captured_at: pd.Timestamp) -> pd.DataFrame:
    """JSON histórico -> una fila por cambio de precio."""
    rows = [
        {
            "fixture_id": fid, "bookmaker": bk, "market_id": mid, "outcome_id": oid,
            "player_id": pid, "price": e.get("price"), "limit": e.get("limit"),
            "active": e.get("active"), "created_at": e.get("createdAt"),
            "exchange_meta": json.dumps(e["exchangeMeta"]) if e.get("exchangeMeta") else None,
        }
        for fid, bk, mid, oid, pid, e in _iter_entries(payload)
    ]
    cols = ["fixture_id", "bookmaker", "market_id", "outcome_id", "player_id", "price", "limit",
            "active", "created_at", "exchange_meta"]
    df = pd.DataFrame(rows, columns=cols)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["limit"] = pd.to_numeric(df["limit"], errors="coerce")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, format="ISO8601")
    df["captured_at"] = captured_at
    return df


def price_at(odds: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Último precio publicado antes de `cutoff` por (casa, mercado, resultado, jugador).

    Es la cuota que realmente se podía tomar en ese momento: base del backtest sin fuga.
    """
    past = odds[odds["created_at"] <= cutoff]
    keys = ["fixture_id", "bookmaker", "market_id", "outcome_id", "player_id"]
    return past.sort_values("created_at").groupby(keys, as_index=False).tail(1).reset_index(drop=True)


def _bookmakers() -> list[str]:
    casas = yaml.safe_load((CONFIG_DIR / "casas.yaml").read_text(encoding="utf-8"))
    slugs = [c["oddspapi_slug"] for group in ("sharp", "soft") for c in casas[group].values()]
    return slugs[:MAX_BOOKMAKERS_HISTORICAL]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tournaments")
    sub.add_parser("markets")
    h = sub.add_parser("historical")
    h.add_argument("--league", default="laliga")
    h.add_argument("--from", dest="start", required=True)
    h.add_argument("--to", dest="end", required=True)
    args = ap.parse_args(argv)

    client = OddsPapiClient()
    raw_dir = storage.DATA_ROOT / "raw" / "oddspapi"
    raw_dir.mkdir(parents=True, exist_ok=True)
    now = storage.utcnow()

    if args.cmd in ("tournaments", "markets"):
        data = client.tournaments() if args.cmd == "tournaments" else client.markets()
        out = raw_dir / f"{args.cmd}_{now:%Y%m%dT%H%M%SZ}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Guardado en {out}")
        return

    league = yaml.safe_load((CONFIG_DIR / "ligas.yaml").read_text(encoding="utf-8"))[args.league]
    tid = league["oddspapi_tournament_id"]
    if not isinstance(tid, int):
        raise SystemExit("Rellena oddspapi_tournament_id en config/ligas.yaml (comando 'tournaments')")
    fixtures = client.fixtures(tid, args.start, args.end, status_id=2)
    books = _bookmakers()
    for fx in fixtures:
        payload = client.historical_odds(fx["fixtureId"], books)
        (raw_dir / f"hist_{fx['fixtureId']}_{now:%Y%m%dT%H%M%SZ}.json").write_text(
            json.dumps(payload), encoding="utf-8")
        df = flatten_historical(payload, now)
        if df.empty:
            print(f"{fx['fixtureId']}: sin cuotas")
            continue
        df["league"] = args.league
        df["start_time"] = pd.to_datetime(fx.get("startTime"), utc=True)
        storage.append(df, "odds_history", partition_cols=["league", "bookmaker"])
        print(f"{fx['fixtureId']} {fx.get('participant1Name')} - {fx.get('participant2Name')}: "
              f"{len(df)} cambios, {df['market_id'].nunique()} mercados")


if __name__ == "__main__":
    main()
