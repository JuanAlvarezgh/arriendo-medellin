"""Distingue paginas de aviso de paginas de listado o categoria.

Es el problema real del descubrimiento: una sonda ingenua toma una pagina de
categoria por una de aviso y extrae basura. Se decide con dos senales
independientes, forma de URL y contenido, y se calibra sola por dominio.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Un aviso tiene un precio dominante. Un listado tiene muchos.
_PRECIO = re.compile(r"\$\s?\d{1,3}(?:[.,]\d{3}){1,3}")
_AREA = re.compile(r"\d+(?:[.,]\d+)?\s*(?:m2|m²|mts2)", re.I)
_ALCOBAS = re.compile(r"\d+\s*(?:habitacion|alcoba|dormitorio)", re.I)

_PISTAS_LISTADO = re.compile(
    r"/buscar|/busqueda|/resultados|/search|/listado|/categoria|"
    r"[?&](?:page|pagina|p)=\d+",
    re.I,
)
_PISTAS_AVISO = re.compile(
    r"/inmueble|/propiedad|/aviso|/detalle|/property|/listing", re.I
)


@dataclass
class PerfilUrl:
    """Lo que el clasificador va aprendiendo de un dominio."""

    dominio: str
    patrones_aviso: Counter = field(default_factory=Counter)
    patrones_listado: Counter = field(default_factory=Counter)
    confirmados: int = 0

    def firma(self, url: str) -> str:
        """Reduce una URL a su forma: /a/b/123 -> /txt/txt/num."""
        ruta = urlparse(url).path.strip("/")
        if not ruta:
            return "/"
        partes = []
        for seg in ruta.split("/"):
            if seg.isdigit():
                partes.append("num")
            elif re.fullmatch(r"[0-9a-f]{8,}", seg, re.I):
                partes.append("hash")
            elif re.search(r"\d", seg):
                partes.append("mixto")
            else:
                partes.append("txt")
        return "/" + "/".join(partes)

    def aprender(self, url: str, es_aviso: bool) -> None:
        f = self.firma(url)
        if es_aviso:
            self.patrones_aviso[f] += 1
            self.confirmados += 1
        else:
            self.patrones_listado[f] += 1

    def predecir(self, url: str) -> bool | None:
        """None significa que aun no hay evidencia suficiente."""
        if self.confirmados < 20:
            return None
        f = self.firma(url)
        a = self.patrones_aviso.get(f, 0)
        l = self.patrones_listado.get(f, 0)
        if a == 0 and l == 0:
            return None
        return a > l

    def patron_dominante(self) -> str | None:
        if not self.patrones_aviso:
            return None
        return self.patrones_aviso.most_common(1)[0][0]


def senal_forma(url: str) -> float:
    """Puntaje por forma de URL. Positivo sugiere aviso, negativo listado."""
    p = 0.0
    ruta = urlparse(url).path
    consulta = urlparse(url).query

    if _PISTAS_AVISO.search(url):
        p += 2.0
    if _PISTAS_LISTADO.search(url):
        p -= 2.5

    # Un identificador numerico largo al final es firma casi segura de detalle
    if re.search(r"/\d{5,}/?$", ruta):
        p += 2.0
    elif re.search(r"-\d{4,}/?$", ruta):
        p += 1.0

    profundidad = len([s for s in ruta.split("/") if s])
    if profundidad >= 2:
        p += 0.5
    if profundidad <= 1:
        p -= 1.0

    # Los listados suelen llevar parametros de filtro
    if consulta:
        p -= 0.5

    return p


def senal_contenido(html: str) -> float:
    """Puntaje por contenido. Un aviso tiene un precio dominante; un listado, muchos."""
    if not html:
        return 0.0

    precios = len(_PRECIO.findall(html))
    areas = len(_AREA.findall(html))
    alcobas = len(_ALCOBAS.findall(html))

    p = 0.0

    if precios == 0:
        p -= 1.0
    elif precios <= 3:
        p += 2.0
    elif precios <= 8:
        p += 0.5
    else:
        p -= 2.0

    if 0 < areas <= 4:
        p += 1.0
    elif areas > 12:
        p -= 1.5

    if alcobas > 20:
        p -= 1.5

    # Marcado de detalle segun schema.org
    if re.search(r'"@type"\s*:\s*"?\[?[^]]*(?:RealEstateListing|SingleFamilyResidence|Apartment)', html):
        p += 2.5
    if re.search(r'"@type"\s*:\s*"ItemList"', html):
        p -= 1.0

    return p


def es_aviso(
    url: str, html: str | None = None, perfil: PerfilUrl | None = None
) -> tuple[bool, float]:
    """Decide si la URL corresponde a un aviso. Devuelve (decision, confianza)."""
    if perfil is not None:
        aprendido = perfil.predecir(url)
        if aprendido is not None:
            return aprendido, 0.9

    puntaje = senal_forma(url)
    if html:
        puntaje += senal_contenido(html)

    confianza = min(abs(puntaje) / 5.0, 1.0)
    return puntaje > 0.5, confianza
