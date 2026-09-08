"""Capa d: lectura heuristica del HTML cuando no hay nada estructurado.

Dos tecnicas: proximidad etiqueta-valor, que es como los portales presentan la
ficha tecnica, y patrones sobre el texto visible. Es la capa con mas ruido, asi
que cada valor se acota a rangos plausibles antes de aceptarse.
"""

from __future__ import annotations

import re
from typing import Any

from selectolax.parser import HTMLParser

from ..normalizacion.area import (
    parsear_alcobas,
    parsear_area,
    parsear_banos,
    parsear_estrato,
    parsear_parqueaderos,
    parsear_piso,
)
from ..normalizacion.moneda import parsear_precio

# Etiquetas que los portales colombianos usan en la ficha tecnica
ETIQUETAS = {
    "area_privada": (r"[aá]rea\s+privada", r"[aá]rea\b", r"superficie"),
    "area_construida": (r"[aá]rea\s+construida", r"construidos?"),
    "alcobas": (r"habitaciones", r"alcobas", r"dormitorios", r"cuartos"),
    "banos": (r"ba[nñ]os"),
    "parqueaderos": (r"parqueaderos", r"garajes", r"estacionamientos"),
    "estrato": (r"estrato",),
    "piso": (r"piso\s*n[°ºo]?", r"\bpiso\b"),
    "administracion": (r"administraci[oó]n", r"expensas"),
    "precio": (r"canon", r"valor\s+arriendo", r"precio", r"arriendo"),
}

_ETIQUETAS_COMPILADAS = {
    campo: [re.compile(p, re.I) for p in (pats if isinstance(pats, tuple) else (pats,))]
    for campo, pats in ETIQUETAS.items()
}

_NUMERO = re.compile(r"-?\d[\d.,]*")

_BASURA = re.compile(r"^(script|style|noscript|svg|head|iframe)$", re.I)


def texto_visible(html: str) -> str:
    """Texto de la pagina sin scripts ni estilos, con separadores preservados."""
    arbol = HTMLParser(html)
    for nodo in arbol.css("script, style, noscript, svg, iframe"):
        nodo.decompose()
    cuerpo = arbol.body or arbol.root
    if cuerpo is None:
        return ""
    txt = cuerpo.text(separator=" | ", strip=True)
    return re.sub(r"\s+", " ", txt)


def pares_etiqueta_valor(html: str) -> dict[str, str]:
    """Recoge pares del tipo 'Estrato: 5' presentes en la ficha tecnica.

    Recorre elementos hoja y mira el texto del hermano siguiente, que es como
    se maqueta una ficha en la practica: <span>Estrato</span><span>5</span>.
    """
    arbol = HTMLParser(html)
    for nodo in arbol.css("script, style, noscript"):
        nodo.decompose()

    pares: dict[str, str] = {}

    for nodo in arbol.css("li, tr, div, span, p, dt, td, th"):
        propio = nodo.text(deep=False, strip=True)
        if not propio or len(propio) > 40:
            continue

        valor = None
        # Forma 1: 'Etiqueta: valor' en el mismo nodo
        completo = nodo.text(strip=True)
        if ":" in completo and len(completo) < 90:
            izq, _, der = completo.partition(":")
            if der.strip() and len(izq) <= 40:
                pares.setdefault(izq.strip().lower(), der.strip())
                continue

        # Forma 2: el valor esta en el hermano siguiente
        hermano = nodo.next
        while hermano is not None and hermano.tag in ("-text", None):
            hermano = hermano.next
        if hermano is not None and not _BASURA.match(hermano.tag or ""):
            texto_hermano = hermano.text(strip=True)
            if texto_hermano and len(texto_hermano) < 60:
                valor = texto_hermano

        if valor:
            pares.setdefault(propio.strip().lower(), valor)

    return pares


def _buscar_en_pares(pares: dict[str, str], campo: str) -> str | None:
    patrones = _ETIQUETAS_COMPILADAS.get(campo, [])
    for etiqueta, valor in pares.items():
        for p in patrones:
            if p.search(etiqueta):
                return valor
    return None


def extraer(html: str, url: str = "") -> dict[str, Any] | None:
    """Devuelve campos canonicos leidos del HTML por heuristica."""
    if not html:
        return None

    pares = pares_etiqueta_valor(html)
    visible = texto_visible(html)
    campos: dict[str, Any] = {}

    # Primero la ficha tecnica, que es la fuente mas confiable del HTML
    crudo_area = _buscar_en_pares(pares, "area_privada")
    if crudo_area:
        campos["area_privada"] = parsear_area(crudo_area) or _solo_numero(crudo_area, 5, 5000)

    crudo_construida = _buscar_en_pares(pares, "area_construida")
    if crudo_construida:
        campos["area_construida"] = parsear_area(crudo_construida) or _solo_numero(
            crudo_construida, 5, 5000
        )

    for campo, tope in (("alcobas", 20), ("banos", 20), ("parqueaderos", 20), ("piso", 60)):
        crudo = _buscar_en_pares(pares, campo)
        if crudo:
            v = _solo_numero(crudo, 1, tope)
            if v is not None:
                campos[campo] = int(v)

    crudo_estrato = _buscar_en_pares(pares, "estrato")
    if crudo_estrato:
        v = _solo_numero(crudo_estrato, 1, 6)
        if v is not None:
            campos["estrato"] = int(v)

    crudo_precio = _buscar_en_pares(pares, "precio")
    if crudo_precio:
        monto, moneda = parsear_precio(crudo_precio)
        if monto:
            campos["precio"] = monto
            campos["moneda"] = moneda

    crudo_admin = _buscar_en_pares(pares, "administracion")
    if crudo_admin:
        monto, _ = parsear_precio(crudo_admin)
        if monto:
            campos["administracion"] = monto

    # Lo que falte, del texto visible
    if campos.get("precio") is None:
        monto, moneda = parsear_precio(visible)
        if monto:
            campos["precio"] = monto
            campos["moneda"] = moneda

    for campo, funcion in (
        ("area_privada", parsear_area),
        ("alcobas", parsear_alcobas),
        ("banos", parsear_banos),
        ("parqueaderos", parsear_parqueaderos),
        ("estrato", parsear_estrato),
        ("piso", parsear_piso),
    ):
        if campos.get(campo) is None:
            v = funcion(visible)
            if v is not None:
                campos[campo] = v

    titulo = _titulo(html)
    if titulo:
        campos["titulo"] = titulo

    descripcion = _descripcion(html, visible)
    if descripcion:
        campos["descripcion"] = descripcion

    campos = {k: v for k, v in campos.items() if v is not None}
    return campos or None


def _solo_numero(texto: str, minimo: float, maximo: float) -> float | None:
    m = _NUMERO.search(texto)
    if not m:
        return None
    s = m.group().rstrip(".,")
    s = s.replace(".", "").replace(",", ".") if s.count(".") > 1 else s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if minimo <= v <= maximo else None


def _titulo(html: str) -> str | None:
    arbol = HTMLParser(html)
    for selector in ("h1", "title"):
        nodo = arbol.css_first(selector)
        if nodo:
            t = nodo.text(strip=True)
            if t:
                return t[:300]
    return None


def _descripcion(html: str, visible: str) -> str | None:
    arbol = HTMLParser(html)
    meta = arbol.css_first('meta[name="description"]')
    if meta:
        c = meta.attributes.get("content")
        if c and len(c) > 40:
            return c[:4000]
    # El bloque de texto corrido mas largo suele ser la descripcion del aviso
    bloques = [b.strip() for b in visible.split(" | ") if len(b.strip()) > 120]
    return max(bloques, key=len)[:4000] if bloques else None
