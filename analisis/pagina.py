"""Genera la pagina del tablero como un unico archivo HTML autocontenido.

Los datos van embebidos en el propio archivo, no en un .json aparte, porque un
HTML abierto con doble clic usa file:// y ahi el navegador bloquea `fetch` sobre
archivos locales. Con todo dentro, la pagina se abre sin servidor.

Por la misma razon se empotra Leaflet en vez de enlazarlo a un CDN: la pagina se
entrega como archivo y tiene que seguir funcionando dentro de un ano, cuando la
version que enlazamos ya no este donde estaba. Lo unico que queda saliendo a la
red son las teselas del mapa base, que por naturaleza no se pueden empotrar.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PLANTILLA = RAIZ / "web" / "plantilla.html"
GUION = RAIZ / "web" / "guion.js"
BIBLIOTECAS = RAIZ / "web" / "bibliotecas"
SALIDA = Path("datos/salidas/web/arriendos_medellin.html")

# Version fija. Una version flotante convierte una pagina que hoy funciona en
# una que manana puede no hacerlo, sin que nadie haya tocado nada.
LEAFLET = "1.9.4"
FUENTES = {
    "leaflet.css": f"https://unpkg.com/leaflet@{LEAFLET}/dist/leaflet.css",
    "leaflet.js": f"https://unpkg.com/leaflet@{LEAFLET}/dist/leaflet.js",
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


def _estilo_leaflet() -> str:
    """La hoja de Leaflet, sin las rutas a imagenes que no usamos.

    Leaflet pide `images/marker-icon.png` y `images/layers.png` para marcadores y
    para el selector de capas. Este mapa no lleva ninguno de los dos, y esas
    rutas relativas, en un archivo abierto con file://, se resolverian contra la
    carpeta del usuario y ensuciarian la consola con errores 404.
    """
    css = biblioteca("leaflet.css")
    return css.replace("url(images/", "url(#sin-imagen-")


def construir(salida: Path = SALIDA) -> Path:
    from .carga_web import construir as construir_datos

    plantilla = PLANTILLA.read_text(encoding="utf-8")
    guion = GUION.read_text(encoding="utf-8")
    datos = construir_datos()

    # separators sin espacios: ahorra decenas de kilobytes en 1.551 celdas
    serializado = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))

    # </script> dentro de una cadena JSON cerraria la etiqueta antes de tiempo
    serializado = serializado.replace("</", "<\\/")

    html = (
        plantilla.replace("__ESTILO_LEAFLET__", _estilo_leaflet())
        .replace("__LEAFLET__", biblioteca("leaflet.js"))
        .replace("__DATOS__", serializado)
        .replace("__GUION__", guion)
    )

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")
    return salida


if __name__ == "__main__":
    ruta = construir()
    print(f"escrito en {ruta}  ({ruta.stat().st_size/1024:.0f} KB)")
