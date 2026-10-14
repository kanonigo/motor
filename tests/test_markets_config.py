import textwrap

import pytest

from motor.markets.definitions import (MarketConfigError, load_markets, load_soft_houses,
                                       pending_report)


def test_real_config_loads_and_nothing_is_scanner_ready():
    ms = load_markets(houses=load_soft_houses())
    assert {"player_shots_on_target", "goalkeeper_saves", "match_cards"} <= ms.keys()
    # Winamax sin verificar: ningún mercado apto en las dos casas
    assert not any(m.scanner_ready for m in ms.values())
    assert not any(m.ready_for("winamax") for m in ms.values())
    # bet365: solo córners y tarjetas de partido tienen las reglas completas
    assert {m.id for m in ms.values() if m.ready_for("bet365")} == {"team_corners", "match_corners", "match_cards"}
    assert len(pending_report(ms)) == 2 * len(ms) - 3


def test_known_rules_loaded():
    ms = load_markets()
    sot = ms["player_shots_on_target"].settlement
    assert sot["bet365"].rules["void_if_player_sub_on"] is True
    assert sot["winamax"].rules["substitute_rule"] == "garantia_sustituto"
    assert ms["match_corners"].settlement["bet365"].rules["regular_time_only"] is True


def test_every_market_covers_both_houses():
    for m in load_markets().values():
        assert set(m.settlement) == {"bet365", "winamax"}


def _write(tmp_path, body: str):
    p = tmp_path / "m.yaml"
    p.write_text(textwrap.dedent(body))
    return p


RULES = """
            data_provider: Opta
            regular_time_only: true
            void_if_player_not_playing: true
            void_if_player_sub_on: false
            substitute_rule: none
            stat_definition: "Remates a puerta según Opta"
            source: "https://example.org 2026-10-14"
            verified: true
"""


def test_verified_market_is_ready(tmp_path):
    p = _write(tmp_path, f"""
    markets:
      player_sot:
        level: player
        family: shots
        sim_variable: player.SoT
        lines: [0.5]
        settlement:
          bet365:{RULES}""")
    assert load_markets(p)["player_sot"].scanner_ready


def test_todo_field_blocks_even_if_marked_verified(tmp_path):
    p = _write(tmp_path, f"""
    markets:
      player_sot:
        level: player
        family: shots
        sim_variable: player.SoT
        lines: [0.5]
        settlement:
          bet365:{RULES.replace('Opta', 'TODO_VERIFICAR', 1)}""")
    m = load_markets(p)["player_sot"]
    assert not m.scanner_ready
    assert m.settlement["bet365"].pending_fields == ["data_provider"]


@pytest.mark.parametrize("bad, msg", [
    ("lines: [1.0]", "x.5"),
    ("level: team", "sim_variable"),
])
def test_invalid_configs(tmp_path, bad, msg):
    body = f"""
    markets:
      player_sot:
        level: player
        family: shots
        sim_variable: player.SoT
        lines: [0.5]
        settlement:
          bet365:{RULES}"""
    key = bad.split(":")[0]
    body = "\n".join(f"        {bad}" if l.strip().startswith(key + ":") else l for l in body.splitlines())
    with pytest.raises(MarketConfigError, match=msg):
        load_markets(_write(tmp_path, body))


def test_unknown_house_rejected(tmp_path):
    p = _write(tmp_path, f"""
    markets:
      player_sot:
        level: player
        family: shots
        sim_variable: player.SoT
        lines: [0.5]
        settlement:
          codere:{RULES}""")
    with pytest.raises(MarketConfigError, match="codere"):
        load_markets(p, houses={"bet365", "winamax"})
