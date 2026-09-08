"""Modelo hedonico de precios y diagnostico espacial.

El hedonico descompone el precio en lo que es atributo del inmueble y lo que es
ubicacion. El residual por barrio mide el sobreprecio que los atributos no
explican, y es el mapa de donde cuesta la ubicacion en si misma.

El diagnostico espacial es el paso que decide si el minimo cuadrado ordinario
sirve: si sus residuales estan autocorrelacionados en el espacio, el modelo
esta mal especificado y sus errores estandar son invalidos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

VENTANA_DIAS = 90
MINIMO_POR_BARRIO = 8

ORDEN_BANDA = {
    "menor_a_1": 0,
    "1_a_8": 1,
    "9_a_15": 2,
    "16_a_30": 3,
    "mayor_a_30": 4,
}

AMENIDADES_MODELO = [
    "ascensor",
    "porteria",
    "gimnasio",
    "piscina",
    "balcon",
    "amoblado",
    "zonas_verdes",
]


@dataclass
class ResultadoHedonico:
    modelo: Any
    datos: pd.DataFrame
    formula: str
    n: int
    r2: float
    r2_ajustado: float
    efectos_barrio: pd.DataFrame = field(default_factory=pd.DataFrame)

    def resumen_coeficientes(self) -> pd.DataFrame:
        m = self.modelo
        tabla = pd.DataFrame(
            {
                "coeficiente": m.params,
                "error_estandar": m.bse,
                "t": m.tvalues,
                "p": m.pvalues,
            }
        )
        # La interpretacion depende de si el regresor entra en logaritmo.
        # Para un regresor en nivel, exp(b)-1 es el cambio porcentual del precio.
        # Para uno en logaritmo la relacion es log-log y el coeficiente ya es la
        # elasticidad: aplicar exp(b)-1 ahi seria un error de lectura.
        es_log = tabla.index.str.startswith("log_")
        tabla["tipo"] = np.where(es_log, "elasticidad", "efecto_pct")
        tabla["interpretacion"] = np.where(
            es_log,
            tabla["coeficiente"],
            (np.exp(tabla["coeficiente"]) - 1) * 100,
        )
        return tabla


def sin_marcas(valor: Any) -> bool:
    """True si el aviso no lleva ninguna marca de sospecha.

    El campo llega como lista desde el jsonl, pero como array de numpy tras
    pasar por parquet, y ahi la verdad de un array vacio es ambigua. Se mide
    por longitud, que funciona con ambos.
    """
    if valor is None:
        return True
    if isinstance(valor, float) and pd.isna(valor):
        return True
    try:
        return len(valor) == 0
    except TypeError:
        return not bool(valor)


def tiene_amenidad(valor: Any, nombre: str) -> bool:
    """True si el aviso declara esa amenidad, venga como lista o como cadena.

    Las amenidades viajan de dos formas distintas segun por donde pasen: lista
    desde el jsonl y desde la base, y cadena unida por barras verticales en los
    exportados planos, que es lo que lee el analisis. La comprobacion ingenua
    `"amoblado" in list(valor)` funciona con la lista y falla en silencio con la
    cadena, porque `list("a|b")` son caracteres sueltos: no lanza error, solo
    devuelve False siempre. Ese fallo mudo dejo el porcentaje de amoblados en
    cero en el mapa y en el tablero durante varias versiones.

    Se parte por la barra en vez de buscar la subcadena porque una amenidad
    puede ser prefijo de otra, y ahi la subcadena daria un falso positivo.
    """
    if valor is None:
        return False
    if isinstance(valor, str):
        return nombre in valor.split("|")
    try:
        return nombre in list(valor)
    except TypeError:
        return False


def preparar(geo: pd.DataFrame, ventana_dias: int | None = VENTANA_DIAS) -> pd.DataFrame:
    """Filtra y construye las variables del modelo.

    La ventana temporal es deliberada: los avisos antiguos que siguen activos
    son los que nadie tomo, tipicamente por estar sobrevalorados, y arrastran
    el modelo hacia arriba.
    """
    d = geo.copy()

    d = d[d["operacion"] == "arriendo"] if "operacion" in d.columns else d
    d = d[d["precio"].notna()]
    d["area"] = d["area_privada"].fillna(d.get("area_construida"))
    d = d[d["area"].notna() & (d["area"] > 0)]

    if "sospechoso" in d.columns:
        d = d[d["sospechoso"].apply(sin_marcas)]

    if ventana_dias and "creado_en" in d.columns:
        creado = pd.to_datetime(d["creado_en"], errors="coerce")
        capturado = pd.to_datetime(d["capturado_en"], errors="coerce", utc=True)
        antiguedad = (capturado.dt.tz_localize(None) - creado).dt.days
        d["dias_en_mercado"] = antiguedad
        d = d[antiguedad.notna() & (antiguedad <= ventana_dias)]

    d["log_precio"] = np.log(d["precio"])
    d["log_area"] = np.log(d["area"])

    d["alcobas"] = pd.to_numeric(d["alcobas"], errors="coerce").fillna(0)
    d["banos"] = pd.to_numeric(d["banos"], errors="coerce").fillna(0)
    d["parqueaderos"] = pd.to_numeric(d["parqueaderos"], errors="coerce").fillna(0)
    d["estrato"] = pd.to_numeric(d["estrato"], errors="coerce")

    d["antiguedad_ord"] = d["banda_antiguedad"].map(ORDEN_BANDA)
    d["antiguedad_ord"] = d["antiguedad_ord"].fillna(d["antiguedad_ord"].median())

    # El piso solo esta en cerca de la mitad de los avisos. Se modela con un
    # indicador de disponibilidad para no perder la mitad de la muestra.
    d["piso_num"] = pd.to_numeric(d["piso"], errors="coerce")
    d["piso_conocido"] = d["piso_num"].notna().astype(int)
    d["piso_valor"] = d["piso_num"].fillna(0)

    amen = d["amenidades"] if "amenidades" in d.columns else pd.Series([[]] * len(d), index=d.index)
    for a in AMENIDADES_MODELO:
        d[f"am_{a}"] = amen.apply(lambda v, a=a: int(tiene_amenidad(v, a)))

    d = d[d["estrato"].notna()]

    if "barrio" in d.columns:
        conteo = d["barrio"].value_counts()
        frecuentes = conteo[conteo >= MINIMO_POR_BARRIO].index
        d["barrio_modelo"] = d["barrio"].where(d["barrio"].isin(frecuentes), "otros")

    return d


def formula(datos: pd.DataFrame, con_barrio: bool = True) -> str:
    terminos = [
        "log_area",
        "alcobas",
        "banos",
        "parqueaderos",
        "C(estrato)",
        "antiguedad_ord",
        "piso_conocido",
        "piso_valor",
    ]
    terminos += [f"am_{a}" for a in AMENIDADES_MODELO if f"am_{a}" in datos.columns]
    if con_barrio and "barrio_modelo" in datos.columns and datos["barrio_modelo"].nunique() > 1:
        terminos.append("C(barrio_modelo)")
    return "log_precio ~ " + " + ".join(terminos)


def estimar(datos: pd.DataFrame, con_barrio: bool = True) -> ResultadoHedonico:
    f = formula(datos, con_barrio=con_barrio)
    modelo = smf.ols(f, data=datos).fit(cov_type="HC3")

    efectos = pd.DataFrame()
    if con_barrio and "barrio_modelo" in datos.columns:
        filas = []
        for nombre, coef in modelo.params.items():
            if nombre.startswith("C(barrio_modelo)"):
                barrio = nombre.split("[T.")[-1].rstrip("]")
                filas.append(
                    {
                        "barrio": barrio,
                        "efecto_log": coef,
                        "sobreprecio_pct": (np.exp(coef) - 1) * 100,
                        "p": modelo.pvalues[nombre],
                    }
                )
        efectos = pd.DataFrame(filas).sort_values("sobreprecio_pct", ascending=False)

    return ResultadoHedonico(
        modelo=modelo,
        datos=datos,
        formula=f,
        n=int(modelo.nobs),
        r2=float(modelo.rsquared),
        r2_ajustado=float(modelo.rsquared_adj),
        efectos_barrio=efectos,
    )


def residuales_por_zona(
    resultado: ResultadoHedonico, columna: str = "barrio", minimo: int = 5
) -> pd.DataFrame:
    """Sobreprecio por zona: lo que los atributos del inmueble no explican.

    Se estima a proposito un modelo SIN efectos fijos de barrio. Con el barrio
    dentro del modelo, el residual medio de cada barrio es cero por
    construccion, porque el efecto fijo absorbe justamente esa media, y el
    mapa resultante no diria nada. Quitando el barrio, el residual recoge todo
    lo que la ubicacion aporta al precio.
    """
    sin_barrio = estimar(resultado.datos, con_barrio=False)
    d = sin_barrio.datos.copy()
    d["residual"] = sin_barrio.modelo.resid
    d["precio_m2"] = d["precio"] / d["area"]

    r = (
        d.groupby(columna)
        .agg(
            avisos=("residual", "size"),
            residual_medio=("residual", "mean"),
            residual_ee=("residual", lambda s: s.std(ddof=1) / max(np.sqrt(len(s)), 1)),
            precio_m2_mediano=("precio_m2", "median"),
        )
        .reset_index()
    )
    r["sobreprecio_pct"] = (np.exp(r["residual_medio"]) - 1) * 100
    r = r[r["avisos"] >= minimo]
    return r.sort_values("sobreprecio_pct", ascending=False)


# --- diagnostico espacial ---


@dataclass
class DiagnosticoEspacial:
    moran_i: float
    moran_p: float
    n: int
    vecinos_medios: float
    lm_error_p: float | None = None
    lm_lag_p: float | None = None
    recomendacion: str = ""


def matriz_pesos(datos: pd.DataFrame, k: int = 8):
    """Matriz de vecindad por los k vecinos mas cercanos."""
    from libpysal.weights import KNN

    coords = np.column_stack([datos["longitud"].values, datos["latitud"].values])
    w = KNN.from_array(coords, k=k)
    w.transform = "r"
    return w


def diagnosticar(resultado: ResultadoHedonico, k: int = 8) -> DiagnosticoEspacial:
    """Comprueba si los residuales del OLS estan correlacionados en el espacio.

    Si lo estan, el modelo omite algo que se distribuye geograficamente y el
    OLS deja de ser fiable: hay que pasar a un modelo espacial.
    """
    from esda.moran import Moran

    d = resultado.datos
    w = matriz_pesos(d, k=k)
    residuales = np.asarray(resultado.modelo.resid)

    moran = Moran(residuales, w)

    diag = DiagnosticoEspacial(
        moran_i=float(moran.I),
        moran_p=float(moran.p_sim),
        n=len(d),
        vecinos_medios=float(w.mean_neighbors),
    )

    try:
        from spreg import OLS

        y = residuales.reshape(-1, 1) * 0 + np.asarray(d["log_precio"]).reshape(-1, 1)
        columnas = ["log_area", "alcobas", "banos", "parqueaderos", "antiguedad_ord"]
        X = d[columnas].astype(float).values
        ols = OLS(y, X, w=w, spat_diag=True, name_y="log_precio", name_x=columnas)
        diag.lm_error_p = float(ols.lm_error[1])
        diag.lm_lag_p = float(ols.lm_lag[1])
    except Exception:
        pass

    if diag.moran_p < 0.05:
        if diag.lm_lag_p is not None and diag.lm_error_p is not None:
            if diag.lm_lag_p < diag.lm_error_p:
                diag.recomendacion = "modelo de rezago espacial"
            else:
                diag.recomendacion = "modelo de error espacial"
        else:
            diag.recomendacion = "modelo espacial (rezago o error)"
    else:
        diag.recomendacion = "el minimo cuadrado ordinario es suficiente"

    return diag


def estimar_espacial(resultado: ResultadoHedonico, tipo: str = "error", k: int = 8):
    """Estima el modelo espacial que corresponda segun el diagnostico."""
    from spreg import GM_Error_Het, GM_Lag

    d = resultado.datos
    w = matriz_pesos(d, k=k)

    columnas = ["log_area", "alcobas", "banos", "parqueaderos", "antiguedad_ord", "piso_conocido"]
    columnas += [f"am_{a}" for a in AMENIDADES_MODELO if f"am_{a}" in d.columns]
    columnas = [c for c in columnas if d[c].std() > 0]

    y = np.asarray(d["log_precio"]).reshape(-1, 1)
    X = d[columnas].astype(float).values

    if tipo == "rezago":
        return GM_Lag(y, X, w=w, name_y="log_precio", name_x=columnas)
    return GM_Error_Het(y, X, w=w, name_y="log_precio", name_x=columnas)


def resumen_espacial(modelo: Any) -> pd.DataFrame:
    """Tabla legible de un modelo de spreg.

    `name_x` ya incluye la constante al principio y lambda al final, asi que no
    hay que anadir rotulos a mano: hacerlo corre todas las etiquetas una
    posicion y hace ilegible el modelo. Lambda no es un efecto sobre el precio,
    de modo que no se le aplica la transformacion porcentual.
    """
    betas = np.asarray(modelo.betas).ravel()
    nombres = list(modelo.name_x)
    errores = np.sqrt(np.diag(modelo.vm))

    filas = []
    for nombre, b, e in zip(nombres, betas, errores):
        if nombre.startswith("log_"):
            tipo, valor = "elasticidad", b
        elif nombre in ("CONSTANT", "lambda", "W_dep_var"):
            tipo, valor = "parametro", b
        else:
            tipo, valor = "efecto_pct", (np.exp(b) - 1) * 100
        filas.append(
            {
                "variable": nombre,
                "coeficiente": b,
                "error_estandar": e,
                "z": b / e if e else np.nan,
                "tipo": tipo,
                "interpretacion": valor,
            }
        )
    return pd.DataFrame(filas)


def lisa(datos: pd.DataFrame, columna: str = "precio_m2", k: int = 8) -> pd.DataFrame:
    """Conglomerados locales: donde se agrupan precios altos rodeados de altos."""
    from esda.moran import Moran_Local

    d = datos.copy()
    if columna not in d.columns:
        d[columna] = d["precio"] / d["area"]
    d = d[d[columna].notna()]

    w = matriz_pesos(d, k=k)
    valores = np.asarray(d[columna], dtype=float)
    local = Moran_Local(valores, w)

    etiquetas = {1: "alto-alto", 2: "bajo-alto", 3: "bajo-bajo", 4: "alto-bajo"}
    d["lisa_q"] = local.q
    d["lisa_p"] = local.p_sim
    d["conglomerado"] = [
        etiquetas.get(q, "otro") if p < 0.05 else "no significativo"
        for q, p in zip(local.q, local.p_sim)
    ]
    return d
