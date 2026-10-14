"""Almacenamiento en Parquet particionado + vistas DuckDB.

Todo lo que se escribe lleva `captured_at` (UTC): sin él no hay backtest honesto.
Los ficheros nunca se sobrescriben; cada escritura añade un fichero nuevo.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def utcnow() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def append(df: pd.DataFrame, dataset: str, partition_cols: list[str] | None = None,
           root: Path = DATA_ROOT) -> Path:
    """Añade `df` a data/processed/<dataset>/ sin tocar lo ya escrito."""
    if df.empty:
        raise ValueError(f"{dataset}: DataFrame vacío")
    if "captured_at" not in df.columns:
        raise ValueError(f"{dataset}: falta la columna captured_at")
    ts = pd.to_datetime(df["captured_at"], utc=False)
    if ts.dt.tz is None:
        raise ValueError(f"{dataset}: captured_at debe tener zona horaria (UTC)")
    target = Path(root) / "processed" / dataset
    target.mkdir(parents=True, exist_ok=True)
    ds.write_dataset(
        pa.Table.from_pandas(df, preserve_index=False),
        base_dir=str(target),
        format="parquet",
        partitioning=partition_cols,
        partitioning_flavor="hive" if partition_cols else None,
        basename_template=f"part-{uuid.uuid4().hex}-{{i}}.parquet",
        existing_data_behavior="overwrite_or_ignore",
    )
    return target


def connect(root: Path = DATA_ROOT) -> duckdb.DuckDBPyConnection:
    """Conexión DuckDB en memoria con una vista por dataset de data/processed."""
    con = duckdb.connect()
    processed = Path(root) / "processed"
    if processed.exists():
        for d in sorted(p for p in processed.iterdir() if p.is_dir()):
            glob = (d / "**" / "*.parquet").as_posix()
            con.execute(
                f"CREATE VIEW {d.name} AS SELECT * FROM read_parquet('{glob}', hive_partitioning = true)"
            )
    return con
