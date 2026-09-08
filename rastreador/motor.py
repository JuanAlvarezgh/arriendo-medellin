"""Motor de rastreo: une descubrimiento, descarga, cascada y persistencia."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from .descarga.cache import CacheDisco
from .descarga.cliente import Cliente, ErrorDescarga
from .descarga.limite import Guardia
from .descubrimiento.clasificador_url import PerfilUrl, es_aviso
from .descubrimiento.sitemaps import UrlDescubierta, recorrer_sitemaps
from .estado import Estado
from .extraccion.cascada import extraer_todo, id_desde_url
from .normalizacion.esquema import Aviso
from .persistencia.almacen import ArchivoJsonl

DIR_PERFILES = Path(__file__).parent / "perfiles"


def cargar_perfil(nombre: str) -> dict[str, Any]:
    ruta = DIR_PERFILES / f"{nombre}.yaml"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el perfil {nombre} en {DIR_PERFILES}")
    return yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}


def perfiles_disponibles() -> list[str]:
    return sorted(p.stem for p in DIR_PERFILES.glob("*.yaml"))


def guardar_perfil(nombre: str, datos: dict[str, Any]) -> Path:
    ruta = DIR_PERFILES / f"{nombre}.yaml"
    ruta.write_text(
        yaml.safe_dump(datos, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return ruta


@dataclass
class Configuracion:
    portal: str
    tope: int | None = None
    dir_crudo: Path = Path("datos/crudo")
    dir_cache: Path = Path("datos/cache")
    concurrencia: int = 8
    usar_modelo: bool = False
    reanudar: bool = True


class Motor:
    def __init__(
        self,
        config: Configuracion,
        estado: Estado | None = None,
        al_avanzar: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.perfil = cargar_perfil(config.portal)
        self.estado = estado or Estado()
        self.al_avanzar = al_avanzar or (lambda: None)
        self.clasificador = PerfilUrl(dominio=self.perfil["dominio"])
        self._extractor_modelo: Any = None
        if config.usar_modelo:
            from .extraccion.modelo import ExtractorModelo

            self._extractor_modelo = ExtractorModelo(cache_dir=config.dir_cache / "modelo")

    # --- descubrimiento ---

    async def descubrir(self, cliente: Cliente) -> list[UrlDescubierta]:
        cfg = self.perfil.get("sitemaps") or {}
        filtro_sm = cfg.get("filtro_sitemap")
        filtro_url = cfg.get("filtro_url")
        excluir = cfg.get("excluir_url")

        # El tope se aplica al final, sobre lo ya clasificado. Si se aplicara
        # aqui, un sitemap lleno de paginas de categoria consumiria la cuota
        # entera y no llegariamos a los avisos.
        tope_bruto = self.config.tope * 25 if self.config.tope else None

        urls = await recorrer_sitemaps(
            cliente,
            self.perfil["dominio"],
            filtro_sitemap=re.compile(filtro_sm, re.I) if filtro_sm else None,
            filtro_url=re.compile(filtro_url, re.I) if filtro_url else None,
            tope=tope_bruto,
        )

        if excluir:
            patron_excluir = re.compile(excluir, re.I)
            urls = [u for u in urls if not patron_excluir.search(u.url)]

        patron = self.perfil.get("patron_aviso")
        if patron:
            compilado = re.compile(patron, re.I)
            urls = [u for u in urls if compilado.search(u.url)]
        else:
            urls = [u for u in urls if es_aviso(u.url, perfil=self.clasificador)[0]]

        # Deduplicar conservando el orden
        vistas: set[str] = set()
        unicas: list[UrlDescubierta] = []
        for u in urls:
            if u.url in vistas:
                continue
            vistas.add(u.url)
            unicas.append(u)

        if self.config.tope:
            unicas = unicas[: self.config.tope]
        return unicas

    async def descubrir_con_navegador(self) -> list[UrlDescubierta]:
        """Cosecha enlaces de aviso desde paginas de resultados renderizadas.

        Es la via para portales que no publican sitemaps utiles y arman los
        enlaces por JavaScript, donde la lectura del HTML servido no ve nada.
        """
        from .descarga.navegador import navegador

        cfg = self.perfil.get("descubrimiento_navegador") or {}
        plantillas = cfg.get("paginas") or []
        hasta = int(cfg.get("hasta_pagina", 1))
        patron = cfg.get("patron_enlace") or self.perfil.get("patron_aviso") or "/"

        encontradas: list[str] = []
        vistas: set[str] = set()

        async with navegador(concurrencia=int(self.perfil.get("concurrencia", 3))) as nav:
            if not nav.disponible:
                return []
            for plantilla in plantillas:
                if "{n}" not in plantilla:
                    paginas = [plantilla]
                else:
                    paginas = [plantilla.format(n=n) for n in range(2, hasta + 1)]
                for pagina in paginas:
                    enlaces = await nav.enlaces(pagina, patron)
                    nuevos = [e for e in enlaces if e not in vistas]
                    if not nuevos:
                        # Una pagina sin enlaces nuevos indica que se acabo el
                        # listado; seguir paginando solo gasta tiempo.
                        break
                    vistas.update(nuevos)
                    encontradas.extend(nuevos)
                    if self.config.tope and len(encontradas) >= self.config.tope:
                        break
                if self.config.tope and len(encontradas) >= self.config.tope:
                    break

        if self.config.tope:
            encontradas = encontradas[: self.config.tope]
        return [UrlDescubierta(url=u, origen="navegador") for u in encontradas]

    # --- raspado ---

    async def raspar(self) -> list[Aviso]:
        p = self.estado.portal(self.config.portal)
        pps = float(self.perfil.get("limite_peticiones", 1.5))
        concurrencia = int(self.perfil.get("concurrencia", self.config.concurrencia))

        cache = CacheDisco(self.config.dir_cache)
        guardia = Guardia(peticiones_por_segundo=pps)

        salida = ArchivoJsonl(self.config.dir_crudo / f"{self.config.portal}.jsonl")
        ya_hechas: set[str] = salida.urls_existentes() if self.config.reanudar else set()

        con_navegador = bool(self.perfil.get("requiere_navegador"))
        avisos: list[Aviso] = []

        async with Cliente(cache=cache, guardia=guardia, concurrencia=concurrencia) as cliente:
            if con_navegador:
                descubiertas = await self.descubrir_con_navegador()
                if not descubiertas:
                    # Un cero aqui casi nunca es "no hay avisos": es que el
                    # portal esta sirviendo una pagina recortada, tipicamente
                    # por limitacion de ritmo. Decirlo evita que parezca que el
                    # bot fallo en silencio.
                    p.registrar_fallo(
                        "el portal no devolvio avisos al renderizar; "
                        "probable limitacion de ritmo, conviene esperar"
                    )
            else:
                descubiertas = await self.descubrir(cliente)
            p.descubiertos = len(descubiertas)
            self.estado.marcar_avance()
            self.estado.guardar()
            self.al_avanzar()

            pendientes = [u for u in descubiertas if u.url not in ya_hechas]
            p.omitidos = len(descubiertas) - len(pendientes)

            semaforo = asyncio.Semaphore(concurrencia)

            from .descarga.navegador import Navegador

            # El navegador es un recurso asincrono y el archivo uno sincrono.
            # Se abre aparte y se cierra en el finally, en vez de mezclar los
            # dos protocolos de gestor de contexto en un mismo 'with'.
            nav = Navegador(concurrencia=concurrencia) if con_navegador else None
            if nav is not None:
                await nav.__aenter__()

            try:
                async def procesar(u: UrlDescubierta) -> None:
                    async with semaforo:
                        html: str | None = None

                        if nav is not None:
                            # Los portales de una sola pagina exigen renderizado;
                            # el HTML servido no trae precio ni area.
                            en_cache = cache.obtener(u.url)
                            html = en_cache.cuerpo if en_cache else await nav.render(u.url)
                            if html and not en_cache:
                                cache.guardar(u.url, 200, html)
                            if not html:
                                p.registrar_fallo("no se pudo renderizar")
                                self._refrescar(cache)
                                return
                        else:
                            try:
                                r = await cliente.obtener(u.url, pps=pps)
                            except ErrorDescarga as e:
                                p.registrar_fallo(e.motivo.split("(")[0].strip())
                                self._refrescar(cache)
                                return
                            if not r.ok:
                                p.descargados += 1
                                p.registrar_fallo(f"http {r.estado}")
                                self._refrescar(cache)
                                return
                            html = r.texto

                        p.descargados += 1

                        resultado = extraer_todo(
                            html,
                            url=u.url,
                            portal=self.config.portal,
                            perfil=self.perfil,
                            extractor_modelo=self._extractor_modelo,
                        )
                        self.clasificador.aprender(u.url, resultado.aviso is not None)

                        if resultado.aviso is None:
                            p.registrar_fallo(resultado.motivo_fallo or "sin datos")
                        else:
                            aviso = resultado.aviso
                            if aviso.actualizado_en is None and u.modificado:
                                aviso.actualizado_en = u.modificado
                            avisos.append(aviso)
                            salida.escribir(aviso)
                            p.registrar_extraido(resultado.capa.value if resultado.capa else None)
                            self.estado.marcar_avance()

                        self._refrescar(cache)

                with salida:
                    tareas = [procesar(u) for u in pendientes]
                    for i in range(0, len(tareas), 200):
                        await asyncio.gather(*tareas[i : i + 200], return_exceptions=True)
                        self.estado.guardar()
            finally:
                if nav is not None:
                    await nav.__aexit__()

        self.estado.guardar()
        return avisos

    def _refrescar(self, cache: CacheDisco) -> None:
        self.estado.cache_aciertos = cache.aciertos
        self.estado.cache_fallos = cache.fallos
        if self._extractor_modelo is not None:
            self.estado.costo_modelo_usd = self._extractor_modelo.costo_estimado_usd
        self.estado.guardar_si_toca()
        self.al_avanzar()


async def rastrear(
    config: Configuracion,
    estado: Estado | None = None,
    al_avanzar: Callable[[], None] | None = None,
) -> list[Aviso]:
    motor = Motor(config, estado=estado, al_avanzar=al_avanzar)
    return await motor.raspar()
