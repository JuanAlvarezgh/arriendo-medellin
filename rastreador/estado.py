"""Estado compartido de una corrida.

Se escribe a disco periodicamente para que `rastreador estado`, desde otra
terminal, pueda responder si el bot sigue vivo sin tocar el proceso.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RUTA_ESTADO = Path("datos/estado.json")
INACTIVIDAD_ALERTA = 180.0  # segundos sin un aviso nuevo antes de avisar


@dataclass
class EstadoPortal:
    descubiertos: int = 0
    descargados: int = 0
    extraidos: int = 0
    fallidos: int = 0
    omitidos: int = 0
    por_capa: dict[str, int] = field(default_factory=dict)
    motivos_fallo: dict[str, int] = field(default_factory=dict)
    ultima_capa: str = ""

    def registrar_extraido(self, capa: str | None) -> None:
        self.extraidos += 1
        clave = capa or "sin_capa"
        self.por_capa[clave] = self.por_capa.get(clave, 0) + 1
        self.ultima_capa = clave

    def registrar_fallo(self, motivo: str) -> None:
        self.fallidos += 1
        self.motivos_fallo[motivo] = self.motivos_fallo.get(motivo, 0) + 1


@dataclass
class Estado:
    """Instantanea de la corrida, serializable a disco."""

    iniciado_en: float = field(default_factory=time.time)
    ultimo_aviso_en: float = field(default_factory=time.time)
    actualizado_en: float = field(default_factory=time.time)
    pid: int = field(default_factory=os.getpid)
    terminado: bool = False
    portales: dict[str, EstadoPortal] = field(default_factory=dict)
    cache_aciertos: int = 0
    cache_fallos: int = 0
    duplicados: int = 0
    costo_modelo_usd: float = 0.0
    ruta: Path = field(default=RUTA_ESTADO, repr=False)

    def portal(self, nombre: str) -> EstadoPortal:
        if nombre not in self.portales:
            self.portales[nombre] = EstadoPortal()
        return self.portales[nombre]

    # --- agregados ---

    @property
    def total_descubiertos(self) -> int:
        return sum(p.descubiertos for p in self.portales.values())

    @property
    def total_descargados(self) -> int:
        return sum(p.descargados for p in self.portales.values())

    @property
    def total_extraidos(self) -> int:
        return sum(p.extraidos for p in self.portales.values())

    @property
    def total_fallidos(self) -> int:
        return sum(p.fallidos for p in self.portales.values())

    @property
    def transcurrido(self) -> float:
        return time.time() - self.iniciado_en

    @property
    def ritmo(self) -> float:
        t = self.transcurrido
        return self.total_descargados / t if t > 0 else 0.0

    @property
    def segundos_sin_avisos(self) -> float:
        return time.time() - self.ultimo_aviso_en

    @property
    def activo(self) -> bool:
        return not self.terminado and self.segundos_sin_avisos < INACTIVIDAD_ALERTA

    @property
    def estancado(self) -> bool:
        return not self.terminado and self.segundos_sin_avisos >= INACTIVIDAD_ALERTA

    @property
    def restantes(self) -> int:
        return max(self.total_descubiertos - self.total_descargados, 0)

    @property
    def segundos_restantes(self) -> float | None:
        r = self.ritmo
        return self.restantes / r if r > 0.01 and self.restantes else None

    def capas_agregadas(self) -> Counter:
        c: Counter = Counter()
        for p in self.portales.values():
            c.update(p.por_capa)
        return c

    def marcar_avance(self) -> None:
        self.ultimo_aviso_en = time.time()

    def guardar_si_toca(self, cada_segundos: float = 5.0) -> None:
        """Guardado periodico por tiempo, no por lote.

        Guardar solo al cerrar cada lote dejaba el archivo de estado minutos
        por detras, y `rastreador estado` reportaba falta de avance cuando el
        bot estaba trabajando con normalidad.
        """
        if time.time() - self.actualizado_en >= cada_segundos:
            self.guardar()

    # --- persistencia ---

    def guardar(self) -> None:
        self.actualizado_en = time.time()
        d = {
            "iniciado_en": self.iniciado_en,
            "ultimo_aviso_en": self.ultimo_aviso_en,
            "actualizado_en": self.actualizado_en,
            "pid": self.pid,
            "terminado": self.terminado,
            "cache_aciertos": self.cache_aciertos,
            "cache_fallos": self.cache_fallos,
            "duplicados": self.duplicados,
            "costo_modelo_usd": self.costo_modelo_usd,
            "portales": {k: asdict(v) for k, v in self.portales.items()},
        }
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.ruta)

    @classmethod
    def cargar(cls, ruta: Path | str = RUTA_ESTADO) -> Estado | None:
        ruta = Path(ruta)
        if not ruta.exists():
            return None
        try:
            d = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        e = cls(ruta=ruta)
        e.iniciado_en = d.get("iniciado_en", time.time())
        e.ultimo_aviso_en = d.get("ultimo_aviso_en", e.iniciado_en)
        e.actualizado_en = d.get("actualizado_en", e.iniciado_en)
        e.pid = d.get("pid", 0)
        e.terminado = d.get("terminado", False)
        e.cache_aciertos = d.get("cache_aciertos", 0)
        e.cache_fallos = d.get("cache_fallos", 0)
        e.duplicados = d.get("duplicados", 0)
        e.costo_modelo_usd = d.get("costo_modelo_usd", 0.0)
        for nombre, datos in (d.get("portales") or {}).items():
            e.portales[nombre] = EstadoPortal(**datos)
        return e

    def proceso_vivo(self) -> bool:
        """Comprueba si el proceso que escribio el estado sigue existiendo."""
        if not self.pid or self.terminado:
            return False
        try:
            if os.name == "nt":
                import ctypes

                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, self.pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            os.kill(self.pid, 0)
            return True
        except (OSError, PermissionError):
            return False


def formato_duracion(segundos: float | None) -> str:
    if segundos is None:
        return "-"
    segundos = int(segundos)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def marca_de_tiempo(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%H:%M:%S")
