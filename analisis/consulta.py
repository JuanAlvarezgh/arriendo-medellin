"""Calculos de la pagina de consulta: una ventana para quien busca arriendo y otra
con la estadistica de cada opcion.

Todo lo que aqui se calcula usa solo herramientas de la primera mitad del curso:
distribucion empirica, CDF, cuantiles, intervalos de confianza, pruebas t, F y
de Kolmogorov-Smirnov, correlacion, ANOVA, Pareto, IQR, puntaje z y las metricas
entre densidades (Bhattacharyya, Hellinger). La regresion y el analisis espacial
del informe quedan fuera a proposito.

La pagina solo hace aritmetica sencilla sobre lo que sale de aqui: contar,
interpolar y elevar potencias. Las pruebas estadisticas se calculan en Python,
con scipy, para que esten cubiertas por pruebas automatizadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial import cKDTree

from .hedonico import tiene_amenidad

# Decreto 1469 de 2025: salario minimo mensual vigente desde el 1 de enero de 2026.
SALARIO_MINIMO = 1_750_905

TIPOS = ("apartamento", "casa", "apartaestudio")
MINIMO_BARRIO = 30   # avisos para que un barrio tenga ficha propia
MINIMO_GRUPO = 30    # avisos para ajustar una distribucion a barrio x alcobas
MINIMO_IC = 10       # avisos para dar un intervalo de confianza
RADIO_VECINOS_M = 500
MINIMO_VECINOS = 8
Z_CRITICO = 1.96     # 95 % de confianza, dos colas
UMBRAL_COLA = 0.05   # el mismo de los atipicos por CDF del analisis de distribuciones
TOLERANCIA_AREA = 0.10

# Familias candidatas para el precio. Las tres son positivas y asimetricas a la
# derecha, que es la forma del precio; las 33 del catalogo completo ya se
# compararon en el analisis de distribuciones y estas son las que quedaban arriba.
FAMILIAS = {"lognorm": stats.lognorm, "fisk": stats.fisk, "gamma": stats.gamma}

# Rejilla comun de precios en la que se evaluan las CDF ajustadas. Es logaritmica
# porque la diferencia entre 1 y 2 millones importa mas que entre 20 y 21.
REJILLA_PRECIO = np.unique(np.round(np.geomspace(500_000, 40_000_000, 90), -4))

CARACTERISTICAS = {
    "amoblado": "Amoblado",
    "parqueadero": "Parqueadero",
    "ascensor": "Ascensor",
    "piscina": "Piscina",
    "gimnasio": "Gimnasio",
    "balcon": "Balcón",
    "porteria": "Portería",
}


# ---------------------------------------------------------------------------
# Preparacion
# ---------------------------------------------------------------------------

def preparar_consulta(d: pd.DataFrame) -> pd.DataFrame:
    """Recorta a vivienda y deja las columnas que usa la pagina.

    Recibe la salida de `hedonico.preparar`, que ya quito los avisos con marcas
    de sospecha y construyo el area.
    """
    d = d[d["tipo_inmueble"].isin(TIPOS)].copy()
    d = d[d["barrio"].notna() & d["latitud"].notna() & d["longitud"].notna()]
    d["precio_m2"] = d["precio"] / d["area"]
    d["alcobas_grupo"] = d["alcobas"].clip(lower=1, upper=4).astype(int)
    amen = d["amenidades"] if "amenidades" in d.columns else pd.Series([None] * len(d), index=d.index)
    for clave in CARACTERISTICAS:
        if clave == "parqueadero":
            d["c_parqueadero"] = d["parqueaderos"] > 0
        else:
            d[f"c_{clave}"] = amen.apply(lambda v, c=clave: tiene_amenidad(v, c))
    return d.reset_index(drop=True)


def barrios_frecuentes(d: pd.DataFrame, minimo: int = MINIMO_BARRIO) -> list[str]:
    conteo = d["barrio"].value_counts()
    return sorted(conteo[conteo >= minimo].index)


# ---------------------------------------------------------------------------
# Metricas entre densidades
# ---------------------------------------------------------------------------

def coeficiente_bhattacharyya(p: np.ndarray, q: np.ndarray) -> float:
    """BC = suma sqrt(p_i q_i), con p y q ya normalizadas a suma 1."""
    return float(np.sum(np.sqrt(np.asarray(p) * np.asarray(q))))


def hellinger(p: np.ndarray, q: np.ndarray) -> float:
    """H = sqrt(1 - BC). Se recorta en cero por el redondeo de punto flotante."""
    return float(np.sqrt(max(0.0, 1.0 - coeficiente_bhattacharyya(p, q))))


def histograma_normalizado(x: np.ndarray, bordes: np.ndarray) -> np.ndarray:
    conteo, _ = np.histogram(x, bins=bordes)
    total = conteo.sum()
    return conteo / total if total else conteo.astype(float)


def bordes_freedman_diaconis(x: np.ndarray, maximo: int = 120) -> np.ndarray:
    """Ancho de bin 2 IQR / n^(1/3), la misma regla del analisis de distribuciones."""
    x = np.asarray(x, dtype=float)
    q1, q3 = np.percentile(x, [25, 75])
    ancho = 2 * (q3 - q1) / len(x) ** (1 / 3)
    if ancho <= 0:
        return np.linspace(x.min(), x.max(), 11)
    n = int(np.clip(np.ceil((x.max() - x.min()) / ancho), 5, maximo))
    return np.linspace(x.min(), x.max(), n + 1)


# ---------------------------------------------------------------------------
# Ajuste de distribuciones
# ---------------------------------------------------------------------------

@dataclass
class Ajuste:
    familia: str
    parametros: tuple
    bhattacharyya: float  # distancia, -ln(BC)

    def cdf(self, x: np.ndarray) -> np.ndarray:
        return FAMILIAS[self.familia].cdf(x, *self.parametros)


def comparar_familias(x: np.ndarray) -> dict:
    """Ajusta las familias candidatas y las compara con el histograma de los datos.

    Se fija la localizacion en cero porque el precio no puede ser negativo, y asi
    cada familia queda con dos parametros y el ajuste es estable aun con 30 datos.
    Devuelve los bins, el histograma p y, por familia, sus parametros, su
    histograma teorico q sobre los mismos bins y su distancia de Bhattacharyya:
    exactamente lo que se compara, para poder dibujarlo.
    """
    x = np.asarray(x, dtype=float)
    bordes = bordes_freedman_diaconis(x)
    p = histograma_normalizado(x, bordes)
    familias = {}
    for nombre, familia in FAMILIAS.items():
        try:
            parametros = familia.fit(x, floc=0)
        except Exception:  # noqa: BLE001 - una familia que no converge simplemente no compite
            continue
        q = np.diff(familia.cdf(bordes, *parametros))
        q = q / q.sum() if q.sum() > 0 else q
        bc = coeficiente_bhattacharyya(p, q)
        familias[nombre] = {
            "parametros": tuple(float(v) for v in parametros),
            "q": q,
            "distancia": float(-np.log(bc)) if bc > 0 else float("inf"),
        }
    if not familias:
        raise ValueError("ninguna familia convergio")
    ganadora = min(familias, key=lambda k: familias[k]["distancia"])
    return {"bordes": bordes, "p": p, "familias": familias, "ganadora": ganadora}


def ajustar(x: np.ndarray) -> Ajuste:
    """La familia de menor distancia de Bhattacharyya entre las candidatas."""
    c = comparar_familias(x)
    f = c["familias"][c["ganadora"]]
    return Ajuste(c["ganadora"], f["parametros"], f["distancia"])


def comparacion_para_dibujar(c: dict) -> dict:
    """La comparacion de familias, redondeada para empotrarla en la pagina."""
    return {
        "bordes": [round(float(v), 1) for v in c["bordes"]],
        "p": [round(float(v), 5) for v in c["p"]],
        "ganadora": c["ganadora"],
        "familias": {n: {"q": [round(float(v), 5) for v in f["q"]], "distancia": round(f["distancia"], 5)}
                     for n, f in c["familias"].items()},
    }


# ---------------------------------------------------------------------------
# Resumenes por grupo
# ---------------------------------------------------------------------------

def intervalo_media(x: np.ndarray, confianza: float = 0.95) -> tuple[float, float, int]:
    """Intervalo t de la media: x_barra +- t(alfa/2, n-1) s / sqrt(n)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    gl = n - 1
    t = stats.t.ppf(1 - (1 - confianza) / 2, gl)
    margen = t * x.std(ddof=1) / np.sqrt(n)
    return float(x.mean() - margen), float(x.mean() + margen), gl


def asimetria_pearson(x: np.ndarray) -> float:
    """Segundo coeficiente de Pearson: 3 (media - mediana) / s."""
    x = np.asarray(x, dtype=float)
    s = x.std(ddof=1)
    return float(3 * (x.mean() - np.median(x)) / s) if s > 0 else 0.0


def resumen_precios(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    q1, mediana, q3 = np.percentile(x, [25, 50, 75])
    salida = {
        "n": int(len(x)),
        "q1": float(q1),
        "mediana": float(mediana),
        "q3": float(q3),
        "media": float(x.mean()),
        "s": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
    }
    if len(x) >= MINIMO_IC:
        inf, sup, gl = intervalo_media(x)
        salida.update(ic_inf=inf, ic_sup=sup, gl=gl, t=float(stats.t.ppf(0.975, gl)))
    return salida


def grupos_precio(d: pd.DataFrame, barrios: list[str]) -> dict:
    """Resumen y CDF ajustada para cada barrio, con y sin filtro de alcobas.

    La clave es "barrio|alcobas", con alcobas en 1..4 o "todas". Un grupo con
    menos de MINIMO_GRUPO avisos no lleva CDF propia: la pagina usa la del barrio.
    """
    salida = {}
    for barrio in barrios:
        sub = d[d["barrio"] == barrio]
        llaves = [("todas", sub)] + [(str(a), sub[sub["alcobas_grupo"] == a]) for a in range(1, 5)]
        for etiqueta, grupo in llaves:
            if len(grupo) < MINIMO_IC:
                continue
            item = resumen_precios(grupo["precio"].to_numpy())
            if len(grupo) >= MINIMO_GRUPO:
                c = comparar_familias(grupo["precio"].to_numpy())
                f = c["familias"][c["ganadora"]]
                ajuste = Ajuste(c["ganadora"], f["parametros"], f["distancia"])
                item["familia"] = ajuste.familia
                item["bhattacharyya"] = ajuste.bhattacharyya
                item["cdf"] = [round(float(v), 5) for v in ajuste.cdf(REJILLA_PRECIO)]
                # La comparacion completa solo para el barrio entero: es la que
                # dibuja la grafica de mejor ajuste de la ventana de estadistica.
                if etiqueta == "todas":
                    item["comparacion"] = comparacion_para_dibujar(c)
            salida[f"{barrio}|{etiqueta}"] = item
    return salida


# ---------------------------------------------------------------------------
# Ideas de la ventana de busqueda
# ---------------------------------------------------------------------------

def percentil_empirico(muestra: np.ndarray, valor: float) -> float:
    """F_n(x) = #{x_i <= x} / n."""
    muestra = np.asarray(muestra, dtype=float)
    return float(np.mean(muestra <= valor))


def probabilidad_en_visitas(f: float, visitas: int) -> float:
    """P(al menos uno <= presupuesto en n visitas) = 1 - (1 - F)^n."""
    return float(1 - (1 - f) ** visitas)


def visitas_necesarias(f: float, probabilidad: float) -> float:
    """n = ln(1 - p) / ln(1 - F), redondeado hacia arriba. Infinito si F = 0."""
    if f <= 0:
        return float("inf")
    if f >= 1:
        return 1.0
    return float(np.ceil(np.log(1 - probabilidad) / np.log(1 - f)))


def gemelos_barrio(d: pd.DataFrame, barrios: list[str], cuantos: int = 3, bins: int = 30) -> dict:
    """Para cada barrio, los barrios con la distribucion de precio por m2 mas parecida.

    Se compara la forma completa, no solo la mediana: dos barrios con la misma
    mediana pero uno muy disperso no son gemelos.
    """
    log_m2 = np.log(d["precio_m2"])
    bordes = np.linspace(*np.percentile(log_m2, [1, 99]), bins + 1)
    hist = {b: histograma_normalizado(log_m2[d["barrio"] == b].to_numpy(), bordes) for b in barrios}
    salida = {}
    for b in barrios:
        distancias = sorted(
            ((hellinger(hist[b], hist[o]), o) for o in barrios if o != b), key=lambda t: t[0]
        )
        salida[b] = [{"barrio": o, "hellinger": round(h, 4)} for h, o in distancias[:cuantos]]
    centros = (bordes[:-1] + bordes[1:]) / 2
    return {
        "gemelos": salida,
        "centros_m2": [round(float(np.exp(c))) for c in centros],
        "histogramas": {b: [round(float(v), 5) for v in hist[b]] for b in barrios},
    }


def duelos(d: pd.DataFrame, barrios: list[str]) -> dict:
    """Pruebas entre cada par de barrios sobre el precio por m2.

    Primero la prueba F de varianzas, como pide el supuesto de varianza
    constante. Si se rechaza, la t usa varianzas separadas (Welch); si no, la
    combinada. Al lado va la KS de dos muestras, que no supone normalidad y
    compara las acumuladas completas.
    """
    muestras = {b: d.loc[d["barrio"] == b, "precio_m2"].to_numpy() for b in barrios}
    salida = {}
    for a, b in combinations(barrios, 2):
        x, y = muestras[a], muestras[b]
        prueba_f = prueba_f_varianzas(x, y)
        iguales = prueba_f["p"] >= 0.05
        t = stats.ttest_ind(x, y, equal_var=iguales)
        ks = stats.ks_2samp(x, y)
        salida[f"{a}|{b}"] = {
            "t": round(float(t.statistic), 3),
            "p_t": float(t.pvalue),
            "gl": round(float(t.df), 1),
            "varianzas_iguales": bool(iguales),
            "f": round(prueba_f["f"], 3),
            "p_f": prueba_f["p"],
            "d_ks": round(float(ks.statistic), 4),
            "p_ks": float(ks.pvalue),
        }
    return salida


def prueba_f_varianzas(x: np.ndarray, y: np.ndarray) -> dict:
    """F = s1^2 / s2^2 con la varianza mayor arriba; p de dos colas."""
    vx, vy = np.var(x, ddof=1), np.var(y, ddof=1)
    if vx >= vy:
        f, gl1, gl2 = vx / vy, len(x) - 1, len(y) - 1
    else:
        f, gl1, gl2 = vy / vx, len(y) - 1, len(x) - 1
    p = min(1.0, 2 * stats.f.sf(f, gl1, gl2))
    return {"f": float(f), "p": float(p), "gl1": int(gl1), "gl2": int(gl2)}


def pareto_oferta(d: pd.DataFrame) -> dict:
    conteo = d["barrio"].value_counts()
    acumulado = conteo.cumsum() / conteo.sum()
    barrios_80 = int((acumulado < 0.8).sum() + 1)
    return {
        "barrios": list(conteo.index),
        "avisos": [int(v) for v in conteo.to_numpy()],
        "acumulado": [round(float(v), 4) for v in acumulado.to_numpy()],
        "total_barrios": int(len(conteo)),
        "barrios_80": barrios_80,
        "fraccion_barrios_80": round(barrios_80 / len(conteo), 4),
    }


def atipicos_precio_m2(d: pd.DataFrame) -> dict:
    """Colas de la CDF ajustada contra el criterio del IQR, sobre el precio por m2."""
    x = d["precio_m2"].to_numpy()
    c = comparar_familias(x)
    ajuste = Ajuste(c["ganadora"], c["familias"][c["ganadora"]]["parametros"], c["familias"][c["ganadora"]]["distancia"])
    f = ajuste.cdf(x)
    bajo = FAMILIAS[ajuste.familia].ppf(UMBRAL_COLA, *ajuste.parametros)
    alto = FAMILIAS[ajuste.familia].ppf(1 - UMBRAL_COLA, *ajuste.parametros)
    q1, q3 = np.percentile(x, [25, 75])
    iqr = q3 - q1
    return {
        "familia": ajuste.familia,
        "parametros": ajuste.parametros,
        "bhattacharyya": ajuste.bhattacharyya,
        "corte_bajo": float(bajo),
        "corte_alto": float(alto),
        "n_bajo": int((f < UMBRAL_COLA).sum()),
        "n_alto": int((1 - f < UMBRAL_COLA).sum()),
        "q1": float(q1),
        "q3": float(q3),
        "iqr_bajo": float(q1 - 1.5 * iqr),
        "iqr_alto": float(q3 + 1.5 * iqr),
        "n_iqr_bajo": int((x < q1 - 1.5 * iqr).sum()),
        "n_iqr_alto": int((x > q3 + 1.5 * iqr).sum()),
        "minimo": float(x.min()),
        "comparacion": comparacion_para_dibujar(c),
        "cola": np.where(f < UMBRAL_COLA, -1, np.where(1 - f < UMBRAL_COLA, 1, 0)),
    }


VARIABLES_CORRELACION = {
    "area": ("Área", True),
    "banos": ("Baños", False),
    "alcobas": ("Alcobas", False),
    "parqueaderos": ("Parqueaderos", False),
    "estrato": ("Estrato", False),
}


def correlaciones(d: pd.DataFrame) -> list[dict]:
    """r de Pearson entre ln(precio) y cada atributo, con su valor p.

    Se usa el logaritmo del precio porque el precio crudo tiene una cola larga y
    unos pocos avisos de lujo dominarian el coeficiente. El area tambien va en
    logaritmo por la misma razon.
    """
    y = np.log(d["precio"])
    salida = []
    for columna, (nombre, en_log) in VARIABLES_CORRELACION.items():
        x = pd.to_numeric(d[columna], errors="coerce")
        validos = x.notna() & (x > 0 if en_log else True)
        xv = np.log(x[validos]) if en_log else x[validos]
        if xv.nunique() < 2:
            continue
        r, p = stats.pearsonr(xv, y[validos])
        salida.append({"variable": columna, "nombre": nombre, "r": round(float(r), 4),
                       "p": float(p), "n": int(validos.sum()), "en_log": en_log})
    return sorted(salida, key=lambda v: -abs(v["r"]))


FACTORES_ANOVA = {
    "barrio": "Barrio",
    "estrato": "Estrato",
    "banos_grupo": "Baños",
    "alcobas_grupo": "Alcobas",
    "tipo_inmueble": "Tipo de inmueble",
    "c_amoblado": "Amoblado",
}


def anova_un_factor(y: np.ndarray, grupos: np.ndarray) -> dict:
    """Descompone SS_total = SS_entre + SS_dentro y da F y eta cuadrado."""
    y = np.asarray(y, dtype=float)
    media = y.mean()
    ss_total = float(((y - media) ** 2).sum())
    ss_entre = 0.0
    for g in pd.unique(grupos):
        yg = y[grupos == g]
        ss_entre += len(yg) * (yg.mean() - media) ** 2
    k, n = len(pd.unique(grupos)), len(y)
    ss_dentro = ss_total - ss_entre
    gl_entre, gl_dentro = k - 1, n - k
    f = (ss_entre / gl_entre) / (ss_dentro / gl_dentro)
    return {
        "ss_entre": ss_entre, "ss_dentro": ss_dentro, "ss_total": ss_total,
        "gl_entre": gl_entre, "gl_dentro": gl_dentro, "f": float(f),
        "p": float(stats.f.sf(f, gl_entre, gl_dentro)), "eta2": ss_entre / ss_total, "k": k, "n": n,
    }


def anovas(d: pd.DataFrame, barrios: list[str]) -> list[dict]:
    d = d.copy()
    d["banos_grupo"] = d["banos"].clip(upper=5)
    y = np.log(d["precio"])
    salida = []
    for columna, nombre in FACTORES_ANOVA.items():
        base = d[d["barrio"].isin(barrios)] if columna == "barrio" else d
        validos = base[columna].notna()
        if base.loc[validos, columna].nunique() < 2:
            continue
        res = anova_un_factor(y[base.index][validos].to_numpy(), base.loc[validos, columna].to_numpy())
        res.update(factor=columna, nombre=nombre)
        salida.append(res)
    return sorted(salida, key=lambda v: -v["eta2"])


def emparejar(d: pd.DataFrame, columna: str, tolerancia: float = TOLERANCIA_AREA) -> np.ndarray:
    """Diferencias ln(precio con) - ln(precio sin) entre avisos gemelos.

    Gemelos: mismo barrio, tipo, estrato, alcobas y banos, y area a menos de
    `tolerancia` en proporcion. A cada aviso con la caracteristica se le busca el
    gemelo sin ella de area mas cercana. Un mismo aviso sin la caracteristica
    puede servir de gemelo a varios: se prefiere eso a descartar pares buenos.
    """
    claves = ["barrio", "tipo_inmueble", "estrato", "alcobas", "banos"]
    diferencias = []
    for _, grupo in d.groupby(claves, sort=False):
        con = grupo[grupo[columna]]
        sin = grupo[~grupo[columna]]
        if con.empty or sin.empty:
            continue
        area_sin = sin["area"].to_numpy()
        precio_sin = sin["precio"].to_numpy()
        for area, precio in zip(con["area"].to_numpy(), con["precio"].to_numpy()):
            relativa = np.abs(area_sin - area) / area
            j = int(np.argmin(relativa))
            if relativa[j] <= tolerancia:
                diferencias.append(np.log(precio) - np.log(precio_sin[j]))
    return np.asarray(diferencias)


def prueba_pareada(diferencias: np.ndarray) -> dict:
    """t = d_barra / (s_d / sqrt(n)), con su intervalo, y el efecto en porcentaje."""
    n = len(diferencias)
    media = float(diferencias.mean())
    s = float(diferencias.std(ddof=1))
    t = media / (s / np.sqrt(n))
    inf, sup, gl = intervalo_media(diferencias)
    return {
        "n": n, "media": media, "s": s, "t": float(t), "gl": gl,
        "p": float(2 * stats.t.sf(abs(t), gl)),
        "ic_inf": inf, "ic_sup": sup,
        "efecto": float(np.exp(media) - 1),
        "efecto_inf": float(np.exp(inf) - 1),
        "efecto_sup": float(np.exp(sup) - 1),
    }


def gemelos_caracteristicas(d: pd.DataFrame, minimo_pares: int = 30) -> list[dict]:
    salida = []
    for clave, nombre in CARACTERISTICAS.items():
        diferencias = emparejar(d, f"c_{clave}")
        if len(diferencias) < minimo_pares:
            continue
        res = prueba_pareada(diferencias)
        res.update(clave=clave, nombre=nombre)
        salida.append(res)
    return sorted(salida, key=lambda v: -v["efecto"])


def z_local(d: pd.DataFrame, radio_m: float = RADIO_VECINOS_M,
            minimo: int = MINIMO_VECINOS) -> tuple[np.ndarray, np.ndarray]:
    """Puntaje z de cada aviso frente a sus vecinos a menos de `radio_m` metros.

    z_i = (x_i - media de vecinos) / s de vecinos, sin contar al propio aviso.
    Es la primera ley de Tobler hecha comparacion: lo caro se mide contra lo que
    esta cerca. Se calcula sobre ln(precio/m2) porque el corte de 1,96 supone
    normalidad, y el logaritmo se acerca a ella; sobre el precio crudo la cola
    derecha produce muchos mas "caros" que "gangas" solo por la asimetria.
    Devuelve z y el numero de vecinos; si hay menos de `minimo`, z queda en NaN.
    """
    lat0 = np.radians(d["latitud"].mean())
    xy = np.column_stack([
        d["longitud"].to_numpy() * 111_320 * np.cos(lat0),
        d["latitud"].to_numpy() * 110_540,
    ])
    arbol = cKDTree(xy)
    valores = np.log(d["precio_m2"].to_numpy())
    z = np.full(len(d), np.nan)
    vecinos = np.zeros(len(d), dtype=int)
    for i, idx in enumerate(arbol.query_ball_point(xy, r=radio_m)):
        otros = [j for j in idx if j != i]
        vecinos[i] = len(otros)
        if len(otros) < minimo:
            continue
        v = valores[otros]
        s = v.std(ddof=1)
        if s > 0:
            z[i] = (valores[i] - v.mean()) / s
    return z, vecinos


def variabilidad(d: pd.DataFrame, barrios: list[str]) -> dict:
    """Coeficiente de variacion por barrio y prueba F de varianzas entre estratos."""
    por_barrio = []
    for b in barrios:
        x = d.loc[d["barrio"] == b, "precio_m2"].to_numpy()
        por_barrio.append({"barrio": b, "cv": float(x.std(ddof=1) / x.mean()), "n": len(x),
                           "s": float(x.std(ddof=1)), "media": float(x.mean())})
    por_barrio.sort(key=lambda v: v["cv"])

    # Sobre el logaritmo: la prueba F supone normalidad, y ln(precio/m2) se
    # acerca mucho mas a ella que el precio crudo.
    estratos = []
    for e in sorted(d["estrato"].dropna().unique()):
        x = np.log(d.loc[d["estrato"] == e, "precio_m2"].to_numpy())
        if len(x) >= MINIMO_IC:
            estratos.append({"estrato": int(e), "n": len(x), "varianza": float(x.var(ddof=1))})
    comparaciones = []
    for a, b in zip(estratos, estratos[1:]):
        xa = np.log(d.loc[d["estrato"] == a["estrato"], "precio_m2"].to_numpy())
        xb = np.log(d.loc[d["estrato"] == b["estrato"], "precio_m2"].to_numpy())
        res = prueba_f_varianzas(xa, xb)
        res.update(a=a["estrato"], b=b["estrato"])
        comparaciones.append(res)
    return {"barrios": por_barrio, "estratos": estratos, "comparaciones": comparaciones}


def estrato_declarado(d: pd.DataFrame) -> dict:
    """Precio por m2 de quien declara su estrato real contra quien declara uno mayor.

    Se compara dentro de un mismo estrato del censo, para que la diferencia no
    sea solo que las manzanas de estrato alto son mas caras.
    """
    con_censo = d[d["estrato_censo"].notna()]
    resumen = {
        "n": int(len(con_censo)),
        "pct_mayor": float((con_censo["estrato"] > con_censo["estrato_censo"]).mean()),
        "pct_menor": float((con_censo["estrato"] < con_censo["estrato_censo"]).mean()),
    }
    salida = []
    for e in range(1, 6):
        base = d[d["estrato_censo"] == e]
        igual = base.loc[base["estrato"] == e, "precio_m2"].to_numpy()
        mayor = base.loc[base["estrato"] > e, "precio_m2"].to_numpy()
        if len(igual) < MINIMO_IC or len(mayor) < MINIMO_IC:
            continue
        t = stats.ttest_ind(np.log(mayor), np.log(igual), equal_var=False)
        salida.append({
            "estrato_censo": e, "n_igual": len(igual), "n_mayor": len(mayor),
            "mediana_igual": float(np.median(igual)), "mediana_mayor": float(np.median(mayor)),
            "diferencia": float(np.median(mayor) / np.median(igual) - 1),
            "t": float(t.statistic), "gl": float(t.df), "p": float(t.pvalue),
        })
    resumen["comparaciones"] = salida
    return resumen


def normalidad_logaritmo(d: pd.DataFrame) -> dict:
    """Distancia de Bhattacharyya del precio y de ln(precio) a una normal ajustada."""
    salida = {}
    for nombre, x in (("precio", d["precio"].to_numpy()), ("log_precio", np.log(d["precio"].to_numpy()))):
        recorte = x[(x >= np.percentile(x, 0.5)) & (x <= np.percentile(x, 99.5))]
        bordes = bordes_freedman_diaconis(recorte, maximo=60)
        p = histograma_normalizado(recorte, bordes)
        mu, s = x.mean(), x.std(ddof=1)
        q = np.diff(stats.norm.cdf(bordes, mu, s))
        q = q / q.sum()
        bc = coeficiente_bhattacharyya(p, q)
        salida[nombre] = {
            "bordes": [float(v) for v in bordes],
            "empirica": [round(float(v), 5) for v in p],
            "normal": [round(float(v), 5) for v in q],
            "media": float(mu), "mediana": float(np.median(x)), "s": float(s),
            "bhattacharyya": float(-np.log(bc)),
        }
    return salida


def poligonos_estrato(d: pd.DataFrame, bins: int = 36) -> dict:
    """Poligonos de frecuencia de ln(precio/m2) por estrato, para las crestas."""
    log_m2 = np.log(d["precio_m2"])
    bordes = np.linspace(*np.percentile(log_m2, [0.5, 99.5]), bins + 1)
    centros = (bordes[:-1] + bordes[1:]) / 2
    salida = {"centros_m2": [round(float(np.exp(c))) for c in centros], "estratos": []}
    for e in sorted(d["estrato"].dropna().unique()):
        x = log_m2[d["estrato"] == e].to_numpy()
        if len(x) < MINIMO_IC:
            continue
        salida["estratos"].append({
            "estrato": int(e), "n": len(x),
            "frecuencia": [round(float(v), 5) for v in histograma_normalizado(x, bordes)],
            "mediana_m2": float(np.exp(np.median(x))),
        })
    return salida


# ---------------------------------------------------------------------------
# Ensamble
# ---------------------------------------------------------------------------

def construir(d: pd.DataFrame) -> dict:
    """Arma todo lo que la pagina necesita a partir de los avisos preparados."""
    barrios = barrios_frecuentes(d)
    z, vecinos = z_local(d)
    atip = atipicos_precio_m2(d)
    cola = atip.pop("cola")
    gem = gemelos_barrio(d, barrios)

    fichas = {}
    for b in barrios:
        sub = d[d["barrio"] == b]
        zb = z[sub.index]
        zb = zb[~np.isnan(zb)]
        fichas[b] = {
            "lat": float(sub["latitud"].median()),
            "lng": float(sub["longitud"].median()),
            "mediana_m2": float(sub["precio_m2"].median()),
            "media_m2": float(sub["precio_m2"].mean()),
            "asimetria": asimetria_pearson(sub["precio"].to_numpy()),
            "media_precio": float(sub["precio"].mean()),
            "mediana_precio": float(sub["precio"].median()),
            "pct_ganga": float((zb <= -Z_CRITICO).mean()) if len(zb) else None,
            "pct_caro": float((zb >= Z_CRITICO).mean()) if len(zb) else None,
            "pct_amoblado": float(sub["c_amoblado"].mean()),
            "estrato_moda": int(sub["estrato"].mode().iloc[0]),
        }

    indice_barrio = {b: i for i, b in enumerate(barrios)}
    avisos = {
        "lat": [round(float(v), 6) for v in d["latitud"]],
        "lng": [round(float(v), 6) for v in d["longitud"]],
        "precio": [int(v) for v in d["precio"]],
        "area": [round(float(v), 1) for v in d["area"]],
        "alcobas": [int(v) for v in d["alcobas_grupo"]],
        "estrato": [None if pd.isna(v) else int(v) for v in d["estrato"]],
        "barrio": [indice_barrio.get(b, -1) for b in d["barrio"]],
        "nombre_barrio": list(d["barrio"]),
        "z": [None if np.isnan(v) else round(float(v), 2) for v in z],
        "vecinos": [int(v) for v in vecinos],
        "cola": [int(v) for v in cola],
        "url": list(d["url"]),
    }

    return {
        "meta": {
            "n": int(len(d)),
            "n_barrios_total": int(d["barrio"].nunique()),
            "salario_minimo": SALARIO_MINIMO,
            "minimo_barrio": MINIMO_BARRIO,
            "minimo_grupo": MINIMO_GRUPO,
            "radio_vecinos_m": RADIO_VECINOS_M,
            "minimo_vecinos": MINIMO_VECINOS,
            "z_critico": Z_CRITICO,
            "umbral_cola": UMBRAL_COLA,
            "tolerancia_area": TOLERANCIA_AREA,
            "captura": str(pd.to_datetime(d["capturado_en"]).max().date()),
            "mediana_ciudad": float(d["precio"].median()),
            "mediana_m2_ciudad": float(d["precio_m2"].median()),
        },
        "barrios": barrios,
        "fichas": fichas,
        "rejilla": [float(v) for v in REJILLA_PRECIO],
        "grupos": grupos_precio(d, barrios),
        "gemelos": gem,
        "duelos": duelos(d, barrios),
        "pareto": pareto_oferta(d),
        "atipicos": atip,
        "correlaciones": correlaciones(d),
        "anovas": anovas(d, barrios),
        "caracteristicas": gemelos_caracteristicas(d),
        "variabilidad": variabilidad(d, barrios),
        "estrato_declarado": estrato_declarado(d),
        "normalidad": normalidad_logaritmo(d),
        "crestas": poligonos_estrato(d),
        "z_local": {
            "n_con_z": int((~np.isnan(z)).sum()),
            "n_ganga": int((z <= -Z_CRITICO).sum()),
            "n_caro": int((z >= Z_CRITICO).sum()),
        },
        "avisos": avisos,
    }
