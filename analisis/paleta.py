"""Paleta y estilo comunes de las figuras del informe.

Los valores estan validados: la pareja categorica separa ΔE 24,7 en protanopia
y 33,6 en vision normal, de modo que las series se distinguen tambien impresas
en escala de grises y con daltonismo.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Categorico: identidad, dos series
SERIE_1 = "#2a78d6"  # azul
SERIE_2 = "#eb6834"  # naranja

# Secuencial: magnitud, un solo tono de claro a oscuro
RAMPA_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Divergente: polaridad, dos tonos opuestos con gris neutro en el centro
POLO_ALTO = "#2a78d6"
POLO_BAJO = "#d03b3b"
NEUTRO = "#f0efec"

# Conglomerados espaciales
COLOR_LISA = {
    "alto-alto": "#184f95",
    "bajo-bajo": "#d03b3b",
    "alto-bajo": "#86b6ef",
    "bajo-alto": "#ec835a",
    "no significativo": "#dcdbd6",
}

# Superficies y tinta
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#8a8880"
REJILLA = "#e4e3de"

MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic"]


def pesos(valor: float, decimales: int = 0) -> str:
    """Formato colombiano: punto para miles, coma para decimales."""
    s = f"{valor:,.{decimales}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def porcentaje(valor: float, decimales: int = 1, signo: bool = False) -> str:
    fmt = f"{{:{'+' if signo else ''}.{decimales}f}}"
    # Signo menos tipografico, no guion: es el mismo que usan los ejes.
    return fmt.format(valor).replace(".", ",").replace("-", "−") + " %"


def estilo_eje(ax, eje_y: bool = True, eje_x: bool = False) -> None:
    """Ejes recesivos: la rejilla no debe competir con los datos."""
    ax.set_facecolor(SUPERFICIE)
    if eje_y:
        ax.grid(True, axis="y", color=REJILLA, linewidth=0.8, zorder=0)
    if eje_x:
        ax.grid(True, axis="x", color=REJILLA, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(REJILLA)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(colors=TINTA_2, labelsize=8.5, length=0)


def estilo_mapa(ax) -> None:
    ax.set_facecolor(SUPERFICIE)
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_visible(False)
    ax.set_aspect("equal")


def titular(fig_o_ax, titulo: str, subtitulo: str | None = None, y: float = 1.0) -> None:
    ax = fig_o_ax
    ax.set_title(titulo, fontsize=13, fontweight="bold", color=TINTA,
                 loc="left", pad=26 if subtitulo else 12)
    if subtitulo:
        ax.text(0, 1.028, subtitulo, transform=ax.transAxes,
                fontsize=9.2, color=TINTA_2, va="bottom")


def fuente(fig, texto: str) -> None:
    fig.text(0.011, 0.016, texto, fontsize=7.6, color=TINTA_3)


def nueva_figura(ancho: float = 9.6, alto: float = 5.6):
    fig, ax = plt.subplots(figsize=(ancho, alto))
    fig.patch.set_facecolor(SUPERFICIE)
    return fig, ax
