"""Cliente HTTP asincrono con cache, ritmo por dominio y reintentos."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path

import httpx

from .cache import CacheDisco
from .limite import AGENTE, Guardia, dominio_de

CABECERAS = {
    "User-Agent": AGENTE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

REINTENTABLES = {408, 429, 500, 502, 503, 504}


@dataclass
class Respuesta:
    url: str
    estado: int
    texto: str
    desde_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.estado < 300 and bool(self.texto)


class ErrorDescarga(Exception):
    def __init__(self, url: str, motivo: str) -> None:
        self.url = url
        self.motivo = motivo
        super().__init__(f"{motivo}: {url}")


class Cliente:
    """Descarga con cache, respeto de robots y reintentos con espera creciente."""

    def __init__(
        self,
        cache: CacheDisco | None = None,
        guardia: Guardia | None = None,
        intentos: int = 3,
        tiempo_limite: float = 30.0,
        concurrencia: int = 8,
    ) -> None:
        self.cache = cache
        self.guardia = guardia or Guardia()
        self.intentos = intentos
        self.tiempo_limite = tiempo_limite
        self._semaforo = asyncio.Semaphore(concurrencia)
        self._cliente: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Cliente:
        self._cliente = httpx.AsyncClient(
            headers=CABECERAS,
            follow_redirects=True,
            timeout=httpx.Timeout(self.tiempo_limite),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._cliente:
            await self._cliente.aclose()

    @property
    def bruto(self) -> httpx.AsyncClient:
        if self._cliente is None:
            raise RuntimeError("El cliente debe usarse dentro de 'async with'")
        return self._cliente

    async def obtener(
        self, url: str, *, usar_cache: bool = True, pps: float | None = None
    ) -> Respuesta:
        if usar_cache and self.cache:
            en_cache = self.cache.obtener(url)
            if en_cache is not None:
                return Respuesta(url, en_cache.estado, en_cache.cuerpo, desde_cache=True)

        dom = dominio_de(url)
        await self.guardia.cargar_robots(self.bruto, dom)

        if not self.guardia.permitido(url):
            raise ErrorDescarga(url, "prohibido por robots.txt")

        estado_dom = self.guardia.estado(dom)
        if estado_dom.cortado:
            raise ErrorDescarga(url, "cortacircuitos abierto para el dominio")

        demora = self.guardia.demora_declarada(dom)
        ritmo = min(pps or 1.5, 1.0 / demora) if demora else pps

        limitador = self.guardia.limitador(dom, ritmo)
        ultimo_error = "desconocido"

        for intento in range(1, self.intentos + 1):
            async with self._semaforo:
                async with limitador:
                    try:
                        r = await self.bruto.get(url)
                    except httpx.HTTPError as e:
                        ultimo_error = f"{type(e).__name__}"
                        estado_dom.registrar_fallo()
                        await self._esperar(intento)
                        continue

            if r.status_code in REINTENTABLES:
                ultimo_error = f"http {r.status_code}"
                estado_dom.registrar_fallo()
                espera = self._respetar_retry_after(r) or self._espera(intento)
                await asyncio.sleep(espera)
                continue

            estado_dom.registrar_exito()
            texto = r.text
            if self.cache and 200 <= r.status_code < 300:
                self.cache.guardar(url, r.status_code, texto)
            return Respuesta(url, r.status_code, texto)

        raise ErrorDescarga(url, f"agotados {self.intentos} intentos ({ultimo_error})")

    @staticmethod
    def _espera(intento: int) -> float:
        """Espera creciente con desorden, para no sincronizar reintentos."""
        return min(2.0 ** intento, 30.0) + random.uniform(0, 1.0)

    async def _esperar(self, intento: int) -> None:
        await asyncio.sleep(self._espera(intento))

    @staticmethod
    def _respetar_retry_after(r: httpx.Response) -> float | None:
        valor = r.headers.get("Retry-After")
        if not valor:
            return None
        try:
            return min(float(valor), 60.0)
        except ValueError:
            return None

    async def obtener_muchos(
        self, urls: list[str], *, pps: float | None = None
    ) -> list[Respuesta | ErrorDescarga]:
        tareas = [self.obtener(u, pps=pps) for u in urls]
        return await asyncio.gather(*tareas, return_exceptions=True)  # type: ignore[return-value]


def cliente_por_defecto(directorio_cache: Path | str = "datos/cache", **kw) -> Cliente:
    return Cliente(cache=CacheDisco(Path(directorio_cache)), **kw)
