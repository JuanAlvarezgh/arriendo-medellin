"""Enriquecimiento geoespacial de los avisos.

Tres fuentes de geografia, de mas barata a mas cara:

1. El barrio sale del slug de la URL del aviso, sin costo ni geocodificacion.
2. La manzana del Marco Geoestadistico del DANE aporta el contexto censal:
   viviendas, hogares, personas y estrato oficial, que permite contrastar el
   estrato que declara el anunciante contra el del censo.
3. La rejilla H3 da celdas de igual tamano, que evitan el problema de la unidad
   areal modificable que tienen los barrios, de tamanos muy dispares.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Point

CRS_MUNDIAL = "EPSG:4326"
CRS_COLOMBIA = "EPSG:9377"  # Origen Nacional, en metros
COD_MEDELLIN = "05001"
RESOLUCION_H3 = 9  # arista de unos 174 m

# La carpeta del proyecto de medidores se movio dentro de "analisis de datos"; se
# acepta tambien la ubicacion anterior para no romper copias viejas del repo.
_CANDIDATAS_MANZANAS = (
    Path("C:/Users/Juan/Desktop/analisis de datos/UrbanAnalysis_salidas/manzanas_medidores.gpkg"),
    Path("C:/Users/Juan/Desktop/UrbanAnalysis_salidas/manzanas_medidores.gpkg"),
)
RUTA_MANZANAS = next((r for r in _CANDIDATAS_MANZANAS if r.exists()), _CANDIDATAS_MANZANAS[0])

COLUMNAS_CENSO = [
    "COD_DANE_A",
    "MPIO_CDPMP",
    "TVIVIENDA",
    "TP16_HOG",
    "TP27_PERSO",
    "estrato_moda",
    "area_ha",
    "med_x_ha",
    "consumo_mediana",
    "geometry",
]


def sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def barrio_desde_url(url: str) -> str | None:
    """Extrae el barrio del slug de la URL. Delega en el extractor del rastreador.

    Aqui vivio una segunda implementacion, mas ingenua, y esa duplicidad costo
    cara. Partia el slug por '-en-' y se quedaba con el ultimo trozo, de modo que
    en una URL sin barrio como

        /apartaestudio-en-arriendo-en-medellin/191669147

    el ultimo trozo era 'arriendo-en' y el analisis acababa con un barrio
    inventado, 'Arriendo En', que reunia 1.273 avisos repartidos por toda la
    ciudad y aparecia en el mapa y en el ranking de sobreprecio como si fuera un
    lugar. El extractor del rastreador ya descartaba esa captura; lo que fallaba
    era tener dos copias de la misma regla y que el analisis usara la vieja.

    Una sola regla, en un solo sitio.
    """
    from rastreador.extraccion.cascada import barrio_desde_url as _extraer

    return _extraer(url)


def a_geodataframe(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Convierte el marco de avisos a geografico, descartando los sin coordenadas."""
    validos = df["latitud"].notna() & df["longitud"].notna()
    geo = gpd.GeoDataFrame(
        df[validos].copy(),
        geometry=[Point(xy) for xy in zip(df.loc[validos, "longitud"], df.loc[validos, "latitud"])],
        crs=CRS_MUNDIAL,
    )
    return geo


def cargar_manzanas(ruta: Path = RUTA_MANZANAS, solo_medellin: bool = True) -> gpd.GeoDataFrame:
    """Carga las manzanas del DANE, filtradas al municipio."""
    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encuentra {ruta}. Es el geopackage de manzanas del MGN."
        )
    filtro = f"MPIO_CDPMP = '{COD_MEDELLIN}'" if solo_medellin else None
    manzanas = gpd.read_file(
        ruta, layer="manzanas_medidores", columns=COLUMNAS_CENSO, where=filtro, engine="pyogrio"
    )
    return manzanas


def unir_con_manzanas(
    avisos: gpd.GeoDataFrame, manzanas: gpd.GeoDataFrame, tolerancia_m: float = 30.0
) -> gpd.GeoDataFrame:
    """Asigna cada aviso a su manzana censal.

    Se usa la manzana mas cercana dentro de una tolerancia, no la interseccion
    estricta: las coordenadas de un aviso apuntan a la fachada o al centroide
    aproximado del edificio, y una interseccion pura perderia buena parte.
    """
    avisos_m = avisos.to_crs(CRS_COLOMBIA)
    manzanas_m = manzanas.to_crs(CRS_COLOMBIA)

    unido = gpd.sjoin_nearest(
        avisos_m,
        manzanas_m,
        how="left",
        max_distance=tolerancia_m,
        distance_col="dist_manzana_m",
    )
    # sjoin_nearest puede duplicar ante empates; se conserva la mas cercana
    unido = unido.sort_values("dist_manzana_m").groupby(level=0).first()
    unido = gpd.GeoDataFrame(unido, geometry="geometry", crs=CRS_COLOMBIA)
    return unido.to_crs(CRS_MUNDIAL)


def agregar_h3(avisos: gpd.GeoDataFrame, resolucion: int = RESOLUCION_H3) -> gpd.GeoDataFrame:
    """Asigna a cada aviso su celda hexagonal."""
    salida = avisos.copy()
    salida["h3"] = [
        h3.latlng_to_cell(lat, lon, resolucion)
        for lat, lon in zip(salida["latitud"], salida["longitud"])
    ]
    return salida


def poligonos_h3(celdas: list[str]) -> gpd.GeoDataFrame:
    """Convierte celdas H3 en poligonos, para dibujarlas en un mapa."""
    from shapely.geometry import Polygon

    filas = []
    for celda in celdas:
        limite = h3.cell_to_boundary(celda)
        filas.append({"h3": celda, "geometry": Polygon([(lon, lat) for lat, lon in limite])})
    return gpd.GeoDataFrame(filas, crs=CRS_MUNDIAL)


def transferir_barrio(
    avisos: gpd.GeoDataFrame, distancia_max_m: float = 400.0
) -> gpd.GeoDataFrame:
    """Asigna barrio, por vecino mas cercano, a los avisos que solo traen coordenadas.

    Algunos portales publican el barrio en la URL y otros solo la posicion.
    Como hay miles de avisos con ambas cosas, sirven de referencia: a un aviso
    sin barrio se le asigna el del aviso etiquetado mas cercano, siempre que
    este dentro de un radio razonable. Fuera de ese radio se deja sin barrio,
    porque una etiqueta lejana seria una invencion.
    """
    salida = avisos.copy()
    if "barrio" not in salida.columns:
        salida["barrio"] = None

    con = salida[salida["barrio"].notna()]
    sin = salida[salida["barrio"].isna()]
    if con.empty or sin.empty:
        return salida

    con_m = con.to_crs(CRS_COLOMBIA)[["barrio", "geometry"]]
    sin_m = sin.to_crs(CRS_COLOMBIA)

    unido = gpd.sjoin_nearest(
        sin_m,
        con_m,
        how="left",
        max_distance=distancia_max_m,
        distance_col="dist_barrio_m",
        lsuffix="orig",
        rsuffix="ref",
    )
    unido = unido.sort_values("dist_barrio_m").groupby(level=0).first()

    columna = "barrio_ref" if "barrio_ref" in unido.columns else "barrio"
    salida.loc[unido.index, "barrio"] = unido[columna]
    salida.loc[unido.index, "barrio_transferido"] = unido[columna].notna()
    return salida


def distancia_a_estaciones(
    avisos: gpd.GeoDataFrame, estaciones: gpd.GeoDataFrame
) -> pd.Series:
    """Distancia en metros de cada aviso a la estacion de transporte mas cercana."""
    a = avisos.to_crs(CRS_COLOMBIA)
    e = estaciones.to_crs(CRS_COLOMBIA)
    unido = gpd.sjoin_nearest(a, e[["geometry"]], how="left", distance_col="dist_m")
    return unido.groupby(level=0)["dist_m"].min()


def cargar_estaciones_osm(lugar: str = "Medellín, Colombia") -> gpd.GeoDataFrame:
    """Estaciones de metro, tranvia y metrocable desde OpenStreetMap."""
    import osmnx as ox

    etiquetas = {"railway": ["station", "halt"], "aerialway": ["station"]}
    puntos = ox.features_from_place(lugar, tags=etiquetas)
    puntos = puntos[puntos.geometry.type.isin(["Point", "Polygon", "MultiPolygon"])].copy()
    puntos["geometry"] = puntos.geometry.centroid
    return puntos.reset_index()[["geometry"]].set_crs(CRS_MUNDIAL, allow_override=True)


def enriquecer(
    df: pd.DataFrame,
    *,
    ruta_manzanas: Path = RUTA_MANZANAS,
    con_estaciones: bool = False,
) -> gpd.GeoDataFrame:
    """Aplica todo el enriquecimiento geografico sobre el marco de avisos."""
    if "barrio" not in df.columns:
        df = df.copy()
        df["barrio"] = None
    faltan = df["barrio"].isna()
    df.loc[faltan, "barrio"] = df.loc[faltan, "url"].apply(barrio_desde_url)

    geo = a_geodataframe(df)
    geo = agregar_h3(geo)

    if ruta_manzanas.exists():
        manzanas = cargar_manzanas(ruta_manzanas)
        geo = unir_con_manzanas(geo, manzanas)
        # El estrato del censo permite contrastar el declarado por el anunciante
        if "estrato_moda" in geo.columns:
            geo["estrato_censo"] = pd.to_numeric(geo["estrato_moda"], errors="coerce")
            geo["discrepa_estrato"] = (
                geo["estrato"].notna()
                & geo["estrato_censo"].notna()
                & (geo["estrato"] != geo["estrato_censo"])
            )

    # El barrio se propaga al final, cuando ya hay geometria. Solo alcanza a los
    # avisos que se quedaron sin etiqueta, y deja constancia en
    # 'barrio_transferido' de que la etiqueta es deducida y no publicada.
    geo = transferir_barrio(geo)

    if con_estaciones:
        try:
            estaciones = cargar_estaciones_osm()
            geo["dist_estacion_m"] = distancia_a_estaciones(geo, estaciones)
        except Exception:
            geo["dist_estacion_m"] = pd.NA

    return geo


def resumen_por(geo: gpd.GeoDataFrame, columna: str, minimo: int = 5) -> pd.DataFrame:
    """Agregado de precio por barrio o por hexagono."""
    g = geo[geo["precio"].notna() & geo["area_privada"].notna()].copy()
    g["precio_m2"] = g["precio"] / g["area_privada"]
    r = (
        g.groupby(columna)
        .agg(
            avisos=("precio", "size"),
            precio_mediano=("precio", "median"),
            precio_m2_mediano=("precio_m2", "median"),
            area_mediana=("area_privada", "median"),
            estrato_moda=("estrato", lambda s: s.mode().iloc[0] if not s.mode().empty else None),
        )
        .reset_index()
    )
    return r[r["avisos"] >= minimo].sort_values("precio_m2_mediano", ascending=False)


RUTA_AVISOS = Path("datos/salidas/arriendos_medellin.parquet")
RUTA_ENRIQUECIDO = Path("datos/salidas/geo_enriquecido.parquet")


def construir(
    ruta_avisos: Path = RUTA_AVISOS,
    salida: Path = RUTA_ENRIQUECIDO,
    ruta_manzanas: Path = RUTA_MANZANAS,
) -> Path:
    """Reconstruye el parquet enriquecido, que es la entrada de todo el analisis.

    Este paso existia solo como una secuencia suelta de llamadas, de modo que el
    parquet de disco era el unico registro de como se habia construido. Cuando se
    corrigio la regla del barrio no hubo forma de reaplicarla sin rehacer el
    raspado entero. Ahora es un comando: `python -m analisis.geo`.
    """
    df = pd.read_parquet(ruta_avisos)
    geo = enriquecer(df, ruta_manzanas=ruta_manzanas)

    # El area privada es la que declara el portal; la construida sirve de
    # respaldo cuando falta, que es el caso en cerca de un tercio de los avisos.
    geo["area"] = geo["area_privada"].fillna(geo.get("area_construida"))
    geo["precio_m2"] = geo["precio"] / geo["area"]

    salida.parent.mkdir(parents=True, exist_ok=True)
    geo.to_parquet(salida)
    return salida


if __name__ == "__main__":
    ruta = construir()
    g = gpd.read_parquet(ruta)
    con_barrio = g["barrio"].notna().sum()
    transferido = int(g.get("barrio_transferido", pd.Series(dtype=bool)).fillna(False).sum())
    print(f"escrito en {ruta}  ({len(g):,} avisos)".replace(",", "."))
    print(f"con barrio:   {con_barrio:,} ({100*con_barrio/len(g):.1f} %)".replace(",", "."))
    print(f"  del slug:   {con_barrio - transferido:,}".replace(",", "."))
    print(f"  transferido:{transferido:,}".replace(",", "."))
    print(f"barrios distintos: {g['barrio'].nunique()}")
