"""Arma el PDF metodologico completo."""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate

from .contenido_documento import parte_bot, portada
from .contenido_espacial import (
    parte_calidad,
    parte_espacial,
    parte_geografia,
    parte_logros,
    parte_sobreprecio,
)
from .contenido_matematico import parte_duplicados, parte_hedonico, parte_sospechoso
from .documento import SALIDA, pie


def construir(salida: Path = SALIDA) -> Path:
    salida.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(salida),
        pagesize=A4,
        leftMargin=2.3 * cm,
        rightMargin=2.3 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
        title="Metodologia. Arriendos en Medellin",
        author="Juan Carlos Alvarez Arias",
        subject="Documento metodologico del analisis de arriendos en Medellin",
    )
    historia = []
    for parte in (portada, parte_bot, parte_sospechoso, parte_duplicados,
                  parte_hedonico, parte_sobreprecio, parte_espacial,
                  parte_geografia, parte_calidad, parte_logros):
        historia.extend(parte())
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida


if __name__ == "__main__":
    print("escrito en", construir())
