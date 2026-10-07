"""Generacion de mapas: coropletas por hexagono y conglomerados espaciales."""

from __future__ import annotations

from pathlib import Path

import folium
import numpy as np
import pandas as pd

from .geo import poligonos_h3

CENTRO_MEDELLIN = (6.2442, -75.5812)

# Fondo satelital libre, el mismo del tablero de incendios: la imagen mundial de
# Esri, sin clave. OpenStreetMap dejo de servir: sus servidores devuelven 403
# "Access blocked" a las paginas abiertas con doble clic, que no mandan Referer.
# Encima van las referencias de Esri, tambien libres, con calles y nombres de
# lugares, para no perder de vista comunas y municipios. Esri sirve imagen hasta
# el zoom 16; por encima Leaflet estira esa tesela en vez de dejar el fondo en blanco.
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/"
SATELITE = ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}"
ATRIBUCION = "Esri, Maxar, Earthstar Geographics"
REFERENCIAS = (
    (ESRI + "Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}", 0.55),
    (ESRI + "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", 1.0),
)
ZOOM_NATIVO = 16
ZOOM_MAXIMO = 19
SALIDA = Path("datos/salidas")

# Puntos de tamano fijo en pixeles, iguales en todos los mapas del proyecto.
RADIO_PUNTO = 2.5


def mapa_base(**opciones) -> folium.Map:
    """Mapa de folium sobre el satelite, con etiquetas. Solo para poligonos.

    Los mapas de puntos no usan folium sino MapLibre (`pagina_puntos`): Leaflet
    anima el zoom estirando la capa de puntos, y con miles de ellos se infla y
    da tirones. Los poligonos, en cambio, si deben crecer con el mapa.
    """
    opciones.setdefault("location", CENTRO_MEDELLIN)
    opciones.setdefault("zoom_start", 12)
    m = folium.Map(tiles=None, max_zoom=ZOOM_MAXIMO, **opciones)
    folium.TileLayer(
        tiles=SATELITE, attr=ATRIBUCION, name="Satélite",
        max_zoom=ZOOM_MAXIMO, max_native_zoom=ZOOM_NATIVO,
    ).add_to(m)
    for url, opacidad in REFERENCIAS:
        folium.TileLayer(
            tiles=url, attr="Etiquetas &copy; Esri", overlay=True, control=False,
            opacity=opacidad, max_zoom=ZOOM_MAXIMO, max_native_zoom=ZOOM_NATIVO,
        ).add_to(m)
    return m


# Pagina de puntos sobre MapLibre, con el fondo comun del sitio (mapa_satelite.js).
PLANTILLA_PUNTOS = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<style>__ESTILO_MAPLIBRE__</style>
<style>
  html, body { margin: 0; height: 100%; font: 13px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
  #mapa { position: absolute; inset: 0; }
  .maplibregl-popup-content { color: #222; padding: 8px 10px; border-radius: 8px; }
  .leyenda { position: absolute; left: 12px; bottom: 30px; z-index: 2; background: rgba(255,255,255,.94);
             padding: 10px 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 12px; color: #222; }
  .leyenda .t { font-weight: 600; margin-bottom: 6px; }
  .leyenda .f { display: flex; align-items: center; gap: 6px; margin: 2px 0; }
  .leyenda i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 1px solid #fff; }
  .opacidad { position: absolute; top: 10px; right: 10px; z-index: 2; display: flex; align-items: center; gap: 8px;
              background: rgba(255,255,255,.94); border: 1px solid #ccc; border-radius: 8px; padding: 6px 10px;
              font-size: 12px; color: #333; }
  .opacidad input { width: 110px; }
</style></head>
<body>
<div id="mapa"><label class="opacidad">Opacidad <input type="range" id="opacidad" min="10" max="100" step="5" value="80"></label></div>
__LEYENDA__
<script>__MAPLIBRE__</script>
<script>__MAPA_SATELITE__</script>
<script>
const P = __DATOS__;
const lat = P.lat, lng = P.lng;
const limites = [[Math.min(...lng), Math.min(...lat)], [Math.max(...lng), Math.max(...lat)]];
const mapa = MapaSatelite.crear("mapa", lat.length
  ? { bounds: limites, fitBoundsOptions: { padding: 30, maxZoom: 15 } } : { center: [-75.58, 6.244], zoom: 12 });
mapa.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
const globo = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
mapa.on("load", () => {
  MapaSatelite.capaPuntos(mapa, "puntos", { radio: __RADIO__ });
  mapa.getSource("puntos").setData(MapaSatelite.rasgos(lat, lng, i => P.c[i], i => P.t[i] === 1));
  MapaSatelite.alPasar(mapa, "puntos", {
    entra: i => { if (P.g[i]) globo.setLngLat([lng[i], lat[i]]).setHTML(P.g[i]).addTo(mapa); },
    sale: () => globo.remove(),
  });
  const opacidad = document.getElementById("opacidad");
  opacidad.addEventListener("input", () => MapaSatelite.opacidad(mapa, "puntos", opacidad.value / 100));
});
</script>
</body></html>
"""


def pagina_puntos(titulo: str, latitudes, longitudes, colores, globos=None, tenues=None,
                  leyenda: str = "") -> str:
    """HTML autocontenido con un punto de tamano fijo por registro, sobre el satelite."""
    import html as html_mod
    import json

    from .pagina import MAPA_SATELITE, biblioteca

    n = len(latitudes)
    datos = {
        "lat": [round(float(v), 6) for v in latitudes],
        "lng": [round(float(v), 6) for v in longitudes],
        "c": list(colores),
        "g": list(globos) if globos is not None else [""] * n,
        "t": [int(bool(v)) for v in tenues] if tenues is not None else [0] * n,
    }
    # </ dentro de una cadena JSON cerraria la etiqueta <script> antes de tiempo
    serializado = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (
        PLANTILLA_PUNTOS.replace("__TITULO__", html_mod.escape(titulo))
        .replace("__ESTILO_MAPLIBRE__", biblioteca("maplibre-gl.css"))
        .replace("__LEYENDA__", leyenda)
        .replace("__RADIO__", str(RADIO_PUNTO))
        .replace("__MAPLIBRE__", biblioteca("maplibre-gl.js"))
        .replace("__MAPA_SATELITE__", MAPA_SATELITE.read_text(encoding="utf-8"))
        .replace("__DATOS__", serializado)
    )


def _escribir(texto: str, salida: Path | str) -> Path:
    ruta = Path(salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


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

    m = mapa_base()

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
    import html

    centros = (
        geo[geo["barrio"].notna()]
        .groupby("barrio")
        .agg(lat=("latitud", "median"), lon=("longitud", "median"))
        .reset_index()
    )
    d = residuales.merge(centros, on="barrio", how="inner")
    if d.empty:
        raise ValueError("No hay barrios con coordenadas y residuales.")

    # Radio fijo: antes crecia con el sobreprecio, y los barrios extremos tapaban
    # a sus vecinos. La magnitud ya la dice el globo.
    globos = [
        (f"<b>{html.escape(str(f['barrio']))}</b><br>sobreprecio {f['sobreprecio_pct']:+.1f}%<br>"
         f"{int(f['avisos'])} avisos<br>${f['precio_m2_mediano']:,.0f}/m2").replace(",", ".")
        for _, f in d.iterrows()
    ]
    colores = ["#a8401c" if pct > 0 else "#2a6f97" for pct in d["sobreprecio_pct"]]
    return _escribir(pagina_puntos("Sobreprecio por barrio", d["lat"], d["lon"], colores, globos), salida)


def mapa_conglomerados(
    datos: pd.DataFrame, salida: Path | str = SALIDA / "mapa_conglomerados.html"
) -> Path:
    """Conglomerados LISA: zonas caras rodeadas de caras, y baratas de baratas."""
    import html

    d = datos[datos["latitud"].notna() & datos["conglomerado"].notna()]
    barrios = d["barrio"] if "barrio" in d.columns else pd.Series([""] * len(d), index=d.index)
    globos = [f"{html.escape(str(b) if isinstance(b, str) else '')} · {c}" for b, c in zip(barrios, d["conglomerado"])]
    colores = [COLOR_CONGLOMERADO.get(c, "#999999") for c in d["conglomerado"]]
    tenues = [c == "no significativo" for c in d["conglomerado"]]
    leyenda = _leyenda_categorica(COLOR_CONGLOMERADO, "Conglomerados de precio")
    return _escribir(
        pagina_puntos("Conglomerados", d["latitud"], d["longitud"], colores, globos, tenues, leyenda), salida
    )


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


def _leyenda_categorica(colores: dict[str, str], titulo: str) -> str:
    filas = "".join(f'<div class="f"><i style="background:{c}"></i>{n}</div>' for n, c in colores.items())
    return f'<div class="leyenda"><div class="t">{titulo}</div>{filas}</div>'


def puntos_html(latitudes, longitudes, color: str) -> str:
    """Mapa de avisos para el tablero: un punto fijo por aviso, sobre el satelite.

    Reemplaza a `st.map`, cuyo radio va en metros y por eso crecia con el zoom,
    y que no admite un fondo satelital sin clave de Mapbox.
    """
    return pagina_puntos("Avisos", latitudes, longitudes, [color] * len(latitudes))


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

