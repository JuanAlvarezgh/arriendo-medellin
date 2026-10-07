"""Datos del mapa del informe web: puntos exactos, sin agregar en zonas.

El mapa dibujaba antes una rejilla de hexagonos H3. Ahora cada aviso es un punto
en su coordenada, con su propio precio, sobreprecio y conglomerado, igual que en
el mapa de los medidores de EPM. El censo tambien va como puntos: cada manzana
del DANE en su centro, con sus viviendas.

La cobertura, que es la capa del hallazgo, no puede ser un atributo de un solo
aviso, porque es oferta frente a parque de vivienda. Se mide por manzana con una
vecindad fija: avisos a menos de RADIO_M metros de su centro, por cada mil
viviendas censadas en ese mismo radio. El radio es de 160 m porque un circulo
asi tiene la misma area que el hexagono de 174 m de arista que se usaba antes
(0,080 frente a 0,079 km2), de modo que las cifras siguen en la misma escala.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .geo import CRS_COLOMBIA, CRS_MUNDIAL, RUTA_MANZANAS, cargar_manzanas
from .hedonico import estimar, lisa, preparar, sin_marcas, tiene_amenidad

RADIO_M = 160
# Caja del valle: un punto fuera de ella no es Medellin, venga de donde venga.
LATITUD = (5.95, 6.45)
LONGITUD = (-75.75, -75.35)
CONGLOMERADOS = ("alto-alto", "bajo-bajo", "alto-bajo", "bajo-alto", "no significativo")


def avisos_validos(geo: pd.DataFrame) -> pd.DataFrame:
    """Avisos utilizables con coordenada dentro del valle y sin marcas de sospecha."""
    d = geo[geo["latitud"].notna() & geo["longitud"].notna() & geo["precio"].notna()].copy()
    if "sospechoso" in d.columns:
        d = d[d["sospechoso"].apply(sin_marcas)]
    d["area"] = d["area_privada"].fillna(d.get("area_construida"))
    d = d[d["area"].notna() & (d["area"] > 0)]
    d = d[d["latitud"].between(*LATITUD) & d["longitud"].between(*LONGITUD)]
    d["precio_m2"] = d["precio"] / d["area"]
    amen = d["amenidades"] if "amenidades" in d.columns else pd.Series([None] * len(d), index=d.index)
    d["amoblado"] = amen.apply(lambda v: tiene_amenidad(v, "amoblado"))
    return d


def sobreprecio_y_conglomerado(geo: pd.DataFrame) -> pd.DataFrame:
    """Residual del modelo sin barrio y clase LISA, aviso por aviso.

    Mismo procedimiento que la rejilla, pero sin promediar por celda: el
    sobreprecio de cada aviso es exp(residual) - 1, y su conglomerado es el
    suyo. Solo tienen valor los avisos de la ventana de 90 dias del modelo.
    """
    d = preparar(geo, ventana_dias=90)
    r = estimar(d, con_barrio=False)
    salida = pd.DataFrame(index=d.index)
    salida["sobreprecio"] = (np.exp(r.modelo.resid) - 1) * 100
    salida["conglomerado"] = lisa(d)["conglomerado"]
    return salida


def _metros(lat: np.ndarray, lng: np.ndarray, lat0: float) -> np.ndarray:
    return np.column_stack([lng * 111_320 * np.cos(np.radians(lat0)), lat * 110_540])


def manzanas_con_cobertura(
    manzanas: gpd.GeoDataFrame, avisos: pd.DataFrame, radio_m: float = RADIO_M
) -> pd.DataFrame:
    """Centro de cada manzana con sus viviendas y la oferta publicada a su alrededor."""
    centros = manzanas.to_crs(CRS_COLOMBIA).geometry.centroid.to_crs(CRS_MUNDIAL)
    m = pd.DataFrame({
        "latitud": centros.y.to_numpy(),
        "longitud": centros.x.to_numpy(),
        "viviendas": pd.to_numeric(manzanas["TVIVIENDA"], errors="coerce").fillna(0).to_numpy(),
        "estrato": pd.to_numeric(manzanas["estrato_moda"], errors="coerce").to_numpy(),
    })
    m = m[m["latitud"].between(*LATITUD) & m["longitud"].between(*LONGITUD)].reset_index(drop=True)

    lat0 = float(m["latitud"].mean())
    xy_m = _metros(m["latitud"].to_numpy(), m["longitud"].to_numpy(), lat0)
    xy_a = _metros(avisos["latitud"].to_numpy(), avisos["longitud"].to_numpy(), lat0)

    m["avisos_cerca"] = [len(v) for v in cKDTree(xy_a).query_ball_point(xy_m, r=radio_m)]
    viv = m["viviendas"].to_numpy()
    m["viviendas_cerca"] = [viv[v].sum() for v in cKDTree(xy_m).query_ball_point(xy_m, r=radio_m)]
    m["cobertura"] = np.where(
        m["viviendas_cerca"] > 0, 1000 * m["avisos_cerca"] / m["viviendas_cerca"], np.nan
    )
    return m


def resumen(manzanas: pd.DataFrame, avisos: pd.DataFrame, radio_m: float = RADIO_M) -> dict:
    con_viviendas = manzanas[manzanas["viviendas"] > 0]
    sin = con_viviendas[con_viviendas["avisos_cerca"] == 0]
    viviendas = float(con_viviendas["viviendas"].sum())
    return {
        "radio_m": radio_m,
        "manzanas": int(len(con_viviendas)),
        "manzanas_sin_avisos": int(len(sin)),
        "avisos": int(len(avisos)),
        "viviendas_censadas": int(viviendas),
        "viviendas_sin_ningun_aviso": int(sin["viviendas"].sum()),
        "pct_viviendas_sin_datos": round(100 * float(sin["viviendas"].sum()) / max(viviendas, 1), 1),
        "precio_m2_mediano": float(avisos["precio_m2"].median()),
    }


def _redondear(serie: pd.Series, dec: int) -> list:
    return [None if pd.isna(v) else (round(float(v), dec) if dec else int(round(float(v)))) for v in serie]


def construir(
    ruta_geo: Path = Path("datos/salidas/geo_enriquecido.parquet"),
    ruta_manzanas: Path = RUTA_MANZANAS,
) -> dict:
    """Puntos de avisos y de manzanas, en columnas, listos para empotrar en la pagina."""
    geo = gpd.read_parquet(ruta_geo)
    avisos = avisos_validos(geo)
    try:
        modelo = sobreprecio_y_conglomerado(geo)
        avisos = avisos.join(modelo, how="left")
    except Exception:  # noqa: BLE001 - sin modelo, el mapa sigue con precio y censo
        avisos["sobreprecio"] = np.nan
        avisos["conglomerado"] = None

    manzanas = manzanas_con_cobertura(cargar_manzanas(ruta_manzanas), avisos)
    codigo = {c: i for i, c in enumerate(CONGLOMERADOS)}

    return {
        "avisos": {
            "lat": _redondear(avisos["latitud"], 6),
            "lng": _redondear(avisos["longitud"], 6),
            "precio": _redondear(avisos["precio"], 0),
            "precio_m2": _redondear(avisos["precio_m2"], 0),
            "area": _redondear(avisos["area"], 0),
            "estrato": _redondear(pd.to_numeric(avisos["estrato"], errors="coerce"), 0),
            "barrio": [b if isinstance(b, str) else None for b in avisos["barrio"]],
            "amoblado": [int(v) for v in avisos["amoblado"]],
            "sobreprecio": _redondear(avisos["sobreprecio"], 1),
            "conglomerado": [codigo.get(c) if isinstance(c, str) else None for c in avisos["conglomerado"]],
        },
        "conglomerados": list(CONGLOMERADOS),
        "manzanas": {
            "lat": _redondear(manzanas["latitud"], 6),
            "lng": _redondear(manzanas["longitud"], 6),
            "viviendas": _redondear(manzanas["viviendas"], 0),
            "estrato": _redondear(manzanas["estrato"], 0),
            "avisos_cerca": [int(v) for v in manzanas["avisos_cerca"]],
            "viviendas_cerca": _redondear(manzanas["viviendas_cerca"], 0),
            "cobertura": _redondear(manzanas["cobertura"], 1),
        },
        "resumen": resumen(manzanas, avisos),
    }
