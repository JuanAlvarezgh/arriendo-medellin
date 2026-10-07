"""Pruebas de los calculos de la pagina de consulta."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from analisis import consulta


def avisos_sinteticos(semilla: int = 7) -> pd.DataFrame:
    """Tres barrios con precios lognormales y atributos controlados."""
    rng = np.random.default_rng(semilla)
    filas = []
    centros = {"Norte": (6.30, -75.56, 35_000), "Centro": (6.25, -75.57, 45_000), "Sur": (6.20, -75.58, 60_000)}
    for barrio, (lat, lng, m2) in centros.items():
        for _ in range(120):
            area = float(rng.uniform(40, 120))
            amoblado = bool(rng.random() < 0.3)
            precio = area * m2 * np.exp(rng.normal(0, 0.15)) * (1.3 if amoblado else 1.0)
            filas.append({
                "barrio": barrio, "latitud": lat + rng.normal(0, 0.001), "longitud": lng + rng.normal(0, 0.001),
                "tipo_inmueble": "apartamento", "precio": precio, "area": area,
                "alcobas": float(rng.integers(1, 4)), "banos": 2.0, "parqueaderos": float(rng.integers(0, 2)),
                "estrato": 4.0, "estrato_censo": 4.0,
                "amenidades": "amoblado|ascensor" if amoblado else "ascensor",
                "url": "https://ejemplo.co/1", "capturado_en": "2026-09-05T00:00:00+00:00",
            })
    return consulta.preparar_consulta(pd.DataFrame(filas))


def test_hellinger_es_funcion_de_bhattacharyya():
    p = np.array([0.2, 0.5, 0.3])
    q = np.array([0.3, 0.3, 0.4])
    bc = consulta.coeficiente_bhattacharyya(p, q)
    assert consulta.hellinger(p, q) == pytest.approx(np.sqrt(1 - bc))
    assert consulta.hellinger(p, p) == pytest.approx(0.0, abs=1e-7)


def test_percentil_empirico_cuenta_menores_o_iguales():
    muestra = np.array([1, 2, 3, 4, 5])
    assert consulta.percentil_empirico(muestra, 3) == pytest.approx(0.6)
    assert consulta.percentil_empirico(muestra, 0) == 0
    assert consulta.percentil_empirico(muestra, 10) == 1


def test_visitas_y_probabilidad_son_inversas():
    f = 0.2
    n = consulta.visitas_necesarias(f, 0.9)
    assert consulta.probabilidad_en_visitas(f, int(n)) >= 0.9
    assert consulta.probabilidad_en_visitas(f, int(n) - 1) < 0.9
    assert consulta.visitas_necesarias(0.0, 0.9) == float("inf")


def test_intervalo_media_coincide_con_scipy():
    x = np.array([502, 501, 497, 491, 496, 501, 502, 500, 489, 490], dtype=float)
    inf, sup, gl = consulta.intervalo_media(x)
    esperado = stats.t.interval(0.95, len(x) - 1, loc=x.mean(), scale=stats.sem(x))
    assert (inf, sup) == pytest.approx(esperado)
    assert gl == 9


def test_anova_coincide_con_scipy():
    rng = np.random.default_rng(1)
    grupos = np.repeat(["a", "b", "c"], 40)
    y = rng.normal(0, 1, 120) + np.repeat([0, 0.5, 1.0], 40)
    res = consulta.anova_un_factor(y, grupos)
    f, p = stats.f_oneway(y[:40], y[40:80], y[80:])
    assert res["f"] == pytest.approx(f)
    assert res["p"] == pytest.approx(p)
    assert res["ss_entre"] + res["ss_dentro"] == pytest.approx(res["ss_total"])
    assert 0 < res["eta2"] < 1


def test_prueba_f_pone_la_varianza_mayor_arriba():
    rng = np.random.default_rng(2)
    x, y = rng.normal(0, 1, 50), rng.normal(0, 3, 60)
    res = consulta.prueba_f_varianzas(x, y)
    assert res["f"] >= 1
    assert res["gl1"] == 59
    assert res["p"] < 0.05


def test_prueba_pareada_coincide_con_ttest_1samp():
    rng = np.random.default_rng(3)
    d = rng.normal(0.2, 0.3, 80)
    res = consulta.prueba_pareada(d)
    esperado = stats.ttest_1samp(d, 0)
    assert res["t"] == pytest.approx(esperado.statistic)
    assert res["p"] == pytest.approx(esperado.pvalue)
    assert res["efecto"] == pytest.approx(np.exp(d.mean()) - 1)


def test_emparejar_recupera_el_efecto_del_amoblado():
    d = avisos_sinteticos()
    res = consulta.prueba_pareada(consulta.emparejar(d, "c_amoblado"))
    assert res["n"] > 30
    assert res["efecto_inf"] < 0.3 < res["efecto_sup"]


def test_asimetria_pearson_es_positiva_con_cola_derecha():
    x = np.concatenate([np.ones(90), np.full(10, 20.0)])
    assert consulta.asimetria_pearson(x) > 0


def test_z_local_marca_el_aviso_caro_entre_vecinos_baratos():
    n = 20
    d = pd.DataFrame({
        "latitud": 6.25 + np.linspace(0, 0.001, n),
        "longitud": np.full(n, -75.57),
        "precio_m2": np.r_[np.linspace(40_000, 42_000, n - 1), 90_000.0],
    })
    z, vecinos = consulta.z_local(d, radio_m=500, minimo=5)
    assert vecinos[0] == n - 1
    assert z[-1] > consulta.Z_CRITICO
    assert abs(z[0]) < consulta.Z_CRITICO


def test_z_local_queda_vacio_sin_suficientes_vecinos():
    d = pd.DataFrame({"latitud": [6.2, 6.3], "longitud": [-75.5, -75.6], "precio_m2": [1.0, 2.0]})
    z, _ = consulta.z_local(d, minimo=1)
    assert np.isnan(z).all()


def test_ajustar_elige_una_familia_cercana_a_los_datos():
    x = stats.lognorm.rvs(0.4, scale=3_000_000, size=2_000, random_state=4)
    ajuste = consulta.ajustar(x)
    assert ajuste.familia in consulta.FAMILIAS
    assert ajuste.bhattacharyya < 0.02
    assert ajuste.cdf(np.array([np.median(x)]))[0] == pytest.approx(0.5, abs=0.05)


def test_pareto_acumula_hasta_uno():
    d = avisos_sinteticos()
    p = consulta.pareto_oferta(d)
    assert p["acumulado"][-1] == pytest.approx(1.0)
    assert p["barrios_80"] <= p["total_barrios"]


def test_construir_arma_todas_las_secciones():
    d = avisos_sinteticos()
    datos = consulta.construir(d)
    assert set(datos["barrios"]) == {"Norte", "Centro", "Sur"}
    assert len(datos["avisos"]["precio"]) == len(d)
    assert len(datos["duelos"]) == 3
    assert datos["gemelos"]["gemelos"]["Centro"][0]["barrio"] in {"Norte", "Sur"}
    cdf = datos["grupos"]["Centro|todas"]["cdf"]
    assert len(cdf) == len(datos["rejilla"])
    assert all(a <= b for a, b in zip(cdf, cdf[1:]))
    assert datos["normalidad"]["log_precio"]["bhattacharyya"] >= 0


def test_comparar_familias_guarda_lo_que_se_comparo():
    x = stats.lognorm.rvs(0.4, scale=3_000_000, size=1_500, random_state=8)
    c = consulta.comparar_familias(x)
    assert len(c["p"]) == len(c["bordes"]) - 1
    assert c["ganadora"] == min(c["familias"], key=lambda k: c["familias"][k]["distancia"])
    for f in c["familias"].values():
        assert len(f["q"]) == len(c["p"])
        assert f["q"].sum() == pytest.approx(1.0)
    assert consulta.ajustar(x).familia == c["ganadora"]
