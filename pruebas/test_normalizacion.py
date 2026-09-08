"""Pruebas de la capa de normalizacion.

El foco esta en los formatos reales colombianos, que son la fuente principal
de errores silenciosos: el punto como separador de miles frente a decimal.
"""

from datetime import date, datetime, timezone

import pytest

from rastreador.normalizacion.area import (
    parsear_alcobas,
    parsear_area,
    parsear_banos,
    parsear_estrato,
    parsear_parqueaderos,
    parsear_piso,
)
from rastreador.normalizacion.esquema import (
    Aviso,
    BandaAntiguedad,
    TipoInmueble,
    a_fecha,
    banda_desde_anio,
    extraer_amenidades,
    inferir_banda_antiguedad,
    inferir_tipo,
)
from rastreador.normalizacion.moneda import parsear_precio


class TestPrecio:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("$1.500.000", 1_500_000),
            ("$ 1.500.000", 1_500_000),
            ("1'500.000", 1_500_000),
            ("COP 2.300.000", 2_300_000),
            ("Arriendo $3.200.000 mensuales", 3_200_000),
            ("$950.000", 950_000),
            ("1,5 millones", 1_500_000),
            ("2 millones", 2_000_000),
            ("$12.000.000", 12_000_000),
            ("Canon: 4.500.000", 4_500_000),
        ],
    )
    def test_formatos_colombianos(self, texto, esperado):
        monto, moneda = parsear_precio(texto)
        assert monto == esperado, f"{texto!r} dio {monto}"
        assert moneda == "COP"

    def test_toma_el_arriendo_no_la_administracion(self):
        # El arriendo es el valor dominante; la administracion es menor.
        monto, _ = parsear_precio("Arriendo $2.800.000 + administracion $450.000")
        assert monto == 2_800_000

    def test_ignora_codigos_y_telefonos(self):
        monto, _ = parsear_precio("Codigo 3.104.567 inmueble sin precio")
        assert monto is None

    def test_dolares(self):
        monto, moneda = parsear_precio("USD 1.200 por mes")
        assert moneda == "USD"
        assert monto == 1_200

    def test_texto_sin_precio(self):
        assert parsear_precio("apartamento acogedor") == (None, "COP")
        assert parsear_precio(None) == (None, "COP")
        assert parsear_precio("") == (None, "COP")


class TestArea:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("60 m2", 60.0),
            ("60m²", 60.0),
            ("85,5 mts2", 85.5),
            ("120 metros cuadrados", 120.0),
            ("Area privada: 74", 74.0),
            ("Superficie 200 m2", 200.0),
        ],
    )
    def test_formatos(self, texto, esperado):
        assert parsear_area(texto) == esperado

    def test_toma_la_mayor(self):
        # Area construida suele ser mayor que la privada; se prefiere la mayor
        assert parsear_area("privada 60 m2, construida 75 m2") == 75.0

    def test_descarta_absurdos(self):
        assert parsear_area("1 m2") is None
        assert parsear_area("99999 m2") is None
        assert parsear_area(None) is None


class TestConteos:
    def test_alcobas(self):
        assert parsear_alcobas("3 habitaciones") == 3
        assert parsear_alcobas("2 alcobas amplias") == 2
        assert parsear_alcobas("Habitaciones: 4") == 4
        assert parsear_alcobas("sin datos") is None

    def test_banos(self):
        assert parsear_banos("2 banos") == 2
        assert parsear_banos("3 baños completos") == 3
        assert parsear_banos("Baños: 1") == 1

    def test_parqueaderos(self):
        assert parsear_parqueaderos("1 parqueadero") == 1
        assert parsear_parqueaderos("2 garajes") == 2

    def test_estrato(self):
        assert parsear_estrato("Estrato 5") == 5
        assert parsear_estrato("estrato: 6") == 6
        assert parsear_estrato("Estrato 9") is None

    def test_piso(self):
        assert parsear_piso("Piso 8") == 8
        assert parsear_piso("Piso N° 12") == 12
        assert parsear_piso("piso: 3") == 3


class TestTipoYAntiguedad:
    def test_apartaestudio_gana_sobre_apartamento(self):
        # 'apartamento' es prefijo de nada, pero el orden importa
        assert inferir_tipo("Apartaestudio en arriendo") == TipoInmueble.APARTAESTUDIO
        assert inferir_tipo("Apartamento en arriendo") == TipoInmueble.APARTAMENTO

    def test_casa(self):
        assert inferir_tipo("Casa campestre") == TipoInmueble.CASA

    def test_desconocido(self):
        assert inferir_tipo("cosa rara") == TipoInmueble.OTRO
        assert inferir_tipo(None) == TipoInmueble.OTRO

    def test_bandas_de_fincaraiz(self):
        assert inferir_banda_antiguedad("16 a 30 años") == BandaAntiguedad.DE_16_A_30
        assert inferir_banda_antiguedad("1 a 8 años") == BandaAntiguedad.DE_1_A_8
        assert inferir_banda_antiguedad("menor a 1 año") == BandaAntiguedad.MENOR_1
        assert inferir_banda_antiguedad("mas de 30 años") == BandaAntiguedad.MAYOR_30
        assert inferir_banda_antiguedad("9 a 15 años") == BandaAntiguedad.DE_9_A_15

    def test_anio_exacto_a_banda(self):
        anio_actual = datetime.now().year
        assert banda_desde_anio(anio_actual) == BandaAntiguedad.MENOR_1
        assert banda_desde_anio(anio_actual - 5) == BandaAntiguedad.DE_1_A_8
        assert banda_desde_anio(anio_actual - 40) == BandaAntiguedad.MAYOR_30
        assert banda_desde_anio(None) is None
        assert banda_desde_anio(1500) is None

    def test_orden_ordinal(self):
        assert BandaAntiguedad.MENOR_1.orden < BandaAntiguedad.MAYOR_30.orden


class TestAmenidades:
    def test_extraccion(self):
        texto = "Cuenta con ascensor, porteria 24 horas, piscina y zonas verdes."
        assert extraer_amenidades(texto) == [
            "ascensor",
            "piscina",
            "porteria",
            "zonas_verdes",
        ]

    def test_vacio(self):
        assert extraer_amenidades(None) == []
        assert extraer_amenidades("apartamento sencillo") == []


class TestFechas:
    def test_iso(self):
        assert a_fecha("2026-03-27") == date(2026, 3, 27)
        assert a_fecha("2026-08-12T08:31:56-05:00") == date(2026, 8, 12)

    def test_epoch(self):
        assert a_fecha(1_700_000_000) == date(2023, 11, 14)

    def test_nulos(self):
        assert a_fecha(None) is None
        assert a_fecha("") is None
        assert a_fecha("no es fecha") is None


class TestAviso:
    def _base(self, **extra):
        datos = dict(
            id_fuente="1",
            portal="fincaraiz",
            url="https://www.fincaraiz.com.co/x/1",
            precio=2_500_000,
            area_privada=70,
            latitud=6.24,
            longitud=-75.58,
        )
        datos.update(extra)
        return Aviso(**datos)

    def test_aviso_valido_es_utilizable(self):
        a = self._base()
        assert a.utilizable
        assert a.sospechoso == []
        assert a.precio_por_m2 == pytest.approx(35714.29, rel=1e-3)

    def test_ceros_se_vuelven_nulos(self):
        # Los portales usan 0 para 'sin dato'
        a = self._base(piso=0, alcobas=0, parqueaderos=0)
        assert a.piso is None
        assert a.alcobas is None
        assert a.parqueaderos is None

    def test_marca_precio_absurdo(self):
        a = self._base(precio=50_000)
        assert "precio_muy_bajo" in a.sospechoso
        assert not a.utilizable

    def test_marca_fuera_del_valle(self):
        a = self._base(latitud=4.6, longitud=-74.1)  # Bogota
        assert "latitud_fuera_del_valle" in a.sospechoso
        assert "longitud_fuera_del_valle" in a.sospechoso

    def test_marca_precio_por_m2_atipico(self):
        a = self._base(precio=60_000_000, area_privada=30)
        assert "precio_por_m2_atipico" in a.sospechoso

    def test_estrato_invalido_se_anula(self):
        assert self._base(estrato=9).estrato is None
        assert self._base(estrato=4).estrato == 4

    def test_url_sin_esquema_falla(self):
        with pytest.raises(ValueError):
            Aviso(id_fuente="1", portal="x", url="www.ejemplo.com")

    def test_dias_en_mercado(self):
        a = self._base(
            creado_en=date(2026, 1, 1),
            capturado_en=datetime(2026, 3, 2, tzinfo=timezone.utc),
        )
        assert a.dias_en_mercado == 60

    def test_clave_natural(self):
        assert self._base().clave_natural() == "fincaraiz:1"

    def test_area_cae_a_construida(self):
        a = self._base(area_privada=None, area_construida=88)
        assert a.area == 88
