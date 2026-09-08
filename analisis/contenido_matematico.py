"""Contenido del documento metodologico: partes matematicas y estadisticas."""

from __future__ import annotations

from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Spacer

from .cifras import cargar as cargar_cifras
from .documento import bloque, formula, p, tabla, vineta

# Cifras del resumen que escribe `analisis.graficos`. Ver analisis/cifras.py.
C = cargar_cifras()


def parte_sospechoso():
    return [
        p("Parte II. Como se decide que un aviso es sospechoso", "h1"),
        p(
            "Esta es la primera pregunta que conviene aclarar, porque la respuesta "
            "honesta no es la que se espera. <b>La marca de sospechoso no es una "
            "prueba estadistica de valores atipicos.</b> Es un conjunto de seis "
            "reglas deterministas de plausibilidad de dominio, que se evaluan sobre "
            "cada aviso en el momento de construirlo y antes de que toque la base de "
            "datos.",
        ),
        p(
            "La diferencia importa. Una prueba estadistica pregunta si un valor es "
            "raro respecto a los demas. Estas reglas preguntan algo mas basico: si el "
            "valor es <b>posible</b>. Un apartamento de cuatrocientos millones al mes "
            "no es raro, es un error de captura o un precio de venta colado en un "
            "aviso de arriendo.",
        ),

        p("2.1 Las seis reglas", "h2"),
        p(
            "Un aviso queda marcado si cumple alguna de estas condiciones. Las marcas "
            "se acumulan: un mismo aviso puede llevar varias.",
        ),
        tabla(
            [
                ["Marca", "Condicion", "Avisos", "%"],
                ["precio_muy_bajo", "precio &lt; 200.000 COP", "3", "0,02"],
                ["precio_muy_alto", "precio &gt; 80.000.000 COP", "12", "0,07"],
                ["area_fuera_de_rango",
                 "area &lt; 10 m2 o area &gt; 2.000 m2", "59", "0,34"],
                ["precio_por_m2_atipico",
                 "precio/area &lt; 3.000 o &gt; 400.000 COP/m2", "56", "0,32"],
                ["latitud_fuera_del_valle", "latitud fuera de [5,95 ; 6,45]", "20", "0,12"],
                ["longitud_fuera_del_valle", "longitud fuera de [−75,75 ; −75,35]", "34", "0,20"],
                ["fechas_invertidas",
                 "fecha de actualizacion anterior a la de publicacion", "0", "0,00"],
            ],
            [4.6 * cm, 7.4 * cm, 2.2 * cm, 2.2 * cm],
            alineacion_derecha=[2, 3],
        ),
        Spacer(1, 0.3 * cm),
        p(
            "En total <b>128 avisos quedaron marcados, el 0,7 %</b>. Los 17.178 "
            "restantes, el 99,3 %, entran limpios al analisis. Un aviso marcado no se "
            "borra: se conserva con su marca, de modo que la decision de excluirlo "
            "queda documentada y es reversible.",
        ),

        p("2.2 De donde salen los umbrales", "h2"),
        p(
            "Un umbral sin justificacion es una cifra inventada. Estos se fijaron por "
            "conocimiento del mercado y despues se contrastaron contra la "
            "distribucion observada de los 17.306 avisos con datos completos. La "
            "prueba de que estan bien puestos es que <b>caen muy por fuera del "
            "recorrido real de los datos</b>, y por tanto no recortan observaciones "
            "legitimas.",
        ),
        tabla(
            [
                ["Variable", "Umbral inferior", "p1 %", "Mediana", "p99 %", "Umbral superior"],
                ["Precio mensual", "200.000", "1.200.000", "4.900.000", "26.000.000", "80.000.000"],
                ["Area (m2)", "10", "25", "98", "700", "2.000"],
                ["Precio por m2", "3.000", "15.356", "48.684", "119.033", "400.000"],
            ],
            [3.4 * cm, 2.9 * cm, 2.5 * cm, 2.4 * cm, 2.6 * cm, 2.6 * cm],
            alineacion_derecha=[1, 2, 3, 4, 5],
        ),
        Spacer(1, 0.3 * cm),
        p(
            "El umbral superior de precio, 80 millones, esta tres veces por encima "
            "del percentil 99. El de area, 2.000 metros, casi tres veces por encima. "
            "Son diques, no filtros finos: solo detienen lo imposible.",
        ),
        p(
            "Los limites geograficos son el rectangulo que encierra el Valle de "
            "Aburra. No son estadisticos sino cartograficos, y sirven para detectar "
            "errores de geocodificacion en origen.",
        ),

        p("2.3 Que haria un criterio estadistico, y por que no se usa como filtro", "h2"),
        p(
            "Para dimensionar lo anterior conviene compararlo con dos criterios "
            "estadisticos clasicos, calculados sobre la misma muestra.",
        ),
        p("<b>Puntuacion z robusta</b> sobre el logaritmo del precio por metro cuadrado:", "cuerpo"),
        formula(
            "z_i = 0,6745 · ( ln(p_i) − mediana(ln p) ) / MAD<br/>"
            "MAD = mediana( | ln(p_i) − mediana(ln p) | )"
        ),
        p(
            "Se usa el logaritmo porque el precio por metro cuadrado tiene una "
            "distribucion muy asimetrica a la derecha, y su logaritmo es casi "
            "simetrico. Se usan la mediana y la MAD en lugar de la media y la "
            "desviacion tipica porque estas ultimas son ellas mismas sensibles a los "
            "valores extremos que se pretende detectar. La constante 0,6745 hace que "
            "la MAD sea comparable con una desviacion tipica bajo normalidad.",
        ),
        p(
            "Con los datos reales: mediana del logaritmo = 10,7931 y MAD = 0,2298. "
            "Aplicando el criterio habitual |z| &gt; 3,5 se marcarian <b>214 avisos, "
            "el 1,24 %</b>, lo que equivale a considerar sospechoso todo precio por "
            "metro cuadrado fuera del rango de 14.773 a 160.438 pesos.",
        ),
        p("<b>Vallas de Tukey</b>, el criterio del diagrama de caja:", "cuerpo"),
        formula("[ Q1 − 1,5·RIC ,  Q3 + 1,5·RIC ]  =  [ 4.169 ,  94.123 ]  COP/m2"),
        bloque(
            "<b>Por que las reglas de dominio y no estas.</b> El criterio estadistico "
            "marcaria como sospechoso un apartamento a 160.000 pesos el metro "
            "cuadrado. En El Poblado eso no es un error: es un apartamento caro y "
            "real. Un filtro estadistico aplicado a ciegas <b>eliminaria justamente la "
            "cola de precios altos que el analisis quiere explicar</b>, y sesgaria a la "
            "baja todo el modelo. Las reglas de dominio detienen lo imposible; la "
            "cola alta legitima se conserva y se estudia."
        ),
        p(
            "Esto no significa que el criterio estadistico sobre: se calcula y se "
            "reporta como diagnostico, y es el que se usaria si el objetivo fuera "
            "detectar anomalias en lugar de explicar el precio.",
            "nota",
        ),
        PageBreak(),
    ]


def parte_duplicados():
    return [
        p("Parte III. Como se detecta que dos avisos son el mismo inmueble", "h1"),
        p(
            "El mismo apartamento anunciado en tres portales entraria tres veces al "
            "modelo y pesaria el triple. La deduplicacion se hace en dos fases, que "
            "es la forma estandar de abordar el problema: una fase barata que descarta "
            "la inmensa mayoria de comparaciones, y una fase fina dentro de cada grupo "
            "reducido.",
        ),

        p("3.1 Bloqueo", "h2"),
        p(
            f"Comparar todos los pares de {C.avisos} avisos serian mas de 150 millones de "
            "comparaciones. El bloqueo lo evita agrupando primero por una clave "
            "barata, y comparando solo dentro de cada bloque:",
        ),
        formula("clave = redondear(latitud, 3) : redondear(longitud, 3) | numero de alcobas"),
        p(
            "Tres decimales de grado equivalen a unos 110 metros, aproximadamente una "
            "manzana. Dos avisos del mismo inmueble tienen que caer en la misma celda "
            "y tener el mismo numero de alcobas. Los avisos sin coordenadas no se "
            "pueden bloquear con seguridad y quedan como grupo propio.",
        ),

        p("3.2 Funcion de puntaje", "h2"),
        p("Dentro del bloque, cada par recibe un puntaje aditivo:", "cuerpo"),
        tabla(
            [
                ["Criterio", "Condicion", "Peso"],
                ["Area", "|a − b| / max(a, b) ≤ 0,05", "0,35"],
                ["Precio", "|a − b| / max(a, b) ≤ 0,03", "0,30"],
                ["Alcobas", "iguales", "0,10"],
                ["Banos", "iguales", "0,05"],
                ["Estrato", "iguales", "0,05"],
                ["Texto", "similitud ≥ 0,55, ponderado por la similitud", "0,20 · s"],
                ["Direccion", "similitud ≥ 0,85", "0,15"],
            ],
            [3.0 * cm, 9.4 * cm, 2.4 * cm],
            alineacion_derecha=[2],
        ),
        Spacer(1, 0.3 * cm),
        p(
            "Se declaran el mismo inmueble si el puntaje alcanza <b>0,60</b>. Hay "
            "ademas una regla de corte previa: si ambos avisos declaran area y "
            "difieren en mas del 5 %, se rechaza el par de inmediato, sin evaluar el "
            "resto. El area es el atributo mas estable de un inmueble entre portales.",
        ),
        p(
            "La similitud textual usa <font face='Metodo-Mono'>token_set_ratio</font>, una "
            "variante de la distancia de Levenshtein que compara conjuntos de "
            "palabras y por tanto tolera el reordenamiento y los anadidos que cada "
            "portal hace a la descripcion. Para busquedas masivas sin coordenadas se "
            "dispone ademas de un indice MinHash sobre n-gramas de cuatro caracteres, "
            "que estima el indice de Jaccard entre descripciones:",
        ),
        formula("J(A, B) = |A ∩ B| / |A ∪ B|"),

        p("3.3 Enlace completo, no transitivo", "h2"),
        p(
            "Este punto merece detalle porque el primer diseno estaba equivocado y el "
            "error es facil de cometer.",
        ),
        bloque(
            "<b>El fallo.</b> La primera version agrupaba con una estructura de "
            "conjuntos disjuntos, que es <b>transitiva</b>: si A coincide con B y B con "
            "C, los tres se funden aunque A y C no se parezcan. En un edificio de "
            "Castropol con 47 apartamentos de areas escalonadas (110, 115, 120, 124, "
            "127...), cada par consecutivo caia dentro de la tolerancia del 5 % y la "
            "cadena termino fundiendo el edificio entero en un unico duplicado. Los "
            "precios iban de 5,5 a 12,1 millones: eran claramente inmuebles distintos."
        ),
        p(
            "La correccion fue pasar a <b>enlace completo</b>: un aviso entra a un "
            "grupo solo si coincide con <b>todos</b> sus miembros, no con uno "
            "cualquiera. Eso rompe la cadena. Se anadio ademas una regla de "
            "procedencia: dos avisos <b>del mismo portal</b> exigen una similitud "
            "textual de al menos 0,95 para considerarse duplicados, porque dos "
            "unidades del mismo edificio publicadas por la misma agencia casi siempre "
            "son inmuebles distintos, mientras que el duplicado real que interesa es "
            "el que ocurre <b>entre</b> portales.",
        ),
        p(
            "Efecto de la correccion sobre la muestra: los duplicados detectados "
            "pasaron del 30 % al 9,3 %. En el conjunto final se identificaron 1.216 "
            "duplicados. El representante de cada grupo es el aviso con mas campos "
            "poblados, de modo que se conserva la version mas completa.",
        ),
        PageBreak(),
    ]


def parte_hedonico():
    return [
        p("Parte IV. El modelo hedonico de precios", "h1"),
        p(
            "Un modelo hedonico descompone el precio de un bien heterogeneo en el "
            "valor implicito de sus atributos. Aplicado a vivienda, permite responder "
            "cuanto vale un bano adicional o un parqueadero, y —lo que aqui "
            "interesa— <b>cuanto del precio no explican los atributos y por tanto es "
            "atribuible a la ubicacion</b>.",
        ),

        p("4.1 Especificacion", "h2"),
        formula(
            "ln(precio_i) = β0 + β1·ln(area_i) + β2·alcobas_i + β3·banos_i<br/>"
            "+ β4·parqueaderos_i + β5·antiguedad_i + β6·piso_conocido_i<br/>"
            "+ β7·piso_valor_i + Σ γ_e·estrato_ei + Σ δ_k·amenidad_ki<br/>"
            "+ Σ θ_b·barrio_bi + ε_i"
        ),
        p(
            f"Estimado por minimos cuadrados ordinarios sobre <b>{C.avisos_modelo} avisos</b> "
            "publicados en los ultimos 90 dias, con los barrios que tienen muestra "
            f"suficiente. Ajuste: <b>R cuadrado ajustado = {C.r2}</b>.",
        ),

        p("4.2 Por que el logaritmo", "h2"),
        p("La transformacion logaritmica de la variable dependiente no es decorativa:", "cuerpo"),
        vineta(
            "<b>Los precios son asimetricos a la derecha.</b> Su logaritmo es "
            "aproximadamente simetrico, que es lo que la regresion supone."
        ),
        vineta(
            "<b>Los efectos son multiplicativos, no aditivos.</b> Un parqueadero no "
            "suma una cifra fija de pesos: suma un porcentaje. El modelo en "
            "logaritmos captura eso de forma natural."
        ),
        vineta(
            "<b>Estabiliza la varianza.</b> La dispersion del precio crece con su "
            "nivel; la del logaritmo, mucho menos."
        ),
        p(
            "El area entra tambien en logaritmo, lo que convierte esa relacion en "
            "log-log y hace que su coeficiente sea directamente una <b>elasticidad</b>.",
        ),

        p("4.3 Como se lee cada coeficiente", "h2"),
        p(
            "Esta distincion es la fuente de error de interpretacion mas comun en "
            "este tipo de modelos, y conviene explicitarla porque en una version "
            "previa de este analisis se cometio.",
        ),
        tabla(
            [
                ["Tipo de regresor", "Lectura del coeficiente", "Formula"],
                ["En logaritmo (log-log)",
                 "Elasticidad: variacion porcentual del precio ante una variacion del "
                 "1 % en el regresor", "β directamente"],
                ["En nivel (semi-logaritmico)",
                 "Variacion porcentual del precio ante un aumento de una unidad",
                 "(e^β − 1) · 100"],
            ],
            [4.0 * cm, 8.4 * cm, 4.0 * cm],
        ),
        Spacer(1, 0.3 * cm),
        bloque(
            f"<b>El error a evitar.</b> El coeficiente del area es {C.elasticidad}. Aplicarle la "
            "transformacion (e^β − 1)·100 daria un 68 % y se leeria como <i>un metro "
            "cuadrado mas encarece el inmueble un 68 %</i>, que es absurdo. La lectura "
            f"correcta es la elasticidad: <b>un inmueble 10 % mas grande cuesta "
            f"{C.elasticidad_por_diez} mas</b>. Que la elasticidad sea menor que uno "
            "significa que el precio por "
            "metro cuadrado <b>disminuye</b> con el tamano, un resultado bien "
            "establecido en la literatura de vivienda."
        ),

        p("4.4 Errores estandar robustos", "h2"),
        p(
            "Se emplean errores estandar HC3, robustos a heterocedasticidad. La "
            "razon es concreta: la dispersion de los precios no es constante entre "
            "estratos, es mucho mayor en los altos. Con errores clasicos, los "
            "intervalos de confianza serian demasiado estrechos y se declararian "
            "significativos efectos que no lo son. HC3 es la variante recomendada "
            "para muestras finitas por penalizar mas las observaciones influyentes.",
        ),

        p("4.5 El problema del piso faltante", "h2"),
        p(
            "El numero de piso solo aparece en el 41,9 % de los avisos. Descartar el "
            "resto costaria mas de la mitad de la muestra; imputar un valor "
            "inventaria informacion. La solucion estandar es descomponerlo en dos "
            "variables:",
        ),
        formula(
            "piso_conocido = 1 si el aviso declara piso, 0 si no<br/>"
            "piso_valor = numero de piso si se declara, 0 si no"
        ),
        p(
            "Asi el coeficiente de <font face='Metodo-Mono'>piso_valor</font> mide el "
            "efecto de subir un piso <b>entre los avisos que lo declaran</b>, mientras "
            "que <font face='Metodo-Mono'>piso_conocido</font> absorbe cualquier "
            "diferencia sistematica entre quienes lo publican y quienes no. Los datos "
            "muestran que si la hay: declarar el piso se asocia a un precio 6,2 % "
            "menor.",
        ),

        p("4.6 Resultados", "h2"),
        tabla(
            C.tabla_efectos(),
            [5.2 * cm, 3.4 * cm, 3.0 * cm, 2.6 * cm],
            alineacion_derecha=[2, 3],
        ),
        Spacer(1, 0.3 * cm),
        p(
            "Que las alcobas no sean significativas una vez controlada el area no es "
            "un fallo: es el resultado esperado. El area ya recoge el tamano, y a "
            "igualdad de metros, repartirlos en mas alcobas no anade valor.",
        ),
        p(
            "Efecto del estrato, tomando el estrato 1 como referencia: estrato 5 un "
            f"{C.estrato_5} mas caro y estrato 6 un {C.estrato_6} mas, ambos "
            "significativos al 1 %.",
        ),
        PageBreak(),
    ]
