"""Pruebas del formateo de cifras al castellano.

El modulo `analisis.cifras` sustituyo a las cifras escritas a mano en los
documentos. Como ahora todos los numeros del informe, la metodologia, el tablero
y la pagina pasan por aqui, un fallo de formato saldria impreso en todos a la
vez.
"""

from __future__ import annotations

import json

import pytest

from analisis.cifras import Cifras, cargar, decimal, miles, porcentaje


class TestFormato:
    @pytest.mark.parametrize(
        "valor,esperado",
        [
            (1234, "1.234"),
            (17345, "17.345"),
            (255413, "255.413"),
            (0, "0"),
            (None, "—"),
        ],
    )
    def test_miles(self, valor, esperado):
        """Punto de millar, no coma: 17.345 y no 17,345."""
        assert miles(valor) == esperado

    def test_miles_con_decimales(self):
        assert miles(1234.56, 2) == "1.234,56"

    @pytest.mark.parametrize(
        "valor,esperado",
        [(0.5208, "0,521"), (0.1128, "0,113"), (-0.014, "−0,014")],
    )
    def test_decimal(self, valor, esperado):
        """Coma decimal, y el menos tipografico en vez del guion del teclado."""
        assert decimal(valor) == esperado

    def test_el_menos_no_es_un_guion(self):
        """Regresion: el guion del teclado desentona con la tipografia del PDF."""
        assert "-" not in decimal(-3.5)
        assert "−" in decimal(-3.5)

    @pytest.mark.parametrize(
        "valor,signo,esperado",
        [
            (31.6, False, "31,6 %"),
            (31.6, True, "+31,6 %"),
            (-18.0, False, "−18,0 %"),
            (-18.0, True, "−18,0 %"),
        ],
    )
    def test_porcentaje(self, valor, signo, esperado):
        assert porcentaje(valor, signo=signo) == esperado

    def test_negativo_no_lleva_doble_signo(self):
        """Pedir signo explicito sobre un negativo no puede dar '+−18,0 %'."""
        assert porcentaje(-18.0, signo=True) == "−18,0 %"


class TestSinResumen:
    """Sin el archivo de resumen, cada campo da un guion en vez de reventar.

    Un documento con un hueco visible es preferible a uno que no se genera: el
    hueco se ve al revisarlo, y el fallo de generacion bloquea la entrega.
    """

    @pytest.fixture
    def vacias(self) -> Cifras:
        return Cifras(modelo={}, rejilla={})

    @pytest.mark.parametrize(
        "campo",
        [
            "avisos", "portales", "avisos_modelo", "precio_m2", "r2", "elasticidad",
            "amoblado", "banda", "barrio_caro", "moran", "lambda_espacial",
            "correlacion_amoblado", "pct_sin_datos",
        ],
    )
    def test_ningun_campo_revienta(self, vacias, campo):
        assert isinstance(getattr(vacias, campo), str)

    def test_las_tablas_traen_al_menos_la_cabecera(self, vacias):
        assert vacias.tabla_efectos()[0][0] == "Variable"
        assert vacias.tabla_espacial()[0][0] == "Parametro"

    def test_cargar_con_rutas_inexistentes(self, tmp_path):
        c = cargar(tmp_path / "no-existe.json", tmp_path / "tampoco.json")
        assert c.modelo == {} and c.rejilla == {}


class TestConResumen:
    @pytest.fixture
    def cifras(self, tmp_path) -> Cifras:
        modelo = {
            "avisos_recogidos": 17345,
            "portales_recogidos": 4,
            "avisos_modelo": 7274,
            "r2_ajustado": 0.8598,
            "elasticidad_area": 0.5208,
            "precio_m2_mediano": 48760,
            "moran_i": 0.1128,
            "moran_p": 0.001,
            "banda_ubicacion_pp": 56.5,
            "barrio_mas_caro": {"barrio": "La Aguacatala", "sobreprecio": 38.4},
            "barrio_mas_barato": {"barrio": "Centro", "sobreprecio": -18.0},
            "efectos": [
                {"nombre": "Amoblado", "efecto": 31.6, "p": 0.0, "significativo": True},
                {"nombre": "Declara el piso", "efecto": -6.1, "p": 0.0, "significativo": True},
            ],
            "espacial": {"lambda": 0.673, "pseudo_r2": 0.7506, "elasticidad_area": 0.5507},
        }
        m = tmp_path / "modelo.json"
        m.write_text(json.dumps(modelo), encoding="utf-8")
        return cargar(m, tmp_path / "sin-rejilla.json")

    def test_portales_en_letra(self, cifras):
        assert cifras.portales == "cuatro"

    def test_r2_como_porcentaje(self, cifras):
        """0,8598 se publica como 86,0 %, no como 0,86."""
        assert cifras.r2 == "86,0 %"

    def test_elasticidad_por_diez(self, cifras):
        """La elasticidad no es un porcentaje: 0,521 significa 5,2 % por cada 10 %."""
        assert cifras.elasticidad == "0,521"
        assert cifras.elasticidad_por_diez == "5,2 %"

    def test_banda_redondea_la_mitad_hacia_arriba(self, cifras):
        """56,5 pp da 57, no 56.

        El formato de Python redondea al par y Math.round de JavaScript hacia
        arriba, de modo que la misma banda salia con dos valores distintos en el
        PDF y en la pagina web. Aqui se fija el criterio.
        """
        assert cifras.banda == "57"

    def test_extremos_del_sobreprecio(self, cifras):
        assert cifras.barrio_caro == "La Aguacatala"
        assert cifras.sobreprecio_caro == "+38,4 %"
        assert cifras.barrio_barato == "Centro"
        assert cifras.sobreprecio_barato == "−18,0 %"

    def test_piso_con_y_sin_signo(self, cifras):
        """La frase 'un precio 6,1 % menor' necesita la magnitud, no el signo."""
        assert cifras.piso_declarado == "−6,1 %"
        assert cifras.piso_declarado_magnitud == "6,1 %"

    def test_tabla_de_efectos_ordenada_de_mayor_a_menor(self, cifras):
        filas = cifras.tabla_efectos()
        assert filas[0] == ["Variable", "Lectura", "Efecto", "p"]
        assert filas[1][0] == "Area (logaritmo)"
        assert filas[1][1] == "elasticidad"  # no es un efecto porcentual
        assert [f[0] for f in filas[2:]] == ["Amoblado", "Declara el piso"]

    def test_efecto_ausente_no_revienta(self, cifras):
        assert cifras.bano == "—"
