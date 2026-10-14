"""Carga y valida config/mercados.yaml.

Regla: un mercado solo es apto para el scanner si todas sus casas tienen
la liquidación verificada y sin campos TODO_VERIFICAR.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TODO = "TODO_VERIFICAR"
LEVELS = {"player", "team", "match"}
SETTLEMENT_FIELDS = (
    "data_provider",
    "regular_time_only",
    "void_if_player_not_playing",
    "void_if_player_sub_on",
    "substitute_rule",   # p. ej. garantía sustituto: liquida con el jugador que entra
    "stat_definition",
    "source",
    "verified",
)
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "mercados.yaml"


@dataclass(frozen=True)
class Settlement:
    house: str
    rules: dict[str, Any]

    @property
    def pending_fields(self) -> list[str]:
        """Campos aún sin verificar."""
        return [k for k in SETTLEMENT_FIELDS if self.rules.get(k) == TODO]

    @property
    def is_verified(self) -> bool:
        return self.rules.get("verified") is True and not self.pending_fields


@dataclass(frozen=True)
class Market:
    id: str
    level: str
    family: str
    sim_variable: str
    lines: tuple[float, ...]
    settlement: dict[str, Settlement] = field(default_factory=dict)
    notes: str = ""

    @property
    def scanner_ready(self) -> bool:
        return bool(self.settlement) and all(s.is_verified for s in self.settlement.values())

    def ready_for(self, house: str) -> bool:
        """Apto para escanear en una casa concreta."""
        s = self.settlement.get(house)
        return s is not None and s.is_verified


class MarketConfigError(ValueError):
    pass


def _parse_market(mid: str, raw: dict[str, Any], houses: set[str] | None) -> Market:
    for key in ("level", "family", "sim_variable", "lines", "settlement"):
        if key not in raw:
            raise MarketConfigError(f"{mid}: falta '{key}'")
    if raw["level"] not in LEVELS:
        raise MarketConfigError(f"{mid}: level '{raw['level']}' no válido")
    if not raw["sim_variable"].startswith(f"{raw['level']}."):
        raise MarketConfigError(f"{mid}: sim_variable debe empezar por '{raw['level']}.'")
    lines = tuple(float(x) for x in raw["lines"])
    if any((x * 2) % 2 != 1 for x in lines):
        # solo líneas .5 en F0: evitan el push y simplifican la liquidación
        raise MarketConfigError(f"{mid}: solo se admiten líneas x.5, recibido {lines}")
    settlement: dict[str, Settlement] = {}
    for house, rules in raw["settlement"].items():
        if houses is not None and house not in houses:
            raise MarketConfigError(f"{mid}: casa '{house}' no está en casas.yaml")
        if not isinstance(rules, dict):
            raise MarketConfigError(f"{mid}/{house}: la liquidación debe ser un diccionario")
        missing = [k for k in SETTLEMENT_FIELDS if k not in rules]
        if missing:
            raise MarketConfigError(f"{mid}/{house}: faltan campos {missing}")
        settlement[house] = Settlement(house, copy.deepcopy(rules))
    return Market(mid, raw["level"], raw["family"], raw["sim_variable"], lines, settlement, raw.get("notes", ""))


def load_markets(path: Path = DEFAULT_PATH, houses: set[str] | None = None) -> dict[str, Market]:
    """Devuelve {market_id: Market}. `houses` restringe las casas permitidas."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    raw_markets = data.get("markets") or {}
    if not raw_markets:
        raise MarketConfigError("mercados.yaml no define ningún mercado")
    return {mid: _parse_market(mid, raw, houses) for mid, raw in raw_markets.items()}


def load_soft_houses(path: Path | None = None) -> set[str]:
    path = path or DEFAULT_PATH.with_name("casas.yaml")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return set((data.get("soft") or {}).keys())


def pending_report(markets: dict[str, Market]) -> list[tuple[str, str, list[str]]]:
    """Lista (mercado, casa, campos pendientes) para la tarea de verificación."""
    out = []
    for m in markets.values():
        for s in m.settlement.values():
            if not s.is_verified:
                out.append((m.id, s.house, s.pending_fields or ["verified"]))
    return out


if __name__ == "__main__":
    ms = load_markets(houses=load_soft_houses())
    for mid, house, fields in pending_report(ms):
        print(f"{mid:28s} {house:10s} pendiente: {', '.join(fields)}")
    for house in sorted({h for m in ms.values() for h in m.settlement}):
        ready = [m.id for m in ms.values() if m.ready_for(house)]
        print(f"\nAptos en {house}: {ready or 'ninguno'}")
