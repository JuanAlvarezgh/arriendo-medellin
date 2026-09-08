"""Esquema canonico al que convergen todos los portales."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class TipoInmueble(str, Enum):
    APARTAMENTO = "apartamento"
    APARTAESTUDIO = "apartaestudio"
    CASA = "casa"
    HABITACION = "habitacion"
    LOCAL = "local"
    OFICINA = "oficina"
    OTRO = "otro"


class Operacion(str, Enum):
    ARRIENDO = "arriendo"
    VENTA = "venta"
    ARRIENDO_TEMPORAL = "arriendo_temporal"


class BandaAntiguedad(str, Enum):
    """Fincaraiz publica la antiguedad en bandas, no como anio."""

    MENOR_1 = "menor_a_1"
    DE_1_A_8 = "1_a_8"
    DE_9_A_15 = "9_a_15"
    DE_16_A_30 = "16_a_30"
    MAYOR_30 = "mayor_a_30"

    @property
    def orden(self) -> int:
        return {
            "menor_a_1": 0,
            "1_a_8": 1,
            "9_a_15": 2,
            "16_a_30": 3,
            "mayor_a_30": 4,
        }[self.value]


class Capa(str, Enum):
    """Capa de la cascada que resolvio la extraccion."""

    API_INTERNA = "api"
    ESTRUCTURADOS = "a"
    ESTADO_JS = "b"
    HEURISTICA = "d"
    MODELO = "e"


# Limites de cordura para Medellin. Fuera de rango se marca como sospechoso.
PRECIO_MIN = 200_000
PRECIO_MAX = 80_000_000
AREA_MIN = 10.0
AREA_MAX = 2_000.0
LAT_MIN, LAT_MAX = 5.95, 6.45
LON_MIN, LON_MAX = -75.75, -75.35


class Aviso(BaseModel):
    """Un aviso de arriendo, normalizado y agnostico del portal de origen."""

    # Identidad
    id_fuente: str
    portal: str
    url: str

    # Clasificacion
    tipo_inmueble: TipoInmueble = TipoInmueble.OTRO
    operacion: Operacion = Operacion.ARRIENDO

    # Precio
    precio: float | None = None
    moneda: str = "COP"
    administracion: float | None = None
    administracion_incluida: bool | None = None

    # Dimensiones
    area_privada: float | None = None
    area_construida: float | None = None

    # Atributos
    alcobas: int | None = None
    banos: int | None = None
    parqueaderos: int | None = None
    estrato: int | None = None
    banda_antiguedad: BandaAntiguedad | None = None
    piso: int | None = None

    # Ubicacion
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    barrio: str | None = None
    comuna: str | None = None
    ciudad: str = "Medellin"

    # Temporal
    creado_en: date | None = None
    actualizado_en: date | None = None
    capturado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Texto
    titulo: str | None = None
    descripcion: str | None = None
    amenidades: list[str] = Field(default_factory=list)

    # Trazabilidad
    capa: Capa | None = None
    sospechoso: list[str] = Field(default_factory=list)

    @field_validator("precio", "administracion", "area_privada", "area_construida")
    @classmethod
    def _positivos_o_nulos(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v <= 0:
            return None
        return float(v)

    @field_validator("alcobas", "banos", "parqueaderos", "piso")
    @classmethod
    def _enteros_razonables(cls, v: int | None) -> int | None:
        if v is None:
            return None
        v = int(v)
        # 0 en estos portales significa "sin dato", no "cero unidades"
        if v <= 0 or v > 60:
            return None
        return v

    @field_validator("estrato")
    @classmethod
    def _estrato_valido(cls, v: int | None) -> int | None:
        if v is None:
            return None
        v = int(v)
        return v if 1 <= v <= 6 else None

    @field_validator("url")
    @classmethod
    def _url_con_esquema(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"url sin esquema: {v!r}")
        return v

    @model_validator(mode="after")
    def _marcar_sospechosos(self) -> Aviso:
        marcas: list[str] = []

        if self.precio is not None:
            if self.precio < PRECIO_MIN:
                marcas.append("precio_muy_bajo")
            elif self.precio > PRECIO_MAX:
                marcas.append("precio_muy_alto")

        area = self.area_privada or self.area_construida
        if area is not None and not (AREA_MIN <= area <= AREA_MAX):
            marcas.append("area_fuera_de_rango")

        if self.latitud is not None and not (LAT_MIN <= self.latitud <= LAT_MAX):
            marcas.append("latitud_fuera_del_valle")
        if self.longitud is not None and not (LON_MIN <= self.longitud <= LON_MAX):
            marcas.append("longitud_fuera_del_valle")

        if self.precio and area and area > 0:
            por_m2 = self.precio / area
            if por_m2 < 3_000 or por_m2 > 400_000:
                marcas.append("precio_por_m2_atipico")

        if self.creado_en and self.actualizado_en and self.actualizado_en < self.creado_en:
            marcas.append("fechas_invertidas")

        # No se sobreescribe lo que la extraccion ya haya marcado.
        object.__setattr__(self, "sospechoso", sorted(set(self.sospechoso) | set(marcas)))
        return self

    @property
    def utilizable(self) -> bool:
        """Minimo para entrar al analisis: precio y alguna medida de area."""
        return (
            self.precio is not None
            and (self.area_privada or self.area_construida) is not None
            and not self.sospechoso
        )

    @property
    def area(self) -> float | None:
        return self.area_privada or self.area_construida

    @property
    def precio_por_m2(self) -> float | None:
        a = self.area
        if self.precio and a:
            return round(self.precio / a, 2)
        return None

    @property
    def dias_en_mercado(self) -> int | None:
        if self.creado_en is None:
            return None
        return (self.capturado_en.date() - self.creado_en).days

    def clave_natural(self) -> str:
        return f"{self.portal}:{self.id_fuente}"


def sin_tildes(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_texto(texto: str | None) -> str | None:
    if not texto:
        return None
    limpio = re.sub(r"\s+", " ", texto).strip()
    return limpio or None


_TIPOS = {
    "apartaestudio": TipoInmueble.APARTAESTUDIO,
    "aparta estudio": TipoInmueble.APARTAESTUDIO,
    "studio": TipoInmueble.APARTAESTUDIO,
    "apartamento": TipoInmueble.APARTAMENTO,
    "apto": TipoInmueble.APARTAMENTO,
    "apartment": TipoInmueble.APARTAMENTO,
    "casa": TipoInmueble.CASA,
    "house": TipoInmueble.CASA,
    "habitacion": TipoInmueble.HABITACION,
    "local": TipoInmueble.LOCAL,
    "oficina": TipoInmueble.OFICINA,
    "bodega": TipoInmueble.OTRO,
    "lote": TipoInmueble.OTRO,
}


def inferir_tipo(texto: str | None) -> TipoInmueble:
    if not texto:
        return TipoInmueble.OTRO
    t = sin_tildes(texto).lower()
    # apartaestudio antes que apartamento: el segundo es prefijo del primero
    for clave in sorted(_TIPOS, key=len, reverse=True):
        if clave in t:
            return _TIPOS[clave]
    return TipoInmueble.OTRO


_BANDAS = [
    (r"menor\s*a\s*1|nuevo|estrenar|sobre\s*planos", BandaAntiguedad.MENOR_1),
    (r"\b1\s*a\s*8\b", BandaAntiguedad.DE_1_A_8),
    (r"\b9\s*a\s*15\b", BandaAntiguedad.DE_9_A_15),
    (r"\b16\s*a\s*30\b", BandaAntiguedad.DE_16_A_30),
    (r"m[aá]s\s*de\s*30|mayor\s*a\s*30", BandaAntiguedad.MAYOR_30),
]


def inferir_banda_antiguedad(texto: str | None) -> BandaAntiguedad | None:
    if not texto:
        return None
    t = sin_tildes(str(texto)).lower()
    for patron, banda in _BANDAS:
        if re.search(patron, t):
            return banda
    return None


def banda_desde_anio(anio: int | None) -> BandaAntiguedad | None:
    """Otros portales si publican anio exacto; se lleva a la misma escala."""
    if not anio or anio < 1800 or anio > datetime.now().year + 2:
        return None
    edad = datetime.now().year - anio
    if edad < 1:
        return BandaAntiguedad.MENOR_1
    if edad <= 8:
        return BandaAntiguedad.DE_1_A_8
    if edad <= 15:
        return BandaAntiguedad.DE_9_A_15
    if edad <= 30:
        return BandaAntiguedad.DE_16_A_30
    return BandaAntiguedad.MAYOR_30


AMENIDADES = {
    "ascensor": r"\bascensor(es)?\b",
    "porteria": r"\bporter[ií]a\b|\bvigilancia\b|\bcelador",
    "gimnasio": r"\bgimnasio\b|\bgym\b",
    "piscina": r"\bpiscina\b",
    "zonas_verdes": r"\bzonas?\s+verdes?\b",
    "salon_social": r"\bsal[oó]n\s+(social|comunal)\b",
    "balcon": r"\bbalc[oó]n\b|\bbalcones\b",
    "amoblado": r"\bamoblad|\bamueblad",
    "parqueadero_visitantes": r"parqueadero\s+de\s+visitantes",
    "juegos_infantiles": r"juegos?\s+infantiles",
    "terraza": r"\bterraza\b",
    "chimenea": r"\bchimenea\b",
    "deposito": r"\bdep[oó]sito\b|\b[uú]til\b",
    "acepta_mascotas": r"acepta\s+mascotas|pet\s*friendly",
}


def extraer_amenidades(texto: str | None) -> list[str]:
    if not texto:
        return []
    t = texto.lower()
    return sorted(nombre for nombre, patron in AMENIDADES.items() if re.search(patron, t))


def a_fecha(valor: Any) -> date | None:
    """Acepta date, datetime, timestamp epoch o cadena ISO."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, (int, float)):
        try:
            seg = valor / 1000 if valor > 1e11 else valor
            return datetime.fromtimestamp(seg, tz=timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(valor, str):
        s = valor.strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            pass
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None
