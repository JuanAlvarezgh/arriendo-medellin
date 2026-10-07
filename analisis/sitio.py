"""Encabezado comun que conecta todas las paginas del proyecto.

Todas las paginas terminan en la misma carpeta, `datos/salidas/web`, para que los
enlaces sean relativos y funcionen al abrir los archivos con doble clic. Las que
genera este repo llevan el marcador `__ENCABEZADO__` en su plantilla; a las que
vienen hechas (los mapas de folium y el de atipicos del analisis de
distribuciones) se les inserta justo despues de `<body>` en una copia, de modo
que los originales que consume el tablero de Streamlit no cambian.

El encabezado no depende del estilo de cada pagina: lleva sus propias variables
y sigue el tema claro u oscuro de las dos convenciones que hay en el proyecto,
`data-tema` en el mapa principal y `data-theme` en la consulta.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

CARPETA = Path("datos/salidas/web")
MARCADOR = "__ENCABEZADO__"
ALTO = 52  # px; los mapas a pantalla completa lo descuentan de su altura


@dataclass(frozen=True)
class Pagina:
    clave: str
    titulo: str
    href: str
    grupo: str | None = None


PAGINAS = (
    Pagina("mapa", "Mapa", "arriendos_medellin.html"),
    Pagina("buscar", "Buscar arriendo", "consulta_arriendos.html#buscar"),
    Pagina("estadistica", "La estadística", "consulta_arriendos.html#estadistica"),
    Pagina("animacion", "Animación", "animacion.html"),
    Pagina("sobreprecio", "Sobreprecio por barrio", "mapa_sobreprecio.html", "Mapas"),
    Pagina("conglomerados", "Conglomerados", "mapa_conglomerados.html", "Mapas"),
    Pagina("atipicos", "Atípicos aviso por aviso", "mapa_atipicos.html", "Mapas"),
    Pagina("informe_pdf", "Informe en PDF", "../informe_arriendos_medellin.pdf", "Documentos"),
    Pagina("metodologia_pdf", "Metodología en PDF", "../metodologia_arriendos_medellin.pdf", "Documentos"),
)

# Copias de paginas hechas por otros generadores: destino, clave y origen.
COPIAS = (
    ("mapa_sobreprecio.html", "sobreprecio", Path("datos/salidas/mapa_sobreprecio.html")),
    ("mapa_conglomerados.html", "conglomerados", Path("datos/salidas/mapa_conglomerados.html")),
    ("mapa_atipicos.html", "atipicos", Path("analisis-distribuciones/salidas/mapa.html")),
)

# Ajustes por pagina para que el encabezado no tape nada.
CSS_PUNTOS = f"#mapa {{ top: {ALTO}px !important; }}"  # mapas de puntos a pantalla completa
CSS_ATIPICOS = (
    f"#mapa {{ top: {ALTO}px !important; }}"
    f" .panel {{ top: {ALTO + 12}px !important; max-height: calc(100% - {ALTO + 48}px) !important; }}"
)
CSS_POR_CLAVE = {
    "sobreprecio": CSS_PUNTOS,
    "conglomerados": CSS_PUNTOS,
    "atipicos": CSS_ATIPICOS,
    "animacion": f"#escena {{ top: {ALTO}px !important; }}",
}

ESTILO = f"""
.sitio {{
  --s-fondo: rgba(252, 252, 251, .94); --s-borde: #e1e0d9; --s-tinta: #0b0b0b; --s-tinta2: #52514e;
  --s-activo: #2a78d6; --s-menu: #ffffff; --s-hover: #f0efec;
  position: relative; z-index: 3000; height: {ALTO}px; box-sizing: border-box;
  display: flex; align-items: center; gap: 18px; padding: 0 20px;
  background: var(--s-fondo); border-bottom: 1px solid var(--s-borde);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  font: 14px/1.2 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--s-tinta);
}}
.sitio *, .sitio *::before, .sitio *::after {{ box-sizing: border-box; }}
.sitio a {{ color: inherit; text-decoration: none; }}
.sitio-marca {{ font: 600 16px/1 "Iowan Old Style", "Palatino Linotype", Georgia, serif; white-space: nowrap; margin-right: 6px; }}
.sitio-nav {{ display: flex; align-items: center; gap: 2px; height: 100%; }}
.sitio-nav > a, .sitio summary {{
  display: flex; align-items: center; gap: 4px; height: 34px; padding: 0 10px; border-radius: 8px;
  color: var(--s-tinta2); cursor: pointer; white-space: nowrap; list-style: none; user-select: none;
}}
.sitio summary::-webkit-details-marker {{ display: none; }}
.sitio summary::after {{ content: ""; width: 6px; height: 6px; margin-left: 4px; border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor; transform: translateY(-2px) rotate(45deg); }}
.sitio-nav > a:hover, .sitio summary:hover {{ background: var(--s-hover); color: var(--s-tinta); }}
.sitio [aria-current="page"], .sitio summary.activo {{ color: var(--s-tinta); font-weight: 600;
  box-shadow: inset 0 -2px 0 var(--s-activo); border-radius: 8px 8px 0 0; }}
.sitio details {{ position: relative; }}
.sitio-lista {{ position: absolute; top: 40px; left: 0; min-width: 230px; padding: 6px; border-radius: 10px;
  background: var(--s-menu); border: 1px solid var(--s-borde); box-shadow: 0 8px 24px rgba(0,0,0,.14);
  display: flex; flex-direction: column; }}
.sitio-lista a {{ padding: 8px 10px; border-radius: 6px; color: var(--s-tinta2); white-space: nowrap; }}
.sitio-lista a:hover {{ background: var(--s-hover); color: var(--s-tinta); }}
.sitio-lista a[aria-current="page"] {{ box-shadow: none; background: var(--s-hover); }}
.sitio-lista .sitio-grupo {{ font-size: 11px; color: var(--s-tinta2); text-transform: uppercase; letter-spacing: .04em; padding: 8px 10px 4px; }}
.sitio-movil {{ display: none; margin-left: auto; }}
.sitio-movil .sitio-lista {{ left: auto; right: 0; }}
.sitio a:focus-visible, .sitio summary:focus-visible {{ outline: 2px solid var(--s-activo); outline-offset: 2px; }}
@media (max-width: 860px) {{
  .sitio {{ padding: 0 16px; }}
  .sitio-nav {{ display: none; }}
  .sitio-movil {{ display: block; }}
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-tema="claro"]):not([data-theme="light"]) .sitio {{
    --s-fondo: rgba(26, 26, 25, .94); --s-borde: #2f2f2b; --s-tinta: #ffffff; --s-tinta2: #c3c2b7;
    --s-activo: #3987e5; --s-menu: #1f1f1d; --s-hover: #2a2a27;
  }}
}}
:root[data-tema="oscuro"] .sitio, :root[data-theme="dark"] .sitio {{
  --s-fondo: rgba(26, 26, 25, .94); --s-borde: #2f2f2b; --s-tinta: #ffffff; --s-tinta2: #c3c2b7;
  --s-activo: #3987e5; --s-menu: #1f1f1d; --s-hover: #2a2a27;
}}
"""

# Cierra los menus abiertos al tocar fuera de ellos o al elegir una opcion.
GUION = """
(function () {
  const menus = document.querySelectorAll(".sitio details");
  document.addEventListener("click", ev => {
    menus.forEach(m => { if (!m.contains(ev.target) || ev.target.closest(".sitio-lista a")) m.open = false; });
  });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape") menus.forEach(m => { m.open = false; }); });
})();
"""


def _enlace(p: Pagina, activa: str) -> str:
    actual = ' aria-current="page"' if p.clave == activa else ""
    return f'<a href="{html.escape(p.href)}" data-pagina="{p.clave}"{actual}>{html.escape(p.titulo)}</a>'


def _menu(titulo: str, paginas: list[Pagina], activa: str) -> str:
    clase = ' class="activo"' if any(p.clave == activa for p in paginas) else ""
    enlaces = "".join(_enlace(p, activa) for p in paginas)
    return (f'<details><summary{clase}>{html.escape(titulo)}</summary>'
            f'<div class="sitio-lista">{enlaces}</div></details>')


def encabezado(activa: str, css_extra: str = "") -> str:
    """HTML del encabezado con la pagina `activa` marcada."""
    sueltas = [p for p in PAGINAS if p.grupo is None]
    grupos: dict[str, list[Pagina]] = {}
    for p in PAGINAS:
        if p.grupo:
            grupos.setdefault(p.grupo, []).append(p)

    nav = "".join(_enlace(p, activa) for p in sueltas)
    nav += "".join(_menu(nombre, paginas, activa) for nombre, paginas in grupos.items())

    # En pantallas angostas todo va en un solo menu, agrupado.
    movil = "".join(_enlace(p, activa) for p in sueltas)
    for nombre, paginas in grupos.items():
        movil += f'<div class="sitio-grupo">{html.escape(nombre)}</div>'
        movil += "".join(_enlace(p, activa) for p in paginas)

    return (
        f"<style>{ESTILO}{css_extra}</style>"
        '<header class="sitio">'
        '<a class="sitio-marca" href="arriendos_medellin.html">Arriendos en Medellín</a>'
        f'<nav class="sitio-nav" aria-label="Páginas del proyecto">{nav}</nav>'
        f'<details class="sitio-movil"><summary>Páginas</summary><div class="sitio-lista">{movil}</div></details>'
        f"</header><script>{GUION}</script>"
    )


def insertar(documento: str, activa: str, css_extra: str | None = None) -> str:
    """Pone el encabezado en el marcador o, si no lo hay, justo despues de `<body>`."""
    bloque = encabezado(activa, CSS_POR_CLAVE.get(activa, "") if css_extra is None else css_extra)
    if MARCADOR in documento:
        return documento.replace(MARCADOR, bloque, 1)
    cuerpo = re.search(r"<body[^>]*>", documento, flags=re.IGNORECASE)
    if not cuerpo:
        raise ValueError("el documento no tiene marcador ni etiqueta <body>")
    return documento[: cuerpo.end()] + bloque + documento[cuerpo.end():]


def copiar_con_encabezado(origen: Path, destino: Path, activa: str) -> Path:
    documento = origen.read_text(encoding="utf-8")
    # Folium no pone titulo, y la pestana del navegador mostraria la ruta.
    if not re.search(r"<title>", documento, flags=re.IGNORECASE):
        titulo = next((p.titulo for p in PAGINAS if p.clave == activa), "Arriendos en Medellín")
        documento = re.sub(r"<head[^>]*>", lambda m: f"{m.group(0)}<title>{html.escape(titulo)}</title>",
                           documento, count=1, flags=re.IGNORECASE)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(insertar(documento, activa), encoding="utf-8")
    return destino


def construir(carpeta: Path = CARPETA, regenerar: bool = True) -> list[Path]:
    """Deja todas las paginas en `carpeta`, conectadas por el encabezado.

    Con `regenerar` rehace el mapa principal y la consulta desde sus datos; los mapas se
    copian tal como esten en disco. Una fuente que falta se avisa y se salta.
    """
    hechas: list[Path] = []
    if regenerar:
        from . import generar_animacion, generar_consulta, pagina

        hechas.append(pagina.construir(carpeta / "arriendos_medellin.html"))
        hechas.append(generar_consulta.construir(carpeta / "consulta_arriendos.html"))
        hechas.append(generar_animacion.construir(carpeta / "animacion.html"))

    for nombre, clave, origen in COPIAS:
        if not origen.exists():
            print(f"  falta {origen}, se omite {nombre}")
            continue
        hechas.append(copiar_con_encabezado(origen, carpeta / nombre, clave))

    for pdf in ("informe_arriendos_medellin.pdf", "metodologia_arriendos_medellin.pdf"):
        if not (carpeta.parent / pdf).exists():
            print(f"  falta {carpeta.parent / pdf}: su enlace en el encabezado quedara roto")
    return hechas


if __name__ == "__main__":
    for ruta in construir():
        print(f"  {ruta}")
