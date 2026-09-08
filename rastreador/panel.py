"""Panel de ejecucion en vivo."""

from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table

from .estado import Estado, formato_duracion, marca_de_tiempo

NOMBRES_CAPA = {
    "api": "api interna",
    "a": "estructurados",
    "b": "estado embebido",
    "d": "heuristica html",
    "e": "modelo lenguaje",
    "sin_capa": "sin identificar",
}
ORDEN_CAPA = ["api", "a", "b", "d", "e", "sin_capa"]


def _cabecera(e: Estado) -> Table:
    t = Table.grid(expand=True)
    t.add_column(justify="left")
    t.add_column(justify="right")

    if e.terminado:
        marca = "[bold blue]TERMINADO[/bold blue]"
        detalle = f"duracion {formato_duracion(e.transcurrido)}"
    elif e.estancado:
        marca = "[bold red]SIN AVANCE[/bold red]"
        detalle = f"[red]{formato_duracion(e.segundos_sin_avisos)} sin avisos nuevos[/red]"
    else:
        marca = "[bold green]ACTIVO[/bold green]"
        detalle = f"ultimo aviso hace {e.segundos_sin_avisos:.1f} s"

    t.add_row(
        f"[bold]rastreador[/bold]  inicio {marca_de_tiempo(e.iniciado_en)}  pid {e.pid}",
        f"{marca}  {detalle}",
    )
    return t


def _tabla_portales(e: Estado) -> Table:
    t = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False)
    t.add_column("Portal", style="bold")
    t.add_column("Descubiertos", justify="right")
    t.add_column("Descargados", justify="right")
    t.add_column("Extraidos", justify="right")
    t.add_column("Capa", justify="center")
    t.add_column("Fallidos", justify="right")
    t.add_column("Omitidos", justify="right")

    for nombre, p in sorted(e.portales.items()):
        color_fallos = "red" if p.fallidos > max(p.extraidos * 0.1, 20) else "white"
        t.add_row(
            nombre,
            f"{p.descubiertos:,}".replace(",", "."),
            f"{p.descargados:,}".replace(",", "."),
            f"{p.extraidos:,}".replace(",", "."),
            p.ultima_capa or "-",
            f"[{color_fallos}]{p.fallidos}[/{color_fallos}]",
            str(p.omitidos),
        )

    if len(e.portales) > 1:
        t.add_section()
        t.add_row(
            "[bold]total[/bold]",
            f"[bold]{e.total_descubiertos:,}[/bold]".replace(",", "."),
            f"[bold]{e.total_descargados:,}[/bold]".replace(",", "."),
            f"[bold]{e.total_extraidos:,}[/bold]".replace(",", "."),
            "",
            f"[bold]{e.total_fallidos}[/bold]",
            "",
        )
    return t


def _tabla_capas(e: Estado) -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", width=3)
    t.add_column(min_width=16)
    t.add_column(justify="right", min_width=7)
    t.add_column(justify="right", style="dim", min_width=6)

    capas = e.capas_agregadas()
    total = sum(capas.values()) or 1
    for clave in ORDEN_CAPA:
        n = capas.get(clave, 0)
        if n == 0 and clave in ("e", "sin_capa"):
            continue
        t.add_row(clave, NOMBRES_CAPA.get(clave, clave), f"{n:,}".replace(",", "."), f"{100*n/total:.1f}%")
    if e.costo_modelo_usd > 0:
        t.add_row("", "[dim]costo modelo[/dim]", f"[dim]${e.costo_modelo_usd:.3f}[/dim]", "")
    return t


def _tabla_salidas(e: Estado) -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(min_width=18)
    t.add_column(justify="right", min_width=10)

    total_cache = e.cache_aciertos + e.cache_fallos
    tasa = f"{100 * e.cache_aciertos / total_cache:.0f}%" if total_cache else "-"

    t.add_row("ritmo", f"{e.ritmo:.1f}/s")
    t.add_row("transcurrido", formato_duracion(e.transcurrido))
    t.add_row("restante estimado", formato_duracion(e.segundos_restantes))
    t.add_row("aciertos de cache", f"{e.cache_aciertos:,}".replace(",", ".") + f" ({tasa})")
    t.add_row("duplicados", f"{e.duplicados:,}".replace(",", "."))
    return t


def construir(e: Estado) -> Group:
    """Arma el panel completo a partir del estado."""
    columnas = Table.grid(expand=True)
    columnas.add_column(ratio=1)
    columnas.add_column(ratio=1)
    columnas.add_row(
        Panel(_tabla_capas(e), title="resuelto por capa", box=box.ROUNDED, border_style="dim"),
        Panel(_tabla_salidas(e), title="marcha", box=box.ROUNDED, border_style="dim"),
    )

    progreso = Progress(
        TextColumn("[bold]avance"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        expand=True,
    )
    total = max(e.total_descubiertos, 1)
    progreso.add_task("", total=total, completed=min(e.total_descargados, total))

    return Group(
        Panel(_cabecera(e), box=box.HEAVY, border_style="cyan"),
        _tabla_portales(e),
        columnas,
        progreso,
    )


def imprimir_resumen(e: Estado, consola: Console | None = None) -> None:
    """Resumen final tras terminar la corrida."""
    c = consola or Console()
    c.print()
    c.print(Panel("[bold]Resumen de la corrida[/bold]", box=box.HEAVY, border_style="cyan"))
    c.print(_tabla_portales(e))

    capas = e.capas_agregadas()
    if capas:
        c.print()
        c.print("[bold]Resuelto por capa[/bold]")
        c.print(_tabla_capas(e))

    motivos: dict[str, int] = {}
    for p in e.portales.values():
        for motivo, n in p.motivos_fallo.items():
            motivos[motivo] = motivos.get(motivo, 0) + n
    if motivos:
        c.print()
        c.print("[bold]Motivos de fallo[/bold]")
        t = Table.grid(padding=(0, 2))
        t.add_column(min_width=30)
        t.add_column(justify="right")
        for motivo, n in sorted(motivos.items(), key=lambda x: -x[1]):
            t.add_row(motivo, str(n))
        c.print(t)

    c.print()
    c.print(
        f"  duracion {formato_duracion(e.transcurrido)}   "
        f"ritmo {e.ritmo:.1f}/s   "
        f"extraidos {e.total_extraidos:,}".replace(",", ".")
    )
    if e.costo_modelo_usd > 0:
        c.print(f"  costo del modelo de lenguaje: ${e.costo_modelo_usd:.4f}")
    c.print()
