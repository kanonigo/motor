# Especificación técnica: Motor de simulación causal de partidos

> Fuente de verdad del modelo. Sustituye al documento de visión original, que contenía parámetros sin fuente y una arquitectura inconsistente (DAG estático con bucles de retroalimentación). La sección 10 recoge las correcciones.

## 0. Objetivo y alcance

**Objetivo.** Construir un modelo generativo de un partido de fútbol que produzca, en cada simulación, un vector completo y coherente de estadísticas: partido, equipos y los jugadores que participen. Cualquier mercado se calcula como una función de ese vector, y su probabilidad es la frecuencia de esa función sobre K simulaciones.

**Uso.**
1. Calibrar el modelo contra las probabilidades sin margen de un mercado sharp.
2. Ajustarlo con la información específica del partido: alineaciones, árbitro, bajas.
3. Comparar sus probabilidades con las cuotas de casas recreacionales y emitir alertas solo cuando la ventaja supere la incertidumbre del modelo.

**Mercados objetivo:**
- **Partido:** 1X2, hándicap asiático, margen exacto, goles totales, ambos marcan, remates, remates a puerta, córners, faltas, tarjetas.
- **Equipo:** goles, remates, remates a puerta, córners, faltas, tarjetas.
- **Jugador:** remates, remates a puerta, paradas (portero), faltas cometidas y recibidas, entradas, tarjeta.

## 1. Notación

| Símbolo | Significado |
|---|---|
| A, B | Equipo local y visitante |
| i, j | Jugadores (i ∈ A, j ∈ B) |
| t | Tramo de tiempo (por defecto 1 minuto; incluye descuento) |
| S_t | Estado del partido en t: marcador, minuto, rojas por equipo, jugadores en campo, amarillas por jugador |
| N^sh_A | Remates del equipo A |
| Bl_A, Off_A, SoT_A | Remates de A bloqueados, fuera y a puerta |
| G_A | Goles de A en jugada de remate (excluye goles en propia puerta) |
| OG_A | Goles en propia puerta a favor de A |
| Sv_B | Paradas del portero de B |
| DL_A | Remates a puerta de A despejados en línea por un defensa |
| C_A | Córners a favor de A |
| D_{a,d} | Duelos entre el atacante a y el defensor d |
| Tk_d, F^c_d, F^r_a, Y_d | Entradas, faltas cometidas, faltas recibidas y amarillas |
| α_ref | Parámetros del árbitro (severidad en faltas y en tarjetas) |
| θ | Vector de parámetros base del partido (se calibra, sección 5) |
| K | Número de simulaciones (por defecto 50.000) |

## 2. Las cuatro leyes del modelo

### Ley 1: Conservación jugador ↔ equipo ↔ partido

En **cada** simulación k:

$$\sum_{i\in A} X_{i,k} = X_{A,k}, \qquad X_{A,k} + X_{B,k} = X_{\text{partido},k}$$

**Mecanismo.** Se genera el evento del equipo y después se asigna a un jugador en campo con probabilidad p_i(t) ∝ w_i · 1[i en campo en t]. Si se simulan jugadores independientes y se suman, la ley solo se cumple en media y se pierden las correlaciones entre ellos.

**Faltas:**

$$\sum_{i\in A} F^c_i = \sum_{j\in B} F^r_j + F^{\text{sin víctima}}_A$$

donde F^sin víctima son las faltas sin jugador objetivo (manos, infracciones técnicas). El reparto depende del proveedor de datos.

**Consecuencia del mecanismo.** Si el total del equipo es Poisson(λ) y la asignación es multinomial, los jugadores salen Poisson(λ·p_i) independientes. Con un total sobredisperso (binomial negativa) o con incertidumbre en λ aparece una correlación positiva entre compañeros. Eso es lo deseado y es lo que capta el efecto "día de dominio".

### Ley 2: Embudo causal (adelgazamiento condicionado)

$$N^{sh}_A \;\to\; (Bl_A,\ Off_A,\ SoT_A) \sim \text{Multinomial}\big(N^{sh}_A;\ \pi^{bl},\pi^{off},\pi^{sot}\big)$$

$$SoT_A \;\to\; (G_A,\ Sv_B,\ DL_A)$$

**Probabilidades por remate.** Se calculan individualmente:
- P(a puerta) depende del rematador y del tipo de remate.
- P(gol | a puerta) depende de la calidad del remate (PSxG) y de la habilidad del portero rival (GSAx, goles evitados sobre lo esperado, con shrinkage).

**Identidad contable (definición tipo Opta, verificar con el proveedor):**

$$SoT_A = G_A + Sv_B + DL_A$$

- Los goles en propia puerta no pasan por el embudo.
- Los penaltis suelen contar como remate. Hay que verificarlo.

**Córners.** Tienen un origen mixto:

$$C_A = \underbrace{\text{Bin}(Bl_A,\ \pi^{c|bl})}_{\text{remate bloqueado}} + \underbrace{\text{Bin}(Sv_B,\ \pi^{c|sv})}_{\text{parada a córner}} + \underbrace{C^{otros}_A}_{\text{centros/despejes}}$$

- π^{c|bl} y π^{c|sv} siguen como `TODO_CALIBRAR` con datos de definición Opta. Los 35 % y 30 % del documento original no tienen fuente. Estimación provisional (StatsBomb, LaLiga 2015/16, 9.168 remates; `config/priors.yaml`): π^{c|bl} ≈ 0,25 [0,24; 0,27] y π^{c|sv} ≈ 0,20 [0,19; 0,22]. Solo el 26 % de los córners viene de un remate; C^otros (≈ 3,7 por equipo y partido) domina.
- C^otros_A es un proceso propio que depende de la posesión en el último tercio y del volumen de centros.

**Implicación correcta.** Pocos remates hacen que los córners esperados *bajen*, pero no los hacen "imposibles", porque C^otros no depende de los remates. La correlación entre remates y córners se estima; no se impone.

### Ley 3: Emparejamientos espaciales

**Duelos.** Para cada pareja (atacante a, defensor d) que comparte zona según formación y datos posicionales (no según la etiqueta de posición):

$$\mathbb{E}[D_{a,d}] = \text{exposición}_{a,d} \cdot r^{\text{1v1}}_a \cdot e_{a,d}$$

- exposición = posesión del equipo de a en la zona compartida × minutos que coinciden en el campo.
- r^1v1_a es la tasa de regates y duelos que intenta a.
- e_{a,d} es un término de interacción con shrinkage fuerte (normalmente cercano a 1).

**Eventos defensivos (adelgazamiento del duelo):**

$$Tk_d \sim \text{Bin}(D_{\cdot,d},\ \tau_d), \qquad F^c_d \sim \text{Bin}(D_{\cdot,d},\ \phi_d \cdot \alpha^{falta}_{ref})$$

Cada falta del defensor d se registra simultáneamente como falta recibida por a, lo que cumple la Ley 1.

**Tarjetas:**

$$P(Y \mid \text{falta}) = h\big(\alpha^{tarjeta}_{ref},\ \text{zona},\ \text{minuto},\ S_t,\ \text{amarilla previa del jugador},\ \text{falta táctica}\big)$$

- Un jugador con amarilla reduce su agresividad: baja φ_d y τ_d (parámetro `TODO_CALIBRAR`).
- El simulador distingue roja directa de expulsión por doble amarilla, porque bet365 liquida las tarjetas de partido como amarilla = 1 y roja = 2, descartando la segunda amarilla (doble amarilla = 3 puntos, roja directa = 2).
- Una roja reconfigura las intensidades de ambos equipos durante el resto del partido.

**Árbitro.** Actúa como multiplicador de las conversiones, con shrinkage hacia la media de la liga. El árbitro se conoce cuando se publica la designación; hasta entonces se usa la distribución de la liga.

### Ley 4: Estado del marcador (bucle de retroalimentación)

Toda intensidad X depende del estado:

$$\lambda_X(t) = \lambda^{base}_X(\theta) \cdot g_X(t) \cdot \exp\big(\beta_X^\top s(S_t)\big)$$

- s(S_t) incluye la diferencia de goles (con signo y saturada), la interacción con el minuto, la superioridad numérica y el factor campo.
- g_X(t) es el perfil temporal (más ritmo al final, descuentos).
- Los β_X se estiman con datos históricos de eventos.

Como goles → estado → intensidades → goles forma un ciclo, **la simulación avanza tramo a tramo**. Dentro de cada tramo el grafo es acíclico; entre tramos el estado se arrastra. Es una red bayesiana dinámica.

## 3. Algoritmo de simulación (una iteración)

```
inicializar S_0 (0-0, 11v11, alineaciones, sin tarjetas)
para cada tramo t:
    para cada equipo X ∈ {A, B}:
        generar remates ~ Poisson(λ_sh_X(t) · Δt)   (con γ de sobredispersión por partido)
        asignar cada remate a un jugador en campo (p_i(t))
        resolver el embudo: bloqueado / fuera / a puerta → gol / parada / despeje
        generar córners derivados (bloqueos, paradas) + C_otros
        generar duelos por emparejamiento → entradas, faltas, tarjetas
    aplicar sustituciones (modelo de minutos) y expulsiones
    actualizar S_{t+1}
devolver el vector completo de estadísticas
```

**Sobredispersión e incertidumbre.** Al inicio de cada simulación se muestrea un "factor de partido" γ ~ Gamma por equipo y familia de eventos, y los parámetros salen de su posterior. Eso genera correlación realista entre mercados y colas más gruesas que Poisson.

**Rendimiento.** Se vectoriza sobre K simulaciones a la vez (arrays K × jugadores). Objetivo: menos de 30 segundos por partido tras publicarse las alineaciones, para tener margen antes del inicio.

## 4. Modelo de jugador y de minutos

**Tasas por 90 minutos.** Remates, % a puerta, distribución del xG por remate, duelos, entradas, faltas cometidas y recibidas, tarjetas por falta. Se estiman con un modelo jerárquico (jugador ⊂ posición ⊂ liga) con shrinkage proporcional a los minutos jugados.

**Pesos de asignación.** w_i son las cuotas de uso del jugador dentro de su equipo, ajustadas por rol y por el rival (Ley 3).

**Modelo de minutos:**
- P(titular): antes de las alineaciones sale de las previsiones; después vale 1 o 0.
- Distribución del minuto de sustitución, que depende del rol, la edad, la carga de partidos y el estado del marcador.
- Probabilidad de entrar desde el banquillo.

**Reglas de liquidación.** El "jugador no participa → apuesta nula" se aplica en la capa de mercados, no en el simulador.

## 5. Calibración macro contra el mercado sharp

1. **Quitar el margen.**
   - Métodos candidatos: multiplicativo, potencia y Shin.
   - Se elige por log-loss histórica contra resultados, por familia de mercado.
2. **Ajuste analítico inicial.** Se ajusta Dixon-Coles (λ_A, λ_B, ρ) a 1X2, hándicap asiático y over/under de goles conjuntamente, por mínimos cuadrados o KL sobre las probabilidades.
3. **Ajuste basado en simulación.** El estado del marcador deforma la distribución de goles, así que el θ base se ajusta minimizando
   $$\sum_m w_m \cdot KL\big(p^{mercado}_m \,\|\, p^{sim}_m(\theta)\big)$$
   - Se usan números aleatorios comunes para que la función objetivo sea suave.
   - w_m pondera cada mercado por su liquidez: los goles pesan más que los córners y las tarjetas.

**Identificabilidad (clave).** Los mercados de goles fijan *cuántos goles*, pero no separan volumen de remate y calidad por remate (16 remates a 0,08 de xG frente a 8 remates a 0,16). Ese reparto lo aportan los priors de estilo de cada equipo. Los mercados sharp de córners y tarjetas, si son líquidos, añaden restricciones independientes.

## 6. Estimación de parámetros (priors)

| Bloque | Parámetros | Datos | Método |
|---|---|---|---|
| Equipo | Volumen de remate, xG/remate, posesión por zona, PPDA, centros | Eventos de 2-3 temporadas | Jerárquico con decaimiento temporal |
| Jugador | Tasas por 90 (sección 4) | Eventos + minutos | Jerárquico con shrinkage |
| Portero | GSAx/PSxG | Remates a puerta con PSxG | Shrinkage fuerte (ruido alto) |
| Árbitro | Faltas por duelo, tarjetas por falta | Histórico de partidos dirigidos | Jerárquico hacia la media de la liga |
| Estado | β_X por familia de eventos | Eventos con minuto y marcador | GLM Poisson / NB con offsets |
| Córners | π^{c\|bl}, π^{c\|sv}, C^otros | Secuencias de eventos | Conteos condicionados |

## 7. Salidas y error Monte Carlo

- La probabilidad de un mercado es la frecuencia de su función de liquidación sobre las K simulaciones.
- El error estándar es $\sqrt{p(1-p)/K}$: con K = 50.000 y p = 0,5 sale ±0,0022. En mercados de cola (p < 0,1) el error relativo crece, y hay que aumentar K o usar técnicas de reducción de varianza.
- El error Monte Carlo es la parte pequeña. El error dominante es el **error de modelo**, que se mide con la validación (roadmap, sección de validación).

## 8. Detección de valor y stake

- **EV** = p_modelo · cuota − 1.
- **Umbral:** se alerta solo si el EV sigue siendo positivo con p tomada en un cuantil conservador de su incertidumbre (posterior de parámetros), más un margen mínimo configurable por familia de mercado.
- **Correlación:** las apuestas del mismo partido se evalúan como cartera, con Kelly fraccional multivariante sobre las simulaciones conjuntas. Varias apuestas de un mismo partido no se cuentan como independientes.
- **Registro:** cada alerta guarda la cuota, p_modelo, el EV, la hora y, después, la cuota de cierre sharp para medir el CLV.

## 9. Matriz de interdependencias (resumen)

| Nodo | Depende de | Afecta a |
|---|---|---|
| Estado del marcador | Goles acumulados, minuto, rojas | Todas las intensidades (Ley 4) |
| Remates (equipo) | θ, estilo, rival, estado | Remates del jugador (asignación), embudo, córners por bloqueo |
| Remates a puerta | Remates × precisión del rematador | Goles, paradas del rival, córners por parada |
| Goles | A puerta × P(gol \| a puerta, PSxG, portero) | Estado del marcador; restan paradas (identidad Ley 2) |
| Paradas | A puerta del rival − goles − despejes en línea | Córners del rival |
| Córners | Bloqueos, paradas, centros y despejes | Remates de cabeza, penaltis por agarrón (efecto menor) |
| Duelos | Emparejamientos, posesión por zona | Entradas, faltas cometidas/recibidas |
| Faltas | Duelos × φ × árbitro | Tarjetas, tiros libres (remates) |
| Tarjetas | Faltas × árbitro × estado × amarilla previa | Agresividad futura, riesgo de roja → intensidades |
| Alineación / bajas | Información pre-partido | Pesos de asignación, emparejamientos, θ |

## 10. Correcciones respecto al documento de visión original

1. **"Grafo acíclico" y "bucle de estado del marcador" son incompatibles.** Se resuelve con una simulación por tramos (red bayesiana dinámica).
2. **La conservación debe cumplirse en cada simulación**, no imponerse a posteriori. Se garantiza con la asignación multinomial.
3. **La identidad SoT = goles + paradas** incluye también los despejes en línea, excluye los goles en propia y depende del proveedor.
4. **P(córner | parada) ≈ 30 % y P(córner | bloqueo) ≈ 35 % no tienen fuente**: quedan como `TODO_CALIBRAR`. Además, los córners tienen un componente independiente de los remates, así que "imposible" pasa a "menos probable".
5. **La calibración contra el mercado sharp se hace sobre la salida simulada**, no solo sobre los λ de entrada.
6. **Los mercados de goles no identifican volumen frente a calidad de remate.** Hacen falta priors de estilo.
7. **La "distribución conjunta perfecta" no existe.** Es una aproximación con error Monte Carlo y error de modelo, y la ventaja se demuestra con el CLV.
8. **Faltaba la capa de liquidación por casa y proveedor**, que es crítica en los props de jugador.
9. **Las referencias a sindicatos profesionales y "el 99 % de los apostadores" son retórica**, no especificación, y se eliminan.
10. **El "simulador interactivo"** que mencionaba el documento no existía. Si se quiere, es una tarea de la fase 5 (herramienta de diagnóstico).
