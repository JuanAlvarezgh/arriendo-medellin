"""Control de ritmo y cumplimiento de robots.txt, por dominio."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from aiolimiter import AsyncLimiter
from protego import Protego

# Cuidado al cambiarlo: se compara como subcadena contra las listas de bots
# prohibidos de los portales. Una version anterior decia "respeta robots.txt" y
# la subcadena "obot", dentro de "robots", coincidia con un bot vetado llamado
# OBot, con lo que el rastreador se prohibia a si mismo.
AGENTE = "rastreador-academico/0.1 (proyecto universitario de analitica de datos)"


def dominio_de(url: str) -> str:
    neto = urlparse(url).netloc.lower()
    return neto[4:] if neto.startswith("www.") else neto


@dataclass
class EstadoDominio:
    """Cortacircuitos: si un dominio acumula fallos seguidos, se deja de insistir."""

    fallos_seguidos: int = 0
    abierto_hasta: float = 0.0
    total_peticiones: int = 0
    total_fallos: int = 0

    def registrar_exito(self) -> None:
        self.fallos_seguidos = 0
        self.total_peticiones += 1

    def registrar_fallo(self) -> None:
        self.fallos_seguidos += 1
        self.total_peticiones += 1
        self.total_fallos += 1

    @property
    def cortado(self) -> bool:
        return self.fallos_seguidos >= 10


class Guardia:
    """Une tres cosas por dominio: ritmo, robots.txt y cortacircuitos."""

    def __init__(self, peticiones_por_segundo: float = 1.5, respetar_robots: bool = True) -> None:
        self.pps = peticiones_por_segundo
        self.respetar_robots = respetar_robots
        self._limitadores: dict[str, AsyncLimiter] = {}
        self._robots: dict[str, Protego | None] = {}
        self._estados: dict[str, EstadoDominio] = {}
        self._cerrojo = asyncio.Lock()

    def limitador(self, dominio: str, pps: float | None = None) -> AsyncLimiter:
        if dominio not in self._limitadores:
            ritmo = pps or self.pps
            # Ventana de 1 s con capacidad = peticiones por segundo
            self._limitadores[dominio] = AsyncLimiter(max_rate=ritmo, time_period=1.0)
        return self._limitadores[dominio]

    def estado(self, dominio: str) -> EstadoDominio:
        return self._estados.setdefault(dominio, EstadoDominio())

    async def cargar_robots(self, cliente: httpx.AsyncClient, dominio: str) -> None:
        if dominio in self._robots:
            return
        async with self._cerrojo:
            if dominio in self._robots:
                return
            texto = None
            for base in (f"https://www.{dominio}", f"https://{dominio}"):
                try:
                    r = await cliente.get(f"{base}/robots.txt", timeout=15.0)
                    if r.status_code == 200 and r.text.strip():
                        texto = r.text
                        break
                except (httpx.HTTPError, UnicodeDecodeError):
                    continue
            try:
                self._robots[dominio] = Protego.parse(texto) if texto else None
            except Exception:
                # Un robots.txt malformado no debe tumbar el rastreo
                self._robots[dominio] = None

    def permitido(self, url: str) -> bool:
        if not self.respetar_robots:
            return True
        dom = dominio_de(url)
        robots = self._robots.get(dom)
        if robots is None:
            return True  # sin robots.txt legible, no hay prohibicion declarada
        try:
            return bool(robots.can_fetch(url, AGENTE))
        except Exception:
            return True

    def demora_declarada(self, dominio: str) -> float | None:
        robots = self._robots.get(dominio)
        if robots is None:
            return None
        try:
            d = robots.crawl_delay(AGENTE)
            return float(d) if d else None
        except Exception:
            return None
