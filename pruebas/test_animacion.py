"""Pruebas de los datos de la animacion."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from analisis import generar_animacion


def _avisos(tmp_path, n=200):
    rng = np.random.default_rng(5)
    barrios = np.where(np.arange(n) % 2 == 0, "El Poblado", "Belen")
    lat = 6.20 + rng.random(n) * 0.08
    lng = -75.60 + rng.random(n) * 0.06
    marco = pd.DataFrame({
        "latitud": lat, "longitud": lng, "barrio": barrios,
        "precio": np.where(barrios == "El Poblado", 6e6, 3e6) * (1 + rng.random(n) * 0.2),
        "area_privada": 80.0, "area_construida": np.nan, "amenidades": "",
        "sospechoso": [[] for _ in range(n)],
    })
    ruta = tmp_path / "geo.parquet"
    gpd.GeoDataFrame(marco, geometry=[Point(x, y) for x, y in zip(lng, lat)], crs="EPSG:4326").to_parquet(ruta)
    return ruta


def test_lluvia_va_del_mas_barato_al_mas_caro(tmp_path):
    d = generar_animacion.datos(_avisos(tmp_path))
    assert d["n"] == 200
    assert d["precio_m2"] == sorted(d["precio_m2"])
    assert len(d["lat"]) == len(d["lng"]) == len(d["tramo"]) == d["n"]


def test_tramos_de_color_crecen_con_el_precio(tmp_path):
    d = generar_animacion.datos(_avisos(tmp_path))
    assert min(d["tramo"]) == 0 and max(d["tramo"]) == len(d["rampa"]) - 1
    assert d["tramo"] == sorted(d["tramo"])


def test_cifra_de_el_poblado_sale_de_los_datos(tmp_path):
    d = generar_animacion.datos(_avisos(tmp_path))
    # La mitad de los avisos es de El Poblado y todos los caros son de ahi.
    assert d["pct_todos_poblado"] == 50
    assert d["pct_caros_poblado"] == 100
