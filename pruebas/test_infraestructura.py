"""Pruebas de deduplicacion, cache, clasificador de URL, estado y persistencia."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rastreador.deduplicacion.similitud import (
    Grupo,
    agrupar,
    celda_geo,
    clave_bloqueo,
    comparar,
    minhash,
)
from rastreador.descarga.cache import CacheDisco
from rastreador.descarga.limite import AGENTE, EstadoDominio, dominio_de
from rastreador.descubrimiento.clasificador_url import (
    PerfilUrl,
    es_aviso,
    senal_contenido,
    senal_forma,
)
from rastreador.estado import Estado, formato_duracion
from rastreador.normalizacion.esquema import Aviso
from rastreador.persistencia.almacen import ArchivoJsonl


def aviso(**extra) -> Aviso:
    datos = dict(
        id_fuente="1",
        portal="fincaraiz",
        url="https://www.fincaraiz.com.co/x/1",
        precio=2_000_000,
        area_privada=70,
        alcobas=2,
        banos=2,
        estrato=4,
        latitud=6.2442,
        longitud=-75.5812,
    )
    datos.update(extra)
    return Aviso(**datos)


class TestDeduplicacion:
    def test_celda_geo(self):
        assert celda_geo(6.24421, -75.58123) == "6.244:-75.581"
        assert celda_geo(None, -75.5) is None

    def test_clave_bloqueo_requiere_coordenadas(self):
        assert clave_bloqueo(aviso(latitud=None, longitud=None)) is None
        assert clave_bloqueo(aviso()) == "6.244:-75.581|2"

    def test_mismo_aviso_coincide(self):
        a = aviso()
        assert comparar(a, a).coincide

    def test_mismo_inmueble_en_dos_portales(self):
        a = aviso(portal="fincaraiz", id_fuente="1", descripcion="Hermoso apartamento en Laureles con balcon")
        b = aviso(portal="metrocuadrado", id_fuente="99", precio=2_010_000, area_privada=71,
                  descripcion="Hermoso apartamento en Laureles con balcon")
        assert comparar(a, b).coincide

    def test_areas_distintas_no_coinciden(self):
        a = aviso(area_privada=70)
        b = aviso(portal="otro", id_fuente="2", area_privada=140)
        assert not comparar(a, b).coincide

    def test_agrupa_duplicados(self):
        a = aviso(portal="p1", id_fuente="1", descripcion="Apartamento amplio con vista")
        b = aviso(portal="p2", id_fuente="2", precio=2_020_000, descripcion="Apartamento amplio con vista")
        c = aviso(portal="p3", id_fuente="3", precio=9_000_000, area_privada=300, alcobas=5,
                  latitud=6.30, longitud=-75.60)
        grupos = agrupar([a, b, c])
        tamanos = sorted(g.tamano for g in grupos)
        assert tamanos == [1, 2]

    def test_canonico_es_el_mas_completo(self):
        pobre = aviso(portal="p1", id_fuente="1")
        rico = aviso(portal="p2", id_fuente="2", piso=5, parqueaderos=1,
                     direccion="Calle 10 # 40-20", descripcion="Con ascensor y balcon")
        grupos = agrupar([pobre, rico])
        grande = max(grupos, key=lambda g: g.tamano)
        assert grande.canonico.portal == "p2"

    def test_no_encadena_un_edificio_entero(self):
        """Regresion: el union-find transitivo fundia edificios enteros.

        Caso real en Castropol: 47 apartamentos distintos, mismas coordenadas,
        areas escalonadas de 110 a 156 m2. Cada par consecutivo caia dentro de
        la tolerancia del 5% y la cadena los unia a todos en un solo grupo.
        """
        texto = "Apartamento en Castropol con vista"
        edificio = [
            aviso(portal="p1", id_fuente=str(i), area_privada=area, precio=5_000_000 + i * 200_000,
                  alcobas=3, descripcion=texto)
            for i, area in enumerate([110, 115, 120, 126, 132, 138, 145, 152])
        ]
        grupos = agrupar(edificio)
        assert max(g.tamano for g in grupos) < len(edificio)

    def test_mismo_portal_exige_texto_casi_identico(self):
        """Dos unidades del mismo edificio y portal no son duplicados."""
        a = aviso(portal="p1", id_fuente="1", descripcion="Apartamento con balcon al norte")
        b = aviso(portal="p1", id_fuente="2", descripcion="Casa campestre con piscina y jardin")
        assert not comparar(a, b).coincide

    def test_sin_coordenadas_queda_solo(self):
        a = aviso(latitud=None, longitud=None)
        grupos = agrupar([a])
        assert len(grupos) == 1 and grupos[0].tamano == 1

    def test_minhash_similar(self):
        m1 = minhash("apartamento con balcon y ascensor en laureles")
        m2 = minhash("apartamento con balcon y ascensor en laureles!")
        assert m1.jaccard(m2) > 0.8

    def test_grupo_reporta_portales(self):
        a = aviso(portal="p1", id_fuente="1")
        b = aviso(portal="p2", id_fuente="2")
        assert Grupo(a, [a, b]).portales == ["p1", "p2"]


class TestCache:
    def test_ida_y_vuelta(self, tmp_path: Path):
        c = CacheDisco(tmp_path)
        assert c.obtener("https://x.co/1") is None
        c.guardar("https://x.co/1", 200, "<html>hola</html>")
        e = c.obtener("https://x.co/1")
        assert e is not None and e.cuerpo == "<html>hola</html>" and e.estado == 200

    def test_contabiliza_aciertos(self, tmp_path: Path):
        c = CacheDisco(tmp_path)
        c.guardar("https://x.co/1", 200, "a")
        c.obtener("https://x.co/1")
        c.obtener("https://x.co/2")
        assert c.aciertos == 1 and c.fallos == 1
        assert c.tasa_aciertos == 0.5

    def test_ttl_expira(self, tmp_path: Path):
        c = CacheDisco(tmp_path, ttl_horas=0.0)
        c.guardar("https://x.co/1", 200, "a")
        time.sleep(0.01)
        assert c.obtener("https://x.co/1") is None

    def test_archivo_corrupto_se_descarta(self, tmp_path: Path):
        c = CacheDisco(tmp_path)
        c.guardar("https://x.co/1", 200, "a")
        ruta = c._ruta("https://x.co/1")
        ruta.write_bytes(b"esto no es gzip")
        assert c.obtener("https://x.co/1") is None
        assert not ruta.exists()

    def test_reparte_en_subcarpetas(self, tmp_path: Path):
        c = CacheDisco(tmp_path)
        for i in range(20):
            c.guardar(f"https://x.co/{i}", 200, "a")
        subcarpetas = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(subcarpetas) > 1


class TestClasificadorUrl:
    def test_detalle_con_id_numerico(self):
        assert senal_forma("https://x.co/apartamento-en-arriendo-en-laureles-medellin/193855882") > 0.5

    def test_listado_penalizado(self):
        assert senal_forma("https://x.co/buscar?pagina=3") < 0

    def test_directorio_de_inmobiliaria_no_es_aviso(self):
        """Caso real: la inmobiliaria 'Arrendamientos Medellin' colaba paginas de categoria."""
        url = "https://www.fincaraiz.com.co/inmobiliarias/arrendamientos-medellin/174802551/venta/apartamentos"
        assert not es_aviso(url)[0]

    def test_contenido_un_precio_dominante(self):
        aviso_html = '<div>$2.500.000</div><div>70 m2</div><div>3 habitaciones</div>'
        listado_html = "".join(f"<div>$1.{i}00.000</div>" for i in range(15))
        assert senal_contenido(aviso_html) > senal_contenido(listado_html)

    def test_perfil_aprende_la_firma(self):
        p = PerfilUrl(dominio="x.co")
        assert p.firma("https://x.co/algo-medellin/12345") == "/txt/num"
        for i in range(25):
            p.aprender(f"https://x.co/a-medellin/{i}", True)
        assert p.predecir("https://x.co/otro-medellin/999") is True

    def test_perfil_sin_evidencia_no_opina(self):
        p = PerfilUrl(dominio="x.co")
        assert p.predecir("https://x.co/a/1") is None


class TestEstado:
    def test_agregados(self):
        e = Estado()
        p = e.portal("fincaraiz")
        p.descubiertos = 100
        p.descargados = 40
        p.registrar_extraido("b")
        p.registrar_fallo("sin precio")
        assert e.total_descubiertos == 100
        assert e.total_extraidos == 1
        assert e.total_fallidos == 1
        assert e.capas_agregadas()["b"] == 1

    def test_guardar_y_cargar(self, tmp_path: Path):
        e = Estado(ruta=tmp_path / "estado.json")
        e.portal("x").descargados = 7
        e.guardar()
        leido = Estado.cargar(tmp_path / "estado.json")
        assert leido is not None
        assert leido.portales["x"].descargados == 7

    def test_cargar_inexistente(self, tmp_path: Path):
        assert Estado.cargar(tmp_path / "no_existe.json") is None

    def test_deteccion_de_estancamiento(self):
        e = Estado()
        assert e.activo and not e.estancado
        e.ultimo_aviso_en = time.time() - 500
        assert e.estancado and not e.activo

    def test_guardado_periodico_no_escribe_siempre(self, tmp_path: Path):
        e = Estado(ruta=tmp_path / "estado.json")
        e.guardar()
        primera = (tmp_path / "estado.json").stat().st_mtime_ns
        e.guardar_si_toca(cada_segundos=999)
        assert (tmp_path / "estado.json").stat().st_mtime_ns == primera

    def test_formato_duracion(self):
        assert formato_duracion(45) == "45s"
        assert formato_duracion(125) == "2m 05s"
        assert formato_duracion(7500) == "2h 05m"
        assert formato_duracion(None) == "-"


class TestJsonl:
    def test_escribe_y_lee(self, tmp_path: Path):
        ruta = tmp_path / "avisos.jsonl"
        with ArchivoJsonl(ruta) as f:
            f.escribir(aviso(id_fuente="1"))
            f.escribir(aviso(id_fuente="2"))
        assert len(list(ArchivoJsonl(ruta).leer())) == 2

    def test_descarta_linea_truncada(self, tmp_path: Path):
        """Si el proceso muere a mitad de escritura, solo se pierde esa linea."""
        ruta = tmp_path / "avisos.jsonl"
        with ArchivoJsonl(ruta) as f:
            f.escribir(aviso(id_fuente="1"))
        with ruta.open("a", encoding="utf-8") as fh:
            fh.write('{"portal": "x", "id_fuen')
        registros = list(ArchivoJsonl(ruta).leer())
        assert len(registros) == 1

    def test_claves_para_reanudar(self, tmp_path: Path):
        ruta = tmp_path / "avisos.jsonl"
        with ArchivoJsonl(ruta) as f:
            f.escribir(aviso(id_fuente="7"))
        assert ArchivoJsonl(ruta).claves_existentes() == {"fincaraiz:7"}

    def test_urls_existentes(self, tmp_path: Path):
        ruta = tmp_path / "avisos.jsonl"
        with ArchivoJsonl(ruta) as f:
            f.escribir(aviso(url="https://x.co/a"))
        assert ArchivoJsonl(ruta).urls_existentes() == {"https://x.co/a"}


class TestGuardia:
    def test_dominio_sin_www(self):
        assert dominio_de("https://www.fincaraiz.com.co/x") == "fincaraiz.com.co"
        assert dominio_de("https://api.ejemplo.co/x") == "api.ejemplo.co"

    def test_cortacircuitos(self):
        e = EstadoDominio()
        for _ in range(10):
            e.registrar_fallo()
        assert e.cortado
        e.registrar_exito()
        assert not e.cortado

    def test_agente_no_contiene_nombres_de_bots_vetados(self):
        """Regresion: 'respeta robots.txt' contenia 'obot', un bot vetado."""
        assert "obot" not in AGENTE.lower()


class TestSerieIpc:
    """Pruebas de la serie del DANE que no requieren red."""

    def test_url_del_anexo(self):
        from analisis.ipc import url_anexo

        assert url_anexo(2026, 7).endswith("/jul2026/anex-IPC-jul2026.xlsx")
        assert url_anexo(2024, 1).endswith("/ene2024/anex-IPC-ene2024.xlsx")

    def test_periodos_consecutivos(self):
        from analisis.ipc import periodos

        p = periodos((2024, 3))
        assert p == [(2024, 1), (2024, 2), (2024, 3)]

    def test_periodos_cruzan_el_ano(self):
        from analisis.ipc import periodos

        p = periodos((2025, 2))
        assert p[-3:] == [(2024, 12), (2025, 1), (2025, 2)]
        assert len(p) == 14

    def test_acumulado(self):
        import pandas as pd

        from analisis.ipc import acumulado

        df = pd.DataFrame({"indice_arriendo": [100.0, 105.0, 110.0]})
        assert acumulado(df) == pytest.approx(10.0)

    def test_acumulado_sin_datos(self):
        import pandas as pd

        from analisis.ipc import acumulado

        assert acumulado(pd.DataFrame({"indice_arriendo": [100.0]})) is None
