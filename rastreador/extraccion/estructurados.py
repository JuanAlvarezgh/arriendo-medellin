"""Capa a: datos estructurados declarados por la propia pagina.

ld+json, microdata, RDFa y OpenGraph. Es la capa mas portable de todas: no
depende del framework ni del maquetado, solo de que el sitio publique marcado
para buscadores, cosa que casi todo portal inmobiliario hace por SEO.
"""

from __future__ import annotations

import json
import re
from typing import Any

import extruct

TIPOS_INMUEBLE = {
    "realestatelisting",
    "singlefamilyresidence",
    "apartment",
    "house",
    "residence",
    "accommodation",
    "product",
    "offer",
}


def _tipos(obj: dict[str, Any]) -> set[str]:
    t = obj.get("@type") or obj.get("type")
    if t is None:
        return set()
    if isinstance(t, str):
        return {t.lower()}
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return set()


def _aplanar(nodo: Any, acumulador: list[dict[str, Any]]) -> None:
    if isinstance(nodo, dict):
        acumulador.append(nodo)
        for v in nodo.values():
            _aplanar(v, acumulador)
    elif isinstance(nodo, list):
        for v in nodo:
            _aplanar(v, acumulador)


def _numero(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for k in ("value", "amount", "price"):
            if k in v:
                return _numero(v[k])
        return None
    if isinstance(v, str):
        s = re.sub(r"[^\d.,]", "", v)
        s = s.replace(".", "").replace(",", ".") if s.count(".") > 1 else s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _texto(v: Any) -> str | None:
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, dict):
        for k in ("name", "text", "value", "@value"):
            if k in v:
                return _texto(v[k])
    if isinstance(v, list) and v:
        return _texto(v[0])
    return None


def extraer(html: str, url: str = "") -> dict[str, Any] | None:
    """Devuelve campos canonicos desde el marcado estructurado, o None."""
    try:
        datos = extruct.extract(
            html, base_url=url or None, syntaxes=["json-ld", "microdata", "opengraph", "rdfa"]
        )
    except Exception:
        return None

    nodos: list[dict[str, Any]] = []
    for sintaxis in ("json-ld", "microdata", "rdfa"):
        _aplanar(datos.get(sintaxis, []), nodos)

    candidatos = [n for n in nodos if _tipos(n) & TIPOS_INMUEBLE]
    if not candidatos:
        candidatos = nodos

    campos: dict[str, Any] = {}

    for n in candidatos:
        # Precio: puede venir en offers.price o directamente
        if campos.get("precio") is None:
            for clave in ("price", "priceSpecification"):
                if clave in n:
                    v = _numero(n[clave])
                    if v:
                        campos["precio"] = v
                        break
            ofertas = n.get("offers")
            if campos.get("precio") is None and ofertas:
                lista = ofertas if isinstance(ofertas, list) else [ofertas]
                for o in lista:
                    if isinstance(o, dict):
                        v = _numero(o.get("price") or o.get("priceSpecification"))
                        if v:
                            campos["precio"] = v
                            campos.setdefault(
                                "moneda", _texto(o.get("priceCurrency")) or "COP"
                            )
                            break

        if campos.get("titulo") is None:
            campos["titulo"] = _texto(n.get("name")) or _texto(n.get("headline"))
        if campos.get("descripcion") is None:
            campos["descripcion"] = _texto(n.get("description"))

        # Ubicacion
        direccion = n.get("address")
        if direccion and campos.get("direccion") is None:
            if isinstance(direccion, dict):
                partes = [
                    _texto(direccion.get(k))
                    for k in ("streetAddress", "addressLocality", "addressRegion")
                ]
                unido = ", ".join(p for p in partes if p)
                campos["direccion"] = unido or None
            else:
                campos["direccion"] = _texto(direccion)

        geo = n.get("geo")
        if isinstance(geo, dict):
            if campos.get("latitud") is None:
                campos["latitud"] = _numero(geo.get("latitude"))
            if campos.get("longitud") is None:
                campos["longitud"] = _numero(geo.get("longitude"))

        # Dimensiones y conteos segun vocabulario schema.org
        if campos.get("area_privada") is None:
            for clave in ("floorSize", "size"):
                if clave in n:
                    v = _numero(n[clave])
                    if v:
                        campos["area_privada"] = v
                        break
        if campos.get("alcobas") is None:
            v = _numero(n.get("numberOfRooms") or n.get("numberOfBedrooms"))
            if v:
                campos["alcobas"] = int(v)
        if campos.get("banos") is None:
            v = _numero(
                n.get("numberOfBathroomsTotal") or n.get("numberOfFullBathrooms")
            )
            if v:
                campos["banos"] = int(v)

    # OpenGraph como ultimo recurso para titulo y descripcion
    og = datos.get("opengraph") or []
    for bloque in og:
        props = dict(bloque.get("properties", []))
        campos.setdefault("titulo", props.get("og:title"))
        campos.setdefault("descripcion", props.get("og:description"))

    campos = {k: v for k, v in campos.items() if v is not None}
    return campos or None


def tipos_declarados(html: str) -> list[str]:
    """Diagnostico: que tipos de schema.org declara la pagina."""
    try:
        datos = extruct.extract(html, syntaxes=["json-ld"])
    except Exception:
        return []
    nodos: list[dict[str, Any]] = []
    _aplanar(datos.get("json-ld", []), nodos)
    vistos: list[str] = []
    for n in nodos:
        for t in _tipos(n):
            if t not in vistos:
                vistos.append(t)
    return vistos
