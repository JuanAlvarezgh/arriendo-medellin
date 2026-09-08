"""Descubrimiento de URLs por sitemap declarado en robots.txt.

Es la via de entrada preferida: la declara el propio sitio, evita paginar a
ciegas y trae 'lastmod', que sirve como senal temporal por aviso.
"""

from __future__ import annotations

import gzip
import io
import re
from dataclasses import dataclass
from datetime import date

from ..descarga.cliente import Cliente, ErrorDescarga
from ..normalizacion.esquema import a_fecha

_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_URL_BLOQUE = re.compile(r"<url>(.*?)</url>", re.I | re.S)
_LASTMOD = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.I | re.S)
_ES_INDICE = re.compile(r"<sitemapindex", re.I)


@dataclass(frozen=True)
class UrlDescubierta:
    url: str
    modificado: date | None = None
    origen: str = ""


def _descomprimir_si_hace_falta(texto: str, url: str) -> str:
    if not url.endswith(".gz"):
        return texto
    try:
        crudo = texto.encode("latin-1", "ignore")
        return gzip.GzipFile(fileobj=io.BytesIO(crudo)).read().decode("utf-8", "replace")
    except (OSError, EOFError):
        return texto


async def sitemaps_declarados(cliente: Cliente, dominio: str) -> list[str]:
    """Lee robots.txt y devuelve las URLs de sitemap que declara."""
    for base in (f"https://www.{dominio}", f"https://{dominio}"):
        try:
            r = await cliente.obtener(f"{base}/robots.txt")
        except ErrorDescarga:
            continue
        if r.ok:
            hallados = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.texto)
            if hallados:
                return hallados
    return []


async def leer_sitemap(
    cliente: Cliente, url: str, *, profundidad: int = 0, tope_profundidad: int = 3
) -> tuple[list[str], list[UrlDescubierta]]:
    """Devuelve (indices hijos, urls). Un sitemap es indice o listado, no ambos."""
    if profundidad > tope_profundidad:
        return [], []
    try:
        r = await cliente.obtener(url)
    except ErrorDescarga:
        return [], []
    if not r.ok:
        return [], []

    xml = _descomprimir_si_hace_falta(r.texto, url)

    if _ES_INDICE.search(xml):
        return _LOC.findall(xml), []

    urls: list[UrlDescubierta] = []
    bloques = _URL_BLOQUE.findall(xml)
    if bloques:
        for bloque in bloques:
            loc = _LOC.search(bloque)
            if not loc:
                continue
            lm = _LASTMOD.search(bloque)
            urls.append(
                UrlDescubierta(
                    url=loc.group(1),
                    modificado=a_fecha(lm.group(1)) if lm else None,
                    origen=url,
                )
            )
    else:
        # Sitemap sin bloques <url>, solo <loc> sueltos
        urls = [UrlDescubierta(url=u, origen=url) for u in _LOC.findall(xml)]
    return [], urls


async def recorrer_sitemaps(
    cliente: Cliente,
    dominio: str,
    *,
    filtro_sitemap: re.Pattern[str] | None = None,
    filtro_url: re.Pattern[str] | None = None,
    tope: int | None = None,
) -> list[UrlDescubierta]:
    """Recorre el arbol de sitemaps de un dominio y devuelve las URLs que pasan filtro.

    `filtro_sitemap` evita descargar ramas enteras que no interesan, que es lo
    que hace viable trabajar con indices de cientos de miles de URLs.
    """
    raices = await sitemaps_declarados(cliente, dominio)
    if not raices:
        for tentativa in (f"https://www.{dominio}/sitemap.xml", f"https://{dominio}/sitemap.xml"):
            try:
                r = await cliente.obtener(tentativa)
                if r.ok and "<" in r.texto:
                    raices = [tentativa]
                    break
            except ErrorDescarga:
                continue

    pendientes = list(raices)
    vistos: set[str] = set()
    resultado: list[UrlDescubierta] = []
    profundidad: dict[str, int] = {u: 0 for u in raices}

    while pendientes:
        sm = pendientes.pop(0)
        if sm in vistos:
            continue
        vistos.add(sm)

        hijos, urls = await leer_sitemap(cliente, sm, profundidad=profundidad.get(sm, 0))

        for h in hijos:
            if h in vistos:
                continue
            if filtro_sitemap and not filtro_sitemap.search(h):
                continue
            profundidad[h] = profundidad.get(sm, 0) + 1
            pendientes.append(h)

        for u in urls:
            if filtro_url and not filtro_url.search(u.url):
                continue
            resultado.append(u)
            if tope and len(resultado) >= tope:
                return resultado

    return resultado
