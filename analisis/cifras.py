"""Las cifras del estudio, en un solo sitio y ya formateadas.

Este modulo existe por un error concreto. Las cifras de resultado -el ajuste del
modelo, la elasticidad del area, la banda de sobreprecio entre barrios, el indice
de Moran- estaban escritas a mano en seis archivos distintos: el informe, los tres
modulos de la metodologia, el tablero y la portada de la pagina web. Cuando se
corrigio una regla de extraccion y el modelo se reestimo, todas quedaron
obsoletas a la vez, y nada fallo: los PDF siguieron saliendo, con numeros que ya
no correspondian a los datos.

Ahora hay una sola fuente, `datos/salidas/resumen_modelo.json`, que escribe
`analisis.graficos` en la misma corrida que estima el modelo. Aqui se lee y se
formatea al castellano -coma decimal, punto de millar, signo menos tipografico-
para que el texto de los documentos pueda interpolarla directamente.

Si el resumen no existe todavia, cada campo devuelve un guion en vez de reventar:
un documento con un hueco visible es preferible a uno que no se genera.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUTA_MODELO = Path("datos/salidas/resumen_modelo.json")
RUTA_REJILLA = Path("datos/salidas/web/resumen_rejilla.json")
RUTA_SOBREPRECIO = Path("datos/salidas/sobreprecio_por_barrio.csv")

SIN_DATO = "—"
NOMBRE_PORTALES = {1: "un", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis"}


def miles(valor: Any, decimales: int = 0) -> str:
    """12345.6 -> '12.345,6'. Punto de millar y coma decimal, como en castellano."""
    if valor is None:
        return SIN_DATO
    texto = f"{float(valor):,.{decimales}f}"
    # Se cambia en dos pasos con un simbolo intermedio para no pisar lo ya puesto.
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def decimal(valor: Any, decimales: int = 3) -> str:
    """1234.5 -> '1.234,5'. El menos es el tipografico, no el guion del teclado."""
    if valor is None:
        return SIN_DATO
    return f"{float(valor):.{decimales}f}".replace(".", ",").replace("-", "−")


def porcentaje(valor: Any, decimales: int = 1, signo: bool = False) -> str:
    if valor is None:
        return SIN_DATO
    texto = decimal(abs(float(valor)), decimales) + " %"
    if float(valor) < 0:
        return "−" + texto  # menos tipografico, no guion
    return ("+" + texto) if signo else texto


@dataclass(frozen=True)
class Cifras:
    """Vista de solo lectura sobre el resumen del modelo."""

    modelo: dict
    rejilla: dict

    def _m(self, clave: str, por_defecto=None):
        return self.modelo.get(clave, por_defecto)

    # --- recoleccion ---
    @property
    def avisos(self) -> str:
        return miles(self._m("avisos_recogidos"))

    @property
    def portales(self) -> str:
        n = self._m("portales_recogidos")
        return NOMBRE_PORTALES.get(n, str(n)) if n else SIN_DATO

    @property
    def avisos_modelo(self) -> str:
        return miles(self._m("avisos_modelo"))

    @property
    def precio_m2(self) -> str:
        return miles(self._m("precio_m2_mediano"))

    # --- modelo hedonico ---
    @property
    def r2(self) -> str:
        r = self._m("r2_ajustado")
        return porcentaje(r * 100) if r is not None else SIN_DATO

    @property
    def elasticidad(self) -> str:
        return decimal(self._m("elasticidad_area"))

    @property
    def elasticidad_por_diez(self) -> str:
        """Lo que sube el precio ante un inmueble 10 % mas grande."""
        e = self._m("elasticidad_area")
        return porcentaje(e * 10, 1) if e is not None else SIN_DATO

    @property
    def amoblado(self) -> str:
        return porcentaje(self._efecto("Amoblado"))

    @property
    def bano(self) -> str:
        return porcentaje(self._efecto("Cada bano"))

    @property
    def parqueadero(self) -> str:
        return porcentaje(self._efecto("Cada parqueadero"))

    @property
    def piso_declarado(self) -> str:
        return porcentaje(self._efecto("Declara el piso"), signo=True)

    @property
    def piso_declarado_magnitud(self) -> str:
        """Sin signo, para frases del tipo "un precio 6,1 % menor"."""
        e = self._efecto("Declara el piso")
        return porcentaje(abs(e)) if e is not None else SIN_DATO

    @property
    def piso_altura(self) -> str:
        return porcentaje(self._efecto("Cada piso de altura"), signo=True)

    @property
    def estrato_5(self) -> str:
        return porcentaje(self._m("estrato_5_vs_1"))

    @property
    def estrato_6(self) -> str:
        return porcentaje(self._m("estrato_6_vs_1"))

    # --- descriptivos ---
    @property
    def precio_mediano_millones(self) -> str:
        v = self._m("precio_mediano")
        return decimal(v / 1_000_000, 1) if v else SIN_DATO

    @property
    def pct_amoblado(self) -> str:
        return porcentaje(self._m("pct_amoblado"))

    @property
    def precio_m2_amoblado(self) -> str:
        return miles(self._m("precio_m2_amoblado"))

    @property
    def precio_m2_sin_amoblar(self) -> str:
        return miles(self._m("precio_m2_sin_amoblar"))

    def _efecto(self, nombre: str):
        for e in self._m("efectos", []) or []:
            if e.get("nombre") == nombre:
                return e.get("efecto")
        return None

    # --- ubicacion ---
    @property
    def banda(self) -> str:
        """Redondeo a la mitad hacia arriba, no al par.

        El formato de Python redondea 56,5 a 56 y Math.round de JavaScript a 57,
        de modo que la misma banda salia con dos valores distintos en el PDF y en
        la pagina. Se fija aqui el criterio que espera un lector.
        """
        b = self._m("banda_ubicacion_pp")
        return miles(math.floor(float(b) + 0.5)) if b is not None else SIN_DATO

    @property
    def barrio_caro(self) -> str:
        return (self._m("barrio_mas_caro") or {}).get("barrio", SIN_DATO)

    @property
    def barrio_barato(self) -> str:
        return (self._m("barrio_mas_barato") or {}).get("barrio", SIN_DATO)

    @property
    def sobreprecio_caro(self) -> str:
        return porcentaje((self._m("barrio_mas_caro") or {}).get("sobreprecio"), signo=True)

    @property
    def sobreprecio_barato(self) -> str:
        return porcentaje((self._m("barrio_mas_barato") or {}).get("sobreprecio"), signo=True)

    @property
    def barrios(self) -> str:
        return miles(self._m("barrios_con_sobreprecio"))

    # --- espacial ---
    @property
    def moran(self) -> str:
        i = self._m("moran_i")
        return ("+" + decimal(i, 4)) if i is not None else SIN_DATO

    @property
    def moran_p(self) -> str:
        return decimal(self._m("moran_p"), 3)

    @property
    def vecinos(self) -> str:
        return str(self._m("vecinos") or SIN_DATO)

    @property
    def lambda_espacial(self) -> str:
        return decimal((self._m("espacial") or {}).get("lambda"))

    @property
    def elasticidad_espacial(self) -> str:
        return decimal((self._m("espacial") or {}).get("elasticidad_area"))

    @property
    def correlacion_amoblado(self) -> str:
        c = self._m("correlacion_amoblado")
        return ("+" + decimal(c, 3)) if c is not None else SIN_DATO

    # --- cobertura, de la rejilla ---
    @property
    def celdas(self) -> str:
        return miles(self.rejilla.get("celdas_totales"))

    @property
    def celdas_sin_avisos(self) -> str:
        return miles(self.rejilla.get("celdas_sin_avisos"))

    @property
    def viviendas_sin_avisos(self) -> str:
        return miles(self.rejilla.get("viviendas_sin_ningun_aviso"))

    @property
    def pct_sin_datos(self) -> str:
        return porcentaje(self.rejilla.get("pct_viviendas_sin_datos"))


    # --- tablas ---
    def tabla_efectos(self) -> list[list[str]]:
        """Coeficientes del modelo, listos para el documento.

        Estaba transcrita a mano en la metodologia, con los valores de una
        estimacion anterior. Se genera del mismo resumen que todo lo demas.
        """
        filas = [["Variable", "Lectura", "Efecto", "p"]]
        e = self._m("elasticidad_area")
        if e is not None:
            filas.append(["Area (logaritmo)", "elasticidad", "+" + decimal(e), "&lt;0,001"])
        for ef in sorted(self._m("efectos", []) or [], key=lambda x: -x["efecto"]):
            pv = ef.get("p")
            texto_p = "&lt;0,001" if pv is not None and pv < 0.001 else decimal(pv, 3)
            filas.append(
                [ef["nombre"], "porcentual", porcentaje(ef["efecto"], 1, signo=True), texto_p]
            )
        return filas

    def tabla_espacial(self) -> list[list[str]]:
        """Parametros del modelo de error espacial."""
        lectura = {
            "lambda": "Dependencia espacial del error",
            "Area (logaritmo)": "Elasticidad",
        }
        filas = [["Parametro", "Coeficiente", "z", "Lectura"]]
        for c in (self._m("espacial") or {}).get("coeficientes", []):
            filas.append([
                c["nombre"],
                decimal(c["coeficiente"], 3) if c["coeficiente"] < 0 else "+" + decimal(c["coeficiente"], 3),
                decimal(c["z"], 1) if c["z"] < 0 else "+" + decimal(c["z"], 1),
                lectura.get(c["nombre"]) or porcentaje(c["efecto"], 1, signo=True),
            ])
        return filas

    @property
    def pseudo_r2(self) -> str:
        return decimal((self._m("espacial") or {}).get("pseudo_r2"), 4)

    def tabla_sobreprecio(self, extremos: int = 6) -> list[list[str]]:
        """Los barrios de los dos extremos del sobreprecio, con puntos suspensivos."""
        import csv

        try:
            with RUTA_SOBREPRECIO.open(encoding="utf-8-sig", newline="") as f:
                datos = list(csv.DictReader(f))
        except OSError:
            return [["Barrio", "Avisos", "Sobreprecio", "Precio por m2"]]

        datos.sort(key=lambda r: float(r["sobreprecio_pct"]), reverse=True)

        def fila(r: dict) -> list[str]:
            return [
                r["barrio"],
                r["avisos"],
                porcentaje(float(r["sobreprecio_pct"]), 1, signo=True),
                miles(float(r["precio_m2_mediano"])),
            ]

        cabecera = [["Barrio", "Avisos", "Sobreprecio", "Precio por m2"]]
        if len(datos) <= extremos * 2:
            return cabecera + [fila(r) for r in datos]
        return (
            cabecera
            + [fila(r) for r in datos[:extremos]]
            + [["...", "", "", ""]]
            + [fila(r) for r in datos[-extremos:]]
        )


def cargar(
    ruta_modelo: Path = RUTA_MODELO, ruta_rejilla: Path = RUTA_REJILLA
) -> Cifras:
    def leer(ruta: Path) -> dict:
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    return Cifras(modelo=leer(ruta_modelo), rejilla=leer(ruta_rejilla))


if __name__ == "__main__":
    c = cargar()
    filas = [
        ("Avisos recogidos", c.avisos, c.portales + " portales"),
        ("Muestra del modelo", c.avisos_modelo, "ultimos 90 dias"),
        ("Precio mediano por m2", c.precio_m2, "pesos"),
        ("Ajuste del modelo", c.r2, "R2 ajustado"),
        ("Elasticidad del area", c.elasticidad, "10 % mas grande = " + c.elasticidad_por_diez),
        ("Amoblado", c.amoblado, "sobre el precio"),
        ("Estrato 6 frente al 1", c.estrato_6, "a igualdad de inmueble"),
        ("Banda de ubicacion", c.banda + " pp", f"{c.barrio_caro} a {c.barrio_barato}"),
        ("Indice de Moran", c.moran, "p = " + c.moran_p),
        ("Lambda espacial", c.lambda_espacial, "modelo de error"),
        ("Parque sin un aviso", c.pct_sin_datos, c.viviendas_sin_avisos + " viviendas"),
    ]
    ancho = max(len(f[0]) for f in filas)
    for nombre, valor, nota in filas:
        print(f"{nombre:<{ancho}}  {valor:>12}   {nota}")
