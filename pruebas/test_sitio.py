"""Pruebas del encabezado comun entre paginas."""

from __future__ import annotations

import re

import pytest

from analisis import sitio


def test_encabezado_marca_solo_la_pagina_activa():
    bloque = sitio.encabezado("sobreprecio")
    cabecera = bloque[bloque.index("<header"):bloque.index("</header>")]
    # Una vez en el menu de escritorio y otra en el de pantallas angostas.
    assert cabecera.count('aria-current="page"') == 2
    assert re.search(r'href="mapa_sobreprecio.html" data-pagina="sobreprecio" aria-current="page"', bloque)
    assert '<summary class="activo">Mapas</summary>' in bloque


def test_encabezado_enlaza_todas_las_paginas_con_rutas_relativas():
    bloque = sitio.encabezado("informe")
    for p in sitio.PAGINAS:
        assert f'href="{p.href}"' in bloque
        assert not p.href.startswith(("/", "http", "file:"))


def test_insertar_usa_el_marcador_si_existe():
    doc = "<html><body><p>a</p>__ENCABEZADO__<p>b</p></body></html>"
    salida = sitio.insertar(doc, "buscar")
    assert sitio.MARCADOR not in salida
    assert salida.index('class="sitio"') > salida.index("<p>a</p>")


def test_insertar_va_despues_de_body_sin_marcador():
    doc = '<html><head></head><BODY class="x"><div id="mapa"></div></BODY></html>'
    salida = sitio.insertar(doc, "atipicos")
    assert salida.index('<header class="sitio">') < salida.index('<div id="mapa">')
    assert "#mapa { top: 52px" in salida


def test_insertar_falla_sin_lugar_donde_ponerlo():
    with pytest.raises(ValueError):
        sitio.insertar("<p>sin cuerpo</p>", "informe")


def test_copiar_no_toca_el_original(tmp_path):
    origen = tmp_path / "mapa.html"
    origen.write_text("<html><body><div class='folium-map'></div></body></html>", encoding="utf-8")
    destino = sitio.copiar_con_encabezado(origen, tmp_path / "web" / "mapa_sobreprecio.html", "sobreprecio")
    assert 'class="sitio"' in destino.read_text(encoding="utf-8")
    assert 'class="sitio"' not in origen.read_text(encoding="utf-8")


def test_construir_sin_regenerar_copia_lo_que_existe(tmp_path, monkeypatch):
    fuente = tmp_path / "hex.html"
    fuente.write_text("<html><body></body></html>", encoding="utf-8")
    monkeypatch.setattr(sitio, "COPIAS", (("mapa_sobreprecio.html", "sobreprecio", fuente),
                                          ("mapa_atipicos.html", "atipicos", tmp_path / "no_existe.html")))
    hechas = sitio.construir(tmp_path / "web", regenerar=False)
    assert [p.name for p in hechas] == ["mapa_sobreprecio.html"]


def test_copiar_pone_titulo_si_falta(tmp_path):
    origen = tmp_path / "mapa.html"
    origen.write_text("<html><head></head><body></body></html>", encoding="utf-8")
    destino = sitio.copiar_con_encabezado(origen, tmp_path / "salida.html", "conglomerados")
    assert "<title>Conglomerados</title>" in destino.read_text(encoding="utf-8")
