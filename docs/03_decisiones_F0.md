# Decisiones abiertas de F0: propuesta

Fecha: 2026-10-14. Responde a la sección 7 del roadmap. Los precios se consultaron hoy en las webs de los proveedores y pueden cambiar; los marcados "verificar" no los he podido confirmar.

## Decisiones cerradas (Iñaki, 2026-10-14)

| Decisión | Valor |
|---|---|
| Liga | LaLiga |
| Presupuesto | 20-40 €/mes |
| Casas soft | bet365 y Winamax ES |
| Nivel | Python medio, programando con ayuda de IA |
| Horas por semana | Sin responder |
| Casa principal | bet365; definición canónica de las estadísticas = Opta. Winamax secundaria |

**Ajuste tras las respuestas.** OddsPapi lista `winamax.es`, `bet365` y `pinnacle`, y su endpoint de cuotas históricas (`/v4/historical-odds`, datos desde enero de 2026, con `createdAt` por cambio de precio y límite de stake) no consume cuota. Eso permite capturar después de cada jornada en vez de mantener un VPS 24/7. Coste en F0-F2: 0 € (football-data.co.uk + OddsPapi gratuito + StatsBomb Open Data). El proveedor de estadísticas de jugador (API-Football Pro, unos 19 $/mes) se contrata al llegar a F3, tras el test de definiciones. El VPS queda como plan B si el histórico de OddsPapi no trae los props.

Pendiente de verificar con la primera llamada real: que el histórico incluya props de jugador de bet365 y Winamax en LaLiga, y que el slug `bet365` corresponda a precios de bet365.es.

## Dos hechos que cambian el roadmap

1. **La API pública de Pinnacle cerró en julio de 2025.** Ya no se puede pedir una clave. Hoy hay revendedores no oficiales (pinnapi, PinnOdds, SharpOddz) que sirven sus cuotas en vivo, pero sin histórico, y agregadores que incluyen Pinnacle. Corrección propuesta a la sección 2: sustituir "API de Pinnacle (verificar acceso actual)" por "agregador con Pinnacle y Betfair Exchange; histórico de cierre de football-data.co.uk".
2. **FBref perdió los datos avanzados de Opta** (Opta cortó el acuerdo y exigió borrarlos). La fuente gratuita habitual de tasas de jugador ya no existe. Opta además pasa a ser distribuidor de datos de apuestas de la FIFA, y es la fuente con la que bet365 y otras casas liquidan props de jugador (verificar por casa en sus reglas).

Consecuencia: **el problema principal de F0 no es el coste, es la coherencia de definiciones.** Si estimamos tasas con un proveedor que no es Opta y las casas liquidan con Opta, "remate a puerta", "entrada" o "parada" pueden no coincidir y aparecerán falsos +EV (riesgo ya listado en la sección 6).

## 1. Liga inicial

**Recomendación: LaLiga.** Segunda opción: Premier League.

- Operas desde España: las casas con licencia DGOJ ofrecen en LaLiga el menú de props más completo junto con la Premier.
- 380 partidos por temporada, Pinnacle líquido en 1X2/AH/OU, córners y tarjetas.
- Mercado de tarjetas grande (LaLiga es de las ligas con más tarjetas por partido), lo que da un caso de uso claro para el bloque árbitro en F4.
- Contra: la Premier tiene más datos públicos y más volumen; si tus cuentas están más activas en la Premier, cambio la recomendación.

## 2. Proveedor de eventos y presupuesto

**Recomendación por fases, ≤ 50 €/mes hasta F2:**

| Uso | Fuente | Coste |
|---|---|---|
| Totales de equipo por partido (remates, a puerta, faltas, córners, tarjetas) + cierre Pinnacle 1X2/OU 2.5/AH, 10+ temporadas | football-data.co.uk (CSV) | Gratis |
| Estadísticas de jugador por partido, alineaciones, árbitro | Sportmonks Starter (5 ligas) o API-Football Pro | 29 €/mes o 19 $/mes |
| xG por remate | Add-on xG de Sportmonks | 24 €/mes |
| Secuencias de eventos para π^{c\|bl}, π^{c\|sv} (córner tras bloqueo o parada) | StatsBomb Open Data (subconjunto histórico) | Gratis |

- Antes de pagar nada, hago un **test de definiciones**: 20 partidos de LaLiga, comparar remates a puerta, paradas, faltas y entradas por jugador del proveedor candidato contra lo que publica una fuente basada en Opta. Si la discrepancia es grande en un mercado, ese mercado no entra en F3-F4 con ese proveedor.
- Cuando lleguemos a F3 (props de jugador) habrá que decidir si pagamos datos con definición Opta. Eso es una decisión de presupuesto que se toma con los resultados del test, no ahora.

## 3. Fuente de cuotas sharp con histórico

**Recomendación:**
- **Histórico para F1:** football-data.co.uk (apertura y cierre Pinnacle de 1X2, OU 2.5 y AH). Basta para validar el quitamárgenes y Dixon-Coles.
- **Captura en vivo desde ya:** un agregador con Pinnacle y Betfair Exchange (OddsPapi tiene plan gratuito y dice ofrecer histórico; TheStatsAPI desde 50 $/mes incluye Pinnacle "donde esté disponible"). Empezar por el plan gratuito y medir cobertura real en LaLiga una semana.
- **Betfair Exchange como sharp desde una cuenta española:** el exchange español funciona con liquidez separada del internacional (verificar el estado actual); probablemente es demasiado fino para usarlo como referencia. No lo propongo como fuente principal.
- **Límite que hay que asumir:** Pinnacle apenas publica props de jugador de fútbol. El anclaje sharp (principio 5) funciona para goles, AH, córners y tarjetas; los props de jugador quedan anclados por el modelo, no por el mercado. Esto refuerza que la validación de props tiene que ser calibración fuera de muestra + CLV contra el cierre soft más eficiente disponible.

## 4. Casas soft y mercados

**Mercados F0** (los que tienen más demanda en casas recreacionales y que el modelo cubre pronto):
1. Remates a puerta de jugador (over 0.5 / 1.5).
2. Remates de jugador (over 0.5 / 1.5 / 2.5).
3. Paradas del portero.
4. Faltas cometidas de jugador.
5. Córners de equipo y de partido.
6. Tarjetas de partido y jugador amonestado.

**Casas**: solo con licencia DGOJ. Candidatas: bet365, Codere, Sportium, Bwin, Winamax, Retabet, William Hill. Elegiría 2-3 en las que tengas cuenta.

- Los agregadores cubren props de bet365 (bet365 UK/.com; hay que comprobar si coinciden con bet365.es), pero casi ninguno cubre Codere, Sportium o Retabet. Para esas habrá que capturar nosotros, y antes hay que leer sus términos de uso.
- Por cada casa elegida, `mercados.yaml` recogerá: proveedor de liquidación, definición de cada estadística, regla de nulidad si el jugador no sale o sale tarde, y tratamiento de la prórroga y del descuento.

## 5. Infraestructura

**Recomendación:** desarrollo en local; **captura de cuotas en un VPS pequeño** (Hetzner o similar, ~5 €/mes) desde esta semana.

- La captura tiene que funcionar 24/7 aunque tu portátil esté apagado; sin snapshots no hay backtest honesto de props (sección 2 del roadmap).
- Frecuencia de captura: sharp cada 30 min hasta T-6h, cada 10 min hasta T-1h, cada 2 min en la última hora. Soft en T-24h, T-6h, T-60, T-30, T-10 y T-2 min, más el cierre.
- Almacenamiento: Parquet particionado por fecha + DuckDB, cada fila con `captured_at` en UTC.

## 6. Lo que solo tú puedes responder

1. Nivel de Python (bajo / medio / alto) y horas por semana.
2. Presupuesto mensual máximo para datos e infraestructura.
3. En qué casas españolas tienes cuenta activa.
4. ¿LaLiga o Premier League?

## Siguiente paso si estás de acuerdo

Montar el esqueleto del repositorio en `/mnt/project-files/motor-props/` con: descarga de football-data.co.uk de LaLiga (3 temporadas), el script de captura de cuotas con timestamp (DuckDB/Parquet) y el primer `mercados.yaml` vacío con su esquema y test.

## Líneas para el registro de decisiones (cuando las confirmes)

```
| 2026-10-14 | Sustituir la API de Pinnacle por agregador + histórico de football-data.co.uk | La API pública de Pinnacle cerró en julio de 2025 |
| 2026-10-14 | Test de definiciones del proveedor de eventos contra fuente Opta antes de F3 | Las casas liquidan props de jugador con Opta; definiciones distintas generan falsos +EV |
| 2026-10-14 | Captura de cuotas en VPS desde F0 | El histórico de props soft no existe; hay que generarlo nosotros |
```

## Fuentes

- Cierre de la API de Pinnacle: https://sportsapis.dev/apis/pinnapi
- FBref y Opta: https://amp.awfulannouncing.com/soccer/sports-reference-pulls-advanced-data-agreement-violation-dispute.html
- Sportmonks, precios: https://www.sportmonks.com/football-api/plans-pricing
- Comparativa de APIs 2026: https://highlightly.net/blogs/best-football-apis-in-2026
- OddsPapi: https://oddspapi.io/es
- TheStatsAPI, cierres y props: https://www.thestatsapi.com/odds-api/closing-odds , https://www.thestatsapi.com/docs/api-reference/matches/player-odds

## Estado del criterio de salida de F0 (2026-10-14)

Criterio: dataset limpio y con timestamps; `mercados.yaml` con las reglas de liquidación de los mercados objetivo.

| Pieza | Estado | Detalle |
|---|---|---|
| Totales de equipo LaLiga | ✓ | 1.900 partidos (2021/22 a 2025/26), espejo en GitHub de football-data.co.uk, con `captured_at` y flags de calidad |
| Eventos con secuencia | ✓ (antiguo) | StatsBomb LaLiga 2015/16: 380 partidos, 9.168 remates, 3.841 córners |
| Cuotas Pinnacle históricas | ✗ | El espejo no trae cuotas; football-data.co.uk está bloqueado en este entorno |
| Historial de cuotas bet365/Pinnacle (OddsPapi) | ✗ | Falta acceso de red y clave |
| Datos de jugador (definición Opta) | Aplazado a F3 | Decisión de proveedor tras el test de definiciones |
| Reglas bet365: córners y tarjetas | ✓ | Verificadas en help.bet365.es |
| Reglas bet365: props de jugador | Parcial | Falta saber si Sustituto+ se aplica en bet365.es a LaLiga y si el penalti cuenta como remate |
| Reglas Winamax | Parcial | Secundaria; la sección de fútbol del reglamento no se pudo leer desde aquí |

**Primeros resultados empíricos** (detalle en `motor-props/config/priors.yaml`):
- P(córner | remate bloqueado) ≈ 0,25 y P(córner | parada) ≈ 0,20, frente a los 35 % y 30 % sin fuente del documento original.
- Solo el 26 % de los córners viene de un remate; el resto es C^otros. La correlación remates-córners por partido es 0,33 (0,54 a nivel de equipo local).
- Varianza/media por equipo y partido: remates ≈ 2,0, córners ≈ 1,5, faltas ≈ 1,2-1,4, goles y amarillas ≈ 1,0. Incluye heterogeneidad entre equipos, así que es una cota superior de la sobredispersión dentro del partido.
- bet365 liquida las tarjetas de partido por puntos (amarilla 1, roja 2, segunda amarilla descartada): el simulador debe distinguir roja directa de doble amarilla.
