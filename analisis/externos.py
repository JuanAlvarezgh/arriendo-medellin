"""Descarga y prepara las fuentes externas: puntos de interes y norma del POT.

Dos origenes:

- GeoMedellin, el servidor de mapas de la Alcaldia (ArcGIS REST). Responde 403 a
  un agente de script y 200 a uno de navegador, asi que se presenta como Chrome.
  Licencia CC BY-SA 4.0: las paginas citan "Alcaldia de Medellin - GeoMedellin".
- OpenStreetMap por Overpass, para lo que la Alcaldia no publica (supermercados)
  y como respaldo de todo lo demas si el servidor oficial no responde. Licencia
  ODbL: las paginas citan "(c) OpenStreetMap".

Lo que se guarda en el repositorio queda en `datos/externos/poi` y
`datos/externos/pot`, con la fecha de descarga en el nombre, para regenerar las
paginas sin volver a descargar. De la OIME (ofertas con telefono, correo y
enlace) y del catastro solo se guardan agregados, nunca filas individuales.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

from .geo import CRS_COLOMBIA, CRS_MUNDIAL

BASE = "https://www.medellin.gov.co/servidormapas/rest/services"
AGENTE_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
AGENTE_OSM = "arriendos-medellin/0.2 (proyecto universitario de analitica de datos)"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
# Caja del Valle de Aburra que cubre Medellin: sur, oeste, norte, este.
CAJA = (6.15, -75.65, 6.33, -75.52)
PAGINA = 2000

CARPETA_POI = Path("datos/externos/poi")
CARPETA_POT = Path("datos/externos/pot")
NORMA = Path(__file__).resolve().parent / "norma_pot.json"

CATEGORIAS = {
    "metro": "Metro, Metrocable, Metroplús y Tranvía",
    "parque": "Parques",
    "colegio": "Colegios",
    "universidad": "Universidades",
    "salud": "Salud",
    "policia": "Policía",
    "bomberos": "Bomberos",
    "supermercado": "Supermercados",
}

# ruleid de la capa de estaciones.
SISTEMAS = {1: "Metro", 2: "Metrocable", 3: "Metroplús", 4: "Tranvía"}
# Lineas que la capa marca como "Proyectado" pero ya operan.
LINEAS_EN_OPERACION = {"H", "M"}

# Comunas (01 a 16) y corregimientos (50 a 90): el prefijo del cobama.
COMUNAS = [f"{c:02d}" for c in range(1, 17)] + ["50", "60", "70", "80", "90"]


def fecha_hoy() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def url_consulta(servicio: str, capa: int) -> str:
    return f"{BASE}/{servicio}/MapServer/{capa}/query"


def parametros_pagina(where: str = "1=1", campos: str = "*", desplazamiento: int = 0,
                      pagina: int = PAGINA, geometria: bool = True) -> dict:
    """Parametros de una pagina de la consulta en GeoJSON y en coordenadas WGS84."""
    return {
        "where": where, "outFields": campos, "outSR": 4326, "f": "geojson",
        "returnGeometry": "true" if geometria else "false",
        "resultOffset": desplazamiento, "resultRecordCount": pagina,
    }


def _cliente():
    import httpx

    return httpx.Client(headers={"User-Agent": AGENTE_NAVEGADOR}, timeout=120, follow_redirects=True)


def _pedir(cliente, url: str, params: dict | None = None, data: dict | None = None,
           intentos: int = 4, espera: float = 3.0) -> Any:
    """GET o POST con reintentos y espera creciente. Devuelve el JSON."""
    ultimo: Exception | None = None
    for k in range(intentos):
        try:
            r = cliente.post(url, data=data) if data is not None else cliente.get(url, params=params)
            r.raise_for_status()
            contenido = r.json()
            if isinstance(contenido, dict) and "error" in contenido:
                raise RuntimeError(f"{url}: {contenido['error']}")
            return contenido
        except Exception as e:  # noqa: BLE001 - se reintenta cualquier fallo de red o de servidor
            ultimo = e
            time.sleep(espera * (k + 1))
    raise RuntimeError(f"no se pudo descargar {url}: {ultimo}")


def unir_paginas(paginas: list[dict]) -> gpd.GeoDataFrame:
    """Une paginas GeoJSON en un GeoDataFrame en WGS84. Rasgos sin geometria se omiten."""
    filas, geometrias = [], []
    for pag in paginas:
        for f in pag.get("features", []):
            if not f.get("geometry"):
                continue
            filas.append(f.get("properties") or {})
            geometrias.append(shape(f["geometry"]))
    return gpd.GeoDataFrame(pd.DataFrame(filas), geometry=geometrias, crs=CRS_MUNDIAL)


def descargar_capa(servicio: str, capa: int, where: str = "1=1", campos: str = "*",
                   cliente=None, pagina: int = PAGINA) -> gpd.GeoDataFrame:
    """Toda la capa, de `pagina` en `pagina` registros con resultOffset."""
    propio = cliente is None
    cliente = cliente or _cliente()
    paginas, desplazamiento = [], 0
    try:
        while True:
            pag = _pedir(cliente, url_consulta(servicio, capa),
                         params=parametros_pagina(where, campos, desplazamiento, pagina))
            n = len(pag.get("features", []))
            paginas.append(pag)
            if n < pagina:
                break
            desplazamiento += n
    finally:
        if propio:
            cliente.close()
    return unir_paginas(paginas)


def estadisticas_agrupadas(servicio: str, capa: int, where: str, estadisticas: list[dict],
                           agrupar: str, cliente=None) -> pd.DataFrame:
    """outStatistics agrupadas. La paginacion de estadisticas no funciona en este
    servidor, asi que quien llama debe partir la consulta con `where`."""
    propio = cliente is None
    cliente = cliente or _cliente()
    try:
        r = _pedir(cliente, url_consulta(servicio, capa), params={
            "where": where, "outStatistics": json.dumps(estadisticas),
            "groupByFieldsForStatistics": agrupar, "f": "json",
        })
    finally:
        if propio:
            cliente.close()
    return pd.DataFrame([f["attributes"] for f in r.get("features", [])])


def consulta_overpass(filtros: list[str], caja: tuple = CAJA) -> str:
    """Consulta Overpass QL: nodos, vias y relaciones de cada filtro, con su centro."""
    s, o, n, e = caja
    cuerpo = "".join(f"nwr{f}({s},{o},{n},{e});" for f in filtros)
    return f"[out:json][timeout:180];({cuerpo});out center tags;"


def descargar_overpass(filtros: list[str], caja: tuple = CAJA, intentos: int = 3) -> list[dict]:
    """Elementos de OSM. Overpass falla a ratos: se prueba cada espejo varias veces."""
    import httpx

    consulta = consulta_overpass(filtros, caja)
    ultimo: Exception | None = None
    with httpx.Client(headers={"User-Agent": AGENTE_OSM}, timeout=240) as cliente:
        for k in range(intentos):
            for url in OVERPASS:
                try:
                    r = cliente.post(url, data={"data": consulta})
                    r.raise_for_status()
                    return r.json().get("elements", [])
                except Exception as e:  # noqa: BLE001
                    ultimo = e
            time.sleep(10 * (k + 1))
    raise RuntimeError(f"Overpass no respondio: {ultimo}")


# ---------------------------------------------------------------------------
# Puntos de interes
# ---------------------------------------------------------------------------

COLUMNAS_PUNTOS = ["categoria", "nombre", "detalle", "latitud", "longitud", "fuente"]


def centros(gdf: gpd.GeoDataFrame) -> gpd.GeoSeries:
    """Un punto por geometria: el punto representativo, que cae siempre dentro del
    poligono (el centroide de un poligono en forma de U puede quedar fuera)."""
    if gdf.empty:
        return gpd.GeoSeries([], crs=CRS_MUNDIAL)
    metros = gdf.to_crs(CRS_COLOMBIA).geometry
    return metros.representative_point().to_crs(CRS_MUNDIAL)


def _texto(v: Any) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def _puntos(gdf: gpd.GeoDataFrame, categoria: str, nombre: str, detalle, fuente: str) -> pd.DataFrame:
    if gdf.empty:
        return pd.DataFrame(columns=COLUMNAS_PUNTOS)
    p = centros(gdf)
    return pd.DataFrame({
        "categoria": categoria,
        "nombre": [_texto(v) for v in gdf[nombre]] if nombre in gdf.columns else "",
        "detalle": [_texto(v) for v in (detalle(gdf) if callable(detalle) else gdf.get(detalle, ""))],
        "latitud": p.y.round(6).to_numpy(),
        "longitud": p.x.round(6).to_numpy(),
        "fuente": fuente,
    })


def estaciones_transporte(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Estaciones existentes, mas las de las lineas H y M que salen como proyectadas."""
    estado = gdf["estado"].fillna("").str.lower()
    linea = gdf["linea"].fillna("").astype(str).str.strip().str.upper()
    proyectada = estado.str.contains("proyect")
    sirve = ~proyectada | linea.isin(LINEAS_EN_OPERACION)
    g = gdf[sirve].copy()
    detalle = lambda x: [f"{SISTEMAS.get(int(r), 'Transporte')} · línea {_texto(l)}"  # noqa: E731
                         for r, l in zip(x["ruleid"].fillna(0), x["linea"])]
    return _puntos(g, "metro", "nombre", detalle, "GeoMedellín")


def equipamientos(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Salud, policia, bomberos y educacion superior del inventario de equipamientos."""
    tipo = gdf["tipo"].fillna("").str.lower()
    comp = gdf["componentes"].fillna("").str.lower()
    grupos = {
        "salud": comp.str.contains("salud") | tipo.str.contains("salud"),
        "policia": tipo.str.contains("polic"),
        "bomberos": tipo.str.contains("bomber"),
        "universidad": tipo.str.contains("educación superior|educacion superior"),
    }
    partes = [_puntos(gdf[m], cat, "nombre", "tipo", "GeoMedellín") for cat, m in grupos.items()]
    return pd.concat(partes, ignore_index=True)


def parques(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Parques del inventario de espacio publico de esparcimiento y encuentro."""
    cat = gdf["categoria"].fillna("").str.lower()
    return _puntos(gdf[cat.str.contains("parque")], "parque", "nombre", "categoria", "GeoMedellín")


def colegios(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Sedes educativas de preescolar a once. Solo nombre, sector y coordenada."""
    g = gdf
    if "estado" in g.columns:
        estado = g["estado"].fillna("").str.lower()
        g = g[~estado.str.contains("cerrad|inactiv")]
    nombre = "sede_educa" if "sede_educa" in g.columns else "nombre_est"
    return _puntos(g, "colegio", nombre, "sector", "GeoMedellín")


def universidades(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    return _puntos(gdf, "universidad", "institucion", "tipo", "GeoMedellín")


# Etiquetas de OSM de cada categoria, para Overpass y para clasificar lo que vuelve.
FILTROS_OSM = {
    "supermercado": ['["shop"="supermarket"]'],
    "policia": ['["amenity"="police"]'],
    "bomberos": ['["amenity"="fire_station"]'],
    "universidad": ['["amenity"~"^(university|college)$"]'],
    "parque": ['["leisure"="park"]'],
    "metro": ['["railway"="station"]', '["aerialway"="station"]', '["railway"="tram_stop"]'],
    "salud": ['["amenity"~"^(hospital|clinic)$"]'],
    "colegio": ['["amenity"="school"]'],
}


def categoria_osm(etiquetas: dict) -> str | None:
    """Categoria de un elemento de OSM segun sus etiquetas."""
    shop, amenity = etiquetas.get("shop"), etiquetas.get("amenity")
    if shop == "supermarket":
        return "supermercado"
    if amenity == "police":
        return "policia"
    if amenity == "fire_station":
        return "bomberos"
    if amenity in ("university", "college"):
        return "universidad"
    if amenity in ("hospital", "clinic"):
        return "salud"
    if amenity == "school":
        return "colegio"
    if etiquetas.get("leisure") == "park":
        return "parque"
    if etiquetas.get("railway") in ("station", "tram_stop") or etiquetas.get("aerialway") == "station":
        return "metro"
    return None


def puntos_osm(elementos: list[dict], categorias: set[str] | None = None) -> pd.DataFrame:
    """Un punto por elemento: el nodo, o el centro que Overpass da para vias y relaciones."""
    filas = []
    for el in elementos:
        etiquetas = el.get("tags") or {}
        cat = categoria_osm(etiquetas)
        if cat is None or (categorias and cat not in categorias):
            continue
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        filas.append({
            "categoria": cat, "nombre": etiquetas.get("name", ""),
            "detalle": etiquetas.get("brand", etiquetas.get("operator", "")),
            "latitud": round(float(lat), 6), "longitud": round(float(lon), 6),
            "fuente": "OpenStreetMap",
        })
    return pd.DataFrame(filas, columns=COLUMNAS_PUNTOS)


def quitar_duplicados(puntos: pd.DataFrame, metros: float = 60) -> pd.DataFrame:
    """Dentro de cada categoria, deja un solo punto por grupo a menos de `metros`.

    La misma universidad puede venir de dos capas, o un hospital como varios
    edificios. Se recorre en orden y se descarta todo punto a menos de `metros` de
    uno ya aceptado de su misma categoria.
    """
    from scipy.spatial import cKDTree

    if puntos.empty:
        return puntos
    lat0 = np.radians(puntos["latitud"].mean())
    quedan = []
    for _, grupo in puntos.groupby("categoria", sort=False):
        xy = np.column_stack([grupo["longitud"] * 111_320 * np.cos(lat0), grupo["latitud"] * 110_540])
        arbol = cKDTree(xy)
        descartado = np.zeros(len(grupo), dtype=bool)
        for i in range(len(grupo)):
            if descartado[i]:
                continue
            for j in arbol.query_ball_point(xy[i], r=metros):
                if j > i:
                    descartado[j] = True
        quedan.append(grupo[~descartado])
    return pd.concat(quedan).reset_index(drop=True)


def dentro_de_caja(puntos: pd.DataFrame, caja: tuple = CAJA) -> pd.DataFrame:
    s, o, n, e = caja
    return puntos[puntos["latitud"].between(s, n) & puntos["longitud"].between(o, e)].reset_index(drop=True)


def puntos_de_interes(cliente=None) -> tuple[pd.DataFrame, dict]:
    """Descarga todas las categorias. Devuelve los puntos y un registro de fuentes.

    Primero el servidor oficial; la categoria que falle o salga vacia se pide a
    OSM. Los supermercados salen siempre de OSM porque no hay capa oficial.
    """
    propio = cliente is None
    cliente = cliente or _cliente()
    partes, registro = [], {}
    oficiales = {
        "metro": lambda: estaciones_transporte(descargar_capa("mapas_nacionales/VC_Transporte", 2, cliente=cliente)),
        "equipamientos": lambda: equipamientos(descargar_capa(
            "mapas_nacionales/VC_Infraestructura_Fisica", 1, campos="nombre,tipo,componentes,nivel", cliente=cliente)),
        "parque": lambda: parques(descargar_capa(
            "mapas_nacionales/VC_Infraestructura_Fisica", 2, campos="nombre,categoria,subcategor,nivel", cliente=cliente)),
        "colegio": lambda: colegios(descargar_capa(
            "educacion/VC_Sedes", 0, campos="sede_educa,nombre_est,sector,estado", cliente=cliente)),
        "universidad": lambda: universidades(descargar_capa(
            "educacion/VC_Sedes", 1, campos="institucion,tipo,sector", cliente=cliente)),
    }
    try:
        for clave, f in oficiales.items():
            try:
                p = f()
                partes.append(p)
                for cat, n in p["categoria"].value_counts().items():
                    registro.setdefault(cat, {"oficial": 0, "osm": 0})["oficial"] += int(n)
            except Exception as e:  # noqa: BLE001
                registro.setdefault("fallas", []).append(f"{clave}: {e}")
    finally:
        if propio:
            cliente.close()

    oficial = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUMNAS_PUNTOS)
    faltan = {c for c in CATEGORIAS if c not in set(oficial["categoria"])}
    faltan.add("supermercado")
    filtros = [f for c in sorted(faltan) for f in FILTROS_OSM[c]]
    try:
        osm = puntos_osm(descargar_overpass(filtros), faltan)
        for cat, n in osm["categoria"].value_counts().items():
            registro.setdefault(cat, {"oficial": 0, "osm": 0})["osm"] += int(n)
    except Exception as e:  # noqa: BLE001
        registro.setdefault("fallas", []).append(f"overpass: {e}")
        osm = pd.DataFrame(columns=COLUMNAS_PUNTOS)

    todos = dentro_de_caja(quitar_duplicados(pd.concat([oficial, osm], ignore_index=True)))
    registro["total"] = {c: int(n) for c, n in todos["categoria"].value_counts().items()}
    return todos.sort_values(["categoria", "nombre"]).reset_index(drop=True), registro


# ---------------------------------------------------------------------------
# Norma del POT
# ---------------------------------------------------------------------------

def leer_norma(ruta: Path = NORMA, clave: str | None = None) -> dict:
    """Configuracion de la norma activa (o de `clave`): servicios, capas y campos."""
    cfg = json.loads(Path(ruta).read_text(encoding="utf-8"))
    clave = clave or cfg["activa"]
    norma = dict(cfg["normas"][clave])
    norma.update(clave=clave, aviso=cfg["aviso"], revision=cfg["revision"])
    return norma


def renombrar(gdf: gpd.GeoDataFrame, campos: dict) -> gpd.GeoDataFrame:
    """Pasa los campos del servidor a los nombres internos; los que falten quedan vacios."""
    salida = gpd.GeoDataFrame({interno: gdf[externo] if externo in gdf.columns else None
                               for interno, externo in campos.items()},
                              geometry=gdf.geometry.to_numpy(), crs=gdf.crs)
    return salida


def simplificar(gdf: gpd.GeoDataFrame, tolerancia_m: float = 8.0, decimales: int = 5) -> gpd.GeoDataFrame:
    """Simplifica en metros conservando la topologia y redondea las coordenadas.

    Con 8 m de tolerancia el borde de un poligono se mueve menos que el ancho de
    una calle, y el archivo baja a una fraccion. Cinco decimales son 1,1 m.
    """
    from shapely import set_precision

    g = gdf.to_crs(CRS_COLOMBIA)
    g["geometry"] = g.geometry.simplify(tolerancia_m, preserve_topology=True)
    g = g.to_crs(CRS_MUNDIAL)
    g["geometry"] = set_precision(g.geometry.make_valid().to_numpy(), 10 ** -decimales)
    return g[~g.geometry.is_empty & g.geometry.notna()]


def tratamientos(norma: dict, cliente=None) -> gpd.GeoDataFrame:
    cfg = norma["tratamientos"]
    gdf = descargar_capa(cfg["servicio"], cfg["capa"], campos=",".join(cfg["campos"].values()), cliente=cliente)
    t = renombrar(gdf, cfg["campos"])
    t.insert(0, "id_poligono", np.arange(len(t)))
    t["area_ha"] = (t.to_crs(CRS_COLOMBIA).area / 10_000).round(2)
    return t


def usos_disueltos(norma: dict, cliente=None) -> gpd.GeoDataFrame:
    """Usos del suelo urbano disueltos por subcategoria: de 25 mil poligonos a unas
    pocas geometrias, que bastan para saber el uso de cada aviso y de cada
    poligono de tratamiento."""
    cfg = norma["usos"]
    gdf = descargar_capa(cfg["servicio"], cfg["capa"], campos=",".join(cfg["campos"].values()), cliente=cliente)
    u = renombrar(gdf, cfg["campos"])
    u["geometry"] = u.to_crs(CRS_COLOMBIA).geometry.buffer(0).to_crs(CRS_MUNDIAL)
    return u.dissolve(by="uso", as_index=False)[["uso", "categoria", "geometry"]]


def pisos_por_manzana(cliente=None, comunas: list[str] = COMUNAS) -> pd.DataFrame:
    """Pisos construidos por manzana catastral, desde estadisticas del servidor.

    Son 1,1 millones de construcciones: se piden ya agrupadas por cobama, una
    consulta por comuna, y se ubican con el centro de su manzana catastral.
    """
    estad = [
        {"statisticType": "avg", "onStatisticField": "numero_pisos", "outStatisticFieldName": "pisos_promedio"},
        {"statisticType": "max", "onStatisticField": "numero_pisos", "outStatisticFieldName": "pisos_max"},
        {"statisticType": "count", "onStatisticField": "numero_pisos", "outStatisticFieldName": "construcciones"},
        {"statisticType": "sum", "onStatisticField": "area_construida", "outStatisticFieldName": "area_construida"},
    ]
    propio = cliente is None
    cliente = cliente or _cliente()
    try:
        partes = [estadisticas_agrupadas("ServiciosCiudad/CartografiaBase", 15, f"cobama LIKE '{c}%'",
                                         estad, "cobama", cliente=cliente) for c in comunas]
        manzanas = descargar_capa("ordenamiento_ter/VA_POT48_Reporte_UsoSuelo_U", 5, campos="cobama", cliente=cliente)
    finally:
        if propio:
            cliente.close()
    pisos = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    return ubicar_manzanas(pisos, manzanas)


def ubicar_manzanas(pisos: pd.DataFrame, manzanas: gpd.GeoDataFrame) -> pd.DataFrame:
    """Une las estadisticas por cobama con el punto representativo de su manzana."""
    p = centros(manzanas)
    ubic = pd.DataFrame({"cobama": manzanas["cobama"].astype(str).to_numpy(),
                         "latitud": p.y.round(6).to_numpy(), "longitud": p.x.round(6).to_numpy()})
    ubic = ubic.drop_duplicates("cobama")
    pisos = pisos.assign(cobama=pisos["cobama"].astype(str))
    salida = pisos.merge(ubic, on="cobama", how="inner")
    salida["pisos_promedio"] = salida["pisos_promedio"].round(2)
    salida["area_construida"] = salida["area_construida"].round(0)
    return salida[["cobama", "latitud", "longitud", "construcciones", "pisos_promedio", "pisos_max", "area_construida"]]


# ---------------------------------------------------------------------------
# OIME: arriendos de 2023, solo agregados
# ---------------------------------------------------------------------------

CAMPOS_OIME = "price,private_area_m2,total_area_m2,stratum,year,commercial_type,category,type,furnished,latitude,longitude"
# Bins de ln(precio/m2) para guardar la distribucion de 2023 sin filas individuales.
# De 5.000 a 300.000 pesos por m2, en 200 bins: la KS sobre bins tan finos se
# aleja de la exacta en menos de 0,005.
BORDES_LN_M2 = np.linspace(np.log(5_000), np.log(300_000), 201)


def descargar_oime(cliente=None) -> pd.DataFrame:
    """Ofertas de arriendo residencial de 2023 (solo en memoria; no se guardan)."""
    servicio, capa = "vivienda_ciudad_terri/VM_Oferta_Comercial_Oime", 1
    gdf = descargar_capa(servicio, capa, where="year = 2023 AND commercial_type = 'RENT'",
                         campos=CAMPOS_OIME, cliente=cliente)
    return limpiar_oime(pd.DataFrame(gdf.drop(columns="geometry")))


def limpiar_oime(d: pd.DataFrame) -> pd.DataFrame:
    """Vivienda en arriendo con precio, area y coordenada plausibles."""
    d = d.copy()
    d["area"] = pd.to_numeric(d["private_area_m2"], errors="coerce")
    if "total_area_m2" in d.columns:
        d["area"] = d["area"].where(d["area"] > 0, pd.to_numeric(d["total_area_m2"], errors="coerce"))
    d["precio"] = pd.to_numeric(d["price"], errors="coerce")
    d["latitud"] = pd.to_numeric(d["latitude"], errors="coerce")
    d["longitud"] = pd.to_numeric(d["longitude"], errors="coerce")
    d["estrato"] = pd.to_numeric(d["stratum"], errors="coerce")
    d["amoblado"] = pd.to_numeric(d.get("furnished"), errors="coerce").fillna(0) > 0
    categoria = d.get("category", pd.Series("RESIDENCIAL", index=d.index)).fillna("").str.upper()
    d = d[categoria.str.contains("RESIDENCIAL") | (categoria == "")]
    d = d[(d["area"].between(15, 1000)) & (d["precio"].between(300_000, 60_000_000))]
    s, o, n, e = CAJA
    d = d[d["latitud"].between(s, n) & d["longitud"].between(o, e)]
    d["precio_m2"] = d["precio"] / d["area"]
    d = d[d["precio_m2"].between(np.exp(BORDES_LN_M2[0]), np.exp(BORDES_LN_M2[-1]))]
    return d[["precio", "area", "precio_m2", "estrato", "amoblado", "latitud", "longitud"]].reset_index(drop=True)


def agregar_por_poligono(puntos: pd.DataFrame, poligonos: gpd.GeoDataFrame,
                         columna: str = "id_poligono") -> pd.DataFrame:
    """n, media y varianza de ln(precio/m2), mediana y % amoblado por poligono."""
    g = gpd.GeoDataFrame(puntos, geometry=gpd.points_from_xy(puntos["longitud"], puntos["latitud"]), crs=CRS_MUNDIAL)
    unido = gpd.sjoin(g, poligonos[[columna, "geometry"]], how="inner", predicate="within")
    unido["ln_m2"] = np.log(unido["precio_m2"])
    resumen = unido.groupby(columna).agg(
        n=("ln_m2", "size"), media_ln_m2=("ln_m2", "mean"), var_ln_m2=("ln_m2", lambda x: x.var(ddof=1)),
        mediana_m2=("precio_m2", "median"), pct_amoblado=("amoblado", "mean"),
    ).reset_index()
    return resumen.round({"media_ln_m2": 5, "var_ln_m2": 5, "mediana_m2": 0, "pct_amoblado": 4})


def histograma_ln_m2(precio_m2: np.ndarray, bordes: np.ndarray = BORDES_LN_M2) -> list[int]:
    conteo, _ = np.histogram(np.log(np.asarray(precio_m2, dtype=float)), bins=bordes)
    return [int(v) for v in conteo]


def resumen_oime(oime: pd.DataFrame, poligonos: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict]:
    """Agregados por poligono y la distribucion de la ciudad en bins, total y por estrato."""
    por_poligono = agregar_por_poligono(oime, poligonos)
    ciudad = {
        "anio": 2023, "n": int(len(oime)),
        "bordes_ln_m2": [round(float(v), 6) for v in BORDES_LN_M2],
        "histograma": histograma_ln_m2(oime["precio_m2"]),
        "por_estrato": {str(int(e)): histograma_ln_m2(g["precio_m2"])
                        for e, g in oime.dropna(subset=["estrato"]).groupby("estrato") if len(g) >= 10},
        "pct_amoblado": round(float(oime["amoblado"].mean()), 4),
    }
    return por_poligono, ciudad


# ---------------------------------------------------------------------------
# Todo junto
# ---------------------------------------------------------------------------

def descargar_todo(fecha: str | None = None, clave_norma: str | None = None) -> dict:
    """Descarga y deja en disco todo lo externo. Devuelve el registro de fuentes."""
    fecha = fecha or fecha_hoy()
    CARPETA_POI.mkdir(parents=True, exist_ok=True)
    CARPETA_POT.mkdir(parents=True, exist_ok=True)
    registro: dict[str, Any] = {"fecha": fecha, "fallas": []}

    with _cliente() as cliente:
        puntos, reg_poi = puntos_de_interes(cliente)
        puntos.to_csv(CARPETA_POI / f"puntos_interes_{fecha}.csv", index=False, encoding="utf-8")
        registro["puntos_interes"] = reg_poi
        registro["fallas"] += reg_poi.pop("fallas", [])

        norma = leer_norma(clave=clave_norma)
        registro["norma"] = norma["clave"]
        try:
            t = tratamientos(norma, cliente)
            simplificar(t).to_file(CARPETA_POT / f"tratamientos_{fecha}.geojson", driver="GeoJSON")
            registro["tratamientos"] = int(len(t))
        except Exception as e:  # noqa: BLE001
            registro["fallas"].append(f"tratamientos: {e}")
            t = None
        try:
            u = usos_disueltos(norma, cliente)
            simplificar(u, tolerancia_m=10).to_file(CARPETA_POT / f"usos_suelo_{fecha}.geojson", driver="GeoJSON")
            registro["usos_suelo"] = int(len(u))
        except Exception as e:  # noqa: BLE001
            registro["fallas"].append(f"usos del suelo: {e}")
        try:
            pisos = pisos_por_manzana(cliente)
            pisos.to_csv(CARPETA_POT / f"pisos_por_manzana_{fecha}.csv", index=False, encoding="utf-8")
            registro["manzanas_con_pisos"] = int(len(pisos))
            registro["construcciones"] = int(pisos["construcciones"].sum())
        except Exception as e:  # noqa: BLE001
            registro["fallas"].append(f"catastro: {e}")
        if t is not None:
            try:
                oime = descargar_oime(cliente)
                por_poligono, ciudad = resumen_oime(oime, t)
                por_poligono.to_csv(CARPETA_POT / f"oime_2023_por_tratamiento_{fecha}.csv", index=False, encoding="utf-8")
                (CARPETA_POT / f"oime_2023_ciudad_{fecha}.json").write_text(
                    json.dumps(ciudad, ensure_ascii=False), encoding="utf-8")
                registro["oime_2023"] = int(len(oime))
            except Exception as e:  # noqa: BLE001
                registro["fallas"].append(f"OIME: {e}")

    (CARPETA_POT.parent / f"fuentes_{fecha}.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return registro


def mas_reciente(carpeta: Path, patron: str) -> Path | None:
    """El archivo mas reciente que cumple el patron; la fecha va en el nombre."""
    candidatos = sorted(Path(carpeta).glob(patron))
    return candidatos[-1] if candidatos else None


if __name__ == "__main__":
    print(json.dumps(descargar_todo(), ensure_ascii=False, indent=2))
