"""Lectura del estado del rastreador, sin nada de interfaz.

El monitor era un solo archivo que leia el disco, decidia si una corrida estaba
viva y ademas la dibujaba. Eso lo hacia imposible de probar: cualquier prueba
tenia que arrancar Streamlit. Aqui queda la parte que decide, que es la que se
puede equivocar; `analisis/monitor.py` se queda con la que pinta.

Nada de este modulo importa Streamlit.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# Segundos sin recoger un aviso antes de avisar. Tres minutos es holgado a
# proposito: los portales limitan el ritmo y una pausa de un minuto es normal.
INACTIVIDAD_ALERTA = 180.0

NOMBRES_CAPA = {
    "api": "API interna",
    "a": "Estructurados (ld+json)",
    "b": "Estado embebido (JS)",
    "d": "Heuristica HTML",
    "e": "Modelo de lenguaje",
    "sin_capa": "Sin identificar",
}

# El orden de la cascada, de la capa mas barata a la mas cara. Fija tambien el
# orden de la barra de composicion, para que se lea como lo que es: cuanto
# resolvio cada peldano antes de tener que bajar al siguiente.
ORDEN_CAPA = ["api", "a", "b", "d", "e", "sin_capa"]


# --- estado del proceso ---


def proceso_vivo(pid: int) -> bool:
    """True si el proceso con ese identificador sigue existiendo."""
    if not pid:
        return False
    try:
        if os.name == "nt":
            import ctypes

            # 0x1000 es PROCESS_QUERY_LIMITED_INFORMATION: el permiso minimo
            # que basta para preguntar si existe, sin pedir acceso al proceso.
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        os.kill(pid, 0)  # senal cero: no hace nada, solo comprueba
        return True
    except (OSError, PermissionError):
        return False


@dataclass(frozen=True)
class Estado:
    """Como esta una corrida y por que."""

    rotulo: str
    tono: str  # clase del punto: "", "quieto", "parado" o "hecho"

    @property
    def activa(self) -> bool:
        return self.tono == ""


def clasificar(terminado: bool, vivo: bool, segundos_sin_avisos: float) -> Estado:
    """Decide el estado de una corrida. Un solo sitio donde se decide.

    El orden importa: una corrida terminada se declara terminada aunque su
    proceso ya no exista, porque acabar es justamente dejar de existir. Si se
    comprobara primero si vive, toda corrida exitosa se anunciaria como caida.
    """
    if terminado:
        return Estado("Terminada", "hecho")
    if not vivo:
        return Estado("El proceso ya no existe", "parado")
    if segundos_sin_avisos >= INACTIVIDAD_ALERTA:
        return Estado("Sin avance", "quieto")
    return Estado("Activa", "")


# --- lectura de archivos ---


def leer_estados(dir_datos: Path) -> list[dict]:
    """Todos los archivos de estado, saltando los que esten a medio escribir."""
    estados = []
    for ruta in sorted(dir_datos.glob("estado*.json")):
        try:
            d = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # El rastreador reescribe el archivo entero cada pocos segundos. Si
            # se lee justo en ese instante sale JSON truncado: se salta esta
            # pasada y se lee en la siguiente, tres segundos despues.
            continue
        d["_archivo"] = ruta.name
        estados.append(d)
    return estados


def contar_lineas(ruta: Path) -> int:
    """Avisos en disco. Es la medida mas fiable del avance.

    El contador que lleva el proceso se vuelca cada pocos segundos y va por
    detras; el archivo, en cambio, ya tiene escrito lo que tiene escrito.
    """
    if not ruta.exists():
        return 0
    try:
        with ruta.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def ultimos_avisos(ruta: Path, n: int = 8):
    """Los ultimos avisos del archivo, leyendo solo su cola.

    Un jsonl de un raspado largo pesa decenas de megas. Leerlo entero cada tres
    segundos para mostrar ocho filas seria absurdo, asi que se salta al final y
    se leen los ultimos sesenta kilobytes hacia atras.
    """
    import pandas as pd

    if not ruta.exists():
        return pd.DataFrame()
    try:
        tam = ruta.stat().st_size
        with ruta.open("rb") as fh:
            fh.seek(max(0, tam - 60_000))
            cola = fh.read().decode("utf-8", "replace")
    except OSError:
        return pd.DataFrame()

    filas = []
    for linea in reversed(cola.splitlines()):
        linea = linea.strip()
        if not linea.startswith("{"):
            # La primera linea del trozo casi siempre esta cortada por la mitad.
            continue
        try:
            filas.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
        if len(filas) >= n:
            break
    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame(filas)

    # Los avisos recogidos antes de que el barrio entrara a la cascada no lo
    # traen en el archivo; se deriva de la URL para no mostrar una columna
    # vacia que parece un fallo y no lo es.
    if "url" in df.columns:
        from rastreador.extraccion.cascada import barrio_desde_url

        if "barrio" not in df.columns:
            df["barrio"] = None
        df["barrio"] = df["barrio"].fillna(df["url"].map(barrio_desde_url))

    columnas = [
        c
        for c in ["barrio", "precio", "area_privada", "alcobas", "estrato", "capa"]
        if c in df.columns
    ]
    return df[columnas]


# --- formato ---


def miles(valor) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def duracion(segundos: float | None) -> str:
    """Duracion legible: '22 h 16 m', '4 m 09 s', '37 s'.

    Se corta en la segunda unidad a proposito: en un panel que se refresca cada
    tres segundos, los segundos de una corrida de veintidos horas son ruido.
    """
    if segundos is None:
        return "–"
    s = int(segundos)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} h {m:02d} m"
    if m:
        return f"{m} m {s:02d} s"
    return f"{s} s"


def ritmo(valor: float | None) -> str:
    if valor is None:
        return "–"
    return f"{valor:.1f}/s".replace(".", ",") if valor < 10 else f"{valor:.0f}/s"
