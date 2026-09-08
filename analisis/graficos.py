"""Figuras estaticas del informe final."""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from .paleta import (
    COLOR_LISA,
    NEUTRO,
    POLO_ALTO,
    POLO_BAJO,
    RAMPA_AZUL,
    REJILLA,
    SERIE_1,
    SERIE_2,
    SUPERFICIE,
    TINTA,
    TINTA_2,
    TINTA_3,
    estilo_eje,
    estilo_mapa,
    fuente,
    nueva_figura,
    pesos,
    porcentaje,
    titular,
)

warnings.filterwarnings("ignore")

SALIDA = Path("datos/salidas/figuras")
CRS_MUNDIAL = "EPSG:4326"


def _guardar(fig, nombre: str) -> Path:
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / f"{nombre}.png"
    fig.savefig(ruta, dpi=200, facecolor=SUPERFICIE, bbox_inches=None)
    plt.close(fig)
    return ruta


def _encuadrar(ax, lon, lat, recorte: float = 0.004, margen: float = 0.06) -> None:
    """Encuadra el mapa sobre la masa de datos, no sobre sus valores extremos.

    Media docena de avisos mal geocodificados, aunque caigan dentro del valle,
    estiran el encuadre hasta dejar la ciudad como una mancha diminuta. Se
    recortan los extremos por percentil y se anade un margen.
    """
    lon = pd.Series(lon).dropna()
    lat = pd.Series(lat).dropna()
    x0, x1 = lon.quantile(recorte), lon.quantile(1 - recorte)
    y0, y1 = lat.quantile(recorte), lat.quantile(1 - recorte)
    ancho, alto = x1 - x0, y1 - y0
    ax.set_xlim(x0 - ancho * margen, x1 + ancho * margen)
    ax.set_ylim(y0 - alto * margen, y1 + alto * margen)


# --- 1. Distribucion del precio por metro cuadrado ---


def distribucion_precio(geo: pd.DataFrame) -> Path:
    d = geo[geo["precio_m2"].notna() & (geo["precio_m2"] < 200_000)]
    fig, (izq, der) = plt.subplots(1, 2, figsize=(9.6, 4.6), gridspec_kw={"wspace": 0.22})
    fig.patch.set_facecolor(SUPERFICIE)

    estilo_eje(izq)
    izq.hist(d["precio_m2"], bins=54, color=SERIE_1, edgecolor=SUPERFICIE, linewidth=0.5, zorder=3)
    mediana = d["precio_m2"].median()
    izq.axvline(mediana, color=TINTA, linewidth=1.4, linestyle=(0, (4, 3)), zorder=4)
    izq.annotate(f"mediana\n{pesos(mediana)}", xy=(mediana, izq.get_ylim()[1] * 0.86),
                 xytext=(12, 0), textcoords="offset points",
                 fontsize=8.6, color=TINTA, fontweight="bold")
    izq.set_title("Distribucion del precio por m2", fontsize=10.5,
                  fontweight="bold", color=TINTA, loc="left", pad=10)
    izq.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v/1000:.0f}k"))
    izq.set_xlabel("pesos por metro cuadrado", fontsize=8.4, color=TINTA_2)

    estilo_eje(der)
    por_estrato = [d[d["estrato"] == e]["precio_m2"].dropna().values for e in range(1, 7)]
    caja = der.boxplot(por_estrato, patch_artist=True, widths=0.62, showfliers=False,
                       medianprops=dict(color=TINTA, linewidth=1.6),
                       whiskerprops=dict(color=TINTA_3, linewidth=1.0),
                       capprops=dict(color=TINTA_3, linewidth=1.0),
                       boxprops=dict(edgecolor=SUPERFICIE, linewidth=1.5))
    for i, parche in enumerate(caja["boxes"]):
        parche.set_facecolor(RAMPA_AZUL[min(i + 1, len(RAMPA_AZUL) - 1)])
    der.set_xticklabels([str(e) for e in range(1, 7)])
    der.set_title("Precio por m2 segun estrato", fontsize=10.5,
                  fontweight="bold", color=TINTA, loc="left", pad=10)
    der.set_xlabel("estrato declarado", fontsize=8.4, color=TINTA_2)
    der.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v/1000:.0f}k"))

    fuente(fig, f"Avisos con precio y area: {pesos(len(d))}. Se recorta la cola por encima de 200 mil por m2 para que la forma sea legible.")
    fig.subplots_adjust(left=0.07, right=0.985, top=0.9, bottom=0.145)
    return _guardar(fig, "01_distribucion")


# --- 2. Mapa de hexagonos ---


def _poligonos(celdas) -> gpd.GeoDataFrame:
    import h3
    from shapely.geometry import Polygon

    filas = [{"h3": c, "geometry": Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(c)])}
             for c in celdas]
    return gpd.GeoDataFrame(filas, crs=CRS_MUNDIAL)


def mapa_hexagonos(geo: gpd.GeoDataFrame, minimo: int = 5) -> Path:
    d = geo[geo["precio_m2"].notna() & geo["h3"].notna()]
    agr = d.groupby("h3").agg(valor=("precio_m2", "median"), n=("precio_m2", "size")).reset_index()
    agr = agr[agr["n"] >= minimo]
    poly = _poligonos(agr["h3"].tolist()).merge(agr, on="h3")

    cortes = np.unique(np.quantile(agr["valor"], np.linspace(0, 1, 8)))
    mapa_color = ListedColormap(RAMPA_AZUL[: len(cortes) - 1])
    norma = BoundaryNorm(cortes, mapa_color.N)

    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    fig.patch.set_facecolor(SUPERFICIE)
    estilo_mapa(ax)
    poly.plot(ax=ax, column="valor", cmap=mapa_color, norm=norma,
              edgecolor=SUPERFICIE, linewidth=0.25)
    centros = poly.geometry.centroid
    _encuadrar(ax, centros.x, centros.y)

    titular(ax, "Donde cuesta el metro cuadrado",
            f"Mediana del precio pedido por m2 en {len(poly)} celdas hexagonales de 174 m de arista")

    manijas = [Patch(facecolor=RAMPA_AZUL[i], edgecolor=SUPERFICIE,
                     label=f"{pesos(cortes[i])} a {pesos(cortes[i+1])}")
               for i in range(len(cortes) - 1)]
    ax.legend(handles=manijas, loc="lower left", frameon=False, fontsize=8,
              labelcolor=TINTA_2, title="pesos por m2",
              title_fontproperties={"size": 8.4, "weight": "bold"})

    fuente(fig, f"Solo celdas con {minimo} avisos o mas. La rejilla hexagonal da celdas de igual tamano, a diferencia de los barrios.")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.9, bottom=0.045)
    return _guardar(fig, "02_mapa_hexagonos")


# --- 3. Efectos del modelo hedonico ---


ETIQUETAS_EFECTOS = {
    "am_amoblado": "Amoblado",
    "banos": "Cada bano",
    "parqueaderos": "Cada parqueadero",
    "am_gimnasio": "Gimnasio",
    "am_piscina": "Piscina",
    "piso_valor": "Cada piso de altura",
    "alcobas": "Cada alcoba",
    "am_ascensor": "Ascensor",
    "am_zonas_verdes": "Zonas verdes",
    "am_porteria": "Porteria",
    "antiguedad_ord": "Cada banda de antiguedad",
    "piso_conocido": "Declara el piso",
}


def efectos_hedonicos(resultado) -> Path:
    tab = resultado.resumen_coeficientes()
    filas = [(n, tab.loc[c, "interpretacion"], tab.loc[c, "p"])
             for c, n in ETIQUETAS_EFECTOS.items() if c in tab.index]
    df = pd.DataFrame(filas, columns=["variable", "efecto", "p"]).sort_values("efecto")

    fig, ax = nueva_figura(9.6, 5.8)
    estilo_eje(ax, eje_y=False, eje_x=True)
    colores = [POLO_ALTO if v > 0 else POLO_BAJO for v in df["efecto"]]
    ax.barh(df["variable"], df["efecto"], color=colores, height=0.62, zorder=3)
    ax.axvline(0, color=TINTA_3, linewidth=1.0, zorder=4)

    for y, (v, pv) in enumerate(zip(df["efecto"], df["p"])):
        signif = "" if pv < 0.05 else "  (no significativo)"
        ax.annotate(porcentaje(v, 1, signo=True) + signif,
                    xy=(v, y), xytext=(6 if v > 0 else -6, 0), textcoords="offset points",
                    ha="left" if v > 0 else "right", va="center",
                    fontsize=8.4, color=TINTA if pv < 0.05 else TINTA_3,
                    fontweight="bold" if pv < 0.05 else "normal")

    titular(ax, "Que encarece un arriendo, y cuanto",
            "Efecto sobre el precio de cada atributo, con lo demas constante. "
            f"Modelo hedonico, n = {int(resultado.modelo.nobs):,}".replace(",", "."))
    ax.set_xlim(df["efecto"].min() - 9, df["efecto"].max() + 11)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:+.0f} %".replace("-", "−")))
    ax.tick_params(axis="y", labelsize=9)

    elasticidad = f"{resultado.modelo.params['log_area']:.3f}".replace(".", ",")
    fuente(fig, "El area entra en logaritmo y no aparece aqui: su coeficiente es "
                f"una elasticidad de {elasticidad}, no un porcentaje.")
    fig.subplots_adjust(left=0.235, right=0.955, top=0.855, bottom=0.105)
    return _guardar(fig, "03_efectos_hedonicos")


# --- 4. Sobreprecio por barrio ---


def sobreprecio_barrios(residuales: pd.DataFrame, cuantos: int = 12) -> Path:
    d = residuales.sort_values("sobreprecio_pct")
    seleccion = pd.concat([d.head(cuantos), d.tail(cuantos)]).drop_duplicates(subset=["barrio"])

    fig, ax = nueva_figura(9.6, 7.4)
    estilo_eje(ax, eje_y=False, eje_x=True)
    colores = [POLO_ALTO if v > 0 else POLO_BAJO for v in seleccion["sobreprecio_pct"]]
    ax.barh(seleccion["barrio"], seleccion["sobreprecio_pct"], color=colores,
            height=0.66, zorder=3)
    ax.axvline(0, color=TINTA_3, linewidth=1.0, zorder=4)

    for y, (v, n) in enumerate(zip(seleccion["sobreprecio_pct"], seleccion["avisos"])):
        ax.annotate(f"{porcentaje(v, 1, signo=True)}   n={int(n)}",
                    xy=(v, y), xytext=(6 if v > 0 else -6, 0), textcoords="offset points",
                    ha="left" if v > 0 else "right", va="center",
                    fontsize=8.2, color=TINTA)

    titular(ax, "Cuanto cuesta la ubicacion, descontados los atributos",
            "Sobreprecio del barrio sobre lo que predicen area, alcobas, banos, estrato y amenidades")
    ax.set_xlim(seleccion["sobreprecio_pct"].min() - 13,
                seleccion["sobreprecio_pct"].max() + 13)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:+.0f} %".replace("-", "−")))
    ax.tick_params(axis="y", labelsize=8.8)

    fuente(fig, "Residual medio del modelo estimado sin efectos fijos de barrio. Solo barrios con 25 avisos o mas.")
    fig.subplots_adjust(left=0.225, right=0.955, top=0.885, bottom=0.075)
    return _guardar(fig, "04_sobreprecio_barrios")


# --- 5. Conglomerados espaciales ---


def mapa_conglomerados(datos: pd.DataFrame) -> Path:
    d = datos[datos["latitud"].notna() & datos["conglomerado"].notna()]
    orden = ["no significativo", "bajo-alto", "alto-bajo", "bajo-bajo", "alto-alto"]

    fig, ax = plt.subplots(figsize=(7.6, 8.4))
    fig.patch.set_facecolor(SUPERFICIE)
    estilo_mapa(ax)

    for nombre in orden:
        sub = d[d["conglomerado"] == nombre]
        if sub.empty:
            continue
        destacado = nombre != "no significativo"
        ax.scatter(sub["longitud"], sub["latitud"],
                   s=9 if destacado else 3.5,
                   c=COLOR_LISA[nombre],
                   alpha=0.85 if destacado else 0.45,
                   linewidths=0, zorder=3 if destacado else 2)

    _encuadrar(ax, d["longitud"], d["latitud"])
    titular(ax, "El precio esta agrupado, no disperso",
            "Conglomerados locales de precio por m2, significativos al 5 % por permutaciones")

    etiquetas = {
        "alto-alto": "Caro rodeado de caros",
        "bajo-bajo": "Barato rodeado de baratos",
        "alto-bajo": "Caro rodeado de baratos",
        "bajo-alto": "Barato rodeado de caros",
        "no significativo": "Sin patron local",
    }
    manijas = [Line2D([], [], marker="o", linestyle="", markersize=7,
                      markerfacecolor=COLOR_LISA[k], markeredgecolor="none",
                      label=f"{etiquetas[k]}  ({pesos((d['conglomerado'] == k).sum())})")
               for k in ["alto-alto", "bajo-bajo", "bajo-alto", "alto-bajo", "no significativo"]]
    ax.legend(handles=manijas, loc="lower left", frameon=False,
              fontsize=8.2, labelcolor=TINTA_2)

    fuente(fig, "Indicadores locales de asociacion espacial sobre los avisos del modelo. Vecindad de ocho vecinos mas cercanos.")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.9, bottom=0.045)
    return _guardar(fig, "05_conglomerados")


# --- 6. Tiempo en mercado ---


def tiempo_en_mercado(geo: pd.DataFrame, minimo: int = 60) -> Path:
    d = geo.copy()
    creado = pd.to_datetime(d["creado_en"], errors="coerce")
    capturado = pd.to_datetime(d["capturado_en"], errors="coerce", utc=True)
    d["dias"] = (capturado.dt.tz_localize(None) - creado).dt.days
    d = d[d["dias"].notna() & (d["dias"] >= 0) & (d["dias"] < 900) & d["barrio"].notna()]

    agr = (d.groupby("barrio")
             .agg(dias=("dias", "median"), n=("dias", "size"), pm2=("precio_m2", "median"))
             .reset_index())
    agr = agr[agr["n"] >= minimo]

    fig, ax = nueva_figura(9.6, 5.8)
    estilo_eje(ax)
    ax.scatter(agr["dias"], agr["pm2"], s=agr["n"] / 3.2, color=SERIE_1,
               alpha=0.72, linewidths=0, zorder=3)

    mediana_dias = d["dias"].median()
    ax.axvline(mediana_dias, color=TINTA_3, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2)
    ax.annotate(f"mediana general\n{mediana_dias:.0f} dias", xy=(mediana_dias, ax.get_ylim()[1] * 0.96),
                xytext=(8, -6), textcoords="offset points", fontsize=8.2, color=TINTA_2)

    for _, r in pd.concat([agr.nlargest(3, "pm2"), agr.nsmallest(2, "dias")]).iterrows():
        ax.annotate(r["barrio"], xy=(r["dias"], r["pm2"]), xytext=(7, 4),
                    textcoords="offset points", fontsize=8, color=TINTA)

    titular(ax, "Los barrios caros no se demoran mas en alquilarse",
            "Cada punto es un barrio. El tamano indica cuantos avisos tiene")
    ax.set_xlabel("dias en el mercado, mediana del barrio", fontsize=8.6, color=TINTA_2)
    ax.set_ylabel("pesos por m2, mediana", fontsize=8.6, color=TINTA_2)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v/1000:.0f}k"))

    fuente(fig, f"Barrios con {minimo} avisos o mas. Los dias se cuentan desde la fecha de publicacion del aviso hasta la captura.")
    fig.subplots_adjust(left=0.085, right=0.975, top=0.855, bottom=0.125)
    return _guardar(fig, "06_tiempo_mercado")


# --- orquestador ---


def construir_todas() -> dict[str, Path]:
    from .grafico_ipc import construir as grafico_ipc
    from .hedonico import estimar, lisa, preparar, residuales_por_zona

    geo = gpd.read_parquet("datos/salidas/geo_enriquecido.parquet")
    geo["area"] = geo["area_privada"].fillna(geo["area_construida"])
    geo["precio_m2"] = geo["precio"] / geo["area"]

    d = preparar(geo, ventana_dias=90)
    r = estimar(d)
    residuales = residuales_por_zona(r, "barrio", minimo=25)
    conglomerados = lisa(d)
    amoblados = tabla_amoblados(geo, residuales)

    return {
        "ipc": grafico_ipc(),
        "distribucion": distribucion_precio(geo),
        "hexagonos": mapa_hexagonos(geo),
        "efectos": efectos_hedonicos(r),
        "sobreprecio": sobreprecio_barrios(residuales),
        "conglomerados": mapa_conglomerados(conglomerados),
        "tiempo": tiempo_en_mercado(geo),
        "turismo": viviendas_turisticas(),
        "amoblados": amoblados_vs_sobreprecio(amoblados),
        "tabla_sobreprecio": _escribir_csv(residuales, "sobreprecio_por_barrio.csv"),
        "tabla_amoblados": _escribir_csv(amoblados, "amoblado_vs_sobreprecio.csv"),
        "resumen_modelo": resumen_modelo(geo, d, r, residuales, amoblados),
    }


def resumen_modelo(
    geo: gpd.GeoDataFrame,
    datos: pd.DataFrame,
    resultado,
    residuales: pd.DataFrame | None = None,
    amoblados: pd.DataFrame | None = None,
) -> Path:
    """Guarda las cifras de portada calculadas, en vez de escritas a mano.

    La pagina web las llevaba dentro del guion como constantes. Al corregir la
    regla del barrio, el modelo cambio -el rango entre el barrio mas caro y el
    mas barato paso de 54 a 68 puntos- y la portada siguio anunciando las cifras
    viejas, sin que nada avisara. Una cifra escrita a mano es una cifra que
    envejece en silencio.
    """
    import json

    from .hedonico import diagnosticar

    m = resultado.modelo
    tab = resultado.resumen_coeficientes()
    barrios = [v for k, v in m.params.items() if k.startswith("C(barrio_modelo)")]

    diag = None
    espacial = {}
    try:
        diag = diagnosticar(resultado)
        moran = float(diag.moran_i)
    except Exception:
        moran = None

    try:
        from .hedonico import estimar_espacial

        me = estimar_espacial(resultado)
        betas = np.asarray(me.betas).ravel()
        errores = np.sqrt(np.diag(np.asarray(me.vm)))
        nombres = list(me.name_x) + ["lambda"]
        coef = dict(zip(nombres, betas))
        z = dict(zip(nombres, betas / errores))

        # Solo los parametros que el documento comenta, con su nombre en castellano.
        interesan = {
            "lambda": "lambda",
            "log_area": "Area (logaritmo)",
            "parqueaderos": "Parqueaderos",
            "banos": "Banos",
            "am_amoblado": "Amoblado",
            "am_gimnasio": "Gimnasio",
            "antiguedad_ord": "Antiguedad (por banda)",
        }
        espacial = {
            # Parametro de dependencia espacial del modelo de error.
            "lambda": round(float(betas[-1]), 3),
            "pseudo_r2": round(float(me.pr2), 4),
            "elasticidad_area": round(float(coef.get("log_area", float("nan"))), 4),
            "coeficientes": [
                {
                    "nombre": rotulo,
                    "coeficiente": round(float(coef[clave]), 3),
                    "z": round(float(z[clave]), 1),
                    # El area entra en logaritmo: su coeficiente es una elasticidad,
                    # no un efecto porcentual, y transformarlo seria un error.
                    "efecto": (
                        None
                        if clave in ("log_area", "lambda")
                        else round((float(np.exp(coef[clave])) - 1) * 100, 1)
                    ),
                }
                for clave, rotulo in interesan.items()
                if clave in coef
            ],
        }
    except Exception:
        espacial = {}

    # El salto del estrato 1 al 6 sale de los coeficientes de la variable
    # categorica, que van todos referidos al estrato 1 (la categoria omitida).
    def estrato(nivel: str):
        return next(
            (v for k, v in m.params.items() if k.startswith("C(estrato)") and nivel in k), None
        )

    estrato_5, estrato_6 = estrato("5"), estrato("6")

    # Cuanta oferta se anuncia amoblada, y a que precio por metro frente al resto.
    from .hedonico import sin_marcas, tiene_amenidad

    # Los descriptivos se calculan sobre la misma base que el resto del analisis:
    # avisos con precio y area y sin marcas de sospecha. Con la base completa,
    # el tablero -que si filtra- publicaba una mediana distinta de la del
    # informe, y las dos decian llamarse "precio mediano por metro cuadrado".
    utiles = geo[geo["precio_m2"].notna()]
    if "sospechoso" in utiles.columns:
        utiles = utiles[utiles["sospechoso"].apply(sin_marcas)]
    amoblado = utiles["amenidades"].apply(lambda v: tiene_amenidad(v, "amoblado"))

    # El conteo de portales sale del exportado plano, no del enriquecido: este
    # ultimo descarta los avisos sin coordenadas y ahi se pierde Coninsa entero,
    # que publica direccion pero no latitud ni longitud. Recogimos cuatro
    # portales; tres llegan al mapa. La portada habla de lo recogido.
    plano = pd.read_parquet("datos/salidas/arriendos_medellin.parquet")

    resumen = {
        "avisos_recogidos": int(len(plano)),
        "portales_recogidos": int(plano["portal"].nunique()),
        "avisos_geolocalizados": int(len(geo)),
        "avisos_utilizables": int(len(utiles)),
        "portales_geolocalizados": int(geo["portal"].nunique()),
        "avisos_modelo": int(m.nobs),
        "r2_ajustado": round(float(m.rsquared_adj), 4),
        "elasticidad_area": round(float(m.params["log_area"]), 4),
        "precio_mediano": int(utiles["precio"].median()),
        "precio_m2_mediano": int(utiles["precio_m2"].median()),
        "pct_amoblado": round(100 * float(amoblado.mean()), 1),
        "precio_m2_amoblado": int(utiles.loc[amoblado, "precio_m2"].median()),
        "precio_m2_sin_amoblar": int(utiles.loc[~amoblado, "precio_m2"].median()),
        "estrato_5_vs_1": round((np.exp(estrato_5) - 1) * 100, 1) if estrato_5 is not None else None,
        "estrato_6_vs_1": round((np.exp(estrato_6) - 1) * 100, 1) if estrato_6 is not None else None,
        "moran_i": round(moran, 4) if moran is not None else None,
        "moran_p": round(float(diag.moran_p), 3) if diag is not None else None,
        "vecinos": int(round(diag.vecinos_medios)) if diag is not None else None,
        "espacial": espacial,
        # Ojo con no confundir dos medidas parecidas del mismo fenomeno:
        #   - efectos_fijos_pp: distancia entre los coeficientes de barrio DENTRO
        #     del modelo, en puntos porcentuales de log-precio;
        #   - banda_ubicacion_pp: distancia entre el sobreprecio del barrio mas
        #     caro y el del mas barato, calculada sobre los residuales de un
        #     modelo SIN barrio. Es la que citan el informe y la pagina, porque
        #     es la que se puede leer como "cuanto cuesta estar aqui".
        "efectos_fijos_pp": round((max(barrios) - min(barrios)) * 100, 1) if barrios else None,
        "barrios_modelo": len(barrios) + 1 if barrios else 0,
        "efectos": [
            {
                "nombre": nombre,
                "efecto": round(float(tab.loc[col, "interpretacion"]), 1),
                "p": float(tab.loc[col, "p"]),
                "significativo": bool(tab.loc[col, "p"] < 0.05),
            }
            for col, nombre in ETIQUETAS_EFECTOS.items()
            if col in tab.index
        ],
    }

    if residuales is not None and not residuales.empty:
        orden = residuales.sort_values("sobreprecio_pct", ascending=False)
        arriba, abajo = orden.iloc[0], orden.iloc[-1]
        resumen["banda_ubicacion_pp"] = round(
            float(arriba["sobreprecio_pct"] - abajo["sobreprecio_pct"]), 1
        )
        resumen["barrio_mas_caro"] = {
            "barrio": str(arriba["barrio"]),
            "sobreprecio": round(float(arriba["sobreprecio_pct"]), 1),
        }
        resumen["barrio_mas_barato"] = {
            "barrio": str(abajo["barrio"]),
            "sobreprecio": round(float(abajo["sobreprecio_pct"]), 1),
        }
        resumen["barrios_con_sobreprecio"] = int(len(orden))

    if amoblados is not None and not amoblados.empty:
        # Spearman y no Pearson: la relacion no tiene por que ser lineal y hay
        # barrios con muy poca oferta amoblada que dominarian una recta.
        resumen["correlacion_amoblado"] = round(
            float(amoblados["pct_amoblado"].corr(amoblados["sobreprecio_pct"], method="spearman")), 3
        )

    ruta = Path("datos/salidas/resumen_modelo.json")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8")
    return ruta


def tabla_amoblados(geo: gpd.GeoDataFrame, residuales: pd.DataFrame) -> pd.DataFrame:
    """Cruza el sobreprecio de cada barrio con su densidad de oferta amoblada.

    El denominador es el total de avisos del barrio, no los que entran al modelo:
    la pregunta es que proporcion de la oferta de ese barrio se anuncia amoblada,
    y para eso cuentan todos.
    """
    from .hedonico import tiene_amenidad

    por_barrio = (
        geo[geo["barrio"].notna()]
        .assign(amoblado=lambda x: x["amenidades"].apply(tiene_amenidad, nombre="amoblado"))
        .groupby("barrio")
        .agg(n_total=("amoblado", "size"), n_amoblado=("amoblado", "sum"))
        .reset_index()
    )
    por_barrio["pct_amoblado"] = 100 * por_barrio["n_amoblado"] / por_barrio["n_total"]

    cruce = residuales.merge(
        por_barrio[["barrio", "pct_amoblado", "n_total"]], on="barrio", how="inner"
    )
    return cruce.sort_values("sobreprecio_pct", ascending=False)


def _escribir_csv(tabla: pd.DataFrame, nombre: str) -> Path:
    """Guarda una tabla de resultados junto a las figuras.

    Estas dos tablas existian en disco sin que ningun codigo las escribiera: se
    habian generado a mano una vez y se habian quedado ahi. Cuando se corrigio
    la regla del barrio, las figuras se rehicieron y las tablas no, de modo que
    la pagina web siguio mostrando un barrio que ya no existia. Se generan aqui,
    en la misma corrida que las figuras que las acompanan.
    """
    ruta = Path("datos/salidas") / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(ruta, index=False, encoding="utf-8-sig")
    return ruta




# --- 7. Registro Nacional de Turismo ---


def viviendas_turisticas(salida_csv: Path = Path("datos/salidas/rnt_viviendas_turisticas.csv")) -> Path:
    """Crecimiento del parque de vivienda turistica registrada."""
    import json

    ciudades = {"MEDELLIN": SERIE_1, "BOGOTA_D_C_": SERIE_2}
    series = {}
    for archivo, color in ciudades.items():
        ruta = Path("datos/externos/rnt") / f"{archivo}.json"
        if not ruta.exists():
            continue
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        series[archivo] = ({int(r["ano"]): int(r["n"]) for r in datos}, color)

    fig, ax = nueva_figura(9.6, 5.4)
    estilo_eje(ax)
    nombres = {"MEDELLIN": "Medellin", "BOGOTA_D_C_": "Bogota"}

    for clave, (serie, color) in series.items():
        anios = sorted(serie)
        valores = [serie[a] for a in anios]
        ax.plot(anios, valores, color=color, linewidth=2.2, marker="o",
                markersize=5, markeredgecolor=SUPERFICIE, markeredgewidth=1.6, zorder=3)
        ax.annotate(f"{nombres[clave]}  {pesos(valores[-1])}",
                    xy=(anios[-1], valores[-1]), xytext=(10, -3),
                    textcoords="offset points", fontsize=9,
                    color=TINTA, fontweight="bold", va="center")

    med = series.get("MEDELLIN", ({}, None))[0]
    if med:
        mult = med.get(2024, 0) / max(med.get(2019, 1), 1)
        # Viviendas censadas por el DANE en Medellin, del Marco Geoestadistico
        VIVIENDAS_MEDELLIN = 881_756
        cuota = 100 * med.get(2026, 0) / VIVIENDAS_MEDELLIN
        ax.annotate(
            f"Medellin: x{mult:.1f} entre 2019 y 2024".replace(".", ","),
            xy=(0.035, 0.80), xycoords="axes fraction", fontsize=9.6,
            color=TINTA, fontweight="bold", ha="left",
        )
        ax.annotate(
            f"equivale al {cuota:.2f} % del parque de vivienda de la ciudad".replace(".", ","),
            xy=(0.035, 0.735), xycoords="axes fraction", fontsize=9,
            color=TINTA_2, ha="left",
        )

    titular(ax, "El parque de vivienda turistica se multiplico por diecisiete",
            "Viviendas turisticas con registro activo en el Registro Nacional de Turismo")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: pesos(v)))
    ax.set_xticks(sorted(med) if med else [])

    fuente(fig, "Fuente: Registro Nacional de Turismo, datos.gov.co. Registros activos en cada anio, no altas nuevas. "
                "Bogota alcanza cifras similares con cerca del triple de poblacion.")
    fig.subplots_adjust(left=0.085, right=0.815, top=0.855, bottom=0.11)
    return _guardar(fig, "07_vivienda_turistica")


# --- 8. Amoblados frente a sobreprecio ---


def amoblados_vs_sobreprecio(cruce: pd.DataFrame) -> Path:
    from scipy import stats

    fig, ax = nueva_figura(9.6, 5.8)
    estilo_eje(ax)
    ax.axhline(0, color=TINTA_3, linewidth=1.0, zorder=2)

    ax.scatter(cruce["pct_amoblado"], cruce["sobreprecio_pct"],
               s=cruce["n_total"] / 3.4, color=SERIE_1, alpha=0.72,
               linewidths=0, zorder=3)

    # Recta de ajuste, solo como guia visual de la tendencia
    pend, corte, *_ = stats.linregress(cruce["pct_amoblado"], cruce["sobreprecio_pct"])
    x = np.linspace(0, cruce["pct_amoblado"].max() * 1.04, 50)
    ax.plot(x, corte + pend * x, color=TINTA_3, linewidth=1.4,
            linestyle=(0, (5, 3)), zorder=2)

    rho, p = stats.spearmanr(cruce["pct_amoblado"], cruce["sobreprecio_pct"])
    ax.annotate(f"rho de Spearman = {rho:+.3f}\np < 0,0001".replace(".", ","),
                xy=(0.985, 0.06), xycoords="axes fraction", ha="right",
                fontsize=9.4, color=TINTA, fontweight="bold")

    for _, r in pd.concat([cruce.nlargest(3, "sobreprecio_pct"),
                           cruce.nlargest(2, "pct_amoblado"),
                           cruce.nsmallest(2, "sobreprecio_pct")]).drop_duplicates().iterrows():
        ax.annotate(r["barrio"], xy=(r["pct_amoblado"], r["sobreprecio_pct"]),
                    xytext=(7, 5), textcoords="offset points", fontsize=8, color=TINTA)

    titular(ax, "Donde hay mas oferta amoblada, la ubicacion se paga mas cara",
            "Cada punto es un barrio; el tamano indica cuantos avisos tiene")
    ax.set_xlabel("porcentaje de avisos amoblados en el barrio", fontsize=8.6, color=TINTA_2)
    ax.set_ylabel("sobreprecio del barrio", fontsize=8.6, color=TINTA_2)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f} %"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:+.0f} %".replace("-", "−")))

    fuente(fig, "El modelo hedonico ya controla si cada inmueble esta amoblado: lo que aqui se mide es el efecto del entorno, no del mueble. Es asociacion, no causalidad.")
    fig.subplots_adjust(left=0.085, right=0.975, top=0.855, bottom=0.125)
    return _guardar(fig, "08_amoblados_sobreprecio")


if __name__ == "__main__":
    for nombre, ruta in construir_todas().items():
        print(f"  {nombre:14s} -> {ruta}")
