"""Pruebas de la cascada de extraccion.

Se apoyan en una pagina real de Fincaraiz guardada como fixture, para que los
parsers puedan probarse sin red y sin depender de que el portal siga igual.
"""

from pathlib import Path

import pytest

from rastreador.extraccion import estado_js, estructurados, heuristica
from rastreador.extraccion.cascada import (
    barrio_desde_url,
    extraer_todo,
    id_desde_url,
    _numero,
)
from rastreador.normalizacion.esquema import BandaAntiguedad, Capa, TipoInmueble

FIXTURE = Path(__file__).parent / "fixtures" / "fincaraiz_aviso.html"
URL = "https://www.fincaraiz.com.co/apartamento-en-arriendo-en-alejandria-medellin/10048391"


@pytest.fixture(scope="module")
def html() -> str:
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


class TestEstadoJs:
    def test_encuentra_bloque_next(self, html):
        bloques = estado_js.bloques_de_estado(html)
        assert "next" in bloques

    def test_extrae_sin_mapeo_explicito(self, html):
        """La busqueda automatica debe hallar el aviso sin configuracion del sitio."""
        campos = estado_js.extraer(html)
        assert campos is not None
        assert campos["precio"] == 9_500_000
        assert campos["area_privada"] == 280
        assert campos["alcobas"] == 3
        assert campos["estrato"] == 6

    def test_extrae_ficha_tecnica(self, html):
        campos = estado_js.extraer(html)
        ficha = campos.get("_ficha")
        assert ficha is not None
        assert "16 a 30" in ficha["constructionYear"]

    def test_por_ruta(self):
        obj = {"a": {"b": [{"c": 42}]}}
        assert estado_js.por_ruta(obj, "a.b.c") == 42
        assert estado_js.por_ruta(obj, "a.b.0.c") == 42
        assert estado_js.por_ruta(obj, "a.x.y") is None

    def test_recorte_json_balanceado(self):
        recorte = estado_js._recortar_json('basura {"a": {"b": 1}} cola')
        assert recorte == '{"a": {"b": 1}}'

    def test_recorte_respeta_llaves_en_cadenas(self):
        recorte = estado_js._recortar_json('{"a": "texto con } dentro", "b": 2}')
        assert recorte == '{"a": "texto con } dentro", "b": 2}'

    def test_sin_estado_devuelve_none(self):
        assert estado_js.extraer("<html><body>nada</body></html>") is None

    def test_no_confunde_diccionario_de_filtros(self):
        """Un objeto con precio pero sin medidas no es un aviso."""
        assert estado_js.buscar_objeto_aviso({"price": {"min": 0, "max": 99}}) is None


class TestEstructurados:
    def test_detecta_tipos_schema(self, html):
        tipos = estructurados.tipos_declarados(html)
        assert any("realestatelisting" in t for t in tipos)

    def test_extrae_algo(self, html):
        campos = estructurados.extraer(html, URL)
        assert campos is not None
        assert campos.get("titulo")

    def test_html_vacio(self):
        assert estructurados.extraer("") is None


class TestHeuristica:
    def test_texto_visible_quita_scripts(self):
        html = "<html><body><p>hola</p><script>var x=1;</script></body></html>"
        visible = heuristica.texto_visible(html)
        assert "hola" in visible
        assert "var x" not in visible

    def test_pares_etiqueta_valor(self):
        html = """<html><body><ul>
            <li>Estrato: 4</li>
            <li><span>Habitaciones</span><span>3</span></li>
        </ul></body></html>"""
        pares = heuristica.pares_etiqueta_valor(html)
        assert pares.get("estrato") == "4"
        assert pares.get("habitaciones") == "3"

    def test_extrae_de_ficha_simple(self):
        html = """<html><body>
            <h1>Apartamento en Laureles</h1>
            <ul>
              <li>Canon: $2.500.000</li>
              <li>Area privada: 78 m2</li>
              <li>Habitaciones: 3</li>
              <li>Banos: 2</li>
              <li>Estrato: 5</li>
            </ul></body></html>"""
        campos = heuristica.extraer(html)
        assert campos["precio"] == 2_500_000
        assert campos["area_privada"] == 78
        assert campos["alcobas"] == 3
        assert campos["estrato"] == 5


class TestCascada:
    def test_resuelve_aviso_real(self, html):
        r = extraer_todo(html, url=URL, portal="fincaraiz")
        assert r.aviso is not None
        assert r.capa == Capa.ESTADO_JS

    def test_campos_del_aviso_real(self, html):
        a = extraer_todo(html, url=URL, portal="fincaraiz").aviso
        assert a.precio == 9_500_000
        assert a.area_privada == 280
        assert a.alcobas == 3
        assert a.banos == 4
        assert a.parqueaderos == 3
        assert a.estrato == 6
        assert a.tipo_inmueble == TipoInmueble.APARTAMENTO
        assert a.banda_antiguedad == BandaAntiguedad.DE_16_A_30
        assert a.direccion == "Calle 3 Sur # 32A - 11"
        assert a.latitud == pytest.approx(6.1974, abs=1e-3)

    def test_piso_cero_se_vuelve_nulo(self, html):
        """El portal usa 0 para 'sin dato'; un piso 0 seria un dato falso."""
        a = extraer_todo(html, url=URL, portal="fincaraiz").aviso
        assert a.piso is None

    def test_amenidades_desde_descripcion(self, html):
        a = extraer_todo(html, url=URL, portal="fincaraiz").aviso
        assert "ascensor" in a.amenidades

    def test_barrio_desde_slug(self, html):
        a = extraer_todo(html, url=URL, portal="fincaraiz").aviso
        assert a.barrio == "Alejandria"

    def test_pagina_sin_datos_falla_limpiamente(self):
        r = extraer_todo("<html><body>vacio</body></html>", url="https://x.co/1", portal="x")
        assert r.aviso is None
        assert r.motivo_fallo is not None

    def test_cae_a_heuristica_sin_estructurados(self):
        html = """<html><body><h1>Apartamento</h1>
            <li>Canon: $1.800.000</li><li>Area privada: 60 m2</li></body></html>"""
        r = extraer_todo(html, url="https://ejemplo.co/inmueble/12345", portal="x")
        assert r.aviso is not None
        assert r.capa == Capa.HEURISTICA


class TestAyudantes:
    @pytest.mark.parametrize(
        "url,esperado",
        [
            # Fincaraiz: dos '-en-' en el slug, el barrio va tras el ultimo
            ("https://x.co/apartamento-en-arriendo-en-el-poblado-medellin/193855882", "El Poblado"),
            ("https://x.co/casa-en-arriendo-en-laureles-medellin/12345678", "Laureles"),
            ("https://x.co/apartaestudio-en-arriendo-en-aguas-frias-medellin/1930", "Aguas Frias"),
            # Ciencuadras: identificador tras guion, no tras barra
            (
                "https://www.ciencuadras.com/inmueble/apartamento-en-arriendo-en-el-velodromo-medellin-3858855",
                "El Velodromo",
            ),
            (
                "https://www.ciencuadras.com/inmueble/apartamento-en-arriendo-en-loma-de-los-bernal-medellin-3809417",
                "Loma De Los Bernal",
            ),
            # Coninsa: el barrio es un segmento de ruta antes del municipio
            ("https://www.coninsa.co/inmuebles/apartamento-en-arriendo/belen/medellin/92524/", "Belen"),
            (
                "https://www.coninsa.co/inmuebles/apartamento-en-arriendo/altos-del-poblado/medellin/95303/",
                "Altos Del Poblado",
            ),
            # arriendo.com: municipio y luego barrio, identificador con prefijo
            ("https://arriendo.com/co/apartaestudios/medellin/el-poblado/AR-506175/", "El Poblado"),
            # 'autopista-medellin' es una via en Cota, no un barrio de Medellin
            ("https://arriendo.com/co/bodegas/cota/autopista-medellin/AR-506308/", None),
            ("https://x.co/sin-patron", None),
        ],
    )
    def test_barrio_desde_url(self, url, esperado):
        assert barrio_desde_url(url) == esperado

    @pytest.mark.parametrize(
        "url",
        [
            # Sin barrio en la URL, solo ciudad: el patron capturaba 'arriendo en'
            "https://www.fincaraiz.com.co/apartaestudio-en-arriendo-en-medellin/191669147",
            "https://www.fincaraiz.com.co/apartamento-en-arriendo-en-medellin/123456",
        ],
    )
    def test_no_inventa_barrio_cuando_la_url_no_lo_trae(self, url):
        """Regresion: 1.273 avisos producian un barrio fantasma, 'Arriendo En'."""
        assert barrio_desde_url(url) is None

    def test_barrio_con_patron_del_perfil(self):
        """Un portal nuevo puede aportar su propio patron sin tocar el codigo."""
        assert (
            barrio_desde_url(
                "https://nuevo.co/aviso/barrio=laureles/999",
                patron_propio=r"barrio=(?P<barrio>[a-z-]+)",
            )
            == "Laureles"
        )

    def test_patron_del_perfil_invalido_no_rompe(self):
        assert barrio_desde_url("https://x.co/a", patron_propio="(?P<barrio>[") is None

    @pytest.mark.parametrize(
        "lat,lon,esperado",
        [
            # Ciencuadras publica la longitud sin signo; Colombia es siempre oeste
            (6.244199, 75.563681, -75.563681),
            (6.271183, 75.602108, -75.602108),
            # Lo que ya viene bien no se toca
            (6.244199, -75.563681, -75.563681),
            # Fuera del rango de longitudes de Colombia, no se asume nada
            (6.24, 120.0, 120.0),
            # Sin latitud que confirme el pais, tampoco
            (None, 75.6, 75.6),
            (6.24, None, None),
        ],
    )
    def test_corrige_longitud_sin_signo(self, lat, lon, esperado):
        from rastreador.extraccion.cascada import _corregir_signo_longitud

        assert _corregir_signo_longitud(lat, lon) == esperado

    def test_id_desde_url(self):
        assert id_desde_url("https://x.co/algo-medellin/10048391") == "10048391"
        assert id_desde_url("https://x.co/ref-98765") == "98765"

    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("280 m2", 280.0),
            ("$1.500.000", 1_500_000.0),
            (0, None),
            ("", None),
            (None, None),
            (75.5, 75.5),
            (True, None),
        ],
    )
    def test_numero_tolerante(self, entrada, esperado):
        assert _numero(entrada) == esperado
