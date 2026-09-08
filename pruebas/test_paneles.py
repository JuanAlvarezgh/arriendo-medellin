"""Pruebas de los paneles: la logica de vigilancia y los componentes visuales.

El monitor decidia si una corrida estaba viva dentro del mismo archivo que la
dibujaba, y eso lo hacia imposible de comprobar sin arrancar Streamlit. Con la
logica separada en `analisis.vigilancia`, lo que puede equivocarse se prueba
aqui: el orden en que se decide el estado, la lectura de archivos a medio
escribir y las cuentas de los componentes.
"""

from __future__ import annotations

import json

import pytest

from analisis.vigilancia import (
    INACTIVIDAD_ALERTA,
    clasificar,
    contar_lineas,
    duracion,
    leer_estados,
    miles,
    proceso_vivo,
    ritmo,
)


class TestClasificar:
    def test_activa(self):
        e = clasificar(terminado=False, vivo=True, segundos_sin_avisos=5)
        assert e.rotulo == "Activa" and e.activa

    def test_sin_avance(self):
        e = clasificar(terminado=False, vivo=True, segundos_sin_avisos=INACTIVIDAD_ALERTA + 1)
        assert e.rotulo == "Sin avance" and e.tono == "quieto" and not e.activa

    def test_proceso_muerto(self):
        e = clasificar(terminado=False, vivo=False, segundos_sin_avisos=5)
        assert e.rotulo == "El proceso ya no existe" and e.tono == "parado"

    def test_terminada_gana_a_muerta(self):
        """Acabar bien es dejar de existir: no puede leerse como una caída.

        Si se comprobara primero si el proceso vive, toda corrida exitosa se
        anunciaría en rojo, que es justo lo contrario de lo que pasó.
        """
        e = clasificar(terminado=True, vivo=False, segundos_sin_avisos=99999)
        assert e.rotulo == "Terminada" and e.tono == "hecho"

    def test_justo_en_el_umbral_ya_avisa(self):
        e = clasificar(terminado=False, vivo=True, segundos_sin_avisos=INACTIVIDAD_ALERTA)
        assert e.rotulo == "Sin avance"


class TestLectura:
    def test_estado_a_medio_escribir_se_salta(self, tmp_path):
        """El rastreador reescribe el archivo entero; leerlo a media escritura
        da JSON truncado. Eso no puede tumbar el panel."""
        (tmp_path / "estado_bueno.json").write_text('{"pid": 1}', encoding="utf-8")
        (tmp_path / "estado_roto.json").write_text('{"pid": 2, "porta', encoding="utf-8")

        estados = leer_estados(tmp_path)
        assert len(estados) == 1
        assert estados[0]["pid"] == 1
        assert estados[0]["_archivo"] == "estado_bueno.json"

    def test_sin_archivos(self, tmp_path):
        assert leer_estados(tmp_path) == []

    def test_contar_lineas(self, tmp_path):
        f = tmp_path / "avisos.jsonl"
        f.write_text("\n".join(json.dumps({"i": i}) for i in range(7)), encoding="utf-8")
        assert contar_lineas(f) == 7

    def test_contar_lineas_de_archivo_ausente(self, tmp_path):
        assert contar_lineas(tmp_path / "no-existe.jsonl") == 0

    def test_proceso_sin_pid(self):
        assert proceso_vivo(0) is False

    def test_proceso_propio_esta_vivo(self):
        import os

        assert proceso_vivo(os.getpid()) is True


class TestFormato:
    @pytest.mark.parametrize(
        "segundos,esperado",
        [
            (0, "0 s"),
            (45, "45 s"),
            (249, "4 m 09 s"),
            (80160, "22 h 16 m"),
            (None, "–"),
        ],
    )
    def test_duracion(self, segundos, esperado):
        assert duracion(segundos) == esperado

    @pytest.mark.parametrize(
        "valor,esperado", [(None, "–"), (0.0, "0,0/s"), (2.35, "2,4/s"), (48.0, "48/s")]
    )
    def test_ritmo(self, valor, esperado):
        assert ritmo(valor) == esperado

    def test_miles(self):
        assert miles(17345) == "17.345"


class TestComponentes:
    @staticmethod
    def _barra(partes):
        from analisis.estilo import barra_proporcion

        return barra_proporcion(partes)

    @staticmethod
    def _banda(muestras, color="#000"):
        from analisis.estilo import banda_ritmo

        return banda_ritmo(muestras, color)

    def test_barra_reparte_el_cien_por_ciento(self):
        html = self._barra([("A", 3, "#111"), ("B", 1, "#222")])
        assert "width:75.0000%" in html and "width:25.0000%" in html
        assert "75,0 %" in html and "25,0 %" in html

    def test_barra_ignora_partes_vacias(self):
        html = self._barra([("A", 5, "#111"), ("B", 0, "#222")])
        assert "width:100.0000%" in html
        assert ">B " not in html

    def test_barra_sin_total_no_dibuja_nada(self):
        assert self._barra([("A", 0, "#111")]) == ""
        assert self._barra([]) == ""

    def test_banda_necesita_tres_muestras(self):
        """Con dos muestras hay un solo intervalo: no hay forma que dibujar."""
        assert self._banda([(0.0, 0), (3.0, 5)]) == ""

    def test_banda_dibuja_con_suficientes_muestras(self):
        html = self._banda([(0.0, 0), (3.0, 5), (6.0, 12), (9.0, 14)])
        assert "<svg" in html and "polyline" in html

    def test_banda_soporta_un_contador_que_retrocede(self):
        """Si el archivo se trunca o la corrida se reinicia, el acumulado baja.

        Una velocidad negativa no significa nada y sacaría la línea del marco.
        """
        html = self._banda([(0.0, 100), (3.0, 40), (6.0, 45), (9.0, 60)])
        assert "<svg" in html
        assert "-" not in html.split('points="')[2].split('"')[0]

    def test_banda_con_todo_parado_no_divide_por_cero(self):
        html = self._banda([(0.0, 7), (3.0, 7), (6.0, 7), (9.0, 7)])
        assert "<svg" in html
