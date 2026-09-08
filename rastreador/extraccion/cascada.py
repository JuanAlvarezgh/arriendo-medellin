"""Orquestador de la cascada de extraccion.

Orden de ejecucion, que no coincide con el de descubrimiento: si el perfil del
sitio ya trae una API interna, esa va primero por ser la mas barata. Luego los
datos estructurados, el estado embebido, la heuristica y, al final, el modelo.

Una capa "resuelve" el aviso cuando aporta precio y alguna medida de area. Las
capas siguientes solo se usan para rellenar huecos, nunca para sobreescribir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..normalizacion.area import parsear_area
from ..normalizacion.esquema import (
    Aviso,
    Capa,
    Operacion,
    TipoInmueble,
    a_fecha,
    banda_desde_anio,
    extraer_amenidades,
    inferir_banda_antiguedad,
    inferir_tipo,
    normalizar_texto,
)
from ..normalizacion.moneda import parsear_entero, parsear_precio
from . import api_interna, estado_js, estructurados, heuristica

CAMPOS_NUCLEO = ("precio", "area_privada", "area_construida")


@dataclass
class Resultado:
    aviso: Aviso | None
    capa: Capa | None
    capas_intentadas: list[str] = field(default_factory=list)
    motivo_fallo: str | None = None


def _suficiente(campos: dict[str, Any]) -> bool:
    """Minimo para dar por resuelto: precio y alguna area."""
    tiene_precio = campos.get("precio") not in (None, 0, "")
    tiene_area = any(campos.get(c) not in (None, 0, "") for c in ("area_privada", "area_construida"))
    return bool(tiene_precio and tiene_area)


def _fusionar(destino: dict[str, Any], nuevo: dict[str, Any] | None) -> None:
    """Rellena huecos sin sobreescribir lo ya obtenido por una capa anterior."""
    if not nuevo:
        return
    for k, v in nuevo.items():
        if v in (None, "", 0) and k != "piso":
            continue
        if destino.get(k) in (None, "", 0):
            destino[k] = v


def _numero(v: Any) -> float | None:
    """Convierte a numero tolerando cadenas como '280 m2' o '$1.500.000'."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v != 0 else None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        area = parsear_area(s)
        if area is not None:
            return area
        m = re.search(r"-?\d[\d.,]*", s)
        if not m:
            return None
        t = m.group().rstrip(".,")
        if t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[-1]) == 3):
            t = t.replace(".", "")
        t = t.replace(",", ".")
        try:
            n = float(t)
        except ValueError:
            return None
        return n if n != 0 else None
    return None


def _entero(v: Any) -> int | None:
    n = _numero(v)
    return int(n) if n is not None else None


def _corregir_signo_longitud(lat: float | None, lon: float | None) -> float | None:
    """Repara la longitud publicada sin signo.

    Colombia esta entera en el hemisferio occidental, asi que su longitud es
    siempre negativa. Ciencuadras publica 75.60 donde deberia decir -75.60, y
    sin corregirlo el aviso cae fuera del pais y queda descartado. Solo se
    invierte cuando la latitud confirma que estamos en Colombia y el valor
    absoluto cae en el rango de longitudes del pais.
    """
    if lon is None or lon <= 0:
        return lon
    if lat is None or not (-4.5 <= lat <= 13.5):
        return lon
    if 66.0 <= lon <= 82.0:
        return -lon
    return lon


def _aplicar_ficha(campos: dict[str, Any], ficha: dict[str, str] | None) -> None:
    """Traduce la ficha tecnica de Fincaraiz a campos canonicos."""
    if not ficha:
        return
    equivalencias = {
        "bathrooms": "banos",
        "bedrooms": "alcobas",
        "garage": "parqueaderos",
        "stratum": "estrato",
        "floor": "piso",
        "m2apto": "area_privada",
        "m2Built": "area_construida",
        "commonExpenses": "administracion",
    }
    for origen, canonico in equivalencias.items():
        crudo = ficha.get(origen)
        if crudo and campos.get(canonico) in (None, "", 0):
            campos[canonico] = crudo

    if ficha.get("property_type_name") and not campos.get("tipo_inmueble"):
        campos["tipo_inmueble"] = ficha["property_type_name"]
    if ficha.get("constructionYear"):
        campos["_antiguedad_texto"] = ficha["constructionYear"]


def construir_aviso(
    campos: dict[str, Any], *, url: str, portal: str, id_fuente: str, capa: Capa | None
) -> Aviso | None:
    """Convierte el diccionario crudo de la cascada en un Aviso validado."""
    _aplicar_ficha(campos, campos.pop("_ficha", None))

    precio = _numero(campos.get("precio"))
    if precio is None and campos.get("titulo"):
        precio, _ = parsear_precio(str(campos["titulo"]))

    moneda = str(campos.get("moneda") or "COP").upper()
    if moneda not in ("COP", "USD"):
        moneda = "COP"

    descripcion = normalizar_texto(
        campos.get("descripcion") if isinstance(campos.get("descripcion"), str) else None
    )
    titulo = normalizar_texto(
        campos.get("titulo") if isinstance(campos.get("titulo"), str) else None
    )

    banda = inferir_banda_antiguedad(campos.get("_antiguedad_texto"))
    if banda is None:
        anio = campos.get("constructionyear") or campos.get("anio_construccion")
        banda = banda_desde_anio(_entero(anio))

    tipo_texto = campos.get("tipo_inmueble") or titulo or url
    tipo = inferir_tipo(str(tipo_texto)) if tipo_texto else TipoInmueble.OTRO

    operacion = Operacion.ARRIENDO
    texto_operacion = f"{url} {titulo or ''}".lower()
    if re.search(r"\bventa\b|\bvender\b|\bsale\b", texto_operacion) and not re.search(
        r"arriendo|alquiler|renta", texto_operacion
    ):
        operacion = Operacion.VENTA

    texto_amenidades = " ".join(filter(None, [descripcion, titulo]))

    try:
        aviso = Aviso(
            id_fuente=str(id_fuente),
            portal=portal,
            url=url,
            tipo_inmueble=tipo,
            operacion=operacion,
            precio=precio,
            moneda=moneda,
            administracion=_numero(campos.get("administracion")),
            area_privada=_numero(campos.get("area_privada")),
            area_construida=_numero(campos.get("area_construida")),
            alcobas=_entero(campos.get("alcobas")),
            banos=_entero(campos.get("banos")),
            parqueaderos=_entero(campos.get("parqueaderos")),
            estrato=_entero(campos.get("estrato")),
            banda_antiguedad=banda,
            piso=_entero(campos.get("piso")),
            direccion=normalizar_texto(
                campos.get("direccion") if isinstance(campos.get("direccion"), str) else None
            ),
            latitud=_numero(campos.get("latitud")),
            longitud=_corregir_signo_longitud(
                _numero(campos.get("latitud")), _numero(campos.get("longitud"))
            ),
            barrio=normalizar_texto(
                campos.get("barrio") if isinstance(campos.get("barrio"), str) else None
            )
            or barrio_desde_url(url),
            creado_en=a_fecha(campos.get("creado_en")),
            actualizado_en=a_fecha(campos.get("actualizado_en")),
            titulo=titulo,
            descripcion=descripcion,
            amenidades=extraer_amenidades(texto_amenidades),
            capa=capa,
        )
    except Exception:
        return None
    return aviso


# Cada portal codifica el barrio en la URL a su manera. Se prueba en orden y
# gana el primero que case; el perfil del sitio puede aportar el suyo propio.
PATRONES_BARRIO = [
    # Fincaraiz: /apartaestudio-en-arriendo-en-el-poblado-medellin/193855882
    # El prefijo es codicioso a proposito: hay dos '-en-' y el barrio va tras
    # el ultimo. Con prefijo perezoso se captura 'arriendo en el poblado'.
    r"/[a-z0-9-]*-en-(?P<barrio>[a-z0-9-]+?)-medellin/\d+",
    # Ciencuadras: /inmueble/apartamento-en-arriendo-en-el-velodromo-medellin-3858855
    # Igual que el anterior pero el identificador va tras un guion, no una barra.
    r"/[a-z0-9-]*-en-(?P<barrio>[a-z0-9-]+?)-medellin-\d+",
    # Coninsa: /inmuebles/apartamento-en-arriendo/altos-del-poblado/medellin/95303/
    r"/(?P<barrio>[a-z0-9-]+)/medellin/\d+",
    # arriendo.com: /co/apartaestudios/medellin/el-poblado/AR-506175/
    r"/medellin/(?P<barrio>[a-z0-9-]+)/[A-Z]{2}-?\d+",
]


def barrio_desde_url(url: str, patron_propio: str | None = None) -> str | None:
    """Extrae el barrio del slug del aviso, sin costo de geocodificacion.

    El perfil de cada sitio puede declarar su propio patron con un grupo
    llamado 'barrio'; si no lo hace, se prueban los conocidos.
    """
    if not url:
        return None

    patrones = [patron_propio] if patron_propio else PATRONES_BARRIO
    for patron in patrones:
        if not patron:
            continue
        try:
            m = re.search(patron, url, re.I)
        except re.error:
            continue
        if not m:
            continue
        try:
            crudo = m.group("barrio")
        except (IndexError, KeyError):
            continue
        if not crudo:
            continue
        barrio = _limpiar_barrio(crudo)
        if barrio:
            return barrio
    return None


_PALABRAS_OPERACION = r"(?:arriendo|alquiler|venta|arrendamiento|renta)"
_RELLENO = {"", "en", "de", "el", "la", "los", "las", "medellin", "inmuebles", "propiedad"}


def _limpiar_barrio(crudo: str) -> str | None:
    """Descarta capturas que son la operacion y no un barrio.

    Hay avisos sin barrio en la URL, solo con la ciudad, como
    'apartaestudio-en-arriendo-en-medellin/191669147'. Ahi el patron captura
    'arriendo-en', que no es un barrio sino un barrio fantasma en el analisis.
    """
    texto = crudo.replace("-", " ").strip().lower()
    # Quita la operacion cuando encabeza la captura
    texto = re.sub(rf"^{_PALABRAS_OPERACION}\b\s*", "", texto)
    texto = re.sub(r"^(?:en|de)\b\s*", "", texto).strip()

    if not texto or texto in _RELLENO:
        return None
    if all(p in _RELLENO for p in texto.split()):
        return None
    return texto.title()


def id_desde_url(url: str) -> str:
    """Identificador estable del aviso a partir de su URL."""
    m = re.search(r"/(\d{4,})/?(?:\?|$)", url)
    if m:
        return m.group(1)
    m = re.search(r"[-/](\d{4,})(?:[-.]|$)", url)
    if m:
        return m.group(1)
    return url.rstrip("/").split("/")[-1][:120] or url[:120]


def extraer_todo(
    html: str,
    *,
    url: str,
    portal: str,
    perfil: dict[str, Any] | None = None,
    extractor_modelo: Any = None,
    es_json: bool = False,
) -> Resultado:
    """Recorre la cascada y devuelve el aviso, o el motivo por el que no salio."""
    perfil = perfil or {}
    mapeo = perfil.get("mapeo") or None
    campos: dict[str, Any] = {}
    intentadas: list[str] = []
    capa_resolutora: Capa | None = None

    def intentar(nombre: str, capa: Capa, fn: Callable[[], dict[str, Any] | None]) -> bool:
        nonlocal capa_resolutora
        intentadas.append(nombre)
        try:
            nuevo = fn()
        except Exception:
            return False
        if not nuevo:
            return False
        antes = _suficiente(campos)
        _fusionar(campos, nuevo)
        if not antes and _suficiente(campos) and capa_resolutora is None:
            capa_resolutora = capa
        return _suficiente(campos)

    # Respuesta que ya es JSON de la API interna
    if es_json:
        intentar("api", Capa.API_INTERNA, lambda: api_interna.extraer(html, mapeo))
        if _suficiente(campos):
            aviso = construir_aviso(
                campos, url=url, portal=portal, id_fuente=id_desde_url(url), capa=Capa.API_INTERNA
            )
            return Resultado(aviso, Capa.API_INTERNA, intentadas)

    if not intentar("b_estado_js", Capa.ESTADO_JS, lambda: estado_js.extraer(html, mapeo)):
        if not intentar("a_estructurados", Capa.ESTRUCTURADOS, lambda: estructurados.extraer(html, url)):
            if not intentar("d_heuristica", Capa.HEURISTICA, lambda: heuristica.extraer(html, url)):
                if extractor_modelo is not None:
                    def con_modelo() -> dict[str, Any] | None:
                        crudo = extractor_modelo.extraer(html, url)
                        if not crudo:
                            return None
                        from .modelo import verificar_coherencia

                        return verificar_coherencia(crudo, html)

                    intentar("e_modelo", Capa.MODELO, con_modelo)

    # Aunque una capa temprana haya resuelto, las demas rellenan huecos.
    if _suficiente(campos):
        for nombre, capa, fn in (
            ("a_estructurados", Capa.ESTRUCTURADOS, lambda: estructurados.extraer(html, url)),
            ("d_heuristica", Capa.HEURISTICA, lambda: heuristica.extraer(html, url)),
        ):
            if nombre not in intentadas:
                intentadas.append(nombre)
                try:
                    _fusionar(campos, fn())
                except Exception:
                    pass

    if not _suficiente(campos):
        faltan = [c for c in ("precio",) if campos.get(c) in (None, 0, "")]
        motivo = "sin precio" if faltan else "sin area"
        return Resultado(None, None, intentadas, motivo)

    aviso = construir_aviso(
        campos, url=url, portal=portal, id_fuente=id_desde_url(url), capa=capa_resolutora
    )
    if aviso is None:
        return Resultado(None, None, intentadas, "no valida contra el esquema")
    return Resultado(aviso, capa_resolutora, intentadas)
