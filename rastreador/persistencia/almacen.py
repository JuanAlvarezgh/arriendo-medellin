"""Persistencia en tres formatos, con papeles distintos.

JSONL durante la corrida: una linea por aviso, se anexa y sobrevive a una
interrupcion. PostgreSQL para el analisis. CSV, Excel y Parquet como export.

La eleccion de JSONL sobre CSV para la escritura en vivo no es estetica: las
descripciones traen comas, comillas y saltos de linea, y un archivo cortado a
la mitad debe poder recuperarse descartando solo la ultima linea.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..normalizacion.esquema import Aviso

ESQUEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS raw.avisos (
    portal          TEXT        NOT NULL,
    id_fuente       TEXT        NOT NULL,
    url             TEXT        NOT NULL,
    capturado_en    TIMESTAMPTZ NOT NULL,
    contenido       JSONB       NOT NULL,
    PRIMARY KEY (portal, id_fuente, capturado_en)
);

CREATE TABLE IF NOT EXISTS stg.avisos (
    portal              TEXT        NOT NULL,
    id_fuente           TEXT        NOT NULL,
    url                 TEXT        NOT NULL,
    tipo_inmueble       TEXT,
    operacion           TEXT,
    precio              NUMERIC(14,2),
    moneda              TEXT,
    administracion      NUMERIC(14,2),
    area_privada        NUMERIC(10,2),
    area_construida     NUMERIC(10,2),
    alcobas             SMALLINT,
    banos               SMALLINT,
    parqueaderos        SMALLINT,
    estrato             SMALLINT,
    banda_antiguedad    TEXT,
    piso                SMALLINT,
    direccion           TEXT,
    latitud             DOUBLE PRECISION,
    longitud            DOUBLE PRECISION,
    barrio              TEXT,
    comuna              TEXT,
    ciudad              TEXT,
    creado_en           DATE,
    actualizado_en      DATE,
    capturado_en        TIMESTAMPTZ NOT NULL,
    titulo              TEXT,
    descripcion         TEXT,
    amenidades          TEXT[],
    capa                TEXT,
    sospechoso          TEXT[],
    id_grupo            TEXT,
    es_canonico         BOOLEAN     DEFAULT TRUE,
    PRIMARY KEY (portal, id_fuente)
);

CREATE INDEX IF NOT EXISTS ix_stg_avisos_geo    ON stg.avisos (latitud, longitud);
CREATE INDEX IF NOT EXISTS ix_stg_avisos_barrio ON stg.avisos (barrio);
CREATE INDEX IF NOT EXISTS ix_stg_avisos_creado ON stg.avisos (creado_en);
CREATE INDEX IF NOT EXISTS ix_stg_avisos_grupo  ON stg.avisos (id_grupo);
"""


def _serializable(valor: Any) -> Any:
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if hasattr(valor, "value"):
        return valor.value
    return valor


def a_dict(aviso: Aviso) -> dict[str, Any]:
    d = aviso.model_dump()
    return {k: _serializable(v) for k, v in d.items()}


class ArchivoJsonl:
    """Escritura por anexado, tolerante a interrupciones."""

    def __init__(self, ruta: Path | str) -> None:
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self.escritos = 0

    def __enter__(self) -> ArchivoJsonl:
        self._fh = self.ruta.open("a", encoding="utf-8", newline="\n")
        return self

    def __exit__(self, *_: object) -> None:
        if self._fh:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    def escribir(self, aviso: Aviso) -> None:
        if self._fh is None:
            raise RuntimeError("Usar dentro de 'with'")
        self._fh.write(json.dumps(a_dict(aviso), ensure_ascii=False) + "\n")
        self.escritos += 1
        # Vaciado periodico: si el proceso muere, se pierde poco
        if self.escritos % 25 == 0:
            self._fh.flush()

    def claves_existentes(self) -> set[str]:
        """Para reanudar: que avisos ya estan en el archivo."""
        if not self.ruta.exists():
            return set()
        claves: set[str] = set()
        for registro in self.leer():
            portal = registro.get("portal")
            id_fuente = registro.get("id_fuente")
            if portal and id_fuente:
                claves.add(f"{portal}:{id_fuente}")
        return claves

    def leer(self) -> Iterator[dict[str, Any]]:
        """Lee el archivo descartando en silencio una ultima linea truncada."""
        if not self.ruta.exists():
            return
        with self.ruta.open("r", encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    yield json.loads(linea)
                except json.JSONDecodeError:
                    continue

    def urls_existentes(self) -> set[str]:
        return {r["url"] for r in self.leer() if r.get("url")}


class AlmacenPostgres:
    """Carga a PostgreSQL. La conexion se abre solo cuando se usa."""

    def __init__(self, dsn: str = "postgresql://postgres@localhost:5432/arriendos") -> None:
        self.dsn = dsn

    def _conectar(self):
        import psycopg

        return psycopg.connect(self.dsn, autocommit=True)

    def crear_esquema(self) -> None:
        with self._conectar() as con, con.cursor() as cur:
            cur.execute(ESQUEMA_SQL)

    def disponible(self) -> bool:
        try:
            with self._conectar() as con, con.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def cargar_crudo(self, registros: Iterable[dict[str, Any]]) -> int:
        filas = [
            (r["portal"], r["id_fuente"], r["url"], r["capturado_en"], json.dumps(r, ensure_ascii=False))
            for r in registros
        ]
        if not filas:
            return 0
        with self._conectar() as con, con.cursor() as cur:
            cur.executemany(
                """INSERT INTO raw.avisos (portal, id_fuente, url, capturado_en, contenido)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (portal, id_fuente, capturado_en) DO NOTHING""",
                filas,
            )
        return len(filas)

    def cargar_limpio(self, avisos: Iterable[Aviso], grupos: dict[str, str] | None = None) -> int:
        grupos = grupos or {}
        filas = []
        for a in avisos:
            clave = a.clave_natural()
            filas.append(
                (
                    a.portal, a.id_fuente, a.url,
                    a.tipo_inmueble.value, a.operacion.value,
                    a.precio, a.moneda, a.administracion,
                    a.area_privada, a.area_construida,
                    a.alcobas, a.banos, a.parqueaderos, a.estrato,
                    a.banda_antiguedad.value if a.banda_antiguedad else None,
                    a.piso, a.direccion, a.latitud, a.longitud,
                    a.barrio, a.comuna, a.ciudad,
                    a.creado_en, a.actualizado_en, a.capturado_en,
                    a.titulo, a.descripcion, a.amenidades,
                    a.capa.value if a.capa else None, a.sospechoso,
                    grupos.get(clave), grupos.get(clave) in (None, clave),
                )
            )
        if not filas:
            return 0
        with self._conectar() as con, con.cursor() as cur:
            cur.executemany(
                """INSERT INTO stg.avisos (
                       portal, id_fuente, url, tipo_inmueble, operacion,
                       precio, moneda, administracion, area_privada, area_construida,
                       alcobas, banos, parqueaderos, estrato, banda_antiguedad,
                       piso, direccion, latitud, longitud, barrio, comuna, ciudad,
                       creado_en, actualizado_en, capturado_en,
                       titulo, descripcion, amenidades, capa, sospechoso,
                       id_grupo, es_canonico)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   -- Se refrescan todas las columnas extraidas, no unas pocas.
                   -- Con una lista corta, una mejora del parser (por ejemplo
                   -- corregir el signo de la longitud) nunca llegaba a la base:
                   -- el aviso ya existia y sus coordenadas viejas se quedaban.
                   ON CONFLICT (portal, id_fuente) DO UPDATE SET
                       url = EXCLUDED.url,
                       tipo_inmueble = EXCLUDED.tipo_inmueble,
                       operacion = EXCLUDED.operacion,
                       precio = EXCLUDED.precio,
                       moneda = EXCLUDED.moneda,
                       administracion = EXCLUDED.administracion,
                       area_privada = EXCLUDED.area_privada,
                       area_construida = EXCLUDED.area_construida,
                       alcobas = EXCLUDED.alcobas,
                       banos = EXCLUDED.banos,
                       parqueaderos = EXCLUDED.parqueaderos,
                       estrato = EXCLUDED.estrato,
                       banda_antiguedad = EXCLUDED.banda_antiguedad,
                       piso = EXCLUDED.piso,
                       direccion = EXCLUDED.direccion,
                       latitud = EXCLUDED.latitud,
                       longitud = EXCLUDED.longitud,
                       barrio = EXCLUDED.barrio,
                       comuna = EXCLUDED.comuna,
                       creado_en = EXCLUDED.creado_en,
                       actualizado_en = EXCLUDED.actualizado_en,
                       capturado_en = EXCLUDED.capturado_en,
                       titulo = EXCLUDED.titulo,
                       descripcion = EXCLUDED.descripcion,
                       amenidades = EXCLUDED.amenidades,
                       capa = EXCLUDED.capa,
                       sospechoso = EXCLUDED.sospechoso,
                       id_grupo = EXCLUDED.id_grupo,
                       es_canonico = EXCLUDED.es_canonico""",
                filas,
            )
        return len(filas)

    def contar(self, tabla: str = "stg.avisos") -> int:
        with self._conectar() as con, con.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {tabla}")
            fila = cur.fetchone()
            return int(fila[0]) if fila else 0
