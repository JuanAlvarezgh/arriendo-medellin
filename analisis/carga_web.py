"""Prepara la carga de datos que se embebe en la pagina.

Va embebida y no como archivo aparte por una razon concreta: un HTML abierto con
doble clic usa el esquema file://, y ahi el navegador bloquea `fetch` sobre
archivos locales por politica de mismo origen. Con los datos dentro, la pagina
funciona sin servidor y sin configuracion.

A cambio hay que ser estricto con el tamano: coordenadas recortadas, campos
nulos fuera y numeros redondeados.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUTA_REJILLA = Path("datos/salidas/web/rejilla_medellin.geojson")
RUTA_RESUMEN = Path("datos/salidas/web/resumen_rejilla.json")
DECIMALES_COORD = 5  # ~1,1 m en el ecuador; de sobra para hexagonos de 174 m

CAMPOS = [
    "h3", "avisos", "viviendas", "precio_m2", "precio_mediano", "area_mediana",
    "cobertura", "estrato_censo", "estrato_avisos", "sobreprecio",
    "conglomerado", "pct_amoblado", "barrio",
]


def _redondear(valor: Any, dec: int = 1) -> Any:
    if valor is None:
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return valor
    if f != f:  # NaN
        return None
    return round(f, dec) if dec else int(f)


def compactar_rejilla(ruta: Path = RUTA_REJILLA) -> dict:
    """Reduce el GeoJSON a lo imprescindible, sin perder informacion util."""
    crudo = json.loads(ruta.read_text(encoding="utf-8"))

    rasgos = []
    for f in crudo["features"]:
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        if geom.get("type") != "Polygon":
            continue

        anillo = [
            [round(x, DECIMALES_COORD), round(y, DECIMALES_COORD)]
            for x, y in geom["coordinates"][0]
        ]

        limpio = {}
        for campo in CAMPOS:
            v = props.get(campo)
            if v is None or (isinstance(v, float) and v != v):
                continue
            if campo in ("avisos",):
                limpio[campo] = int(v)
            elif campo in ("viviendas", "precio_mediano"):
                limpio[campo] = _redondear(v, 0)
            elif campo in ("h3", "conglomerado", "barrio"):
                limpio[campo] = v
            else:
                limpio[campo] = _redondear(v, 1)

        rasgos.append({"g": anillo, "p": limpio})

    return {"celdas": rasgos}


def resumen(ruta: Path = RUTA_RESUMEN) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def _csv_a_lista(ruta: Path, columnas: list[str] | None = None,
                 renombrar: dict[str, str] | None = None) -> list[dict]:
    import pandas as pd

    if not ruta.exists():
        return []
    df = pd.read_csv(ruta)
    if columnas:
        df = df[[c for c in columnas if c in df.columns]]
    if renombrar:
        df = df.rename(columns=renombrar)
    return json.loads(df.round(2).to_json(orient="records"))


def construir() -> dict:
    """Todo lo que la pagina necesita, en un solo objeto.

    La pagina principal es solo el mapa de puntos; las cifras del informe
    (modelo, IPC, renta corta) quedaron en el PDF y ya no se empotran aqui.
    """
    from .puntos_web import construir as construir_puntos

    return {"puntos": construir_puntos()}


if __name__ == "__main__":
    datos = construir()
    bruto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    print(f"avisos:    {len(datos['puntos']['avisos']['lat']):,}".replace(",", "."))
    print(f"manzanas:  {len(datos['puntos']['manzanas']['lat']):,}".replace(",", "."))
    print(f"tamano:    {len(bruto)/1024:.0f} KB")
