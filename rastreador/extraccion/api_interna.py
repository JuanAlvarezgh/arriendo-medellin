"""Capa api: consumo de la API interna que alimenta al portal.

Cuando un portal es una aplicacion de una sola pagina, el HTML no trae datos:
los pide por XHR. Descubrir ese endpoint una vez y llamarlo directamente es un
orden de magnitud mas barato que renderizar cada aviso en un navegador.

El descubrimiento usa Playwright, que es opcional. El consumo, no: una vez el
endpoint esta en el perfil del sitio, basta httpx.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .estado_js import SINONIMOS, por_ruta, _valor_por_sinonimo

# Un JSON de aviso tiene precio y alguna medida. Se usa para reconocerlo
# entre todas las respuestas de red que emite la pagina.
_CLAVES_PRECIO = set(SINONIMOS["precio"])
_CLAVES_MEDIDA = set(SINONIMOS["area_privada"]) | set(SINONIMOS["alcobas"])


@dataclass
class Hallazgo:
    """Un endpoint candidato descubierto durante la observacion."""

    url: str
    metodo: str = "GET"
    ruta_items: str = ""
    muestra: dict[str, Any] | None = None
    cantidad_items: int = 0
    cuerpo_peticion: dict[str, Any] | None = None


def _puntuar_objeto(obj: Any) -> int:
    if not isinstance(obj, dict):
        return 0
    claves = {k.lower() for k in obj.keys()}
    puntaje = sum(1 for sinonimos in SINONIMOS.values() if claves & set(sinonimos))
    if not (claves & _CLAVES_PRECIO):
        return 0
    if not (claves & _CLAVES_MEDIDA):
        return 0
    return puntaje


def buscar_lista_de_avisos(datos: Any, prefijo: str = "", prof: int = 0) -> tuple[str, list, int]:
    """Encuentra la lista de avisos dentro de una respuesta JSON.

    Devuelve (ruta, lista, puntaje). La ruta sirve para escribirla en el perfil.
    """
    mejor: tuple[str, list, int] = ("", [], 0)
    if prof > 6:
        return mejor

    if isinstance(datos, list):
        if datos and isinstance(datos[0], dict):
            p = _puntuar_objeto(datos[0])
            if p > mejor[2]:
                mejor = (prefijo, datos, p)
        return mejor

    if isinstance(datos, dict):
        for k, v in datos.items():
            ruta = f"{prefijo}.{k}" if prefijo else k
            sub = buscar_lista_de_avisos(v, ruta, prof + 1)
            if sub[2] > mejor[2]:
                mejor = sub
    return mejor


def analizar_respuesta(url: str, cuerpo: str) -> Hallazgo | None:
    """Decide si una respuesta de red contiene avisos."""
    if not cuerpo or len(cuerpo) < 40:
        return None
    try:
        datos = json.loads(cuerpo)
    except (json.JSONDecodeError, ValueError):
        return None

    ruta, lista, puntaje = buscar_lista_de_avisos(datos)
    if puntaje >= 3 and lista:
        return Hallazgo(
            url=url,
            ruta_items=ruta,
            muestra=lista[0] if isinstance(lista[0], dict) else None,
            cantidad_items=len(lista),
        )

    # Respuesta de un solo aviso, no de una lista
    if _puntuar_objeto(datos) >= 4:
        return Hallazgo(url=url, ruta_items="", muestra=datos, cantidad_items=1)
    return None


async def descubrir(url_inicial: str, *, espera_ms: int = 6000) -> list[Hallazgo]:
    """Abre la pagina con Playwright y observa que peticiones JSON hace.

    Requiere `pip install playwright && playwright install chromium`. Si no
    esta disponible, devuelve lista vacia en vez de fallar: el resto de la
    cascada sigue funcionando.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    hallazgos: list[Hallazgo] = []
    vistos: set[str] = set()

    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=True)
        pagina = await navegador.new_page()

        async def al_responder(respuesta) -> None:
            tipo = (respuesta.headers or {}).get("content-type", "")
            if "json" not in tipo.lower():
                return
            if respuesta.url in vistos:
                return
            vistos.add(respuesta.url)
            try:
                cuerpo = await respuesta.text()
            except Exception:
                return
            h = analizar_respuesta(respuesta.url, cuerpo)
            if h:
                h.metodo = respuesta.request.method
                try:
                    datos_peticion = respuesta.request.post_data
                    if datos_peticion:
                        h.cuerpo_peticion = json.loads(datos_peticion)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                hallazgos.append(h)

        pagina.on("response", al_responder)
        try:
            await pagina.goto(url_inicial, wait_until="networkidle", timeout=45_000)
            await pagina.wait_for_timeout(espera_ms)
        except Exception:
            pass
        finally:
            await navegador.close()

    # El mejor candidato es el que trae mas avisos
    hallazgos.sort(key=lambda h: h.cantidad_items, reverse=True)
    return hallazgos


def extraer_de_item(item: dict[str, Any], mapeo: dict[str, str] | None = None) -> dict[str, Any]:
    """Convierte un elemento de la API a campos canonicos."""
    campos: dict[str, Any] = {}
    if mapeo:
        for canonico, ruta in mapeo.items():
            v = por_ruta(item, ruta)
            if v is not None:
                campos[canonico] = v
    for canonico in SINONIMOS:
        if campos.get(canonico) is None:
            v = _valor_por_sinonimo(item, canonico)
            if v is not None:
                campos[canonico] = v
    return campos


def extraer(cuerpo_json: str, mapeo: dict[str, str] | None = None) -> dict[str, Any] | None:
    """Extrae campos canonicos de la respuesta JSON de un aviso individual."""
    try:
        datos = json.loads(cuerpo_json)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(datos, dict):
        return None
    campos = extraer_de_item(datos, mapeo)
    return campos or None
