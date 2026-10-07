"""Genera la pagina de consulta como un unico archivo HTML autocontenido.

Sigue las mismas reglas que `pagina.py`: datos y MapLibre empotrados, para que el
archivo se abra con doble clic y siga funcionando sin servidor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import consulta
from .hedonico import preparar
from .pagina import MAPA_SATELITE, biblioteca
from .sitio import insertar

RAIZ = Path(__file__).resolve().parent
PLANTILLA = RAIZ / "web" / "consulta.html"
GUION = RAIZ / "web" / "consulta.js"
ENTRADA = Path("datos/salidas/geo_enriquecido.parquet")
SALIDA = Path("datos/salidas/web/consulta_arriendos.html")


def datos(entrada: Path = ENTRADA) -> dict:
    geo = pd.read_parquet(entrada)
    # Sin ventana de 90 dias: la consulta describe lo que hoy se pide en los
    # portales, y un aviso viejo sigue siendo una opcion que el usuario ve.
    d = consulta.preparar_consulta(preparar(geo, ventana_dias=None))
    return consulta.construir(d)


def construir(salida: Path = SALIDA, entrada: Path = ENTRADA) -> Path:
    serializado = json.dumps(datos(entrada), ensure_ascii=False, separators=(",", ":"))
    serializado = serializado.replace("</", "<\\/")

    html = (
        PLANTILLA.read_text(encoding="utf-8")
        .replace("__ESTILO_MAPLIBRE__", biblioteca("maplibre-gl.css"))
        .replace("__MAPLIBRE__", biblioteca("maplibre-gl.js"))
        .replace("__MAPA_SATELITE__", MAPA_SATELITE.read_text(encoding="utf-8"))
        .replace("__DATOS__", serializado)
        .replace("__GUION__", GUION.read_text(encoding="utf-8"))
    )
    html = insertar(html, "buscar")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")
    return salida


if __name__ == "__main__":
    ruta = construir()
    print(f"escrito en {ruta}  ({ruta.stat().st_size/1024:.0f} KB)")
