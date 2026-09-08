"""Generacion de mapas: coropletas por hexagono y conglomerados espaciales."""

from __future__ import annotations

from pathlib import Path

import folium
import numpy as np
import pandas as pd

from .geo import poligonos_h3

CENTRO_MEDELLIN = (6.2442, -75.5812)

# OpenStreetMap en vez de CartoDB: las teselas de CartoDB pasaron a exigir
# clave de API y estampan una marca de agua sobre el mapa sin ella.
TESELAS = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
ATRIBUCION = "OpenStreetMap"
SALIDA = Path("datos/salidas")

# Escala secuencial de arena a ladrillo, legible sobre el mapa base claro
ESCALA = ["#f5efe0", "#f0d494", "#e5a75c", "#d4762f", "#a8401c", "#6d1f10"]

COLOR_CONGLOMERADO = {
    "alto-alto": "#a8401c",
    "bajo-bajo": "#2a6f97",
    "alto-bajo": "#e5a75c",
    "bajo-alto": "#89c2d9",
    "no significativo": "#d9d9d9",
}


def _tramos(valores: pd.Series, n: int = 6) -> list[float]:
    """Cortes por cuantiles: reparten los colores segun la distribucion real."""
    limpios = valores.dropna()
    if limpios.empty:
        return [0, 1]
    cortes = list(np.unique(np.quantile(limpios, np.linspace(0, 1, n + 1))))
    return cortes if len(cortes) > 2 else [limpios.min(), limpios.max()]


def _color(valor: float, cortes: list[float]) -> str:
    for i in range(len(cortes) - 1):
        if valor <= cortes[i + 1]:
            return ESCALA[min(i, len(ESCALA) - 1)]
    return ESCALA[-1]


def mapa_hexagonos(
    geo: pd.DataFrame,
    columna: str = "precio_m2",
    minimo: int = 3,
    salida: Path | str = SALIDA / "mapa_hexagonos.html",
) -> Path:
    """Coropleta por celda H3 del precio por metro cuadrado.

    El hexagono resuelve el problema de la unidad areal modificable: los
    barrios de Medellin tienen tamanos muy dispares y comparar medianas entre
    ellos mezcla el efecto del precio con el del tamano de la unidad.
    """
    d = geo.copy()
    if columna not in d.columns:
        d[columna] = d["precio"] / d["area_privada"].fillna(d.get("area_construida"))
    d = d[d[columna].notna() & d["h3"].notna()]

    agregado = (
        d.groupby("h3")
        .agg(valor=(columna, "median"), avisos=(columna, "size"))
        .reset_index()
    )
    agregado = agregado[agregado["avisos"] >= minimo]
    if agregado.empty:
        raise ValueError(f"Ningun hexagono alcanza {minimo} avisos.")

    poligonos = poligonos_h3(agregado["h3"].tolist()).merge(agregado, on="h3")
    cortes = _tramos(agregado["valor"])

    m = folium.Map(location=CENTRO_MEDELLIN, zoom_start=12, tiles=TESELAS, attr=ATRIBUCION)

    for _, fila in poligonos.iterrows():
        folium.GeoJson(
            fila["geometry"].__geo_interface__,
            style_function=lambda _f, v=fila["valor"]: {
                "fillColor": _color(v, cortes),
                "color": "#ffffff",
                "weight": 0.4,
                "fillOpacity": 0.75,
            },
            tooltip=folium.Tooltip(
                f"<b>${fila['valor']:,.0f}/m2</b><br>{fila['avisos']} avisos".replace(",", ".")
            ),
        ).add_to(m)

    _leyenda(m, cortes, "Precio pedido por m2")
    ruta = Path(salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(ruta))
    return ruta


def mapa_sobreprecio(
    residuales: pd.DataFrame,
    geo: pd.DataFrame,
    salida: Path | str = SALIDA / "mapa_sobreprecio.html",
) -> Path:
    """Sobreprecio por barrio: lo que los atributos del inmueble no explican."""
    centros = (
        geo[geo["barrio"].notna()]
        .groupby("barrio")
        .agg(lat=("latitud", "median"), lon=("longitud", "median"))
        .reset_index()
    )
    d = residuales.merge(centros, on="barrio", how="inner")
    if d.empty:
        raise ValueError("No hay barrios con coordenadas y residuales.")

    m = folium.Map(location=CENTRO_MEDELLIN, zoom_start=12, tiles=TESELAS, attr=ATRIBUCION)
    tope = max(abs(d["sobreprecio_pct"].min()), abs(d["sobreprecio_pct"].max())) or 1

    for _, f in d.iterrows():
        pct = f["sobreprecio_pct"]
        color = "#a8401c" if pct > 0 else "#2a6f97"
        folium.CircleMarker(
            location=(f["lat"], f["lon"]),
            radius=4 + 12 * abs(pct) / tope,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.65,
            weight=1,
            tooltip=folium.Tooltip(
                f"<b>{f['barrio']}</b><br>"
                f"sobreprecio {pct:+.1f}%<br>"
                f"{int(f['avisos'])} avisos<br>"
                f"${f['precio_m2_mediano']:,.0f}/m2".replace(",", ".")
            ),
        ).add_to(m)

    ruta = Path(salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(ruta))
    return ruta


def mapa_conglomerados(
    datos: pd.DataFrame, salida: Path | str = SALIDA / "mapa_conglomerados.html"
) -> Path:
    """Conglomerados LISA: zonas caras rodeadas de caras, y baratas de baratas."""
    d = datos[datos["latitud"].notna() & datos["conglomerado"].notna()]

    m = folium.Map(location=CENTRO_MEDELLIN, zoom_start=12, tiles=TESELAS, attr=ATRIBUCION)
    for _, f in d.iterrows():
        cong = f["conglomerado"]
        folium.CircleMarker(
            location=(f["latitud"], f["longitud"]),
            radius=3 if cong == "no significativo" else 5,
            color=COLOR_CONGLOMERADO.get(cong, "#999999"),
            fill=True,
            fill_opacity=0.35 if cong == "no significativo" else 0.85,
            weight=0,
            tooltip=f"{f.get('barrio', '')} · {cong}",
        ).add_to(m)

    _leyenda_categorica(m, COLOR_CONGLOMERADO, "Conglomerados de precio")
    ruta = Path(salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(ruta))
    return ruta


def _leyenda(mapa: folium.Map, cortes: list[float], titulo: str) -> None:
    filas = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
        f'<span style="width:16px;height:12px;background:{ESCALA[min(i, len(ESCALA)-1)]};'
        f'border:1px solid #bbb"></span>'
        f'<span>${cortes[i]:,.0f} a ${cortes[i+1]:,.0f}</span></div>'.replace(",", ".")
        for i in range(len(cortes) - 1)
    )
    html = f"""
    <div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:rgba(255,255,255,.94);
                padding:10px 12px;border:1px solid #ccc;border-radius:6px;
                font:12px system-ui,sans-serif;color:#222">
      <div style="font-weight:600;margin-bottom:6px">{titulo}</div>{filas}
    </div>"""
    mapa.get_root().html.add_child(folium.Element(html))


def _leyenda_categorica(mapa: folium.Map, colores: dict[str, str], titulo: str) -> None:
    filas = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
        f'<span style="width:12px;height:12px;border-radius:50%;background:{c}"></span>'
        f"<span>{n}</span></div>"
        for n, c in colores.items()
    )
    html = f"""
    <div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:rgba(255,255,255,.94);
                padding:10px 12px;border:1px solid #ccc;border-radius:6px;
                font:12px system-ui,sans-serif;color:#222">
      <div style="font-weight:600;margin-bottom:6px">{titulo}</div>{filas}
    </div>"""
    mapa.get_root().html.add_child(folium.Element(html))


def construir_todos(
    ruta_geo: Path = Path("datos/salidas/geo_enriquecido.parquet"),
) -> dict[str, Path]:
    """Regenera los tres mapas interactivos que muestra el tablero.

    Existian solo como llamadas sueltas, igual que el parquet enriquecido y las
    tablas de barrio: el archivo en disco era el unico registro de como se habia
    hecho. Al corregir la regla del barrio hubo que rehacerlos, y no habia
    comando que los rehiciera.

    El mapa completo de la ciudad, con las cinco capas y el callejero de fondo,
    no esta aqui sino en la pagina del informe (`python -m analisis.pagina`).
    Estos tres son la version embebible que consume el tablero.
    """
    import geopandas as gpd

    from .hedonico import estimar, lisa, preparar, residuales_por_zona

    geo = gpd.read_parquet(ruta_geo)
    geo["area"] = geo["area_privada"].fillna(geo["area_construida"])
    geo["precio_m2"] = geo["precio"] / geo["area"]

    datos = preparar(geo, ventana_dias=90)
    resultado = estimar(datos)

    return {
        "hexagonos": mapa_hexagonos(geo),
        "sobreprecio": mapa_sobreprecio(residuales_por_zona(resultado, "barrio", minimo=25), geo),
        "conglomerados": mapa_conglomerados(lisa(datos)),
    }


if __name__ == "__main__":
    for nombre, ruta in construir_todos().items():
        print(f"  {nombre:14s} -> {ruta}")
