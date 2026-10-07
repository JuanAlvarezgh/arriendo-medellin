"""Genera la pagina de animacion: vuelo 3D sobre el Valle de Aburra y lluvia de avisos.

La pagina se reproduce sola en el navegador y tambien se puede grabar cuadro por
cuadro a MP4 con `grabar_video.py`. Las cifras de los textos salen de los datos,
no estan escritas a mano.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np

from .pagina import MAPA_SATELITE, biblioteca
from .puntos_web import avisos_validos
from .sitio import insertar

RAIZ = Path(__file__).resolve().parent
PLANTILLA = RAIZ / "web" / "animacion.html"
GUION = RAIZ / "web" / "animacion.js"
ENTRADA = Path("datos/salidas/geo_enriquecido.parquet")
SALIDA = Path("datos/salidas/web/animacion.html")

# Rampa del precio por m2, la misma del mapa principal (siete tramos por cuantiles).
RAMPA = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Barrios de la comuna 14, El Poblado, tal como vienen escritos en los avisos.
EL_POBLADO = {
    "El Poblado", "Los Balsos", "Los Balsos No2", "El Tesoro", "Las Palmas", "Castropol",
    "La Aguacatala", "Altos Del Poblado", "Loma De Los Gonzalez", "Santa Maria De Los Angeles",
    "Milla De Oro", "Lalinde", "La Calera", "Manila", "Provenza", "Patio Bonito", "Alejandria",
    "El Campestre", "Las Lomas No1", "San Lucas", "Cola Del Zorro", "Loma Del Indio",
    "Los Naranjos", "La Florida", "Astorga", "Los Parra",
}


def datos(entrada: Path = ENTRADA) -> dict:
    d = avisos_validos(gpd.read_parquet(entrada)).sort_values("precio_m2").reset_index(drop=True)
    cortes = np.quantile(d["precio_m2"], np.linspace(0, 1, len(RAMPA) + 1))
    tramo = np.clip(np.searchsorted(cortes[1:-1], d["precio_m2"], side="right"), 0, len(RAMPA) - 1)
    caros = d[d["precio_m2"] >= d["precio_m2"].quantile(0.9)]
    return {
        # Ordenados del mas barato al mas caro por m2: el orden es el de la lluvia.
        "lat": [round(float(v), 6) for v in d["latitud"]],
        "lng": [round(float(v), 6) for v in d["longitud"]],
        "tramo": [int(v) for v in tramo],
        "precio_m2": [int(round(v)) for v in d["precio_m2"]],
        "rampa": RAMPA,
        "n": int(len(d)),
        "barrios": int(d["barrio"].nunique()),
        "pct_caros_poblado": round(float(caros["barrio"].isin(EL_POBLADO).mean()) * 100),
        "pct_todos_poblado": round(float(d["barrio"].isin(EL_POBLADO).mean()) * 100),
    }


def construir(salida: Path = SALIDA, entrada: Path = ENTRADA) -> Path:
    serializado = json.dumps(datos(entrada), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (
        PLANTILLA.read_text(encoding="utf-8")
        .replace("__ESTILO_MAPLIBRE__", biblioteca("maplibre-gl.css"))
        .replace("__MAPLIBRE__", biblioteca("maplibre-gl.js"))
        .replace("__MAPA_SATELITE__", MAPA_SATELITE.read_text(encoding="utf-8"))
        .replace("__DATOS__", serializado)
        .replace("__GUION__", GUION.read_text(encoding="utf-8"))
    )
    html = insertar(html, "animacion")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")
    return salida


if __name__ == "__main__":
    ruta = construir()
    print(f"escrito en {ruta}  ({ruta.stat().st_size/1024:.0f} KB)")
