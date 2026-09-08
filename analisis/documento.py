"""Genera el documento metodologico del proyecto en PDF."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SALIDA = Path("datos/salidas/metodologia_arriendos_medellin.pdf")
TEXTO_PIE = "Arriendos en Medellin"


def _registrar_fuentes() -> tuple[str, str, str, str, str]:
    """Registra DejaVu, que si tiene los simbolos matematicos.

    Las fuentes base del formato PDF (Helvetica, Courier) no incluyen letras
    griegas ni operadores como sumatorio, menor o igual o pertenencia: donde
    deberia haber una formula aparecerian recuadros negros. DejaVu los cubre y
    viaja dentro del entorno del proyecto, asi que no depende del equipo.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    try:
        import matplotlib

        raiz = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
        caras = {
            "Metodo": "DejaVuSans.ttf",
            "Metodo-Bold": "DejaVuSans-Bold.ttf",
            "Metodo-Oblique": "DejaVuSans-Oblique.ttf",
            "Metodo-Mono": "DejaVuSansMono.ttf",
            "Metodo-MonoBold": "DejaVuSansMono-Bold.ttf",
        }
        for nombre, archivo in caras.items():
            pdfmetrics.registerFont(TTFont(nombre, str(raiz / archivo)))
        pdfmetrics.registerFontFamily(
            "Metodo", normal="Metodo", bold="Metodo-Bold",
            italic="Metodo-Oblique", boldItalic="Metodo-Bold",
        )
        pdfmetrics.registerFontFamily(
            "Metodo-Mono", normal="Metodo-Mono", bold="Metodo-MonoBold",
            italic="Metodo-Mono", boldItalic="Metodo-MonoBold",
        )
        return ("Metodo", "Metodo-Bold", "Metodo-Oblique", "Metodo-Mono", "Metodo-MonoBold")
    except Exception:
        return ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Courier", "Courier-Bold")


REGULAR, NEGRITA, CURSIVA, MONO, MONO_NEGRITA = _registrar_fuentes()

TINTA = colors.HexColor("#1a1a1a")
GRIS = colors.HexColor("#5f5f5f")
LINEA = colors.HexColor("#c8c8c8")
FONDO = colors.HexColor("#f2f0eb")
ACENTO = colors.HexColor("#8c3a1e")

_hoja = getSampleStyleSheet()


def estilo(nombre, **kw):
    base = kw.pop("padre", _hoja["Normal"])
    return ParagraphStyle(nombre, parent=base, **kw)


E = {
    "titulo": estilo("titulo", fontName=NEGRITA, fontSize=23, leading=27,
                     textColor=TINTA, spaceAfter=6),
    "subtitulo": estilo("subtitulo", fontName=REGULAR, fontSize=11.5, leading=16,
                        textColor=GRIS, spaceAfter=20),
    "h1": estilo("h1", fontName=NEGRITA, fontSize=15, leading=19,
                 textColor=TINTA, spaceBefore=20, spaceAfter=9),
    "h2": estilo("h2", fontName=NEGRITA, fontSize=11.5, leading=15,
                 textColor=ACENTO, spaceBefore=13, spaceAfter=6),
    "cuerpo": estilo("cuerpo", fontName=REGULAR, fontSize=9.6, leading=14.2,
                     textColor=TINTA, alignment=TA_JUSTIFY, spaceAfter=8),
    "nota": estilo("nota", fontName=CURSIVA, fontSize=8.7, leading=12.6,
                   textColor=GRIS, alignment=TA_JUSTIFY, spaceAfter=8),
    "formula": estilo("formula", fontName=MONO_NEGRITA, fontSize=9.6, leading=14,
                      textColor=TINTA, alignment=TA_CENTER, spaceBefore=6, spaceAfter=8),
    "codigo": estilo("codigo", fontName=MONO, fontSize=8.2, leading=11.4,
                     textColor=TINTA, spaceAfter=8),
    "celda": estilo("celda", fontName=REGULAR, fontSize=8.4, leading=11.4, textColor=TINTA),
    "celdaneg": estilo("celdaneg", fontName=NEGRITA, fontSize=8.4, leading=11.4,
                       textColor=TINTA),
    "vineta": estilo("vineta", fontName=REGULAR, fontSize=9.6, leading=14,
                     textColor=TINTA, alignment=TA_JUSTIFY, leftIndent=13,
                     bulletIndent=3, spaceAfter=5),
}


def p(texto, e="cuerpo"):
    return Paragraph(texto, E[e])


def vineta(texto):
    return Paragraph(texto, E["vineta"], bulletText="–")


def formula(texto):
    return Paragraph(texto, E["formula"])


def tabla(filas, anchos, cabecera=True, alineacion_derecha=None):
    datos = []
    for i, fila in enumerate(filas):
        est = "celdaneg" if (cabecera and i == 0) else "celda"
        datos.append([Paragraph(str(c), E[est]) for c in fila])

    t = Table(datos, colWidths=anchos, hAlign="LEFT", repeatRows=1 if cabecera else 0)
    orden = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINEA),
    ]
    if cabecera:
        orden += [
            ("BACKGROUND", (0, 0), (-1, 0), FONDO),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, GRIS),
        ]
    for col in alineacion_derecha or []:
        orden.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    t.setStyle(TableStyle(orden))
    return t


def bloque(texto):
    """Recuadro para observaciones importantes."""
    t = Table([[Paragraph(texto, E["cuerpo"])]], colWidths=[16.4 * cm], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), FONDO),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACENTO),
            ]
        )
    )
    return t


def pie(canvas, doc):
    canvas.saveState()
    canvas.setFont(REGULAR, 7.6)
    canvas.setFillColor(GRIS)
    canvas.drawString(2.3 * cm, 1.3 * cm, TEXTO_PIE)
    canvas.drawRightString(A4[0] - 2.3 * cm, 1.3 * cm, str(doc.page))
    canvas.setStrokeColor(LINEA)
    canvas.setLineWidth(0.4)
    canvas.line(2.3 * cm, 1.75 * cm, A4[0] - 2.3 * cm, 1.75 * cm)
    canvas.restoreState()
