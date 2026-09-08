"""Renderizado con navegador, para portales que no sirven datos en el HTML.

Es la via cara: un navegador por pagina cuesta uno o dos ordenes de magnitud
mas que una peticion HTTP. Se usa solo cuando el perfil del sitio declara
`categoria: spa` y el descubrimiento de API interna no dio resultado.

Ciencuadras es el caso que motivo este modulo: su HTML servido no trae precios
ni areas, pero tras renderizar aparecen, y no expone un endpoint JSON de
listados que se pueda llamar directamente.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .limite import AGENTE

ESPERA_RED_MS = 45_000
ESPERA_EXTRA_MS = 3_000

# Cargar imagenes y tipografias no aporta datos y multiplica el tiempo.
RECURSOS_BLOQUEADOS = {"image", "media", "font", "stylesheet"}


class Navegador:
    """Envoltura de Playwright con una sola instancia reutilizada."""

    def __init__(self, concurrencia: int = 3, bloquear_recursos: bool = True) -> None:
        self.concurrencia = concurrencia
        self.bloquear_recursos = bloquear_recursos
        self._pw = None
        self._navegador = None
        self._contexto = None
        self._semaforo = asyncio.Semaphore(concurrencia)
        self.disponible = False

    async def __aenter__(self) -> "Navegador":
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return self
        self._pw = await async_playwright().start()
        self._navegador = await self._pw.chromium.launch(headless=True)
        self._contexto = await self._navegador.new_context(
            user_agent=AGENTE,
            locale="es-CO",
            viewport={"width": 1366, "height": 900},
        )
        if self.bloquear_recursos:
            await self._contexto.route("**/*", self._filtrar)
        self.disponible = True
        return self

    async def __aexit__(self, *_: object) -> None:
        for cerrar in (self._contexto, self._navegador):
            if cerrar is not None:
                try:
                    await cerrar.close()
                except Exception:
                    pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self.disponible = False

    @staticmethod
    async def _filtrar(ruta, peticion) -> None:
        if peticion.resource_type in RECURSOS_BLOQUEADOS:
            await ruta.abort()
        else:
            await ruta.continue_()

    async def render(self, url: str, espera_extra_ms: int = ESPERA_EXTRA_MS) -> str | None:
        """Devuelve el HTML ya renderizado, o None si no se pudo."""
        if not self.disponible or self._contexto is None:
            return None
        async with self._semaforo:
            pagina = await self._contexto.new_page()
            try:
                await pagina.goto(url, wait_until="domcontentloaded", timeout=ESPERA_RED_MS)
                try:
                    await pagina.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    # Muchas paginas nunca quedan del todo en reposo por
                    # analitica y sondeos; no es motivo para descartarlas.
                    pass
                if espera_extra_ms:
                    await pagina.wait_for_timeout(espera_extra_ms)
                return await pagina.content()
            except Exception:
                return None
            finally:
                await pagina.close()

    async def enlaces(self, url: str, patron: str) -> list[str]:
        """Enlaces de la pagina renderizada que casan con un patron."""
        import re

        html = await self.render(url)
        if not html:
            return []
        from urllib.parse import urljoin

        compilado = re.compile(patron, re.I)
        vistos: list[str] = []
        for m in re.finditer(r'href="([^"#?]+)"', html):
            completo = urljoin(url, m.group(1))
            if compilado.search(completo) and completo not in vistos:
                vistos.append(completo)
        return vistos


@asynccontextmanager
async def navegador(concurrencia: int = 3) -> AsyncIterator[Navegador]:
    n = Navegador(concurrencia=concurrencia)
    try:
        await n.__aenter__()
        yield n
    finally:
        await n.__aexit__()
