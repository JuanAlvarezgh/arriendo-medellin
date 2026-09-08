"""Pruebas de la capa de analisis geografico.

La razon de existir de este modulo es una sola: durante semanas hubo dos
implementaciones de la misma regla, una en el rastreador y otra en el analisis,
y la del analisis era la equivocada. Aqui se fija que solo puede haber una.
"""

from __future__ import annotations

import pytest

from analisis import geo
from rastreador.extraccion.cascada import barrio_desde_url as extractor


URLS_SIN_BARRIO = [
    # Fincaraiz cuando el aviso no declara barrio: la URL solo trae la ciudad.
    "https://www.fincaraiz.com.co/apartaestudio-en-arriendo-en-medellin/191669147",
    "https://www.fincaraiz.com.co/apartamento-en-arriendo-en-medellin/193013032",
    "https://www.fincaraiz.com.co/casa-en-arriendo-en-medellin/193939070",
    "https://www.doomos.com.co/propiedad/arriendo-bodega-en-medellin-c6343788",
]

URLS_CON_BARRIO = [
    ("https://www.fincaraiz.com.co/apartamento-en-arriendo-en-el-poblado-medellin/1938", "El Poblado"),
    ("https://www.fincaraiz.com.co/casa-en-arriendo-en-laureles-medellin/12345678", "Laureles"),
    ("https://www.coninsa.co/inmuebles/apartamento-en-arriendo/belen/medellin/92524/", "Belen"),
]


@pytest.mark.parametrize("url", URLS_SIN_BARRIO)
def test_no_hay_barrio_fantasma(url: str) -> None:
    """El analisis no puede inventar un barrio donde la URL no lo trae.

    La version anterior partia el slug por '-en-' y devolvia el ultimo trozo, que
    en estas URLs es 'arriendo-en'. Eso creo un barrio llamado 'Arriendo En' con
    1.273 avisos repartidos por toda la ciudad, que entro en el mapa y en el
    ranking de sobreprecio como si fuera un lugar real.
    """
    assert geo.barrio_desde_url(url) is None


@pytest.mark.parametrize("url,esperado", URLS_CON_BARRIO)
def test_extrae_el_barrio_cuando_si_esta(url: str, esperado: str) -> None:
    assert geo.barrio_desde_url(url) == esperado


@pytest.mark.parametrize("url", URLS_SIN_BARRIO + [u for u, _ in URLS_CON_BARRIO])
def test_analisis_y_rastreador_dan_lo_mismo(url: str) -> None:
    """Una sola regla. Si alguien vuelve a duplicarla, esta prueba lo dice."""
    assert geo.barrio_desde_url(url) == extractor(url)


def test_ninguna_etiqueta_contiene_la_operacion() -> None:
    """Un barrio nunca se llama 'arriendo', 'venta' ni 'alquiler'.

    Red de proteccion generica: cubre variantes futuras del fallo, no solo la que
    ya se corrigio.
    """
    sospechosas = [
        "https://x.co/apartamento-en-arriendo-en-medellin/1",
        "https://x.co/casa-en-venta-en-medellin/2",
        "https://x.co/local-en-alquiler-en-medellin/3",
        "https://x.co/oficina-en-arrendamiento-en-medellin/4",
    ]
    operaciones = ("arriendo", "alquiler", "venta", "arrendamiento", "renta")
    for url in sospechosas:
        barrio = geo.barrio_desde_url(url)
        assert barrio is None or not any(o in barrio.lower() for o in operaciones), barrio


class TestAmenidades:
    """Las amenidades viajan como lista o como cadena segun el formato.

    Esta ambiguedad produjo un fallo mudo: la comprobacion ingenua devolvia
    False siempre sobre la cadena, sin lanzar error, y el porcentaje de
    amoblados quedo en cero en el mapa y en el tablero.
    """

    @staticmethod
    def _tiene(valor, nombre):
        from analisis.hedonico import tiene_amenidad

        return tiene_amenidad(valor, nombre)

    def test_lista(self):
        assert self._tiene(["ascensor", "amoblado"], "amoblado")
        assert not self._tiene(["ascensor"], "amoblado")

    def test_cadena_con_barras(self):
        assert self._tiene("ascensor|amoblado|porteria", "amoblado")
        assert self._tiene("amoblado", "amoblado")
        assert not self._tiene("ascensor|porteria", "amoblado")

    def test_vacios(self):
        assert not self._tiene("", "amoblado")
        assert not self._tiene(None, "amoblado")
        assert not self._tiene([], "amoblado")
        assert not self._tiene(float("nan"), "amoblado")

    def test_no_confunde_prefijos(self):
        """'piscina' no puede activarse porque exista 'piscina_climatizada'."""
        assert not self._tiene("piscina_climatizada", "piscina")

    def test_array_de_numpy(self):
        """Tras pasar por parquet la lista vuelve como array de numpy."""
        import numpy as np

        assert self._tiene(np.array(["ascensor", "amoblado"]), "amoblado")
        assert not self._tiene(np.array([], dtype=object), "amoblado")
