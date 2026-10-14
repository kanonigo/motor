"""Estimación de π^{c|bl}, π^{c|sv} y C^otros (Ley 2, córners de origen mixto).

Uso:
    python -m motor.priors.corners     # lee sb_shots y sb_corners de data/processed

Las proporciones salen con posterior Beta(1, 1) e intervalo creíble del 90 %.
C^otros por equipo y partido se resume con media y varianza/media (sobredispersión).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from motor import storage


def _beta_ci(k: int, n: int, level: float = 0.90) -> tuple[float, float]:
    """Intervalo creíble de Beta(1 + k, 1 + n - k) por muestreo."""
    rng = np.random.default_rng(0)
    draws = rng.beta(1 + k, 1 + n - k, 200_000)
    a = (1 - level) / 2
    return float(np.quantile(draws, a)), float(np.quantile(draws, 1 - a))


def conversion_by_funnel(shots: pd.DataFrame) -> pd.DataFrame:
    """P(córner a favor del rematador | resultado del remate) por categoría del embudo."""
    g = shots.groupby("funnel")["corner_next"].agg(n="size", corners="sum").reset_index()
    g["p"] = (g["corners"] + 1) / (g["n"] + 2)  # media posterior
    ci = [_beta_ci(int(k), int(n)) for k, n in zip(g["corners"], g["n"])]
    g["ci90_low"], g["ci90_high"] = zip(*ci)
    return g.sort_values("n", ascending=False).reset_index(drop=True)


def other_corners(shots: pd.DataFrame, corners: pd.DataFrame) -> pd.DataFrame:
    """C^otros por (partido, equipo) = córners totales − córners atribuidos a remates."""
    total = corners.groupby(["match_id", "team"]).size().rename("corners")
    from_shots = shots[shots["corner_next"]].groupby(["match_id", "team"]).size().rename("from_shots")
    df = pd.concat([total, from_shots], axis=1).fillna(0).astype(int)
    # equipos con remates pero sin córners también cuentan como 0
    teams = shots[["match_id", "team"]].drop_duplicates().set_index(["match_id", "team"]).index
    df = df.reindex(df.index.union(teams), fill_value=0)
    df["other"] = df["corners"] - df["from_shots"]
    if (df["other"] < 0).any():
        raise ValueError("Más córners atribuidos a remates que córners totales")
    return df.reset_index()


def summary(x: pd.Series) -> dict[str, float]:
    m, v = float(x.mean()), float(x.var(ddof=1))
    return {"mean": m, "var": v, "var_over_mean": v / m if m else float("nan")}


def main() -> None:
    con = storage.connect()
    shots, corners = con.sql("SELECT * FROM sb_shots").df(), con.sql("SELECT * FROM sb_corners").df()
    conv = conversion_by_funnel(shots)
    print("P(córner | resultado del remate), StatsBomb LaLiga 2015/16:")
    print(conv.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    oc = other_corners(shots, corners)
    print("\nPor equipo y partido:")
    for col in ("corners", "from_shots", "other"):
        s = summary(oc[col])
        print(f"  {col:11s} media={s['mean']:.2f}  var/media={s['var_over_mean']:.2f}")
    print(f"  fracción de córners que vienen de remates: {oc['from_shots'].sum() / oc['corners'].sum():.3f}")


if __name__ == "__main__":
    main()
