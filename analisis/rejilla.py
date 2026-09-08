"""Construye la rejilla hexagonal que alimenta el mapa web.

La idea central: **una sola geometria para todo**. Las manzanas del censo y los
avisos se agregan a la misma malla H3, de modo que cada celda lleva a la vez
cuantas viviendas hay y cuantos avisos se recogieron. Eso permite dibujar la
ciudad completa y hacer visible donde no hay datos, en lugar de dejar un hueco
blanco que parece que la zona no existiera.

Efecto secundario util: no hace falta mapa base de teselas. La silueta de la
ciudad la dibujan las propias celdas con viviendas censadas.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

warnings.filterwarnings("ignore")

RESOLUCION = 9
CRS_MUNDIAL = "EPSG:4326"
CRS_COLOMBIA = "EPSG:9377"
SALIDA = Path("datos/salidas/web")


def celdas_de_poligono(geometria, resolucion: int = RESOLUCION) -> list[str]:
    """Celdas H3 que cubren un poligono.

    Las manzanas son mucho mas pequenas que una celda, asi que en la practica
    casi siempre devuelve una sola: la del centroide. Se consulta igualmente el
    relleno para las pocas manzanas grandes de borde urbano.
    """
    try:
        relleno = h3.geo_to_cells(geometria.__geo_interface__, resolucion)
        if relleno:
            return list(relleno)
    except Exception:
        pass
    c = geometria.centroid
    return [h3.latlng_to_cell(c.y, c.x, resolucion)]


def poligono_de_celda(celda: str) -> Polygon:
    """Poligono de una celda H3, con el sentido de giro que exige GeoJSON.

    La norma RFC 7946 pide que el anillo exterior vaya en sentido antihorario, y
    no es un formalismo: las librerias que trabajan con geometria esferica, D3
    entre ellas, leen un anillo horario como el complemento, es decir el planeta
    entero menos ese hexagono. Sin orientar, el mapa web calculaba unos limites
    de [-180,-90] a [180,90] y dibujaba Medellin del tamano de un punto.
    """
    from shapely.geometry.polygon import orient

    return orient(Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(celda)]), sign=1.0)


def censo_por_celda(ruta_manzanas: Path, resolucion: int = RESOLUCION) -> pd.DataFrame:
    """Reparte las viviendas censadas de cada manzana entre sus celdas H3."""
    from .geo import COLUMNAS_CENSO, cargar_manzanas

    manzanas = cargar_manzanas(ruta_manzanas)
    manzanas = manzanas.to_crs(CRS_MUNDIAL)

    filas = []
    for _, mz in manzanas.iterrows():
        if mz.geometry is None or mz.geometry.is_empty:
            continue
        celdas = celdas_de_poligono(mz.geometry, resolucion)
        if not celdas:
            continue
        # Reparto proporcional: una manzana que toca varias celdas divide sus
        # viviendas entre ellas, para no contarlas mas de una vez.
        parte = 1 / len(celdas)
        for celda in celdas:
            filas.append(
                {
                    "h3": celda,
                    "viviendas": (mz.get("TVIVIENDA") or 0) * parte,
                    "hogares": (mz.get("TP16_HOG") or 0) * parte,
                    "personas": (mz.get("TP27_PERSO") or 0) * parte,
                    "estrato_censo": mz.get("estrato_moda"),
                    "manzanas": parte,
                }
            )

    df = pd.DataFrame(filas)
    agrupado = df.groupby("h3").agg(
        viviendas=("viviendas", "sum"),
        hogares=("hogares", "sum"),
        personas=("personas", "sum"),
        manzanas=("manzanas", "sum"),
        estrato_censo=("estrato_censo", lambda s: s.mode().iloc[0] if not s.mode().empty else None),
    )
    return agrupado.reset_index()


def avisos_por_celda(geo: gpd.GeoDataFrame) -> pd.DataFrame:
    """Agrega los avisos a la rejilla, descartando los marcados como sospechosos.

    Sin este filtro entraban 56 celdas mal geocodificadas, una de ellas en
    Bogota. Todas tenian avisos y cero viviendas censadas, y al estirar la
    extension del mapa dejaban la ciudad del tamano de una moneda. El validador
    del esquema ya las habia marcado; lo que faltaba era hacerle caso aqui, como
    ya hace el modelo.
    """
    from .hedonico import sin_marcas, tiene_amenidad

    d = geo[geo["h3"].notna()].copy()
    if "sospechoso" in d.columns:
        d = d[d["sospechoso"].apply(sin_marcas)]
    d["area"] = d["area_privada"].fillna(d.get("area_construida"))
    d["precio_m2"] = d["precio"] / d["area"]

    d["amoblado"] = (
        d["amenidades"].apply(lambda v: int(tiene_amenidad(v, "amoblado")))
        if "amenidades" in d.columns
        else 0
    )

    return (
        d.groupby("h3")
        .agg(
            avisos=("precio", "size"),
            precio_mediano=("precio", "median"),
            precio_m2=("precio_m2", "median"),
            area_mediana=("area", "median"),
            alcobas=("alcobas", "median"),
            estrato_avisos=("estrato", lambda s: s.mode().iloc[0] if not s.mode().empty else None),
            amoblados=("amoblado", "sum"),
            barrio=("barrio", lambda s: s.mode().iloc[0] if not s.mode().empty else None),
        )
        .reset_index()
    )


def construir(
    ruta_geo: Path = Path("datos/salidas/geo_enriquecido.parquet"),
    ruta_manzanas: Path | None = None,
    salida: Path = SALIDA,
) -> Path:
    """Genera el GeoJSON unico que consume el mapa web."""
    from .geo import RUTA_MANZANAS

    ruta_manzanas = ruta_manzanas or RUTA_MANZANAS
    geo = gpd.read_parquet(ruta_geo)

    censo = censo_por_celda(ruta_manzanas)
    avisos = avisos_por_celda(geo)

    rejilla = censo.merge(avisos, on="h3", how="outer")
    rejilla["viviendas"] = rejilla["viviendas"].fillna(0).round(0)
    rejilla["avisos"] = rejilla["avisos"].fillna(0).astype(int)

    # La medida del hallazgo: cuanta oferta publicada hay por parque de vivienda.
    rejilla["cobertura"] = np.where(
        rejilla["viviendas"] > 0,
        1000 * rejilla["avisos"] / rejilla["viviendas"],
        np.nan,
    )
    rejilla["pct_amoblado"] = np.where(
        rejilla["avisos"] > 0, 100 * rejilla["amoblados"].fillna(0) / rejilla["avisos"], np.nan
    )

    # Sobreprecio y conglomerados, si el analisis ya se corrio
    rejilla = _anadir_residuales(rejilla, geo)

    poligonos = gpd.GeoDataFrame(
        rejilla,
        geometry=[poligono_de_celda(c) for c in rejilla["h3"]],
        crs=CRS_MUNDIAL,
    )

    # Se recorta a lo que es ciudad: celdas con viviendas censadas o con avisos.
    poligonos = poligonos[(poligonos["viviendas"] > 0) | (poligonos["avisos"] > 0)]

    # Red de seguridad geografica: una celda cuyo centro cae fuera del valle no
    # es Medellin, venga de donde venga. Sin este recorte, un solo aviso mal
    # geocodificado estira la extension del mapa cientos de kilometros.
    centros = poligonos.geometry.centroid
    poligonos = poligonos[
        centros.y.between(5.95, 6.45) & centros.x.between(-75.75, -75.35)
    ]

    for col in ("precio_mediano", "precio_m2", "area_mediana", "cobertura",
                "pct_amoblado", "sobreprecio", "viviendas", "hogares", "personas"):
        if col in poligonos.columns:
            poligonos[col] = pd.to_numeric(poligonos[col], errors="coerce").round(1)

    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / "rejilla_medellin.geojson"
    poligonos.to_file(ruta, driver="GeoJSON")

    _escribir_resumen(poligonos, salida)
    return ruta


def _anadir_residuales(rejilla: pd.DataFrame, geo: gpd.GeoDataFrame) -> pd.DataFrame:
    """Sobreprecio y conglomerado por celda, si el modelo puede estimarse."""
    try:
        from .hedonico import estimar, lisa, preparar

        d = preparar(geo, ventana_dias=90)
        r = estimar(d, con_barrio=False)
        d = d.copy()
        d["residual"] = r.modelo.resid

        por_celda = d.groupby("h3")["residual"].agg(["mean", "size"])
        por_celda["sobreprecio"] = (np.exp(por_celda["mean"]) - 1) * 100
        rejilla = rejilla.merge(
            por_celda[["sobreprecio"]].reset_index(), on="h3", how="left"
        )

        dl = lisa(d)
        cong = dl.groupby("h3")["conglomerado"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else None
        )
        rejilla = rejilla.merge(cong.reset_index(), on="h3", how="left")
    except Exception:
        rejilla["sobreprecio"] = np.nan
        rejilla["conglomerado"] = None
    return rejilla


def _escribir_resumen(poligonos: gpd.GeoDataFrame, salida: Path) -> None:
    """Cifras agregadas que la pagina usa para sus indicadores."""
    con_datos = poligonos[poligonos["avisos"] > 0]
    sin_datos = poligonos[poligonos["avisos"] == 0]

    resumen = {
        "celdas_totales": int(len(poligonos)),
        "celdas_con_avisos": int(len(con_datos)),
        "celdas_sin_avisos": int(len(sin_datos)),
        "avisos": int(poligonos["avisos"].sum()),
        "viviendas_censadas": int(poligonos["viviendas"].sum()),
        "viviendas_sin_ningun_aviso": int(sin_datos["viviendas"].sum()),
        "precio_m2_mediano": float(con_datos["precio_m2"].median()),
        "cobertura_mediana": float(con_datos["cobertura"].median()),
    }
    resumen["pct_viviendas_sin_datos"] = round(
        100 * resumen["viviendas_sin_ningun_aviso"] / max(resumen["viviendas_censadas"], 1), 1
    )
    (salida / "resumen_rejilla.json").write_text(
        json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    ruta = construir()
    tam = ruta.stat().st_size / 1024
    print(f"escrito en {ruta}  ({tam:.0f} KB)")
    print(json.loads((SALIDA / "resumen_rejilla.json").read_text(encoding="utf-8")))
