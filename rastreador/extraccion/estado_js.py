"""Capa b: estado embebido por el framework de la pagina.

Cubre Next.js, Nuxt, Apollo y los patrones habituales de estado precargado.
Es la capa mas valiosa de la cascada porque entrega el objeto del aviso tal como
lo tiene el servidor, sin ambiguedad de parseo.
"""

from __future__ import annotations

import json
import re
from typing import Any

_BLOQUES = [
    ("next", re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)),
    ("nuxt", re.compile(r"window\.__NUXT__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)),
    ("estado", re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)),
    ("precargado", re.compile(r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)),
    ("apollo", re.compile(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)),
]

# Nombres que los portales usan para los mismos conceptos.
SINONIMOS: dict[str, tuple[str, ...]] = {
    "precio": ("price", "rentprice", "precio", "amount", "valorcanon", "canon", "valor"),
    "administracion": ("commonexpenses", "administracion", "adminprice", "expensas"),
    "area_privada": ("m2apto", "areaprivada", "privatearea", "area", "surface", "m2"),
    "area_construida": ("m2built", "areaconstruida", "builtarea", "construidos"),
    "alcobas": ("bedrooms", "habitaciones", "alcobas", "rooms", "nrodormitorios"),
    "banos": ("bathrooms", "banos", "banios", "restrooms"),
    "parqueaderos": ("garage", "parking", "parqueaderos", "garajes", "parkinglots"),
    "estrato": ("stratum", "estrato", "socialstratum"),
    "piso": ("floor", "piso", "nivel"),
    "direccion": ("address", "direccion", "streetaddress"),
    "latitud": ("latitude", "lat", "latitud"),
    "longitud": ("longitude", "lng", "lon", "longitud"),
    "titulo": ("title", "titulo", "name"),
    "descripcion": ("description", "descripcion", "detalle"),
    "creado_en": ("created_at", "createdat", "publishdate", "fechapublicacion", "createddate"),
    "actualizado_en": ("updated_at", "updatedat", "modifieddate", "fechaactualizacion"),
}


def bloques_de_estado(html: str) -> dict[str, Any]:
    """Extrae todos los estados embebidos que la pagina traiga."""
    hallados: dict[str, Any] = {}
    for nombre, patron in _BLOQUES:
        m = patron.search(html)
        if not m:
            continue
        crudo = m.group(1).strip()
        try:
            hallados[nombre] = json.loads(crudo)
        except json.JSONDecodeError:
            # Nuxt a veces emite una funcion autoejecutada en vez de JSON puro
            recorte = _recortar_json(crudo)
            if recorte:
                try:
                    hallados[nombre] = json.loads(recorte)
                except json.JSONDecodeError:
                    continue
    return hallados


def _recortar_json(texto: str) -> str | None:
    """Recorta el primer objeto JSON balanceado del texto."""
    inicio = texto.find("{")
    if inicio < 0:
        return None
    nivel = 0
    en_cadena = False
    escapado = False
    for i in range(inicio, len(texto)):
        c = texto[i]
        if en_cadena:
            if escapado:
                escapado = False
            elif c == "\\":
                escapado = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c == "{":
            nivel += 1
        elif c == "}":
            nivel -= 1
            if nivel == 0:
                return texto[inicio : i + 1]
    return None


def por_ruta(obj: Any, ruta: str) -> Any:
    """Navega 'props.pageProps.data.price.amount'. Soporta indices de lista."""
    actual = obj
    for parte in ruta.split("."):
        if actual is None:
            return None
        if isinstance(actual, list):
            if parte.isdigit():
                idx = int(parte)
                actual = actual[idx] if 0 <= idx < len(actual) else None
                continue
            actual = actual[0] if actual else None
            if actual is None:
                return None
        if isinstance(actual, dict):
            actual = actual.get(parte)
        else:
            return None
    return actual


def buscar_objeto_aviso(estado: Any, profundidad_max: int = 8) -> dict[str, Any] | None:
    """Busca el diccionario que mas parece ser el aviso.

    Puntua cada diccionario del arbol por cuantos conceptos del esquema
    reconoce. El de mayor puntaje gana. Evita depender de la ruta exacta,
    que cambia entre versiones del portal.
    """
    mejor: dict[str, Any] | None = None
    mejor_puntaje = 0

    def visitar(nodo: Any, prof: int) -> None:
        nonlocal mejor, mejor_puntaje
        if prof > profundidad_max:
            return
        if isinstance(nodo, dict):
            claves = {k.lower() for k in nodo.keys()}
            puntaje = sum(
                1 for sinonimos in SINONIMOS.values() if claves & set(sinonimos)
            )
            # Exigir senales de precio y de tamano para no premiar diccionarios de filtros
            tiene_precio = bool(claves & set(SINONIMOS["precio"]))
            tiene_medida = bool(
                claves & (set(SINONIMOS["area_privada"]) | set(SINONIMOS["alcobas"]))
            )
            if puntaje > mejor_puntaje and tiene_precio and tiene_medida:
                mejor_puntaje = puntaje
                mejor = nodo
            for v in nodo.values():
                visitar(v, prof + 1)
        elif isinstance(nodo, list):
            for v in nodo[:50]:
                visitar(v, prof + 1)

    visitar(estado, 0)
    return mejor if mejor_puntaje >= 4 else None


def _valor_por_sinonimo(obj: dict[str, Any], campo: str) -> Any:
    minusculas = {k.lower(): v for k, v in obj.items()}
    for nombre in SINONIMOS.get(campo, ()):
        if nombre in minusculas:
            v = minusculas[nombre]
            # Los portales anidan el precio en {'amount': N, 'currency': ...}
            if isinstance(v, dict):
                for interno in ("amount", "value", "valor", "monto"):
                    if interno in v:
                        return v[interno]
                continue
            if isinstance(v, (str, int, float, bool)):
                return v
    return None


def extraer(html: str, mapeo: dict[str, str] | None = None) -> dict[str, Any] | None:
    """Devuelve campos canonicos desde el estado embebido, o None si no hay."""
    estados = bloques_de_estado(html)
    if not estados:
        return None

    campos: dict[str, Any] = {}

    # Ruta explicita del perfil del sitio, si la hay
    if mapeo:
        for estado in estados.values():
            for canonico, ruta in mapeo.items():
                if canonico in campos:
                    continue
                v = por_ruta(estado, ruta)
                if v is not None:
                    campos[canonico] = v

    # Busqueda automatica del objeto del aviso
    for estado in estados.values():
        obj = buscar_objeto_aviso(estado)
        if not obj:
            continue
        for canonico in SINONIMOS:
            if campos.get(canonico) is None:
                v = _valor_por_sinonimo(obj, canonico)
                if v is not None:
                    campos[canonico] = v
        if campos.get("_ficha") is None:
            campos["_ficha"] = _buscar_ficha_tecnica(estado)
        break

    return campos or None


def _buscar_ficha_tecnica(estado: Any) -> dict[str, str] | None:
    """Fincaraiz publica una 'technicalSheet': lista de {field, text, value}."""
    encontrado: dict[str, str] = {}

    def visitar(nodo: Any, prof: int = 0) -> None:
        if prof > 8 or encontrado:
            return
        if isinstance(nodo, list) and nodo and isinstance(nodo[0], dict):
            claves = set(nodo[0].keys())
            if {"field", "value"} <= claves:
                for e in nodo:
                    if isinstance(e, dict) and e.get("field"):
                        encontrado[str(e["field"])] = str(e.get("value") or "")
                return
        if isinstance(nodo, dict):
            for v in nodo.values():
                visitar(v, prof + 1)
        elif isinstance(nodo, list):
            for v in nodo[:50]:
                visitar(v, prof + 1)

    visitar(estado)
    return encontrado or None
