"""Panel de seguimiento del bot, en el navegador.

Lee los archivos de estado y los jsonl que el rastreador va escribiendo, y se
refresca solo. Sirve para dejarlo abierto mientras una corrida larga avanza,
sin tocar el proceso ni ocupar la terminal.

La pregunta que tiene que responder de un vistazo es una sola: **esto sigue
recogiendo datos o se quedo quieto**. De ahi el punto que late junto al nombre
del portal, la banda de velocidad de los ultimos minutos, y que la cifra de
avance sea el conteo real de lineas del archivo y no el contador del proceso,
que se escribe cada pocos segundos y puede ir por detras.

Este archivo solo pinta. Lo que decide -si una corrida vive, en que estado
esta, como se lee un archivo a medio escribir- vive en `analisis/vigilancia.py`,
que no importa Streamlit y por tanto se puede probar.

Se ejecuta con:  streamlit run analisis/monitor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit ejecuta este archivo como guion suelto y pone en la ruta de busqueda
# la carpeta del archivo, no la raiz del proyecto. Sin esto, `import analisis`
# falla cuando el panel se abre con `streamlit run`, aunque funcione al
# importarlo desde la raiz. Se anade la raiz antes de cualquier import propio.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import os
import time
from collections import deque
from datetime import datetime

import streamlit as st

from analisis.estilo import (
    aplicar,
    banda_ritmo,
    barra_proporcion,
    chip,
    encabezado,
    paleta,
    panel,
)
from analisis.vigilancia import (
    NOMBRES_CAPA,
    ORDEN_CAPA,
    clasificar,
    contar_lineas,
    duracion,
    leer_estados,
    miles,
    proceso_vivo,
    ritmo,
    ultimos_avisos,
)

aplicar("Rastreador en marcha", icono=":material/radar:")

# La carpeta de datos se puede apuntar a otro sitio con ARRIENDOS_DATOS. Sirve
# para vigilar una corrida de otra copia del proyecto, y para probar el panel
# contra una carpeta de mentira sin ensuciar la de verdad, que es la que lee el
# exportador.
DIR_DATOS = Path(os.environ.get("ARRIENDOS_DATOS") or (RAIZ / "datos"))
DIR_CRUDO = DIR_DATOS / "crudo"

MUESTRAS_RITMO = 100  # a 3 s por muestra, unos cinco minutos de historia


if "historial" not in st.session_state:
    st.session_state.historial = {}

encabezado(
    "Rastreador en marcha",
    "Lee los archivos que el bot va escribiendo. No toca el proceso.",
    etiqueta="Seguimiento en vivo",
)


def color_de_capa(p: dict[str, str]) -> dict[str, str]:
    """Un color por peldano de la cascada, del mas barato al mas caro."""
    return {
        "api": p["musgo"],
        "a": p["serie_1"],
        "b": p["terracota"],
        "d": p["arcilla"],
        "e": p["serie_2"],
        "sin_capa": p["tinta_3"],
    }


def resumen_general(estados: list[dict], ahora: float) -> None:
    total_disco = sum(contar_lineas(f) for f in DIR_CRUDO.glob("*.jsonl"))
    aciertos = sum(e.get("cache_aciertos", 0) for e in estados)
    fallos = sum(e.get("cache_fallos", 0) for e in estados)
    costo = sum(e.get("costo_modelo_usd", 0.0) for e in estados)
    activas = sum(
        1 for e in estados if not e.get("terminado") and proceso_vivo(e.get("pid", 0))
    )
    consultas = aciertos + fallos

    with panel():
        c = st.columns(4)
        c[0].metric("Avisos en disco", miles(total_disco), help="Todos los portales")
        c[1].metric(
            "Corridas activas", str(activas), help="Procesos vivos que aún no han terminado"
        )
        c[2].metric(
            "Aciertos de caché",
            f"{100 * aciertos / consultas:.1f} %".replace(".", ",") if consultas else "–",
            help="Páginas servidas desde el caché en vez de volver a descargarlas",
        )
        c[3].metric(
            "Costo del modelo",
            ("US$ " + f"{costo:,.2f}").replace(",", "@").replace(".", ",").replace("@", "."),
            help="Solo se gasta cuando la última capa de la cascada tiene que intervenir",
        )
        st.markdown(
            f'<p class="nota-pie">Actualizado a las '
            f'{datetime.now().strftime("%H:%M:%S")} · se refresca cada 3 segundos</p>',
            unsafe_allow_html=True,
        )


def tarjeta_portal(portal: str, datos: dict, est: dict, ahora: float, p: dict) -> None:
    descubiertos = datos.get("descubiertos", 0)
    descargados = datos.get("descargados", 0)
    extraidos = datos.get("extraidos", 0)
    fallidos = datos.get("fallidos", 0)
    omitidos = datos.get("omitidos", 0)

    iniciado = est.get("iniciado_en", ahora)
    ultimo = est.get("ultimo_aviso_en", iniciado)
    pid = est.get("pid", 0)
    terminado = bool(est.get("terminado", False))
    sin_avisos = ahora - ultimo

    en_disco = contar_lineas(DIR_CRUDO / f"{portal}.jsonl")

    # Historia de la velocidad. Se anota una muestra cuando el conteo cambia, o
    # cada dos segundos aunque no cambie: sin lo segundo, una parada larga no
    # dejaria rastro en la banda y pareceria que el tiempo no pasa.
    historia = st.session_state.historial.setdefault(portal, deque(maxlen=MUESTRAS_RITMO))
    if not historia or historia[-1][1] != en_disco or ahora - historia[-1][0] > 2:
        historia.append((ahora, en_disco))

    velocidad = None
    if len(historia) >= 2:
        (t0, n0), (t1, n1) = historia[0], historia[-1]
        if t1 > t0:
            velocidad = max((n1 - n0) / (t1 - t0), 0.0)

    estado = clasificar(terminado, proceso_vivo(pid), sin_avisos)

    with panel():
        st.markdown(
            f'<div class="titulo-portal">{portal}{chip(estado.rotulo, estado.tono)}</div>',
            unsafe_allow_html=True,
        )

        if descubiertos:
            avance = min(max(descargados, en_disco) / descubiertos, 1.0)
            st.progress(
                avance,
                text=f"{avance * 100:.1f}".replace(".", ",")
                + f" % de {miles(descubiertos)} avisos descubiertos",
            )

        c = st.columns(6)
        c[0].metric("Descubiertos", miles(descubiertos))
        c[1].metric("Extraídos", miles(extraidos))
        c[2].metric("En disco", miles(en_disco), help="Líneas reales del archivo")
        c[3].metric("Fallidos", miles(fallidos))
        c[4].metric("Transcurrido", duracion(ahora - iniciado))

        if velocidad and velocidad > 0.01 and descubiertos > max(descargados, en_disco):
            restantes = descubiertos - max(descargados, en_disco)
            c[5].metric(
                "Faltan",
                duracion(restantes / velocidad),
                help=f"Al ritmo actual de {ritmo(velocidad)}",
            )
        else:
            c[5].metric("Ritmo", ritmo(velocidad))

        izq, der = st.columns([1, 1], gap="large")

        with izq:
            # En una corrida terminada la banda seria una linea plana en cero,
            # que no informa de nada: se dibuja solo mientras puede cambiar.
            banda = "" if terminado else banda_ritmo(historia, p["terracota"])
            if banda:
                st.markdown(
                    '<p class="nota-pie" style="margin-bottom:2px">Velocidad de los '
                    "últimos minutos</p>" + banda,
                    unsafe_allow_html=True,
                )
            elif not terminado:
                st.markdown(
                    '<p class="nota-pie">Midiendo la velocidad…</p>', unsafe_allow_html=True
                )

            capas = datos.get("por_capa") or {}
            if capas:
                colores = color_de_capa(p)
                partes = [
                    (NOMBRES_CAPA.get(k, k), capas[k], colores.get(k, p["tinta_3"]))
                    for k in ORDEN_CAPA
                    if capas.get(k)
                ]
                st.markdown(
                    '<p class="nota-pie" style="margin-top:14px">Resuelto por capa de la '
                    "cascada</p>" + barra_proporcion(partes),
                    unsafe_allow_html=True,
                )

            motivos = datos.get("motivos_fallo") or {}
            if motivos:
                lista = " · ".join(
                    f"<b>{v}</b> {k}"
                    for k, v in sorted(motivos.items(), key=lambda x: -x[1])
                )
                st.markdown(
                    f'<p class="nota-pie" style="margin-top:12px">Motivos de fallo: {lista}</p>',
                    unsafe_allow_html=True,
                )

        with der:
            st.markdown(
                '<p class="nota-pie" style="margin-bottom:6px">Últimos avisos recogidos</p>',
                unsafe_allow_html=True,
            )
            ultimos = ultimos_avisos(DIR_CRUDO / f"{portal}.jsonl")
            if ultimos.empty:
                st.markdown(
                    '<p class="nota-pie">Todavía no hay avisos en el archivo.</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.dataframe(ultimos, hide_index=True, use_container_width=True, height=248)

        detalles = [f"último aviso hace {duracion(sin_avisos)}"]
        if omitidos:
            detalles.append(f"{miles(omitidos)} omitidos al reanudar")
        if pid:
            detalles.append(f"pid {pid}")
        st.markdown(f'<p class="nota-pie">{" · ".join(detalles)}</p>', unsafe_allow_html=True)


@st.fragment(run_every="3s")
def panel_completo() -> None:
    estados = leer_estados(DIR_DATOS)
    if not estados:
        st.info(
            "No hay ninguna corrida registrada todavía. Lanza una desde otra terminal "
            "con `python -m rastreador.cli raspar --portal fincaraiz`.",
            icon=":material/hourglass_empty:",
        )
        return

    ahora = time.time()
    p = paleta()

    resumen_general(estados, ahora)
    for est in estados:
        for portal, datos in (est.get("portales") or {}).items():
            tarjeta_portal(portal, datos, est, ahora, p)


panel_completo()

with st.sidebar:
    st.markdown('<span class="etiqueta-seccion">Cómo usarlo</span>', unsafe_allow_html=True)
    st.markdown(
        """
Deja esta página abierta mientras una corrida avanza. Se refresca sola cada tres
segundos leyendo los archivos que el bot escribe, sin tocar el proceso.

**Lanzar una corrida** desde otra terminal:

```
python -m rastreador.cli raspar --portal fincaraiz
```

**Los cuatro estados**

- **Activa** — el proceso vive y llegan avisos.
- **Sin avance** — vive, pero lleva más de tres minutos sin recoger nada. Casi
  siempre es el portal limitando el ritmo, no un fallo.
- **El proceso ya no existe** — murió sin terminar. Volver a lanzarlo reanuda
  desde donde iba.
- **Terminada** — acabó bien.

**En disco** cuenta las líneas reales del archivo, que es la medida más fiable
del avance: el contador del proceso se escribe cada pocos segundos y puede ir
por detrás.

La **banda de velocidad** muestra los últimos minutos. Una línea plana en cero
con estado *Activa* significa que el bot está esperando su turno, respetando el
límite del portal.
"""
    )
