"""Genera la pagina del tablero como un unico archivo HTML autocontenido.

Los datos van embebidos en el propio archivo, no en un .json aparte, porque un
HTML abierto con doble clic usa file:// y ahi el navegador bloquea `fetch` sobre
archivos locales. Con todo dentro, la pagina se abre sin servidor.

Por la misma razon se empotra MapLibre en vez de enlazarlo a un CDN: la pagina se
entrega como archivo y tiene que seguir funcionando dentro de un ano, cuando la
version que enlazamos ya no este donde estaba. Lo unico que queda saliendo a la
red son las teselas del mapa base, que por naturaleza no se pueden empotrar.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .sitio import insertar

RAIZ = Path(__file__).resolve().parent
PLANTILLA = RAIZ / "web" / "plantilla.html"
GUION = RAIZ / "web" / "guion.js"
MAPA_SATELITE = RAIZ / "web" / "mapa_satelite.js"
BIBLIOTECAS = RAIZ / "web" / "bibliotecas"
SALIDA = Path("datos/salidas/web/arriendos_medellin.html")

# Version fija. Una version flotante convierte una pagina que hoy funciona en
# una que manana puede no hacerlo, sin que nadie haya tocado nada.
MAPLIBRE = "4.7.1"
FUENTES = {
    "maplibre-gl.css": f"https://unpkg.com/maplibre-gl@{MAPLIBRE}/dist/maplibre-gl.css",
    "maplibre-gl.js": f"https://unpkg.com/maplibre-gl@{MAPLIBRE}/dist/maplibre-gl.js",
}


def biblioteca(nombre: str) -> str:
    """Devuelve el contenido de una biblioteca, descargandola la primera vez.

    Se guarda en disco para que las siguientes construcciones no dependan de la
    red. Si no esta y no hay red, se lanza el error: es preferible que falle la
    construccion a publicar una pagina con un mapa mudo.
    """
    destino = BIBLIOTECAS / nombre
    if destino.exists():
        return destino.read_text(encoding="utf-8")

    destino.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(FUENTES[nombre], timeout=60) as r:
        contenido = r.read().decode("utf-8")
    destino.write_text(contenido, encoding="utf-8")
    return contenido


def construir(salida: Path = SALIDA) -> Path:
    from .carga_web import construir as construir_datos

    plantilla = PLANTILLA.read_text(encoding="utf-8")
    guion = GUION.read_text(encoding="utf-8")
    datos = construir_datos()

    # separators sin espacios: ahorra cientos de kilobytes en treinta mil puntos
    serializado = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))

    # </script> dentro de una cadena JSON cerraria la etiqueta antes de tiempo
    serializado = serializado.replace("</", "<\\/")

    html = (
        plantilla.replace("__ESTILO_MAPLIBRE__", biblioteca("maplibre-gl.css"))
        .replace("__MAPLIBRE__", biblioteca("maplibre-gl.js"))
        .replace("__MAPA_SATELITE__", MAPA_SATELITE.read_text(encoding="utf-8"))
        .replace("__DATOS__", serializado)
        .replace("__GUION__", guion)
    )
    html = insertar(html, "mapa")

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")
    return salida


if __name__ == "__main__":
    ruta = construir()
    print(f"escrito en {ruta}  ({ruta.stat().st_size/1024:.0f} KB)")
