"""Distancia a pie de cada aviso a lo mas cercano de cada categoria.

Se baja la red peatonal de OpenStreetMap con osmnx y se corre un Dijkstra de
varias fuentes por categoria: todos los puntos de la categoria salen a la vez y
cada nodo de la red queda con la distancia al mas cercano de ellos. Asi una
categoria cuesta una sola pasada por la red, sin importar cuantos puntos tenga.

La pagina no puede correr Dijkstra sobre la red entera, asi que para el punto de
referencia que la persona marca usa la linea recta por un factor de rodeo. Ese
factor se calibra aqui mismo, con rutas reales sobre la red entre avisos.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .externos import CAJA, CARPETA_POI, fecha_hoy, mas_reciente

CACHE_RED = Path("datos/cache/red_peatonal.graphml")
MINUTOS_POR_KM = 13          # unos 4,6 km/h, paso de adulto en ciudad con pendiente
FACTOR_RODEO_REFERENCIA = 1.43
TOPE_M = 8_000               # mas alla de esto, a pie no cuenta como cerca
LAT0 = 6.25


def a_metros(lat: np.ndarray, lng: np.ndarray, lat0: float = LAT0) -> np.ndarray:
    """Proyeccion equirectangular local: sobra para distancias de pocos kilometros."""
    lat, lng = np.asarray(lat, dtype=float), np.asarray(lng, dtype=float)
    return np.column_stack([lng * 111_320 * np.cos(np.radians(lat0)), lat * 110_540])


def minutos(metros: np.ndarray | float) -> np.ndarray | float:
    return np.asarray(metros) / 1000 * MINUTOS_POR_KM


# ---------------------------------------------------------------------------
# Red
# ---------------------------------------------------------------------------

def descargar_red(caja: tuple = CAJA, cache: Path = CACHE_RED):
    """Red peatonal de OSM dentro de la caja, guardada en cache la primera vez."""
    import osmnx as ox

    if cache.exists():
        return ox.load_graphml(cache)
    s, o, n, e = caja
    ox.settings.use_cache = True
    ox.settings.http_user_agent = "arriendos-medellin/0.2 (proyecto universitario de analitica de datos)"
    red = ox.graph_from_bbox((o, s, e, n), network_type="walk", simplify=True, retain_all=False)
    cache.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(red, cache)
    return red


class Red:
    """La red como matriz dispersa simetrica, con los nodos en metros."""

    def __init__(self, lat: np.ndarray, lng: np.ndarray, origen: np.ndarray, destino: np.ndarray,
                 largo: np.ndarray):
        self.xy = a_metros(lat, lng)
        self.n = len(lat)
        filas = np.r_[origen, destino]
        cols = np.r_[destino, origen]
        pesos = np.r_[largo, largo]
        # Con aristas repetidas entre dos nodos, coo->csr suma: se toma el minimo antes.
        orden = pd.DataFrame({"a": filas, "b": cols, "w": pesos}).groupby(["a", "b"], as_index=False)["w"].min()
        self.matriz = coo_matrix((orden["w"], (orden["a"], orden["b"])), shape=(self.n, self.n)).tocsr()
        self.arbol = cKDTree(self.xy)

    @classmethod
    def desde_osmnx(cls, grafo) -> "Red":
        nodos = list(grafo.nodes)
        indice = {nd: k for k, nd in enumerate(nodos)}
        lat = np.array([grafo.nodes[nd]["y"] for nd in nodos])
        lng = np.array([grafo.nodes[nd]["x"] for nd in nodos])
        o, d, w = [], [], []
        for a, b, datos in grafo.edges(data=True):
            o.append(indice[a]); d.append(indice[b]); w.append(float(datos.get("length", 0.0)))
        return cls(lat, lng, np.array(o), np.array(d), np.array(w))

    def mas_cercano(self, lat: np.ndarray, lng: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Nodo de la red mas cercano y la distancia en linea recta hasta el."""
        distancia, nodo = self.arbol.query(a_metros(lat, lng))
        return nodo, distancia

    def desde_varias_fuentes(self, lat: np.ndarray, lng: np.ndarray, tope: float = TOPE_M) -> np.ndarray:
        """Distancia de cada nodo a la fuente mas cercana, sumando el tramo recto
        de cada fuente a su nodo. Se agrega un nodo virtual unido a todas."""
        nodo, recto = self.mas_cercano(lat, lng)
        n = self.n
        # El tramo recto lleva un milimetro de mas: un peso cero se tomaria como sin arista.
        extra = coo_matrix((recto + 1e-3, (np.full(len(nodo), n), nodo)), shape=(n + 1, n + 1))
        m = _ampliar(self.matriz, n + 1) + extra.tocsr()
        dist = dijkstra(m, directed=True, indices=n, limit=tope)
        return dist[:n]


def _ampliar(m, tam: int):
    """La matriz con una fila y una columna mas, vacias."""
    m = m.tocoo()
    return coo_matrix((m.data, (m.row, m.col)), shape=(tam, tam)).tocsr()


def distancia_a_categoria(red: Red, nodos_dist: np.ndarray, lat: np.ndarray, lng: np.ndarray) -> np.ndarray:
    """Distancia a pie de cada punto: su tramo recto hasta la red mas lo que dice la red."""
    nodo, recto = red.mas_cercano(lat, lng)
    return recto + nodos_dist[nodo]


# ---------------------------------------------------------------------------
# Factor de rodeo
# ---------------------------------------------------------------------------

def factor_rodeo(red: Red, lat: np.ndarray, lng: np.ndarray, origenes: int = 300,
                 rango: tuple = (300.0, 3000.0), semilla: int = 11) -> dict:
    """Mediana de distancia a pie / linea recta entre pares de avisos reales.

    Se toman `origenes` avisos al azar y, para cada uno, los demas avisos a una
    distancia recta dentro de `rango` (lo que alguien caminaria). La mediana es
    robusta a los pocos pares que la red rodea mucho (una quebrada sin puente).
    """
    rng = np.random.default_rng(semilla)
    xy = a_metros(lat, lng)
    nodo, recto_nodo = red.mas_cercano(lat, lng)
    elegidos = rng.choice(len(lat), size=min(origenes, len(lat)), replace=False)
    arbol = cKDTree(xy)
    razones = []
    for k in range(0, len(elegidos), 50):
        lote = elegidos[k:k + 50]
        dist = dijkstra(red.matriz, directed=False, indices=nodo[lote], limit=rango[1] * 2.5)
        for fila, i in enumerate(lote):
            vecinos = np.array(arbol.query_ball_point(xy[i], r=rango[1]))
            if not len(vecinos):
                continue
            recta = np.hypot(*(xy[vecinos] - xy[i]).T)
            utiles = vecinos[recta >= rango[0]]
            recta = recta[recta >= rango[0]]
            a_pie = recto_nodo[i] + dist[fila, nodo[utiles]] + recto_nodo[utiles]
            validos = np.isfinite(a_pie)
            razones.append(a_pie[validos] / recta[validos])
    todas = np.concatenate(razones) if razones else np.array([FACTOR_RODEO_REFERENCIA])
    return {
        "factor": round(float(np.median(todas)), 3),
        "p25": round(float(np.percentile(todas, 25)), 3),
        "p75": round(float(np.percentile(todas, 75)), 3),
        "pares": int(len(todas)),
        "origenes": int(len(elegidos)),
        "rango_m": list(rango),
    }


# ---------------------------------------------------------------------------
# Todo junto
# ---------------------------------------------------------------------------

def coordenadas_unicas(lat: np.ndarray, lng: np.ndarray) -> pd.DataFrame:
    """Las coordenadas distintas, redondeadas a 6 decimales (11 cm): la distancia
    solo depende del lugar, y muchos avisos comparten punto."""
    return (pd.DataFrame({"latitud": np.round(lat, 6), "longitud": np.round(lng, 6)})
            .drop_duplicates().reset_index(drop=True))


def calcular(avisos: pd.DataFrame, puntos: pd.DataFrame, red: Red) -> tuple[pd.DataFrame, dict]:
    """Distancia a pie en metros de cada coordenada de aviso a cada categoria."""
    coords = coordenadas_unicas(avisos["latitud"].to_numpy(), avisos["longitud"].to_numpy())
    salida = coords.copy()
    for categoria, grupo in puntos.groupby("categoria"):
        nodos = red.desde_varias_fuentes(grupo["latitud"].to_numpy(), grupo["longitud"].to_numpy())
        d = distancia_a_categoria(red, nodos, coords["latitud"].to_numpy(), coords["longitud"].to_numpy())
        salida[categoria] = np.where(np.isfinite(d), np.round(d), np.nan)
    calibracion = factor_rodeo(red, coords["latitud"].to_numpy(), coords["longitud"].to_numpy())
    calibracion.update(minutos_por_km=MINUTOS_POR_KM, metodo="osmnx + Dijkstra de varias fuentes",
                       nodos=int(red.n), aristas=int(red.matriz.nnz // 2))
    return salida, calibracion


def construir(entrada: Path = Path("datos/salidas/geo_enriquecido.parquet"), fecha: str | None = None) -> dict:
    fecha = fecha or fecha_hoy()
    avisos = pd.read_parquet(entrada, columns=["latitud", "longitud"]).dropna()
    puntos = pd.read_csv(mas_reciente(CARPETA_POI, "puntos_interes_*.csv"))
    red = Red.desde_osmnx(descargar_red())
    distancias, calibracion = calcular(avisos, puntos, red)
    distancias.to_csv(CARPETA_POI / f"distancias_a_pie_{fecha}.csv", index=False, encoding="utf-8")
    (CARPETA_POI / f"caminata_{fecha}.json").write_text(json.dumps(calibracion, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
    return calibracion


if __name__ == "__main__":
    print(json.dumps(construir(), ensure_ascii=False, indent=2))
