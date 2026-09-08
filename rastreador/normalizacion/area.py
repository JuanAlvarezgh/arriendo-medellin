"""Interpretacion de areas y conteos de habitaciones en texto libre."""

from __future__ import annotations

import re

from .moneda import _limpiar_numero

_UNIDAD = r"(?:m2|m²|mts2|mts²|mt2|metros?\s*cuadrados?|metros?²)"

_PATRON_AREA = re.compile(rf"(\d+(?:[.,]\d+)?)\s*{_UNIDAD}", re.IGNORECASE)
_PATRON_AREA_INVERSO = re.compile(
    rf"(?:[aá]rea|superficie)\s*(?:privada|construida|total)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

_PATRON_ALCOBAS = re.compile(
    r"(\d+)\s*(?:habitaci[oó]n(?:es)?|alcobas?|dormitorios?|cuartos?|hab\b|alc\b)",
    re.IGNORECASE,
)
_PATRON_ALCOBAS_INV = re.compile(
    r"(?:habitaci[oó]n(?:es)?|alcobas?|dormitorios?)\s*[:\-]?\s*(\d+)", re.IGNORECASE
)

_PATRON_BANOS = re.compile(r"(\d+)\s*(?:ba[nñ]os?|ba[nñ]\b)", re.IGNORECASE)
_PATRON_BANOS_INV = re.compile(r"ba[nñ]os?\s*[:\-]?\s*(\d+)", re.IGNORECASE)

_PATRON_PARQ = re.compile(
    r"(\d+)\s*(?:parqueaderos?|garajes?|estacionamientos?)", re.IGNORECASE
)
_PATRON_PARQ_INV = re.compile(
    r"(?:parqueaderos?|garajes?|estacionamientos?)\s*[:\-]?\s*(\d+)", re.IGNORECASE
)

_PATRON_ESTRATO = re.compile(r"estrato\s*[:\-]?\s*(\d)", re.IGNORECASE)
_PATRON_PISO = re.compile(r"piso\s*(?:n[°ºo]\.?)?\s*[:\-]?\s*(\d{1,2})\b", re.IGNORECASE)


def parsear_area(texto: str | None) -> float | None:
    """Area en metros cuadrados. Toma la mayor plausible del texto."""
    if not texto:
        return None
    valores: list[float] = []
    for patron in (_PATRON_AREA, _PATRON_AREA_INVERSO):
        for m in patron.finditer(texto):
            v = _limpiar_numero(m.group(1))
            if v is not None and 5 <= v <= 5_000:
                valores.append(v)
    return max(valores) if valores else None


def _primer_conteo(texto: str, *patrones: re.Pattern[str], tope: int = 30) -> int | None:
    for patron in patrones:
        for m in patron.finditer(texto):
            try:
                v = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if 0 < v <= tope:
                return v
    return None


def parsear_alcobas(texto: str | None) -> int | None:
    if not texto:
        return None
    return _primer_conteo(texto, _PATRON_ALCOBAS, _PATRON_ALCOBAS_INV, tope=20)


def parsear_banos(texto: str | None) -> int | None:
    if not texto:
        return None
    return _primer_conteo(texto, _PATRON_BANOS, _PATRON_BANOS_INV, tope=20)


def parsear_parqueaderos(texto: str | None) -> int | None:
    if not texto:
        return None
    return _primer_conteo(texto, _PATRON_PARQ, _PATRON_PARQ_INV, tope=20)


def parsear_estrato(texto: str | None) -> int | None:
    if not texto:
        return None
    m = _PATRON_ESTRATO.search(texto)
    if not m:
        return None
    v = int(m.group(1))
    return v if 1 <= v <= 6 else None


def parsear_piso(texto: str | None) -> int | None:
    if not texto:
        return None
    m = _PATRON_PISO.search(texto)
    if not m:
        return None
    v = int(m.group(1))
    return v if 1 <= v <= 60 else None
