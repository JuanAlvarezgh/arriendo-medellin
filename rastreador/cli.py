"""Interfaz de linea de comandos del rastreador."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from . import panel
from .estado import Estado, formato_duracion, marca_de_tiempo
from .motor import Configuracion, cargar_perfil, guardar_perfil, perfiles_disponibles
from .persistencia.almacen import AlmacenPostgres, ArchivoJsonl

app = typer.Typer(
    add_completion=False,
    help="Rastreador de avisos de arriendo. Cascada de extraccion multi portal.",
)
consola = Console()

DSN_POR_DEFECTO = "postgresql://postgres@localhost:5432/arriendos"


@app.command()
def portales() -> None:
    """Lista los perfiles de portal disponibles."""
    t = Table("Perfil", "Dominio", "Categoria", "Ritmo", title="Portales configurados")
    for nombre in perfiles_disponibles():
        p = cargar_perfil(nombre)
        t.add_row(
            nombre,
            p.get("dominio", "-"),
            p.get("categoria", "-"),
            f"{p.get('limite_peticiones', '-')}/s",
        )
    consola.print(t)


@app.command()
def descubrir(
    portal: str = typer.Option(..., help="Nombre del perfil, por ejemplo fincaraiz"),
    tope: Optional[int] = typer.Option(None, help="Maximo de URLs a listar"),
) -> None:
    """Recorre los sitemaps del portal y reporta cuantos avisos encuentra."""
    from .descarga.cache import CacheDisco
    from .descarga.cliente import Cliente
    from .motor import Motor

    async def correr() -> None:
        motor = Motor(Configuracion(portal=portal, tope=tope))
        async with Cliente(cache=CacheDisco(Path("datos/cache"))) as cliente:
            with consola.status(f"Recorriendo sitemaps de {portal}..."):
                urls = await motor.descubrir(cliente)
        consola.print(f"\n  [bold]{len(urls):,}[/bold] avisos descubiertos".replace(",", "."))
        con_fecha = [u for u in urls if u.modificado]
        if con_fecha:
            fechas = sorted(u.modificado for u in con_fecha)  # type: ignore[type-var]
            consola.print(f"  con fecha de modificacion: {len(con_fecha):,}".replace(",", "."))
            consola.print(f"  rango: {fechas[0]} a {fechas[-1]}")
        consola.print("\n  primeros cinco:")
        for u in urls[:5]:
            consola.print(f"    [dim]{u.url}[/dim]")

    asyncio.run(correr())


@app.command()
def raspar(
    portal: str = typer.Option(..., help="Nombre del perfil"),
    tope: Optional[int] = typer.Option(None, help="Maximo de avisos a raspar"),
    modelo: bool = typer.Option(False, "--modelo", help="Habilita la capa e"),
    reanudar: bool = typer.Option(True, help="Omite lo ya presente en el jsonl"),
    panel_vivo: bool = typer.Option(True, "--panel/--sin-panel"),
) -> None:
    """Raspa un portal y escribe los avisos en datos/crudo/<portal>.jsonl."""
    from .motor import rastrear

    # Un archivo de estado por portal: dos corridas simultaneas de portales
    # distintos se pisaban el estado y `rastreador estado` informaba de la
    # equivocada.
    estado = Estado(ruta=Path("datos") / f"estado_{portal}.json")
    config = Configuracion(portal=portal, tope=tope, usar_modelo=modelo, reanudar=reanudar)

    async def correr() -> None:
        if not panel_vivo:
            try:
                await rastrear(config, estado=estado)
            finally:
                estado.terminado = True
                estado.guardar()
            return
        with Live(panel.construir(estado), console=consola, refresh_per_second=4) as vivo:
            def refrescar() -> None:
                vivo.update(panel.construir(estado))

            try:
                await rastrear(config, estado=estado, al_avanzar=refrescar)
            finally:
                estado.terminado = True
                estado.guardar()
                vivo.update(panel.construir(estado))

    try:
        asyncio.run(correr())
    except KeyboardInterrupt:
        estado.terminado = True
        estado.guardar()
        consola.print("\n[yellow]Interrumpido. El progreso quedo guardado; "
                      "vuelve a correr para reanudar.[/yellow]")
        raise typer.Exit(130)

    panel.imprimir_resumen(estado, consola)


@app.command()
def estado(
    portal: Optional[str] = typer.Option(None, help="Portal concreto; por omision, todos"),
) -> None:
    """Informa si hay corridas activas, sin tocar los procesos."""
    carpeta = Path("datos")
    if portal:
        rutas = [carpeta / f"estado_{portal}.json"]
    else:
        rutas = sorted(carpeta.glob("estado_*.json")) or [carpeta / "estado.json"]

    encontrados = [(r, Estado.cargar(r)) for r in rutas]
    encontrados = [(r, e) for r, e in encontrados if e is not None]

    if not encontrados:
        consola.print("[yellow]No hay ninguna corrida registrada.[/yellow]")
        raise typer.Exit(1)

    for ruta, e in encontrados:
        _informar_estado(ruta, e)


def _informar_estado(ruta: Path, e: Estado) -> None:
    vivo = e.proceso_vivo()
    if e.terminado:
        etiqueta = "[blue]TERMINADA[/blue]"
    elif not vivo:
        etiqueta = "[red]EL PROCESO YA NO EXISTE[/red]"
    elif e.estancado:
        etiqueta = "[red]SIN AVANCE[/red]"
    else:
        etiqueta = "[green]ACTIVA[/green]"

    consola.print()
    consola.print(f"  corrida {etiqueta}   pid {e.pid}   inicio {marca_de_tiempo(e.iniciado_en)}")
    consola.print(f"  transcurrido {formato_duracion(e.transcurrido)}   ritmo {e.ritmo:.1f}/s")
    consola.print(f"  ultimo aviso hace {formato_duracion(e.segundos_sin_avisos)}")
    consola.print()
    consola.print(panel._tabla_portales(e))
    if e.segundos_restantes:
        consola.print(f"  restante estimado: {formato_duracion(e.segundos_restantes)}")
    consola.print()


@app.command()
def exportar(
    formato: str = typer.Option("csv", help="csv, excel, parquet o jsonl"),
    salida: Optional[Path] = typer.Option(None, help="Archivo de destino"),
    entrada: Path = typer.Option(Path("datos/crudo"), help="Carpeta con los .jsonl"),
    solo_utilizables: bool = typer.Option(
        False, help="Excluye avisos marcados como sospechosos"
    ),
) -> None:
    """Exporta los avisos recogidos a un archivo plano."""
    import pandas as pd

    registros: list[dict] = []
    archivos = sorted(entrada.glob("*.jsonl")) if entrada.is_dir() else [entrada]
    for arch in archivos:
        registros.extend(ArchivoJsonl(arch).leer())

    if not registros:
        consola.print(f"[yellow]No hay avisos en {entrada}.[/yellow]")
        raise typer.Exit(1)

    df = pd.DataFrame(registros)
    df = df.drop_duplicates(subset=["portal", "id_fuente"], keep="last")

    if solo_utilizables and "sospechoso" in df.columns:
        antes = len(df)
        df = df[df["sospechoso"].apply(lambda s: not s)]
        consola.print(f"  descartados {antes - len(df)} avisos marcados")

    if "amenidades" in df.columns:
        df["amenidades"] = df["amenidades"].apply(
            lambda v: "|".join(v) if isinstance(v, list) else v
        )
    if "sospechoso" in df.columns:
        df["sospechoso"] = df["sospechoso"].apply(
            lambda v: "|".join(v) if isinstance(v, list) else v
        )

    destinos = {
        "csv": ("datos/salidas/arriendos_medellin.csv", lambda d, r: d.to_csv(r, index=False, encoding="utf-8-sig")),
        "excel": ("datos/salidas/arriendos_medellin.xlsx", lambda d, r: d.to_excel(r, index=False)),
        "parquet": ("datos/salidas/arriendos_medellin.parquet", lambda d, r: d.to_parquet(r, index=False)),
        "jsonl": ("datos/salidas/arriendos_medellin.jsonl", lambda d, r: d.to_json(r, orient="records", lines=True, force_ascii=False)),
    }
    if formato not in destinos:
        consola.print(f"[red]Formato no soportado: {formato}[/red]")
        raise typer.Exit(1)

    por_defecto, escritor = destinos[formato]
    ruta = salida or Path(por_defecto)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escritor(df, ruta)

    consola.print(f"\n  [green]{len(df):,} avisos[/green] escritos en [bold]{ruta}[/bold]".replace(",", "."))
    consola.print(f"  columnas: {len(df.columns)}")


@app.command()
def cargar(
    dsn: str = typer.Option(DSN_POR_DEFECTO, help="Cadena de conexion a PostgreSQL"),
    entrada: Path = typer.Option(Path("datos/crudo"), help="Carpeta con los .jsonl"),
    deduplicar: bool = typer.Option(True, help="Agrupa el mismo inmueble entre portales"),
) -> None:
    """Carga los avisos a PostgreSQL, en raw y stg."""
    from .deduplicacion.similitud import agrupar
    from .normalizacion.esquema import Aviso

    almacen = AlmacenPostgres(dsn)
    if not almacen.disponible():
        consola.print(f"[red]No hay conexion a PostgreSQL con {dsn}[/red]")
        raise typer.Exit(1)

    almacen.crear_esquema()

    registros: list[dict] = []
    archivos = sorted(entrada.glob("*.jsonl")) if entrada.is_dir() else [entrada]
    for arch in archivos:
        registros.extend(ArchivoJsonl(arch).leer())

    if not registros:
        consola.print("[yellow]No hay avisos que cargar.[/yellow]")
        raise typer.Exit(1)

    unicos: dict[tuple[str, str], dict] = {}
    for r in registros:
        unicos[(r.get("portal", ""), r.get("id_fuente", ""))] = r
    registros = list(unicos.values())

    n_crudo = almacen.cargar_crudo(registros)
    consola.print(f"  raw.avisos: {n_crudo:,} filas".replace(",", "."))

    from .extraccion.cascada import barrio_desde_url

    avisos: list[Aviso] = []
    for r in registros:
        try:
            a = Aviso.model_validate(r)
        except Exception:
            continue
        # Los avisos raspados antes de que el barrio entrara a la cascada no lo
        # traen; se completa aqui para no tener que volver a raspar.
        if not a.barrio:
            a.barrio = barrio_desde_url(a.url)
        avisos.append(a)

    grupos: dict[str, str] = {}
    if deduplicar:
        with consola.status("Agrupando duplicados entre portales..."):
            for g in agrupar(avisos):
                canonico = g.canonico.clave_natural()
                for m in g.miembros:
                    grupos[m.clave_natural()] = canonico
        repetidos = sum(1 for k, v in grupos.items() if k != v)
        consola.print(f"  duplicados detectados: {repetidos:,}".replace(",", "."))

    n_limpio = almacen.cargar_limpio(avisos, grupos)
    consola.print(f"  stg.avisos: {n_limpio:,} filas".replace(",", "."))
    consola.print(f"\n  [green]total en base:[/green] {almacen.contar():,}".replace(",", "."))


@app.command()
def perfil(
    dominio: str = typer.Argument(..., help="Dominio a inspeccionar"),
    descubrir_api: bool = typer.Option(
        False, "--descubrir", help="Observa el trafico de red para hallar la API interna"
    ),
    url: Optional[str] = typer.Option(None, help="URL de partida para la observacion"),
) -> None:
    """Inspecciona un dominio nuevo y propone un perfil."""
    from .extraccion.api_interna import descubrir as descubrir_endpoints

    if descubrir_api:
        if not url:
            consola.print("[red]--descubrir requiere --url[/red]")
            raise typer.Exit(1)
        with consola.status(f"Observando el trafico de {url}..."):
            hallazgos = asyncio.run(descubrir_endpoints(url))
        if not hallazgos:
            consola.print(
                "[yellow]Sin endpoints con avisos. Puede faltar Playwright: "
                "pip install playwright && playwright install chromium[/yellow]"
            )
            raise typer.Exit(1)
        t = Table("Endpoint", "Metodo", "Ruta de items", "Items")
        for h in hallazgos[:10]:
            t.add_row(h.url[:70], h.metodo, h.ruta_items or "(raiz)", str(h.cantidad_items))
        consola.print(t)
        mejor = hallazgos[0]
        consola.print(f"\n  Mejor candidato: [bold]{mejor.url}[/bold]")
        if mejor.muestra:
            consola.print(f"  Campos del item: {', '.join(list(mejor.muestra.keys())[:14])}")
        return

    nombre = dominio.split(".")[0]
    propuesta = {
        "dominio": dominio,
        "portal": nombre,
        "categoria": "por_determinar",
        "limite_peticiones": 1.5,
        "concurrencia": 4,
    }
    consola.print(json.dumps(propuesta, indent=2, ensure_ascii=False))
    if typer.confirm(f"Guardar como perfil {nombre}?", default=False):
        ruta = guardar_perfil(nombre, propuesta)
        consola.print(f"  escrito en {ruta}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
