"""Informe final: hallazgos del analisis, con las figuras."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, PageBreak, SimpleDocTemplate, Spacer

from .cifras import cargar as cargar_cifras
from .documento import bloque, p, pie, tabla, vineta

# Las cifras del estudio, leidas del resumen que escribe `analisis.graficos`.
# De ahi el orden obligatorio: primero las figuras, despues los documentos.
C = cargar_cifras()

SALIDA = Path("datos/salidas/informe_arriendos_medellin.pdf")
FIGURAS = Path("datos/salidas/figuras")
ANCHO = 14.6 * cm


def figura(ruta: Path, pie_texto: str, ancho: float = ANCHO):
    """Inserta una figura escalada al ancho util, con su pie."""
    from PIL import Image as PILImage

    with PILImage.open(ruta) as im:
        w, h = im.size
    alto = ancho * h / w
    tope = 16.0 * cm
    if alto > tope:
        ancho, alto = ancho * tope / alto, tope
    return KeepTogether([
        Spacer(1, 0.25 * cm),
        Image(str(ruta), width=ancho, height=alto),
        Spacer(1, 0.12 * cm),
        p(pie_texto, "nota"),
    ])


def portada():
    return [
        Spacer(1, 3.2 * cm),
        p("Por que subio el precio de los arriendos en Medellin", "titulo"),
        p(
            f"Informe de resultados. Analisis de {C.avisos} avisos de arriendo recogidos "
            f"de {C.portales} portales inmobiliarios, cruzados con el censo del DANE y con "
            "el indice de precios al consumidor.",
            "subtitulo",
        ),
        tabla(
            [
                ["Cuanto subio", "El arriendo nacional acumulo +10,5 % en 24 meses"],
                ["Y en Medellin", "Se desacoplo del pais: de 4,45 % a 7,42 % anual desde julio de 2025"],
                ["Que lo encarece", f"Estar amoblado suma {C.amoblado}; el estrato 6 paga {C.estrato_6} mas que el 1"],
                ["Cuanto vale la ubicacion", f"{C.banda} puntos entre el barrio mas caro y el mas barato, a igualdad de inmueble"],
                ["Y esta agrupada", f"I de Moran = {C.moran} (p = {C.moran_p}): el precio depende del de los vecinos"],
                ["La renta corta", "Las viviendas turisticas registradas pasaron de 521 a 8.766 entre 2019 y 2024"],
            ],
            [4.6 * cm, 11.8 * cm],
            cabecera=False,
        ),
        Spacer(1, 0.8 * cm),
        p(
            "La metodologia, las formulas y la arquitectura del bot de extraccion se "
            "documentan aparte, en el documento metodologico que acompana a este "
            "informe.",
            "nota",
        ),
        PageBreak(),
    ]


def resumen():
    return [
        p("Resumen", "h1"),
        p(
            "El arriendo en Medellin subio, y subio distinto al resto del pais. Ese es "
            "el hallazgo central y conviene enunciarlo antes que nada, porque cambia "
            "la lectura de todo lo demas.",
        ),
        p(
            "El indice de precios del DANE muestra que el arriendo efectivo nacional "
            "viene <b>desacelerando</b>: su variacion anual bajo de 8,05 % a 4,89 % en "
            "dos anos. Medellin hizo lo contrario. Su division de alojamiento toco "
            "fondo en julio de 2025 con 4,45 % y desde entonces subio hasta 7,42 %. La "
            "brecha con el promedio nacional paso de −0,09 a <b>+2,02 puntos "
            "porcentuales</b>.",
        ),
        p(
            f"El corte transversal de {C.avisos} avisos explica donde se concentra ese "
            f"movimiento. Un modelo hedonico da cuenta del <b>{C.r2}</b> de la varianza "
            "del precio pedido a partir de los atributos del inmueble. Lo que queda sin "
            "explicar, agrupado por barrio, mide cuanto cuesta la ubicacion en si "
            f"misma: <b>{C.banda} puntos porcentuales</b> entre {C.barrio_caro} y "
            f"{C.barrio_barato}, para inmuebles equivalentes.",
        ),
        p(
            "Y esa ubicacion no esta dispersa. El indice de Moran sobre los residuales "
            f"del modelo da <b>{C.moran} con p = {C.moran_p}</b>: el precio de un inmueble "
            "depende del de sus vecinos por encima de lo que explican sus propios "
            "atributos. El modelo espacial estimado sobre ese diagnostico arroja un "
            f"parametro de dependencia de <b>{C.lambda_espacial}</b>. El mercado no es un "
            "conjunto de precios individuales, es un territorio segmentado.",
        ),
        bloque(
            "<b>Que aporta cada fuente.</b> El raspado de portales es una fotografia: "
            "dice donde esta caro hoy, no si subio. El indice del DANE aporta la "
            "dimension temporal, que ninguna cantidad de avisos puede dar. El censo "
            "aporta el denominador y permite contrastar el estrato declarado con el "
            "oficial. Las tres piezas responden preguntas distintas y ninguna sustituye "
            "a las otras."
        ),
        PageBreak(),
    ]


def parte_cuanto():
    return [
        p("1. Cuanto subio, y donde se separa Medellin", "h1"),
        p(
            "La pregunta contiene un verbo en pasado, y un verbo en pasado exige dos "
            "momentos. Un raspado entrega uno solo: todos los avisos son de hoy. Por "
            "eso la magnitud del alza viene del indice de precios al consumidor del "
            "DANE, que publica mensualmente la subclase <b>04130100, arriendo "
            "efectivo</b>.",
        ),
        p(
            "El arriendo efectivo nacional paso de un indice de 125,28 en agosto de "
            "2024 a 138,44 en julio de 2026: <b>+10,5 % acumulado en veinticuatro "
            "meses</b>. Pero su ritmo viene bajando, de 8,05 % a 4,89 % anual. En "
            "terminos agregados, el pais esta saliendo del episodio inflacionario.",
        ),
        p(
            "Medellin no. Su division de alojamiento toco un minimo de 4,45 % en julio "
            "de 2025 y desde ahi se reacelero casi tres puntos, hasta 7,42 % en julio "
            "de 2026. Hace dos anos iba levemente por debajo del promedio nacional; "
            "hoy va dos puntos por encima.",
        ),
        figura(
            Path("datos/salidas/ipc_divergencia_medellin.png"),
            "Figura 1. La linea de Medellin cae con el pais hasta mediados de 2025 y "
            "luego se separa. El panel inferior muestra la brecha, que cambia de signo "
            "y se ensancha hasta superar los dos puntos porcentuales.",
        ),
        bloque(
            "<b>Precision necesaria.</b> El DANE publica la subclase de arriendo puro "
            "solo a nivel nacional. Para Medellin, el mayor detalle disponible es la "
            "division completa de alojamiento, que incluye agua, electricidad, gas y "
            "recogida de basuras. No es lo mismo que arriendo, y este informe no lo "
            "presenta como si lo fuera: lo que la figura muestra es que el costo de "
            "habitar en Medellin se separo del nacional, no que el canon lo hiciera en "
            "esa magnitud exacta."
        ),
        PageBreak(),
    ]


def parte_mercado():
    return [
        p("2. Como es el mercado que se observa", "h1"),
        p(
            "Antes de modelar conviene mirar los datos. El precio pedido mediano en "
            f"Medellin es de <b>{C.precio_mediano_millones} millones de pesos</b> mensuales "
            f"y la mediana del precio por metro cuadrado es de <b>{C.precio_m2} pesos</b>. "
            "La distribucion esta "
            "fuertemente sesgada a la derecha, que es la forma tipica de un mercado de "
            "vivienda y la razon por la que el modelo trabaja con logaritmos.",
        ),
        figura(
            FIGURAS / "01_distribucion.png",
            "Figura 2. A la izquierda, la distribucion del precio por metro cuadrado, "
            "con su cola larga hacia arriba. A la derecha, el mismo indicador por "
            "estrato: la progresion es monotona y el salto mas grande ocurre entre el "
            "estrato 4 y el 5.",
        ),
        p(
            "El estrato ordena el precio, pero no lo determina. Las cajas se solapan "
            "de forma considerable: hay inmuebles de estrato 4 mas caros por metro que "
            "muchos de estrato 6. Esa superposicion es justamente lo que el modelo "
            "hedonico se encarga de descomponer.",
        ),
        PageBreak(),
    ]


def parte_donde():
    return [
        p("3. Donde esta caro", "h1"),
        p(
            "El precio por metro cuadrado agregado en una rejilla hexagonal de 174 "
            "metros de arista. Se usan hexagonos y no barrios porque los barrios de "
            "Medellin tienen tamanos muy dispares, y comparar medianas entre unidades "
            "desiguales confunde el precio con el tamano de la unidad.",
        ),
        figura(
            FIGURAS / "02_mapa_hexagonos.png",
            "Figura 3. La concentracion oscura del suroriente corresponde a El Poblado "
            "y su entorno. El occidente y el norte aparecen sistematicamente mas "
            "baratos. El gradiente no es suave: hay saltos abruptos entre celdas "
            "contiguas.",
            ancho=11.4 * cm,
        ),
        PageBreak(),
    ]


def parte_atributos():
    return [
        p("4. Que encarece un arriendo", "h1"),
        p(
            "El modelo hedonico descompone el precio en el valor implicito de cada "
            f"atributo. Estimado sobre <b>{C.avisos_modelo} avisos</b> publicados en los "
            f"ultimos noventa dias, explica el <b>{C.r2}</b> de la varianza del precio pedido.",
        ),
        p(
            "La restriccion a noventa dias es deliberada. Los avisos antiguos que "
            "siguen publicados son los que nadie tomo, tipicamente por estar "
            "sobrevalorados, y arrastran el modelo hacia arriba.",
        ),
        figura(
            FIGURAS / "03_efectos_hedonicos.png",
            "Figura 4. Efecto de cada atributo sobre el precio, con todo lo demas "
            "constante. En gris, los efectos que no alcanzan significacion estadistica.",
        ),
        p(
            f"Tres lecturas merecen comentario. <b>Estar amoblado suma {C.amoblado}</b>, con "
            "diferencia el atributo mas valioso: es el precio de la flexibilidad, y "
            "apunta a un segmento de estancia corta. <b>Las alcobas no son "
            "significativas</b> una vez controlada el area, lo cual no es un fallo sino "
            "el resultado esperado: a igualdad de metros, repartirlos en mas "
            "habitaciones no anade valor. Y <b>declarar el piso se asocia a un precio "
            f"{C.piso_declarado_magnitud} menor</b>, mientras que cada piso de altura "
            f"suma {C.piso_altura}: quien "
            "publica el piso tiende a tener algo distinto que quien lo omite.",
        ),
        p(
            "El area entra en logaritmo y su coeficiente es una elasticidad de "
            f"<b>{C.elasticidad}</b>. Se lee asi: un inmueble 10 % mas grande cuesta "
            f"{C.elasticidad_por_diez} mas, no 10 % mas. Que la elasticidad sea menor que "
            "uno significa que el precio por metro cuadrado <b>disminuye</b> con el tamano.",
        ),
        p(
            "El estrato conserva un efecto propio despues de controlar todo lo demas: "
            f"el estrato 5 paga {C.estrato_5} mas que el estrato 1 y el estrato 6 un "
            f"{C.estrato_6} mas.",
        ),
        PageBreak(),
    ]


def parte_ubicacion():
    return [
        p("5. Cuanto vale la ubicacion", "h1"),
        p(
            "Aqui esta el nucleo del analisis. Si dos apartamentos tienen la misma "
            "area, las mismas alcobas, el mismo estrato y las mismas amenidades, pero "
            "uno cuesta un 38 % mas, esa diferencia no la explica el inmueble: la "
            "explica donde esta.",
        ),
        p(
            "Se estima el modelo <b>sin efectos fijos de barrio</b> y se promedian sus "
            "residuales por zona. La razon es tecnica pero decisiva: con el barrio "
            "dentro del modelo, su coeficiente absorbe la media de los residuales de "
            "ese barrio, que pasa a valer cero por construccion y no dice nada.",
        ),
        figura(
            FIGURAS / "04_sobreprecio_barrios.png",
            "Figura 5. Sobreprecio por barrio sobre lo que predicen los atributos del "
            "inmueble. Solo barrios con veinticinco avisos o mas.",
        ),
        p(
            f"La banda va de <b>{C.sobreprecio_caro} en {C.barrio_caro}</b> a "
            f"<b>{C.sobreprecio_barato} en {C.barrio_barato}</b>: <b>{C.banda} puntos "
            "porcentuales</b> que no explican ni el area, ni las alcobas, ni el estrato, "
            "ni las amenidades.",
        ),
        p(
            "Conviene notar que el ordenamiento por sobreprecio no coincide con el "
            "ordenamiento por precio por metro cuadrado. Hay barrios caros en nivel "
            "cuyo sobreprecio es modesto, porque su precio se explica por inmuebles "
            "mejores; y barrios de precio medio con sobreprecio alto, donde se paga "
            "mas de lo que el inmueble justifica.",
        ),
        PageBreak(),
    ]


def parte_espacio():
    return [
        p("6. El precio esta agrupado en el territorio", "h1"),
        p(
            "Un modelo de regresion supone que sus errores son independientes. En "
            "datos geograficos ese supuesto suele fallar, y comprobarlo no es un "
            "tecnicismo: si falla, los errores estandar del modelo son invalidos y "
            "toda la significacion reportada es optimista.",
        ),
        p(
            f"El indice de Moran sobre los residuales da <b>{C.moran} con p = {C.moran_p}</b>, "
            "evaluado por 999 permutaciones. Hay autocorrelacion espacial positiva y es "
            "significativa: <b>el precio de un inmueble depende del de sus vecinos por "
            "encima de lo que explican sus atributos</b>.",
        ),
        p(
            "Las pruebas del multiplicador de Lagrange apuntan a un modelo de error "
            "espacial, y no de rezago. Tiene sentido sustantivo: lo que falta en el "
            "modelo no es el precio del vecino sino atributos del entorno que no se "
            "observan, como seguridad percibida, calidad del comercio cercano o "
            "prestigio del sector, que varian de forma continua en el territorio. El "
            "modelo estimado da un parametro de dependencia de <b>lambda = 0,673</b>: "
            "dos tercios de lo que no se explica en un inmueble tampoco se explica en "
            "sus vecinos.",
        ),
        figura(
            FIGURAS / "05_conglomerados.png",
            "Figura 6. Conglomerados locales de precio. El nucleo azul del suroriente "
            "agrupa avisos caros rodeados de caros; el rojo del norte y el occidente, "
            "baratos rodeados de baratos.",
            ancho=11.4 * cm,
        ),
        p(
            "La figura muestra segregacion espacial nitida: <b>974 avisos</b> en "
            "conglomerados caro-rodeado-de-caro y <b>1.349</b> en el opuesto. No son "
            "puntos caros dispersos, son zonas.",
        ),
        p(
            "Un detalle util para politica publica: los <b>246 avisos baratos rodeados "
            "de caros</b> marcan bordes de transicion, donde la presion de precios de "
            "la zona todavia no se traslado al inmueble. Son los lugares donde cabria "
            "esperar el proximo movimiento.",
        ),
        PageBreak(),
    ]


def parte_tiempo():
    return [
        p("7. Tiempo en mercado", "h1"),
        p(
            "La fecha de publicacion de cada aviso permite medir cuanto lleva "
            "ofrecido. Es un indicador de tension: en un mercado apretado, la oferta "
            "rota rapido.",
        ),
        figura(
            FIGURAS / "06_tiempo_mercado.png",
            "Figura 7. Cada punto es un barrio; el tamano indica cuantos avisos tiene. "
            "No aparece la relacion que uno esperaria entre precio y permanencia.",
        ),
        p(
            "El resultado es que <b>los barrios caros no tardan sistematicamente mas "
            "en alquilarse</b>. Si el precio alto reflejara oferta que no encuentra "
            "demanda, esos barrios acumularian inventario viejo. No ocurre: hay "
            "barrios caros con rotacion rapida y barrios baratos con inventario "
            "estancado. Es consistente con un mercado donde el precio alto responde a "
            "demanda real y no a expectativas del arrendador.",
        ),
        p(
            "La medida tiene un limite que conviene declarar: mide el tiempo que el "
            "aviso lleva <b>publicado</b>, no el que el inmueble tardo en alquilarse. "
            "Un aviso puede seguir activo por inercia despues de arrendado.",
            "nota",
        ),
        PageBreak(),
    ]


def parte_turismo():
    return [
        p("8. La presion de la renta corta", "h1"),
        p(
            f"El atributo mas valioso del modelo es estar amoblado, con un {C.amoblado} de "
            "sobreprecio. Ese coeficiente apunta a un segmento de estancia corta, y "
            "conviene mirarlo de frente porque es el mecanismo mas citado para explicar "
            "el alza en Medellin.",
        ),
        p(
            "La fuente natural para medirlo habria sido InsideAirbnb, pero <b>ya no "
            "publica Medellin</b>: de Colombia solo cubre Bogota. La alternativa es el "
            "<b>Registro Nacional de Turismo</b>, obligatorio para toda vivienda que se "
            "alquile a turistas, publicado en el portal de datos abiertos.",
        ),
        figura(
            FIGURAS / "07_vivienda_turistica.png",
            "Figura 8. Viviendas con registro turistico activo. Son inventarios de cada "
            "anio, no altas nuevas.",
        ),
        p(
            "En 2019 Medellin tenia <b>521</b> viviendas turisticas registradas. En 2024 "
            "tenia <b>8.766</b>: se multiplico por <b>16,8</b> en cinco anos. Desde 2024 "
            "el registro se estabiliza cerca de 8.500. Hoy equivale al <b>0,94 % del "
            "parque de vivienda</b> de la ciudad.",
        ),
        p(
            "Bogota alcanza cifras absolutas parecidas, pero con cerca del triple de "
            "poblacion. Medida contra su propio parque, la densidad de vivienda "
            "turistica de Medellin es sustancialmente mayor.",
        ),

        p("8.1 Y donde se concentra", "h2"),
        p(
            "El registro nacional no publica direcciones ni coordenadas, asi que no se "
            "puede mapear. Para la dimension espacial se recurre a los propios avisos: "
            f"el <b>{C.pct_amoblado}</b> declara estar amoblado, y esos avisos piden "
            f"<b>{C.precio_m2_amoblado} pesos por metro</b> frente a {C.precio_m2_sin_amoblar} "
            "de los demas.",
        ),
        figura(
            FIGURAS / "08_amoblados_sobreprecio.png",
            "Figura 9. Densidad de oferta amoblada frente al sobreprecio del barrio.",
        ),
        p(
            f"La relacion es clara y significativa: <b>rho de Spearman = {C.correlacion_amoblado} "
            f"con p &lt; 0,0001</b> sobre {C.barrios} barrios. Los barrios con mas oferta "
            "amoblada tienen mayor sobreprecio de ubicacion.",
        ),
        bloque(
            "<b>Lo que este resultado si dice, y lo que no.</b> El modelo hedonico ya "
            "controla si <i>cada inmueble</i> esta amoblado. Lo que la correlacion "
            "mide, por tanto, no es que un apartamento amoblado sea mas caro, sino que "
            "<b>estar en un barrio con mucha oferta amoblada encarece tambien a los que "
            "no lo estan</b>. Es un efecto de entorno.<br/><br/>"
            "Dicho eso, es una <b>asociacion, no una causa demostrada</b>. La direccion "
            "podria ser la contraria: los barrios ya caros y bien ubicados atraen "
            "oferta de estancia corta. Separar ambas hipotesis exigiria variacion "
            "temporal por barrio, que este trabajo no tiene."
        ),
        PageBreak(),
    ]


def conclusiones():
    return [
        p("Conclusiones", "h1"),

        p("El alza es real y en Medellin tiene ritmo propio", "h2"),
        p(
            "El arriendo nacional acumulo 10,5 % en dos anos mientras desaceleraba. "
            "Medellin se desacoplo a mediados de 2025 y hoy corre dos puntos por "
            "encima del pais. Cualquier lectura que trate a Medellin como un caso "
            "promedio del mercado colombiano pierde precisamente lo que la distingue.",
        ),

        p("Los atributos explican mucho, pero no la diferencia entre barrios", "h2"),
        p(
            f"El modelo captura el {C.r2} de la varianza con caracteristicas del "
            f"inmueble. Aun asi, a igualdad de inmueble, quedan {C.banda} puntos porcentuales "
            "de diferencia entre el barrio mas caro y el mas barato. La ubicacion no "
            "es un factor mas: es el factor que el mercado cobra por separado.",
        ),

        p("El mercado esta segmentado en el espacio, no disperso", "h2"),
        p(
            "La autocorrelacion espacial es significativa y el parametro del modelo "
            "espacial es alto. Los precios forman zonas, con bordes reconocibles. Esto "
            "tiene una implicacion practica: una intervencion sobre un barrio no actua "
            "sobre un mercado aislado, actua sobre un vecindario que responde en "
            "bloque.",
        ),

        p("La renta corta crecio diecisiete veces y coincide con el sobreprecio", "h2"),
        p(
            "Las viviendas turisticas registradas en Medellin pasaron de 521 en 2019 a "
            "8.766 en 2024, casi el 1 % del parque de vivienda. Y los barrios con mas "
            "oferta amoblada son los que muestran mayor sobreprecio de ubicacion, con "
            f"una correlacion de {C.correlacion_amoblado}. El modelo ya controla si cada "
            "inmueble esta "
            "amoblado, de modo que lo que se observa es un efecto de entorno: la "
            "concentracion de estancia corta encarece tambien a los arriendos "
            "tradicionales de su alrededor. Es asociacion y no causa demostrada, pero "
            "es la pista mas concreta que arrojan los datos.",
        ),

        p("Lo que este informe no puede afirmar", "h1"),
        vineta(
            "Son <b>precios pedidos</b>, no pactados. La brecha entre lo que se pide y "
            "lo que se firma no es observable desde avisos publicos, y suele favorecer "
            "al arrendatario en mercados flojos."
        ),
        vineta(
            "Es <b>un corte transversal</b> enriquecido con una serie oficial, no un "
            "panel propio. No se sigue el mismo inmueble en el tiempo."
        ),
        vineta(
            "Los avisos <b>no son una muestra aleatoria</b> del parque de vivienda: "
            "sobrerrepresentan la oferta formal e intermediada y no capturan el "
            "arriendo informal."
        ),
        vineta(
            "Las relaciones son <b>asociaciones, no efectos causales</b>. El diseno no "
            "identifica causalidad, y las conclusiones no deben leerse en esa clave."
        ),
        vineta(
            "La serie del DANE para Medellin es de la <b>division de alojamiento "
            "completa</b>, que incluye servicios publicos, no de la subclase de "
            "arriendo."
        ),
        Spacer(1, 0.4 * cm),
        p(
            "Declarar estos limites no debilita el trabajo. Un resultado cuyas "
            "fronteras se conocen es utilizable; uno que las esconde, no.",
            "nota",
        ),
    ]


def construir(salida: Path = SALIDA) -> Path:
    salida.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(salida),
        pagesize=A4,
        leftMargin=2.3 * cm,
        rightMargin=2.3 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
        title="Por que subio el precio de los arriendos en Medellin",
        author="Juan Carlos Alvarez Arias",
        subject="Informe de resultados del analisis del mercado de arriendos de Medellin",
    )
    historia = []
    for parte in (portada, resumen, parte_cuanto, parte_mercado, parte_donde,
                  parte_atributos, parte_ubicacion, parte_espacio, parte_tiempo,
                  parte_turismo, conclusiones):
        historia.extend(parte())
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida


if __name__ == "__main__":
    print("escrito en", construir())
