# Arquitectura, roadmap y decisiones

## 1. Estructura del repositorio

```
motor-props/
├── config/
│   ├── ligas.yaml            # ligas activas, temporadas
│   ├── casas.yaml            # casas sharp/soft, límites conocidos
│   └── mercados.yaml         # definiciones y reglas de liquidación por casa
├── data/                     # raw/ y processed/ (Parquet), snapshots con timestamp
├── src/motor/
│   ├── ingest/               # events.py, odds_sharp.py, odds_soft.py, lineups.py, referees.py
│   ├── priors/               # player_rates.py, team_style.py, keeper.py, referee.py, game_state.py
│   ├── calibration/          # devig.py, dixon_coles.py, macro_calibrator.py
│   ├── sim/                  # state.py, engine.py (por tramos), allocator.py, minutes.py
│   ├── markets/              # definitions.py, settle.py  (vector simulado → resultado del mercado)
│   ├── scanner/              # ev.py, staking.py, alerts_telegram.py
│   └── eval/                 # backtest.py, metrics.py, clv.py
├── tests/                    # test_conservation.py, test_funnel.py, test_settlement.py, ...
└── notebooks/                # exploración y diagnóstico (nunca lógica de producción)
```

**Equivalencia con los módulos del documento original:**

| Original | Ahora |
|---|---|
| `macro_calibrator.py` | `calibration/` |
| `causal_dag_engine.py` | `sim/engine.py` (por tramos) |
| `player_allocator.py` | `sim/allocator.py` + `sim/minutes.py` |
| `discrepancy_scanner.py` | `scanner/` |

La capa `markets/` es nueva y obligatoria.

**Almacenamiento.** DuckDB + Parquet al principio; Postgres cuando funcione como servicio. Todo dato de cuotas y alineaciones se guarda con su **timestamp de captura**, porque sin eso no hay backtest honesto.

## 2. Datos necesarios

Opciones a evaluar; el acceso y los precios hay que verificarlos al decidir.

| Necesidad | Para qué | Opciones |
|---|---|---|
| Eventos por partido (remates con xG/PSxG, duelos, faltas, córners, minutos) | Priors, β de estado, π de córners | Proveedor comercial (Opta/Stats Perform, Hudl StatsBomb/Wyscout), APIs de agregadores (Sportmonks, API-Football) |
| Cuotas sharp con histórico y timestamp | Calibración y CLV | API de Pinnacle (verificar acceso actual) o agregador de cuotas |
| Cuotas soft de props | Scanner | Scraping o agregador. Revisar los términos de uso de cada casa |
| Alineaciones oficiales | Ajuste a T-60 min | Mismo proveedor de eventos o fuente de alineaciones |
| Designaciones arbitrales | α_ref | Publicación oficial de cada federación o liga |
| Proveedor de liquidación de cada casa | Capa `markets/` | Reglas de la casa (cada mercado declara su fuente) |

**Punto crítico.** El histórico de cuotas soft de props casi nunca está disponible. Hay que **empezar a guardar snapshots desde la fase 0**, aunque el modelo aún no exista, para poder validar después.

## 3. Ciclo por partido

| Momento | Acción |
|---|---|
| T-72h a T-24h | Snapshot de cuotas sharp, priors actualizados, simulación con alineación probable |
| Designación del árbitro | Re-simular con α_ref |
| T-60 min (alineaciones) | Re-simular (objetivo < 30 s), escanear casas soft, emitir alertas |
| Hasta el inicio | Re-escanear cuando se muevan las cuotas sharp |
| Cierre | Guardar cuotas de cierre sharp y soft → CLV |
| Post-partido | Guardar estadísticas reales → calibración por mercado |

## 4. Validación (cómo sabremos que funciona)

1. **Tests de leyes** (deterministas, en CI): conservación por simulación, identidad del embudo y faltas cometidas = faltas recibidas + faltas sin víctima.
2. **Reproducción del sharp:** las marginales simuladas de los mercados calibrados quedan dentro de la tolerancia (por ejemplo, < 1 punto porcentual).
3. **Calibración por mercado:** log-loss, Brier y curvas de fiabilidad sobre datos fuera de muestra, por familia (remates de jugador, paradas, córners, tarjetas...).
4. **CLV de las alertas** (KPI principal): ¿la cuota apostada supera de forma sistemática al cierre sin margen? El ROI solo es informativo con una muestra grande, porque tiene mucha varianza.
5. **Ablaciones:** confirmar que cada ley añade precisión (por ejemplo, el modelo con emparejamientos frente al modelo sin ellos).

## 5. Roadmap por fases (cada fase tiene criterio de salida)

| Fase | Contenido | Criterio de salida |
|---|---|---|
| **F0 Datos y definiciones** | Elegir 1 liga, mercados objetivo, proveedores. Ingesta de eventos históricos (2-3 temporadas). Empezar a capturar cuotas sharp y soft con timestamp | Dataset limpio y con timestamps; `mercados.yaml` con las reglas de liquidación de los mercados objetivo |
| **F1 Calibrador macro** | Quitar margen, Dixon-Coles, ajuste a 1X2/AH/OU | Log-loss en resultados ≈ la del cierre sharp sin margen |
| **F2 Simulador de equipo** | Motor por tramos: remates, embudo, goles, paradas, córners, estado del marcador, sobredispersión. Calibración basada en simulación | Tests de leyes en verde; marginales sharp reproducidas; córners y paradas calibrados fuera de muestra |
| **F3 Jugadores (ataque)** | Priors de jugador, modelo de minutos, asignación de remates y remates a puerta, pipeline de alineaciones | Calibración de props de remates y remates a puerta de jugador fuera de muestra |
| **F4 Duelos y disciplina** | Emparejamientos, entradas, faltas, tarjetas, árbitro, efecto de la amarilla y de la roja | Calibración de faltas, entradas y tarjetas por jugador y por equipo |
| **F5 Scanner (sin dinero)** | Capa de mercados completa, EV conservador, Kelly de cartera, alertas en Telegram, paper trading | Al menos 300 alertas registradas con CLV medio positivo y estable |
| **F6 Dinero real** | Stakes pequeños, Kelly fraccional, seguimiento de límites de cuenta | Revisión mensual de CLV, ROI y estado de las cuentas |

## 6. Riesgos principales

- **Limitación de cuentas.** Las casas recreacionales limitan pronto a quien gana de forma constante, y los límites en props son bajos. La capacidad real de apostar decide la rentabilidad tanto como el modelo.
- **Definiciones de datos.** Si el proveedor de liquidación cuenta "remate a puerta" o "entrada" de forma distinta a nuestros datos, aparecerán falsos +EV.
- **Fuga de información en el backtest.** Usar alineaciones, cuotas o lesiones que no se conocían en el momento de la apuesta.
- **Sobreajuste.** Demasiados parámetros de interacción (e_{a,d}, efectos de árbitro) con poca muestra; se mitiga con shrinkage.
- **Latencia.** Las ventajas en props tras las alineaciones duran poco.
- **Legal y términos de uso.** El scraping puede violar los términos de las casas. Operar solo con casas con licencia en España.

## 7. Decisiones abiertas (responder antes de cerrar F0)

1. Liga inicial (recomendado: una sola, con buen mercado de props).
2. Proveedor de datos de eventos y presupuesto mensual.
3. Fuente de cuotas sharp con histórico.
4. Casas soft a escanear y mercados concretos de cada una.
5. Infraestructura: ejecución local o servidor; frecuencia de escaneo.
6. Nivel de programación del usuario y tiempo semanal disponible (ajusta el ritmo de las fases).

## 8. Registro de decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-14 | Simulación por tramos de 1 minuto (red bayesiana dinámica) en lugar de DAG estático | El estado del marcador crea un ciclo que un DAG estático no puede representar |
| 2026-10-14 | Conservación jugador-equipo por asignación multinomial dentro de cada simulación | Garantiza la Ley 1 por simulación y la correlación entre compañeros |
| 2026-10-14 | Calibración contra el sharp sobre las marginales simuladas | El estado del marcador deforma la distribución de goles respecto a los λ de entrada |
| 2026-10-14 | Parámetros sin fuente marcados como `TODO_CALIBRAR` | Los porcentajes de córner por parada o bloqueo del documento original no tenían base empírica |
| 2026-10-14 | KPI principal: CLV; el ROI es secundario | El ROI tiene demasiada varianza con muestras pequeñas |
| 2026-10-14 | Python 3.12 + numpy/numba + DuckDB/Parquet + pytest | Stack sencillo, rápido para Monte Carlo vectorizado |
