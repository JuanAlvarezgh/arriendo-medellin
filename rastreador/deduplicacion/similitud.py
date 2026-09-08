"""Deteccion del mismo inmueble publicado en varios portales.

Sin esto, un apartamento anunciado en tres sitios entra tres veces al modelo y
sesga el analisis. La estrategia es la clasica de dos fases: bloqueo barato
para descartar la mayoria de comparaciones, y comparacion fina dentro del bloque.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from datasketch import MinHash, MinHashLSH
from rapidfuzz import fuzz

from ..normalizacion.esquema import Aviso, sin_tildes

TOLERANCIA_AREA = 0.05
TOLERANCIA_PRECIO = 0.03
PRECISION_GEO = 3  # ~110 m por celda
UMBRAL_TEXTO = 0.55


def celda_geo(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    return f"{round(lat, PRECISION_GEO)}:{round(lon, PRECISION_GEO)}"


def clave_bloqueo(a: Aviso) -> str | None:
    """Bloque = celda geografica + numero de alcobas.

    Reduce el problema de N al cuadrado a comparaciones dentro de vecindarios
    pequenos. Sin coordenadas no se puede bloquear con seguridad.
    """
    celda = celda_geo(a.latitud, a.longitud)
    if celda is None:
        return None
    return f"{celda}|{a.alcobas or 0}"


def _fichas(texto: str, n: int = 4) -> set[str]:
    limpio = re.sub(r"\s+", " ", sin_tildes(texto).lower())
    limpio = re.sub(r"[^a-z0-9 ]", "", limpio)
    if len(limpio) < n:
        return {limpio} if limpio else set()
    return {limpio[i : i + n] for i in range(len(limpio) - n + 1)}


def minhash(texto: str, num_perm: int = 64) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for f in _fichas(texto):
        m.update(f.encode("utf-8"))
    return m


def _cerca(a: float | None, b: float | None, tolerancia: float) -> bool:
    if a is None or b is None:
        return False
    if a == 0 or b == 0:
        return False
    return abs(a - b) / max(a, b) <= tolerancia


@dataclass
class Comparacion:
    coincide: bool
    puntaje: float
    razones: list[str] = field(default_factory=list)


def comparar(a: Aviso, b: Aviso) -> Comparacion:
    """Decide si dos avisos son el mismo inmueble.

    El objetivo real es el duplicado ENTRE portales: la misma vivienda anunciada
    en varios sitios. Dos avisos del mismo portal, en el mismo edificio, casi
    siempre son unidades distintas, no repeticiones, y por eso se les exige un
    texto practicamente identico antes de fusionarlos.
    """
    if a.portal == b.portal and a.id_fuente == b.id_fuente:
        return Comparacion(True, 1.0, ["mismo aviso"])

    mismo_portal = a.portal == b.portal
    if mismo_portal:
        if not (a.descripcion and b.descripcion):
            return Comparacion(False, 0.0, ["mismo portal sin texto que comparar"])
        parecido = fuzz.token_set_ratio(a.descripcion[:600], b.descripcion[:600]) / 100.0
        if parecido < 0.95:
            return Comparacion(False, parecido, ["mismo portal, texto distinto"])

    razones: list[str] = []
    puntaje = 0.0

    if _cerca(a.area, b.area, TOLERANCIA_AREA):
        puntaje += 0.35
        razones.append("area")
    elif a.area and b.area:
        return Comparacion(False, 0.0, ["area distinta"])

    if _cerca(a.precio, b.precio, TOLERANCIA_PRECIO):
        puntaje += 0.30
        razones.append("precio")

    if a.alcobas and b.alcobas and a.alcobas == b.alcobas:
        puntaje += 0.10
        razones.append("alcobas")
    if a.banos and b.banos and a.banos == b.banos:
        puntaje += 0.05
        razones.append("banos")
    if a.estrato and b.estrato and a.estrato == b.estrato:
        puntaje += 0.05
        razones.append("estrato")

    if a.descripcion and b.descripcion:
        similitud = fuzz.token_set_ratio(a.descripcion[:600], b.descripcion[:600]) / 100.0
        if similitud >= UMBRAL_TEXTO:
            puntaje += 0.20 * similitud
            razones.append(f"texto {similitud:.2f}")

    if a.direccion and b.direccion:
        d = fuzz.ratio(sin_tildes(a.direccion).lower(), sin_tildes(b.direccion).lower()) / 100.0
        if d >= 0.85:
            puntaje += 0.15
            razones.append("direccion")

    return Comparacion(puntaje >= 0.60, round(puntaje, 3), razones)


@dataclass
class Grupo:
    canonico: Aviso
    miembros: list[Aviso] = field(default_factory=list)

    @property
    def portales(self) -> list[str]:
        return sorted({m.portal for m in self.miembros})

    @property
    def tamano(self) -> int:
        return len(self.miembros)


def agrupar(avisos: Sequence[Aviso]) -> list[Grupo]:
    """Agrupa avisos duplicados. Cada grupo tiene un representante canonico.

    El canonico es el aviso con mas campos poblados: si un portal publica mas
    detalle que otro, se conserva el mejor.
    """
    bloques: dict[str, list[Aviso]] = defaultdict(list)
    sin_bloque: list[Aviso] = []

    for a in avisos:
        clave = clave_bloqueo(a)
        if clave is None:
            sin_bloque.append(a)
        else:
            bloques[clave].append(a)

    grupos: list[Grupo] = []

    for miembros in bloques.values():
        if len(miembros) == 1:
            grupos.append(Grupo(miembros[0], list(miembros)))
            continue

        # Enlace completo, no union-find. El union-find es transitivo, y en un
        # edificio con areas escalonadas (110, 115, 120, 124...) cada par
        # consecutivo cae dentro de la tolerancia y la cadena termina fundiendo
        # el edificio entero en un solo "duplicado". Exigiendo que un aviso
        # coincida con TODOS los miembros del grupo, la cadena se rompe.
        conjuntos: list[list[Aviso]] = []
        for candidato in miembros:
            for conjunto in conjuntos:
                if all(comparar(candidato, m).coincide for m in conjunto):
                    conjunto.append(candidato)
                    break
            else:
                conjuntos.append([candidato])

        for conjunto in conjuntos:
            grupos.append(Grupo(_mejor(conjunto), conjunto))

    grupos.extend(Grupo(a, [a]) for a in sin_bloque)
    return grupos


def _completitud(a: Aviso) -> int:
    campos = (
        a.precio,
        a.area_privada,
        a.alcobas,
        a.banos,
        a.parqueaderos,
        a.estrato,
        a.piso,
        a.banda_antiguedad,
        a.direccion,
        a.latitud,
        a.descripcion,
    )
    return sum(1 for c in campos if c not in (None, ""))


def _mejor(avisos: Iterable[Aviso]) -> Aviso:
    return max(avisos, key=lambda a: (_completitud(a), a.capturado_en))


def indice_lsh(avisos: Sequence[Aviso], umbral: float = 0.6) -> MinHashLSH:
    """Indice MinHash sobre descripciones, para busqueda de similares sin coordenadas."""
    lsh = MinHashLSH(threshold=umbral, num_perm=64)
    for a in avisos:
        if a.descripcion:
            lsh.insert(a.clave_natural(), minhash(a.descripcion))
    return lsh
