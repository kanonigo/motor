# motor-props

Motor de simulación causal de partidos de fútbol (LaLiga) para detectar props mal valorados en bet365 y Winamax.
Fuente de verdad del modelo: `docs/01_especificacion_tecnica.md`. Fases y decisiones: `docs/02_arquitectura_y_roadmap.md` y `docs/03_decisiones_F0.md`.

## Estado: F0 (datos y definiciones)

| Pieza | Estado |
|---|---|
| `config/ligas.yaml`, `casas.yaml` | LaLiga; Pinnacle (sharp), bet365 y Winamax ES (soft) |
| `config/mercados.yaml` | 8 mercados objetivo; **ninguna regla de liquidación verificada todavía** |
| `ingest/football_data.py` | Totales de equipo y cuotas Pinnacle apertura/cierre, sin hora de captura |
| `ingest/oddspapi.py` | Historial de cuotas con `createdAt` por cambio de precio y `price_at(cutoff)` |
| `storage.py` | Parquet append-only + vistas DuckDB; `captured_at` obligatorio |

## Instalación

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Uso mínimo

```bash
# 1. Histórico LaLiga (5 temporadas) desde football-data.co.uk
python -m motor.ingest.football_data --league laliga

# 2. OddsPapi: crea una cuenta gratuita y exporta la clave
export ODDSPAPI_API_KEY=...
python -m motor.ingest.oddspapi tournaments     # buscar LaLiga y copiar su id a config/ligas.yaml
python -m motor.ingest.oddspapi markets         # catálogo de mercados (ids -> nombres)
python -m motor.ingest.oddspapi historical --from 2026-10-01 --to 2026-10-08

# 3. Consultar
python -c "from motor import storage; print(storage.connect().sql('SELECT season, count(*) FROM fd_matches GROUP BY 1'))"

# 4. Qué reglas de liquidación faltan por verificar
python -m motor.markets.definitions
```

Las escrituras son append-only: volver a lanzar una ingesta añade un snapshot nuevo con su `captured_at`. Para leer la versión vigente, quedarse con el `captured_at` más reciente por clave.

## Reglas que el código hace cumplir

- Nada se guarda sin `captured_at` con zona horaria.
- Las cuotas de football-data.co.uk llevan `odds_time_known = False`: valen para calibrar y medir CLV, no como cuota tomable en un backtest.
- `price_at(odds, cutoff)` solo usa precios publicados antes del corte (sin fuga de información).
- Un mercado solo es `scanner_ready` cuando todas sus casas tienen la liquidación verificada y sin `TODO_VERIFICAR`.
