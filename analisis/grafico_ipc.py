"""Grafico de la divergencia del IPC de arriendos entre Medellin y el pais.

Dos paneles con un solo eje cada uno. Nunca dos escalas en el mismo eje: si
hicieran falta dos unidades, se separan en dos graficos, que es lo que se hace
aqui.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

# Paleta validada: separacion ΔE 24,7 en protanopia y 33,6 en vision normal.
MEDELLIN = "#2a78d6"
NACIONAL = "#eb6834"
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#8a8880"
REJILLA = "#e4e3de"

# matplotlib rotula los meses segun la configuracion regional del sistema, que
# aqui esta en ingles. Se traducen a mano en vez de depender del locale, que en
# Windows no es fiable entre equipos.
MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic"]


def _mes_es(fecha) -> str:
    return MESES_ES[fecha.month - 1]


RUTA_SERIE = Path("datos/salidas/ipc_arriendo_dane.csv")
RUTA_FIGURA = Path("datos/salidas/ipc_divergencia_medellin.png")


def _formato_pct(v, _pos):
    return f"{v:.0f} %".replace(".", ",")


def _estilo_eje(ax):
    ax.set_facecolor(SUPERFICIE)
    ax.grid(True, axis="y", color=REJILLA, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(REJILLA)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=TINTA_2, labelsize=8.5, length=0)


def construir(ruta_serie: Path = RUTA_SERIE, salida: Path = RUTA_FIGURA) -> Path:
    df = pd.read_csv(ruta_serie, parse_dates=["periodo"])
    df["brecha"] = df["alojamiento_medellin_anual"] - df["alojamiento_nacional_anual"]

    fig, (arriba, abajo) = plt.subplots(
        2, 1, figsize=(9.6, 7.4), sharex=True,
        gridspec_kw={"height_ratios": [2.5, 1], "hspace": 0.16},
    )
    fig.patch.set_facecolor(SUPERFICIE)

    # --- panel superior: las dos series ---
    _estilo_eje(arriba)
    arriba.plot(df["periodo"], df["alojamiento_medellin_anual"],
                color=MEDELLIN, linewidth=2.0, zorder=3, solid_capstyle="round")
    arriba.plot(df["periodo"], df["alojamiento_nacional_anual"],
                color=NACIONAL, linewidth=2.0, zorder=3, solid_capstyle="round")

    # Marcar el punto de giro de Medellin
    minimo = df.loc[df["alojamiento_medellin_anual"].idxmin()]
    arriba.scatter([minimo["periodo"]], [minimo["alojamiento_medellin_anual"]],
                   s=46, color=MEDELLIN, edgecolor=SUPERFICIE, linewidth=2, zorder=4)
    arriba.annotate(
        f"minimo {minimo['alojamiento_medellin_anual']:.2f} %".replace(".", ",") +
        f"\n{_mes_es(minimo['periodo'])} {minimo['periodo'].year}",
        xy=(minimo["periodo"], minimo["alojamiento_medellin_anual"]),
        xytext=(-4, -38), textcoords="offset points",
        fontsize=8.2, color=TINTA_2, ha="center",
        arrowprops=dict(arrowstyle="-", color=TINTA_3, linewidth=0.8),
    )

    # Etiquetas directas al final de cada linea: la identidad no depende del color
    ultimo = df.iloc[-1]
    for valor, color, nombre in (
        (ultimo["alojamiento_medellin_anual"], MEDELLIN, "Medellin"),
        (ultimo["alojamiento_nacional_anual"], NACIONAL, "Nacional"),
    ):
        arriba.annotate(
            f"{nombre}  {valor:.2f} %".replace(".", ","),
            xy=(ultimo["periodo"], valor), xytext=(9, -3), textcoords="offset points",
            fontsize=9, color=TINTA, fontweight="bold", va="center",
        )
        arriba.scatter([ultimo["periodo"]], [valor], s=34, color=color,
                       edgecolor=SUPERFICIE, linewidth=2, zorder=4)

    arriba.set_title(
        "El alojamiento en Medellin se desacopla de la tendencia nacional",
        fontsize=13.5, fontweight="bold", color=TINTA, loc="left", pad=26,
    )
    arriba.text(
        0, 1.042,
        "Variacion anual del IPC, division de alojamiento, agua, electricidad y gas",
        transform=arriba.transAxes, fontsize=9.4, color=TINTA_2, va="bottom",
    )
    arriba.yaxis.set_major_formatter(FuncFormatter(_formato_pct))
    arriba.set_ylim(3.4, 9.6)

    # --- panel inferior: la brecha ---
    _estilo_eje(abajo)
    abajo.axhline(0, color=TINTA_3, linewidth=1.0, zorder=2)
    abajo.fill_between(df["periodo"], 0, df["brecha"],
                       where=df["brecha"] >= 0, color=MEDELLIN, alpha=0.22, zorder=1)
    abajo.fill_between(df["periodo"], 0, df["brecha"],
                       where=df["brecha"] < 0, color=NACIONAL, alpha=0.22, zorder=1)
    abajo.plot(df["periodo"], df["brecha"], color=MEDELLIN, linewidth=1.8, zorder=3)
    abajo.annotate(
        f"{ultimo['brecha']:+.2f} pp".replace(".", ","),
        xy=(ultimo["periodo"], ultimo["brecha"]), xytext=(9, -3),
        textcoords="offset points", fontsize=9, color=TINTA, fontweight="bold", va="center",
    )
    abajo.set_title(
        "Brecha: Medellin menos nacional, en puntos porcentuales",
        fontsize=9.6, color=TINTA_2, loc="left", pad=8,
    )
    # Ticks explicitos: con formato entero automatico, 1,5 y 2,0 se dibujaban
    # ambos como "+2" y 0,0 aparecia como "−0".
    abajo.set_yticks([-1, 0, 1, 2])
    abajo.set_yticklabels(["−1", "0", "+1", "+2"])
    abajo.set_ylim(-1.15, 2.5)

    abajo.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    abajo.xaxis.set_major_formatter(
        FuncFormatter(
            lambda v, _p: "{}\n{}".format(
                _mes_es(mdates.num2date(v)), mdates.num2date(v).year
            )
        )
    )

    fig.text(
        0.011, 0.018,
        "Fuente: DANE, anexos mensuales del IPC. Serie de agosto de 2024 a julio de 2026, "
        "que es el periodo con anexo publicado en este formato.",
        fontsize=7.8, color=TINTA_3,
    )
    fig.subplots_adjust(left=0.075, right=0.845, top=0.885, bottom=0.115)

    salida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(salida, dpi=200, facecolor=SUPERFICIE)
    plt.close(fig)
    return salida


if __name__ == "__main__":
    print("escrito en", construir())
