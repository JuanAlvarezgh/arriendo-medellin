"""Lenguaje visual compartido de los dos paneles de Streamlit.

El tablero del analisis y el monitor del bot son herramientas distintas, pero
son del mismo proyecto y deben parecerlo. Aqui vive lo que las iguala: la paleta
"Modern Organic Glass" de la pagina del informe -superficie calida de arena,
tinta cafe en vez de negro, terracota como acento, cristal esmerilado y manchas
organicas en el fondo-, mas los pocos componentes que Streamlit no trae.

El reparto es deliberado:

* `.streamlit/config.toml` lleva lo que Streamlit sabe tematizar por si mismo:
  colores base, tipografias, radios, colores de las graficas. Eso hace que los
  controles nativos -selectores, deslizadores, tablas- salgan ya en paleta, sin
  pelearse con el CSS.
* Este modulo lleva lo que el tema no alcanza: el cristal, las manchas, las
  pestanas en pastilla y los componentes propios.

Los colores se emiten como valores concretos segun el tema activo, en vez de
depender de `prefers-color-scheme`. La razon es que Streamlit tiene su propio
interruptor de tema, independiente del sistema operativo: preguntandole a el
-`st.context.theme`- el CSS inyectado siempre concuerda con lo que el usuario
ve, y no con lo que tenga configurado el escritorio.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Sequence

import streamlit as st

# Los mismos tokens de analisis/web/plantilla.html. Si cambian alli, cambian
# aqui: son el mismo proyecto visto por dos ventanas distintas.
CLARO = {
    "arena_0": "#fbf8f3",
    "arena_1": "#f4efe6",
    "arena_2": "#eae2d5",
    "arena_3": "#ddd2c0",
    "tinta": "#262320",
    "tinta_2": "#5f584e",
    "tinta_3": "#928a7d",
    "terracota": "#b0603a",
    "musgo": "#6c7f5f",
    "arcilla": "#c98c5e",
    "vidrio": "rgba(255, 255, 255, 0.55)",
    "vidrio_fuerte": "rgba(255, 255, 255, 0.75)",
    "vidrio_borde": "rgba(255, 255, 255, 0.85)",
    "sombra": "0 10px 40px rgba(94, 82, 66, .10), 0 2px 8px rgba(94, 82, 66, .05)",
    "mancha_1": "#cbd8c3",
    "mancha_2": "#f0d9c2",
    "mancha_3": "#d9cfe2",
    "opacidad_mancha": ".50",
    "serie_1": "#2a78d6",
    "serie_2": "#eb6834",
    "alerta": "#c0392b",
}

OSCURO = {
    "arena_0": "#131210",
    "arena_1": "#1b1917",
    "arena_2": "#23201c",
    "arena_3": "#2f2b25",
    "tinta": "#f2ede4",
    "tinta_2": "#b8b0a3",
    "tinta_3": "#857d70",
    "terracota": "#d98a5f",
    "musgo": "#9bb18a",
    "arcilla": "#d9a877",
    "vidrio": "rgba(46, 43, 38, 0.58)",
    "vidrio_fuerte": "rgba(52, 48, 42, 0.78)",
    "vidrio_borde": "rgba(255, 255, 255, 0.10)",
    "sombra": "0 10px 40px rgba(0, 0, 0, .34)",
    "mancha_1": "#35402f",
    "mancha_2": "#47372a",
    "mancha_3": "#363048",
    "opacidad_mancha": ".38",
    "serie_1": "#3987e5",
    "serie_2": "#d95926",
    "alerta": "#e66767",
}

FUENTES = (
    "https://fonts.googleapis.com/css2?"
    "family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700"
    "&family=Inter:wght@400;500;600&display=swap"
)


def tema() -> str:
    """'light' u 'oscuro' segun lo que Streamlit este mostrando ahora mismo.

    Se pregunta al contexto y no al sistema operativo porque Streamlit lleva su
    propio interruptor en el menu: si el usuario fuerza el modo oscuro con el
    escritorio en claro, `prefers-color-scheme` diria claro y el CSS inyectado
    pintaria texto oscuro sobre fondo oscuro.
    """
    try:
        return getattr(getattr(st, "context", None).theme, "type", None) or "light"
    except Exception:
        return "light"


def paleta() -> dict[str, str]:
    return OSCURO if tema() == "dark" else CLARO


def _css(p: dict[str, str]) -> str:
    return f"""
<style>
@import url('{FUENTES}');

:root {{
  --arena-0: {p["arena_0"]};
  --arena-1: {p["arena_1"]};
  --arena-2: {p["arena_2"]};
  --arena-3: {p["arena_3"]};
  --tinta:   {p["tinta"]};
  --tinta-2: {p["tinta_2"]};
  --tinta-3: {p["tinta_3"]};
  --terracota: {p["terracota"]};
  --musgo:   {p["musgo"]};
  --arcilla: {p["arcilla"]};
  --alerta:  {p["alerta"]};
  --vidrio:  {p["vidrio"]};
  --vidrio-fuerte: {p["vidrio_fuerte"]};
  --vidrio-borde:  {p["vidrio_borde"]};
  --sombra: {p["sombra"]};
  --radio: 20px;
  --radio-sm: 13px;
  --suave: cubic-bezier(.22,.61,.36,1);
}}

/* ── Fondo orgánico ─────────────────────────────────────────
   Dos manchas difuminadas que derivan muy despacio. Van en
   pseudoelementos de la aplicación y no en divs inyectados, para
   no meter nodos que Streamlit vuelve a dibujar en cada pasada. */

.stApp {{ background: var(--arena-1); }}

.stApp::before, .stApp::after {{
  content: ""; position: fixed; pointer-events: none; z-index: 0;
  border-radius: 46% 54% 62% 38% / 52% 44% 56% 48%;
  filter: blur(72px); opacity: {p["opacidad_mancha"]};
  animation: deriva 38s var(--suave) infinite alternate;
}}
.stApp::before {{
  width: 46vw; height: 46vw; left: -12vw; top: -10vw;
  background: {p["mancha_1"]};
}}
.stApp::after {{
  width: 40vw; height: 40vw; right: -10vw; top: 34vh;
  background: {p["mancha_2"]}; animation-delay: -14s;
}}

@keyframes deriva {{
  from {{ transform: translate3d(0,0,0) scale(1) rotate(0deg); }}
  to   {{ transform: translate3d(3vw,-3vh,0) scale(1.14) rotate(14deg); }}
}}
@media (prefers-reduced-motion: reduce) {{
  .stApp::before, .stApp::after {{ animation: none; }}
}}

[data-testid="stAppViewContainer"] {{ background: transparent; position: relative; z-index: 1; }}
[data-testid="stMain"] {{ background: transparent; }}
[data-testid="stBottomBlockContainer"] {{ background: transparent; }}

[data-testid="stHeader"] {{
  background: transparent;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}}

[data-testid="stMainBlockContainer"] {{
  padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1360px;
}}

/* ── Tipografía ─────────────────────────────────────────────
   Fraunces es una serif variable con eje óptico: a tamaño de
   titular conviene apretar el interletraje, que por defecto va
   calibrado para texto corrido. */

h1, h2, h3 {{
  font-family: Fraunces, Georgia, serif !important;
  font-optical-sizing: auto;
  letter-spacing: -0.02em;
  color: var(--tinta);
}}
h1 {{ font-weight: 600 !important; line-height: 1.06; }}
h2 {{ font-weight: 600 !important; }}
h3 {{ font-size: 1.18rem !important; }}

[data-testid="stCaptionContainer"], .stCaption {{ color: var(--tinta-3) !important; }}

/* ── Cristal ────────────────────────────────────────────────
   El panel se reconoce por una marca invisible que `panel()`
   escribe dentro, no por la clase que Streamlit le ponga.

   Es a proposito: entre versiones, Streamlit ha renombrado el
   contenedor con borde, ha quitado los atributos `data-baseweb`
   y ha cambiado las clases generadas. Un estilo colgado de esos
   nombres deja de aplicarse en una actualizacion menor y no
   avisa: la pagina sigue saliendo, solo que sin estilo. Colgado
   de una marca propia, sobrevive. */

.marca-panel {{ display: none; }}

[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .marca-panel) {{
  background: var(--vidrio);
  backdrop-filter: blur(20px) saturate(175%);
  -webkit-backdrop-filter: blur(20px) saturate(175%);
  border: 1px solid var(--vidrio-borde);
  border-radius: var(--radio);
  box-shadow: var(--sombra);
  padding: 20px 22px;
}}

/* ── Indicadores ────────────────────────────────────────────
   Cada métrica es una tarjeta, no una línea de texto: es lo que
   más se mira y lo que mejor aguanta el tratamiento de cristal. */

[data-testid="stMetric"] {{
  background: var(--vidrio);
  backdrop-filter: blur(20px) saturate(175%);
  -webkit-backdrop-filter: blur(20px) saturate(175%);
  border: 1px solid var(--vidrio-borde);
  border-radius: var(--radio);
  box-shadow: var(--sombra);
  padding: 16px 18px 14px;
  transition: transform .25s var(--suave), box-shadow .25s var(--suave);
}}
[data-testid="stMetric"]:hover {{
  transform: translateY(-2px);
  box-shadow: 0 16px 46px rgba(94, 82, 66, .14);
}}
/* El valor se deja envolver y se acota con el ancho de la columna.
   Streamlit lo recorta con puntos suspensivos y una duracion como
   "22 h 16 m" salia como "22 h ..." en una fila de seis columnas. */
[data-testid="stMetricValue"] {{
  font-family: Fraunces, Georgia, serif;
  font-weight: 600; letter-spacing: -0.022em; line-height: 1.12;
  font-size: clamp(1.15rem, 1.75vw, 1.72rem) !important;
  color: var(--tinta);
  white-space: normal; overflow: visible; text-overflow: clip;
}}
[data-testid="stMetricValue"] > div {{
  white-space: normal; overflow: visible; text-overflow: clip;
}}
[data-testid="stMetricLabel"] p {{
  font-size: .78rem !important; font-weight: 500;
  color: var(--tinta-2) !important; letter-spacing: .01em;
}}
[data-testid="stMetricDelta"] {{ font-size: .76rem !important; }}

/* ── Pestañas en pastilla ───────────────────────────────────
   La barra inferior de Streamlit marca la pestaña activa con un
   subrayado; con pastillas sobra y se retira. */

[data-testid="stTabs"] [role="tablist"] {{
  gap: 6px; background: transparent; border-bottom: none;
  flex-wrap: wrap; padding-bottom: 8px; margin-bottom: 10px;
}}
[data-testid="stTab"] {{
  height: auto; padding: 8px 16px; border-radius: 999px !important;
  background: transparent; border: 1px solid transparent;
  color: var(--tinta-2); font-weight: 500; font-size: .9rem;
  transition: all .2s var(--suave); white-space: nowrap;
}}
[data-testid="stTab"]:hover {{ background: var(--vidrio-fuerte); color: var(--tinta); }}
[data-testid="stTab"][aria-selected="true"] {{
  background: var(--vidrio-fuerte);
  border-color: var(--vidrio-borde);
  color: var(--tinta); font-weight: 600;
  box-shadow: var(--sombra);
}}
/* La barra que marca la pestaña activa sobra cuando ya hay pastilla. */
[data-testid="stTabs"] [role="tablist"] + div[style*="height"],
[data-testid="stTabs"] [data-testid="stTabHighlight"] {{ display: none; }}

/* ── Avisos y desplegables ──────────────────────────────────
   Un filo de color a la izquierda dice de qué tipo es el aviso
   sin recurrir a un fondo saturado que rompa la superficie. */

[data-testid="stAlert"] {{
  background: var(--vidrio) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--vidrio-borde) !important;
  border-left: 3px solid var(--terracota) !important;
  border-radius: var(--radio-sm) !important;
  box-shadow: var(--sombra);
}}
[data-testid="stExpander"] details {{
  background: var(--vidrio);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--vidrio-borde) !important;
  border-radius: var(--radio-sm) !important;
}}
[data-testid="stExpander"] summary:hover {{ color: var(--terracota); }}

hr, [data-testid="stDivider"] hr {{
  border-color: var(--arena-3); opacity: .7;
}}

/* ── Barra de progreso ──────────────────────────────────────*/

[data-testid="stProgressBarTrack"] {{ background: var(--arena-2); border-radius: 999px; }}
[data-testid="stProgressBarTrack"] > div {{
  background: linear-gradient(90deg, var(--arcilla), var(--terracota));
  border-radius: 999px;
}}

/* ── Tablas ─────────────────────────────────────────────────*/

[data-testid="stDataFrame"], [data-testid="stTable"] {{
  border-radius: var(--radio-sm); overflow: hidden;
  border: 1px solid var(--arena-3);
}}

/* ── Barra lateral ──────────────────────────────────────────*/

[data-testid="stSidebar"] {{
  backdrop-filter: blur(24px) saturate(160%);
  -webkit-backdrop-filter: blur(24px) saturate(160%);
  border-right: 1px solid var(--arena-3);
}}
[data-testid="stSidebar"] .block-container {{ padding-top: 2.2rem; }}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] li {{ font-size: .89rem; }}
[data-testid="stSidebar"] code {{ font-size: .78rem; }}
/* El comando de ejemplo es mas ancho que la barra: que se desplace en vez de
   desbordarse por debajo del borde. */
[data-testid="stSidebar"] [data-testid="stCode"] {{ overflow-x: auto; }}

/* ── Componentes propios ────────────────────────────────────*/

.etiqueta-seccion {{
  display: inline-flex; align-items: center; gap: 8px;
  font: 500 12px Inter, sans-serif; letter-spacing: .08em;
  text-transform: uppercase; color: var(--tinta-2);
  padding: 6px 14px; border-radius: 999px; margin-bottom: 16px;
  background: var(--vidrio); border: 1px solid var(--vidrio-borde);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}}

.pulso {{
  width: 8px; height: 8px; border-radius: 50%; flex: none;
  background: var(--musgo); box-shadow: 0 0 0 0 currentColor;
  animation: latido 2.1s ease-out infinite;
}}
.pulso.quieto  {{ background: var(--arcilla); animation: none; }}
.pulso.parado  {{ background: var(--alerta);  animation: none; }}
.pulso.hecho   {{ background: var(--tinta-3); animation: none; }}

@keyframes latido {{
  0%   {{ box-shadow: 0 0 0 0 rgba(108,127,95,.55); }}
  70%  {{ box-shadow: 0 0 0 9px rgba(108,127,95,0); }}
  100% {{ box-shadow: 0 0 0 0 rgba(108,127,95,0); }}
}}
@media (prefers-reduced-motion: reduce) {{ .pulso {{ animation: none; }} }}

.chip {{
  display: inline-flex; align-items: center; gap: 8px;
  font: 600 11.5px Inter, sans-serif; letter-spacing: .07em;
  text-transform: uppercase; padding: 5px 13px; border-radius: 999px;
  background: var(--vidrio-fuerte); border: 1px solid var(--vidrio-borde);
  color: var(--tinta-2); vertical-align: middle;
}}

.titulo-portal {{
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin: 0 0 4px;
  font: 600 1.55rem/1.15 Fraunces, Georgia, serif; letter-spacing: -0.02em;
  color: var(--tinta);
}}

/* Barra de proporción: una fila de segmentos con su leyenda debajo.
   Sustituye a una tabla de tres filas que decía lo mismo peor. */
.proporcion {{
  display: flex; width: 100%; height: 12px; border-radius: 999px;
  overflow: hidden; background: var(--arena-2); margin: 4px 0 10px;
}}
.proporcion span {{ display: block; height: 100%; }}
.leyenda-prop {{ display: flex; flex-wrap: wrap; gap: 6px 18px; }}
.leyenda-prop div {{
  display: flex; align-items: center; gap: 7px;
  font-size: 12.5px; color: var(--tinta-2);
}}
.leyenda-prop i {{
  width: 10px; height: 10px; border-radius: 3px; flex: none; display: block;
}}
.leyenda-prop b {{ color: var(--tinta); font-weight: 600; font-variant-numeric: tabular-nums; }}

.nota-pie {{ color: var(--tinta-3); font-size: 12.5px; margin: 2px 0 0; }}
</style>
"""


def aplicar(titulo: str, icono: str = ":material/insights:", ancho: str = "wide") -> None:
    """Configura la pagina e inyecta el estilo. Primera llamada del guion.

    `st.set_page_config` tiene que ser la primera orden de Streamlit del
    archivo, asi que la configuracion y el estilo van juntos en una sola
    llamada: separarlos invita a colar una orden en medio y romperlo.
    """
    st.set_page_config(page_title=titulo, layout=ancho, page_icon=icono)
    st.markdown(_css(paleta()), unsafe_allow_html=True)


def encabezado(titulo: str, bajada: str = "", etiqueta: str = "") -> None:
    """Portada de la pagina, con la etiqueta de cristal de la web."""
    if etiqueta:
        st.markdown(
            f'<span class="etiqueta-seccion"><span class="pulso"></span>{etiqueta}</span>',
            unsafe_allow_html=True,
        )
    st.title(titulo)
    if bajada:
        st.caption(bajada)


@contextmanager
def panel(clave: str | None = None):
    """Tarjeta de cristal.

    Deja dentro una marca invisible, que es de lo que cuelga el CSS. Vale un
    nodo de mas por no depender de como llame Streamlit a su contenedor con
    borde, que ha cambiado de nombre varias veces.
    """
    with st.container(key=clave):
        # st.html y no st.markdown: el markdown pasa por un saneador que se
        # come las etiquetas vacias, y la marca desaparecia sin dejar rastro.
        st.html('<span class="marca-panel"></span>')
        yield


def chip(texto: str, estado: str = "hecho") -> str:
    """Pastilla de estado con su punto de color.

    Devuelve HTML en vez de escribirlo, para poder componerlo dentro de un
    titulo en la misma linea.
    """
    return f'<span class="chip"><span class="pulso {estado}"></span>{texto}</span>'


def barra_proporcion(partes: Iterable[tuple[str, int, str]]) -> str:
    """Barra de una sola fila con la composicion de un total.

    Cada parte es (rotulo, cantidad, color). Devuelve la barra y su leyenda con
    el porcentaje ya calculado; con dos o tres categorias se lee de un vistazo,
    que es justo lo que una tabla de tres filas no consigue.
    """
    partes = [p for p in partes if p[1] > 0]
    total = sum(c for _, c, _ in partes)
    if not total:
        return ""

    segmentos = "".join(
        f'<span style="width:{100 * c / total:.4f}%;background:{color}" '
        f'title="{rotulo}: {c}"></span>'
        for rotulo, c, color in partes
    )
    leyenda = "".join(
        f'<div><i style="background:{color}"></i>{rotulo} '
        f"<b>{100 * c / total:.1f} %</b></div>".replace(".", ",")
        for rotulo, c, color in partes
    )
    return f'<div class="proporcion">{segmentos}</div><div class="leyenda-prop">{leyenda}</div>'


def banda_ritmo(muestras: Sequence[tuple[float, int]], color: str, alto: int = 44) -> str:
    """Banda de la velocidad reciente, dibujada en SVG.

    Recibe pares (instante, acumulado) y dibuja la derivada: cuantas unidades
    por segundo entre muestra y muestra. Es la respuesta grafica a "sigue
    recogiendo": una linea que cae a cero se ve antes que un contador que deja
    de cambiar.

    Va como SVG en linea y no como grafica de Streamlit porque se redibuja cada
    tres segundos, y una grafica completa con sus ejes y su cromo pesa mas de lo
    que aporta a este tamano.
    """
    pares = list(muestras)
    if len(pares) < 3:
        return ""

    ritmos = []
    for (t0, n0), (t1, n1) in zip(pares, pares[1:]):
        dt = t1 - t0
        # Nunca negativo: si el archivo se trunca o se reinicia la corrida, el
        # acumulado puede bajar, y una velocidad negativa no significa nada.
        ritmos.append(max((n1 - n0) / dt, 0) if dt > 0 else 0)
    if not ritmos:
        return ""

    ancho, margen = 100.0, 3.0
    # El tope minimo evita dividir por cero cuando todo el tramo esta parado.
    tope = max(max(ritmos), 0.001)
    paso = ancho / max(len(ritmos) - 1, 1)
    puntos = [
        (i * paso, alto - margen - (r / tope) * (alto - 2 * margen))
        for i, r in enumerate(ritmos)
    ]

    linea = " ".join(f"{x:.2f},{y:.2f}" for x, y in puntos)
    area = f"0,{alto} {linea} {puntos[-1][0]:.2f},{alto}"

    return f"""
<svg viewBox="0 0 {ancho} {alto}" preserveAspectRatio="none"
     style="width:100%;height:{alto}px;display:block" role="img"
     aria-label="Velocidad de recolección de los últimos minutos">
  <polygon points="{area}" fill="{color}" opacity=".16"/>
  <polyline points="{linea}" fill="none" stroke="{color}" stroke-width="1.6"
            stroke-linejoin="round" stroke-linecap="round"
            vector-effect="non-scaling-stroke"/>
  <circle cx="{puntos[-1][0]:.2f}" cy="{puntos[-1][1]:.2f}" r="2.2" fill="{color}"
          vector-effect="non-scaling-stroke"/>
</svg>"""


def colores_serie(n: int) -> list[str]:
    """n colores de la paleta, para asignar a categorias."""
    p = paleta()
    base = [p["serie_1"], p["serie_2"], p["musgo"], p["terracota"], p["arcilla"], p["tinta_3"]]
    return [base[i % len(base)] for i in range(n)]
