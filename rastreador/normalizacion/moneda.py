"""Interpretacion de precios en texto libre colombiano.

El caso dificil es la ambiguedad del separador: en Colombia el punto es separador
de miles ("$1.500.000") pero en texto tecnico puede ser decimal ("1.5 millones").
Se resuelve por forma del grupo, no por suposicion.
"""

from __future__ import annotations

import re

MONEDAS = {
    "COP": r"\bCOP\b|\bpesos?\b|\$",
    "USD": r"\bUSD\b|\bd[oó]lares?\b|US\$",
}

_MULTIPLICADORES = [
    (r"\bmillones?\b|\bmill?\.?\b|\bmm\b", 1_000_000),
    (r"\bmil\b|\bk\b", 1_000),
]

# Ruido que nunca es el precio del arriendo
_RUIDO = re.compile(
    r"c[oó]digo|c[eé]dula|tel[eé]fono|nit\b|matr[ií]cula|whatsapp|"
    r"\bcel\b|\bref\b|referencia",
    re.IGNORECASE,
)


def _limpiar_numero(bruto: str) -> float | None:
    """Convierte '1.500.000' , '1,500,000' , '1500000' , '1.5' a float."""
    s = bruto.strip().replace(" ", "").replace("'", ".")
    if not s:
        return None

    tiene_punto = "." in s
    tiene_coma = "," in s

    if tiene_punto and tiene_coma:
        # El ultimo separador que aparece es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif tiene_coma:
        cola = s.split(",")[-1]
        # ',' seguido de exactamente 3 digitos y mas de un grupo: son miles
        s = s.replace(",", "") if len(cola) == 3 and s.count(",") >= 1 and len(s.split(",")[0]) <= 3 else s.replace(",", ".")
    elif tiene_punto:
        partes = s.split(".")
        cola = partes[-1]
        # Todos los grupos posteriores al primero de 3 digitos: separador de miles
        if len(partes) > 2 or (len(cola) == 3 and len(partes[0]) <= 3 and len(partes[0]) > 0):
            s = s.replace(".", "")
        # si no, se deja como decimal

    try:
        return float(s)
    except ValueError:
        return None


def parsear_precio(texto: str | None) -> tuple[float | None, str]:
    """Devuelve (monto, moneda). Toma el mayor candidato plausible del texto."""
    if not texto:
        return None, "COP"

    moneda = "USD" if re.search(MONEDAS["USD"], texto, re.IGNORECASE) else "COP"

    candidatos: list[float] = []

    # Forma 1: numero seguido de multiplicador ("1,5 millones", "2 mill")
    for patron, factor in _MULTIPLICADORES:
        for m in re.finditer(rf"(\d+(?:[.,]\d+)?)\s*(?:{patron})", texto, re.IGNORECASE):
            if _RUIDO.search(texto[max(0, m.start() - 40) : m.start()]):
                continue
            n = _limpiar_numero(m.group(1))
            if n is not None:
                candidatos.append(n * factor)

    # Forma 2: numero con separadores de miles, con o sin simbolo
    for m in re.finditer(r"\$?\s*(\d{1,3}(?:[.,\s']\d{3})+(?:[.,]\d{1,2})?)", texto):
        if _RUIDO.search(texto[max(0, m.start() - 40) : m.start()]):
            continue
        n = _limpiar_numero(m.group(1))
        if n is not None:
            candidatos.append(n)

    # Forma 3: numero pelado largo precedido de simbolo de moneda
    for m in re.finditer(r"(?:\$|COP)\s*(\d{6,12})\b", texto, re.IGNORECASE):
        n = _limpiar_numero(m.group(1))
        if n is not None:
            candidatos.append(n)

    plausibles = [c for c in candidatos if 100_000 <= c <= 200_000_000] if moneda == "COP" else [
        c for c in candidatos if 50 <= c <= 50_000
    ]
    if not plausibles:
        return None, moneda

    # El precio del arriendo es el valor dominante, no la administracion.
    return max(plausibles), moneda


def parsear_entero(texto: str | None) -> int | None:
    if not texto:
        return None
    m = re.search(r"\d+", str(texto).replace(".", "").replace(",", ""))
    return int(m.group()) if m else None
