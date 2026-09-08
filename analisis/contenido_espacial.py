"""Contenido del documento: sobreprecio, estadistica espacial, calidad y logros."""

from __future__ import annotations

from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Spacer

from .cifras import cargar as cargar_cifras
from .documento import bloque, formula, p, tabla, vineta

# Cifras del resumen que escribe `analisis.graficos`. Ver analisis/cifras.py.
C = cargar_cifras()


def parte_sobreprecio():
    return [
        p("Parte V. Como se calcula el sobreprecio por barrio", "h1"),
        p(
            "El sobreprecio de un barrio es <b>la parte del precio que los atributos "
            "del inmueble no explican</b>. Si dos apartamentos tienen la misma area, "
            "las mismas alcobas, el mismo estrato y las mismas amenidades, pero uno "
            "cuesta un 38 % mas, esa diferencia es ubicacion.",
        ),

        p("5.1 Definicion formal", "h2"),
        p("Se calcula en tres pasos.", "cuerpo"),
        p(
            "<b>Paso 1.</b> Se estima el modelo hedonico <b>sin efectos fijos de "
            "barrio</b>, dejando solo los atributos del inmueble:",
        ),
        formula(
            "ln(precio_i) = β0 + β1·ln(area_i) + β2·alcobas_i + β3·banos_i<br/>"
            "+ β4·parqueaderos_i + Σ γ_e·estrato_ei + β5·antiguedad_i<br/>"
            "+ β6·piso_conocido_i + β7·piso_valor_i + Σ δ_k·amenidad_ki + ε_i"
        ),
        p("<b>Paso 2.</b> Se calcula el residual de cada aviso:", "cuerpo"),
        formula("e_i = ln(precio_i) − ln(precio estimado_i)"),
        p(
            "Un residual positivo significa que el aviso pide mas de lo que sus "
            "atributos justifican.",
        ),
        p(
            "<b>Paso 3.</b> Se promedian los residuales dentro de cada barrio y se "
            "convierte el resultado a porcentaje:",
        ),
        formula(
            "e̅_b = ( 1 / n_b ) · Σ_(i ∈ b) e_i<br/><br/>"
            "sobreprecio_b = ( e^(e̅_b) − 1 ) · 100"
        ),
        p(
            "La exponencial deshace el logaritmo: una media de residuales de 0,325 "
            "equivale a e^0,325 − 1 = 38,4 % de sobreprecio. Solo se reportan barrios "
            "con al menos 25 avisos, y se acompana el error estandar de la media, "
            "s_b / raiz(n_b), para saber cuanta confianza merece cada cifra.",
        ),

        p("5.2 Por que se quita el barrio del modelo", "h2"),
        bloque(
            "<b>Este es el punto sutil, y una version previa del analisis lo tuvo "
            "mal.</b> Si el barrio esta <i>dentro</i> del modelo como efecto fijo, su "
            "coeficiente absorbe exactamente la media de los residuales de ese "
            "barrio. En consecuencia, la media de los residuales por barrio vale "
            "<b>cero por construccion</b>, no por hallazgo. El mapa resultante seria "
            "un mapa de ceros y no diria absolutamente nada. Por eso el modelo del "
            "que se extraen los residuales excluye deliberadamente el barrio."
        ),
        p(
            "Existe una alternativa equivalente y igual de valida: leer directamente "
            "los coeficientes de barrio del modelo completo. Se prefirio la via del "
            "residual porque no exige elegir un barrio de referencia y porque produce "
            "una medida por aviso, agregable despues a cualquier unidad geografica: "
            "barrio, comuna o hexagono.",
        ),

        p("5.3 Una precision sobre la conversion a porcentaje", "h2"),
        p(
            "La expresion e^(e̅) − 1 estima la razon <b>mediana</b> entre el precio "
            "observado y el estimado, no la media. Es consecuencia de la desigualdad "
            "de Jensen: la exponencial es una funcion convexa, de modo que la "
            "exponencial de una media no coincide con la media de las exponenciales. "
            "Para estimar la media habria que aplicar una correccion de tipo "
            "<i>smearing</i>. Se opto por no aplicarla, porque para comparar barrios "
            "entre si la mediana es una medida mas robusta y la interpretacion "
            "—cuanto mas caro es este barrio de lo que sus atributos justifican— se "
            "mantiene intacta.",
            "nota",
        ),

        p("5.4 Resultados", "h2"),
        tabla(
            C.tabla_sobreprecio(),
            [6.0 * cm, 2.6 * cm, 3.6 * cm, 4.2 * cm],
            alineacion_derecha=[1, 2, 3],
        ),
        Spacer(1, 0.3 * cm),
        p(
            f"La distancia entre los extremos es de <b>{C.banda} puntos porcentuales</b>. Es "
            "diferencia que no explica ni el area, ni las alcobas, ni el estrato, ni "
            "las amenidades: es el precio de la ubicacion en si misma.",
        ),
        PageBreak(),
    ]


def parte_espacial():
    return [
        p("Parte VI. Estadistica espacial", "h1"),
        p(
            "Esta es la parte que decide si el modelo anterior es fiable. Un modelo "
            "de regresion supone que sus errores son independientes entre "
            "observaciones. En datos geograficos ese supuesto suele fallar: lo que "
            "ocurre en un lugar se parece a lo que ocurre al lado. Si los residuales "
            "estan correlacionados en el espacio, el modelo omite algo que se "
            "distribuye geograficamente y <b>sus errores estandar dejan de ser "
            "validos</b>.",
        ),

        p("6.1 La matriz de pesos espaciales", "h2"),
        p(
            "Antes de medir vecindad hay que definirla. Se emplea una matriz W de "
            "los <b>ocho vecinos mas cercanos</b>, estandarizada por filas:",
        ),
        formula(
            "w_ij = 1 si j es uno de los 8 avisos mas cercanos a i; 0 en otro caso<br/>"
            "despues cada fila se normaliza:  Σ_j w_ij = 1"
        ),
        p(
            "Se eligio vecindad por numero de vecinos y no por radio fijo porque la "
            "densidad de avisos varia mucho: un radio de 300 metros dejaria sin "
            "vecinos a los avisos de la periferia y daria cientos a los de El "
            "Poblado. Con ocho vecinos, cada observacion tiene el mismo peso "
            "estructural. La estandarizacion por filas convierte el termino Wx en el "
            "<b>promedio del vecindario</b>, que es lo que se quiere comparar.",
        ),

        p("6.2 El indice I de Moran", "h2"),
        p(
            "Mide si valores parecidos tienden a estar cerca. Se aplica sobre los "
            "residuales del modelo:",
        ),
        formula(
            "I = ( n / S0 ) · [ Σ_i Σ_j w_ij (e_i − e̅)(e_j − e̅) ] / [ Σ_i (e_i − e̅)² ]<br/>"
            "con S0 = Σ_i Σ_j w_ij"
        ),
        p(
            "Se lee como un coeficiente de correlacion entre el valor de cada punto y "
            "el promedio de sus vecinos. Bajo la hipotesis nula de distribucion "
            "aleatoria en el espacio, su valor esperado no es cero exactamente sino:",
        ),
        formula("E[I] = −1 / (n − 1)"),
        p(
            f"que para n = {C.avisos_modelo} vale −0,000137, practicamente cero. La significacion "
            "se evalua por <b>permutaciones</b>: se reordenan al azar los residuales "
            "sobre las mismas posiciones 999 veces, se calcula I en cada reordenacion "
            "y se compara el valor observado con esa distribucion empirica. No se "
            "asume normalidad.",
        ),
        bloque(
            f"<b>Resultado: I = {C.moran} con p = {C.moran_p}.</b> Los residuales del modelo "
            "estan positivamente autocorrelacionados en el espacio, y el resultado es "
            "significativo. Traducido: <b>el precio de un inmueble depende del precio "
            "de sus vecinos, por encima de lo que explican sus propios atributos.</b> "
            "El minimo cuadrado ordinario esta mal especificado.<br/><br/>"
            "Conviene senalar que con una muestra parcial de 773 avisos el indice era "
            "+0,0425. Con la muestra completa se triplica: la evidencia se refuerza al "
            "crecer los datos, que es el comportamiento esperado de un efecto real."
        ),

        p("6.3 Que modelo espacial corresponde", "h2"),
        p(
            "Detectada la dependencia, hay que decidir su forma. Las pruebas del "
            "<b>multiplicador de Lagrange</b> discriminan entre dos alternativas:",
        ),
        vineta(
            "<b>Rezago espacial:</b> el precio del vecino influye directamente en el "
            "precio propio. ln(P) = ρ·W·ln(P) + Xβ + ε"
        ),
        vineta(
            "<b>Error espacial:</b> lo que esta correlacionado no es el precio sino "
            "una variable omitida que se distribuye geograficamente. "
            "ln(P) = Xβ + u, con u = λ·W·u + ε"
        ),
        p(
            "Ambas pruebas resultaron significativas, y el diagnostico apunta al "
            "<b>modelo de error espacial</b>. Tiene sentido sustantivo: lo que falta en "
            "el modelo no es el precio del vecino, sino atributos del entorno que no "
            "se observan —seguridad percibida, calidad del comercio cercano, "
            "accesibilidad, prestigio del sector— y que varian de forma continua en "
            "el territorio.",
        ),

        p("6.4 El modelo de error espacial estimado", "h2"),
        p(
            "Estimado por metodo generalizado de momentos con correccion de "
            "heterocedasticidad. El parametro clave es lambda, que mide cuanto del "
            "error de un inmueble se explica por el error de sus vecinos:",
        ),
        tabla(
            C.tabla_espacial(),
            [5.0 * cm, 3.2 * cm, 2.4 * cm, 5.8 * cm],
            alineacion_derecha=[1, 2],
        ),
        Spacer(1, 0.3 * cm),
        p(
            f"Pseudo R cuadrado = {C.pseudo_r2}. <b>Lambda = {C.lambda_espacial} es alto</b>: dos tercios de "
            "lo que el modelo no explica en un inmueble se explica por lo que tampoco "
            "explica en sus vecinos. Es la confirmacion cuantitativa de que el "
            "mercado de arriendos de Medellin esta fuertemente estructurado en el "
            "espacio.",
        ),
        p(
            f"Comparando con el modelo ordinario, la elasticidad del area pasa de {C.elasticidad} "
            f"a {C.elasticidad_espacial}. La cercania de ambas cifras indica que <b>el problema del OLS no "
            "era el sesgo de los coeficientes sino la validez de su inferencia</b>: los "
            "efectos estimados eran correctos, pero sus errores estandar estaban "
            "subestimados.",
        ),

        p("6.5 Conglomerados locales", "h2"),
        p(
            "El indice de Moran es global: dice que hay estructura espacial, pero no "
            "donde. Los indicadores locales de asociacion espacial descomponen ese "
            "indice observacion por observacion y clasifican cada aviso segun su "
            "valor y el de su vecindario, con significacion tambien por permutaciones "
            "al 5 %:",
        ),
        tabla(
            [
                ["Tipo de conglomerado", "Interpretacion", "Avisos"],
                ["Alto-alto", "Caro rodeado de caros: nucleo de mercado tensionado", "926"],
                ["Bajo-bajo", "Barato rodeado de baratos", "1.498"],
                ["Bajo-alto", "Barato rodeado de caros: posible oportunidad o rezago", "236"],
                ["Alto-bajo", "Caro rodeado de baratos: proyecto aislado", "177"],
                ["No significativo", "Sin patron local detectable", "4.437"],
            ],
            [3.8 * cm, 9.4 * cm, 3.2 * cm],
            alineacion_derecha=[2],
        ),
        Spacer(1, 0.3 * cm),
        p(
            "Los conglomerados alto-alto son la evidencia visual mas directa del "
            "fenomeno: no son puntos caros dispersos, son <b>zonas</b> caras.",
        ),
        PageBreak(),
    ]


def parte_geografia():
    return [
        p("Parte VII. El componente geografico", "h1"),

        p("7.1 De donde sale el barrio", "h2"),
        p(
            "No se geocodifico ninguna direccion. El barrio viaja en la propia "
            "direccion web del aviso, y basta con leerlo. Cada portal lo codifica a "
            "su manera y el bot reconoce los cuatro formatos:",
        ),
        p(
            "fincaraiz.com.co/apartamento-en-arriendo-en-<b>el-poblado</b>-medellin/193855882<br/>"
            "ciencuadras.com/inmueble/apartamento-en-arriendo-en-<b>el-velodromo</b>-medellin-3858855<br/>"
            "coninsa.co/inmuebles/apartamento-en-arriendo/<b>altos-del-poblado</b>/medellin/95303<br/>"
            "arriendo.com/co/apartaestudios/medellin/<b>el-poblado</b>/AR-506175",
            "codigo",
        ),
        p(
            "El metodo es gratuito y tiene cobertura practicamente total, pero exige "
            "cuidado. Dos casos reales lo muestran: la direccion "
            "<font face='Metodo-Mono'>arriendo.com/co/bodegas/cota/autopista-medellin/</font> "
            "corresponde a una via en Cota, Cundinamarca, y no a un barrio; y las "
            "direcciones de Fincaraiz sin barrio, del tipo "
            "<font face='Metodo-Mono'>/apartaestudio-en-arriendo-en-medellin/191669147</font>, "
            "dejan tras el ultimo <i>-en-</i> el resto <i>arriendo-en</i>, que no es un "
            "lugar. Ambos se descartan explicitamente.",
        ),
        bloque(
            "<b>Como se colo un barrio inventado, y como se cerro.</b> Esa segunda "
            "regla existia por duplicado: una version correcta en el extractor del "
            "rastreador y otra mas ingenua en la capa de analisis, que partia la "
            "direccion por <i>-en-</i> y se quedaba con el ultimo trozo. El analisis "
            "usaba la version equivocada, de modo que <b>1.273 avisos repartidos por "
            "toda la ciudad</b> quedaron agrupados bajo un barrio llamado "
            "<i>Arriendo En</i>, que entro en el mapa y en el ranking de sobreprecio "
            "como si fuera un lugar real. La correccion no fue afinar la expresion "
            "regular sino <b>borrar la copia</b>: el analisis ahora llama a la misma "
            "funcion del rastreador, y una prueba comprueba que ambas dan lo mismo. De "
            "esos 1.273 avisos, 1.073 recibieron el barrio de su vecino mas cercano "
            "por el metodo de la seccion siguiente, y 200 se quedaron sin barrio, que "
            "es la respuesta honesta cuando el dato no esta.",
        ),

        p("7.2 Transferencia de barrio por vecino mas cercano", "h2"),
        p(
            "Algunos portales publican coordenadas pero no barrio. Como hay miles de "
            "avisos con ambas cosas, estos sirven de referencia: a un aviso sin "
            "barrio se le asigna el del aviso etiquetado mas cercano, siempre que "
            "este a menos de <b>400 metros</b>. Fuera de ese radio se deja sin barrio, "
            "porque una etiqueta lejana seria una invencion. Doomos paso asi de 4 a "
            "19 barrios identificados de 29 avisos.",
        ),

        p("7.3 La rejilla hexagonal", "h2"),
        p(
            "Los barrios de Medellin tienen tamanos muy dispares, y comparar medianas "
            "entre unidades de tamano desigual mezcla el efecto del precio con el del "
            "tamano de la unidad. Es el <b>problema de la unidad areal modificable</b>: "
            "los resultados cambian segun como se dibujen las fronteras.",
        ),
        p(
            "Para evitarlo se agrega tambien en una rejilla hexagonal en resolucion "
            "9, con celdas de unos 174 metros de arista y area constante. Los 17.306 "
            "avisos con coordenadas caen en <b>1.029 celdas</b>. El hexagono tiene "
            "ademas la propiedad de que sus seis vecinos estan todos a la misma "
            "distancia del centro, cosa que no ocurre con una cuadricula.",
        ),

        p("7.4 Cruce con el censo", "h2"),
        p(
            "Cada aviso se une a la manzana del Marco Geoestadistico Nacional del "
            "DANE en la que cae, mediante una union espacial por cercania con "
            "tolerancia de 30 metros. La tolerancia es necesaria porque las "
            "coordenadas de un aviso apuntan a la fachada o al centroide aproximado "
            "del edificio, y una interseccion estricta perderia buena parte.",
        ),
        p(
            "<b>16.837 avisos, el 97,3 %, quedaron asignados a una manzana censal.</b> "
            "Eso incorpora al analisis viviendas censadas, hogares, personas y el "
            "estrato oficial de la manzana, lo que permite contrastar el estrato que "
            "declara el anunciante con el que registra el censo.",
        ),
        PageBreak(),
    ]


def parte_calidad():
    return [
        p("Parte VIII. Control de calidad", "h1"),
        p(
            "Los datos pasan por tres esquemas en la base: "
            "<font face='Metodo-Mono'>raw</font> guarda la respuesta cruda de cada aviso "
            "sin modificar, lo que permite reprocesar sin volver a descargar; "
            "<font face='Metodo-Mono'>stg</font> contiene el dato tipado y validado; y "
            "<font face='Metodo-Mono'>mart</font>, el modelo dimensional listo para "
            "analizar.",
        ),
        p(
            "Las transformaciones entre esquemas estan escritas como modelos SQL con "
            "pruebas declaradas, que se ejecutan en cada carga. Son 25 comprobaciones "
            "automaticas: unicidad de la clave del hecho, ausencia de nulos en los "
            "campos criticos, valores admitidos para estrato y antiguedad, rangos de "
            "precio y area, coordenadas dentro del valle y ausencia de direcciones "
            "web repetidas tras la deduplicacion.",
        ),
        p(
            "El codigo del bot y del analisis tiene ademas <b>133 pruebas "
            "automatizadas</b>. Varias son pruebas de regresion escritas "
            "especificamente para errores que llegaron a ocurrir: que la agrupacion de "
            "duplicados no encadene un edificio entero, que el agente de usuario no "
            "contenga el nombre de un bot vetado, que no se invente un barrio cuando "
            "la direccion no lo trae y que se corrija la longitud publicada sin "
            "signo.",
        ),
        bloque(
            "<b>Un fallo silencioso que conviene documentar.</b> La sentencia de carga "
            "actualizaba solo siete columnas cuando un aviso ya existia. Eso "
            "significaba que cualquier mejora del extractor —por ejemplo la "
            "correccion del signo de la longitud— nunca llegaba a la base: el registro "
            "ya estaba y conservaba sus valores viejos. No producia ningun error "
            "visible. Ahora se refrescan todas las columnas extraidas."
        ),
        PageBreak(),
    ]


def parte_logros():
    return [
        p("Parte IX. Que se hizo y por que", "h1"),
        p(
            "Resumen del proceso en los terminos de las decisiones que lo "
            "determinaron.",
        ),

        p("1. Se construyo un bot generico en vez de un raspador por sitio", "h2"),
        p(
            "<b>Porque</b> un raspador especifico se rompe con cada cambio de "
            "maquetado y anadir un portal cuesta un dia. <b>Se hizo</b> una cascada de "
            "cinco estrategias genericas donde un portal nuevo es un archivo de "
            "configuracion. <b>Resultado:</b> cuatro portales funcionando, cada uno "
            "resuelto por una capa distinta de la misma cascada. Fincaraiz por estado "
            "embebido, Coninsa por heuristica de HTML, Doomos y Ciencuadras por datos "
            "estructurados. Anadir Coninsa costo un archivo de veinte lineas.",
        ),

        p("2. Se verifico la viabilidad antes de comprometer el diseno", "h2"),
        p(
            "<b>Porque</b> disenar sobre supuestos es como se pierden semanas. <b>Se "
            "hizo</b> un sondeo previo de veintidos dominios, midiendo tasas reales de "
            "llenado sobre una muestra de 45 avisos. <b>Resultado:</b> se supo desde el "
            "principio que la antiguedad no existe como anio sino como banda, y que "
            "el numero de piso solo esta en el 42 % de los avisos, dos hechos que "
            "cambiaron la especificacion del modelo.",
        ),

        p("3. Se descarto la serie temporal propia, con evidencia", "h2"),
        p(
            "<b>Porque</b> cada aviso trae su fecha de publicacion y es tentador "
            "agrupar por ano para reconstruir la historia de precios. <b>Se comprobo</b> "
            "que esa serie muestra una caida inexistente: los avisos de 2022 que "
            "siguen activos piden 69.200 pesos por metro y los de 2026 piden 50.581. "
            "<b>Es sesgo de supervivencia</b>: los avisos viejos que siguen publicados "
            "son justamente los que nadie tomo por estar sobrevalorados. <b>Decision:</b> "
            "la magnitud del alza se toma de fuente oficial, y la fecha de "
            "publicacion se usa solo para medir tiempo en mercado y para restringir "
            "el modelo a los ultimos 90 dias.",
        ),

        p("4. Se separo lo imposible de lo raro", "h2"),
        p(
            "<b>Porque</b> un filtro estadistico de atipicos habria eliminado la cola "
            "de precios altos, que es precisamente lo que el analisis quiere "
            "explicar. <b>Se hizo</b> un conjunto de seis reglas de plausibilidad de "
            "dominio, contrastadas contra la distribucion observada, que marcan sin "
            "borrar. <b>Resultado:</b> 0,7 % marcado, 99,3 % utilizable, y la cola alta "
            "conservada.",
        ),

        p("5. Se corrigio una deduplicacion que fundia edificios", "h2"),
        p(
            "<b>Porque</b> la agrupacion transitiva encadenaba apartamentos distintos "
            "con areas escalonadas: 47 inmuebles de Castropol quedaron como un unico "
            "duplicado. <b>Se cambio</b> a enlace completo, exigiendo coincidencia con "
            "todos los miembros del grupo, mas una regla que pide texto casi identico "
            "cuando los dos avisos son del mismo portal. <b>Resultado:</b> los "
            "duplicados detectados bajaron del 30 % al 9,3 %.",
        ),

        p("6. Se comprobo que el modelo ordinario no bastaba", "h2"),
        p(
            "<b>Porque</b> presentar una regresion sin diagnosticar sus supuestos es "
            "presentar un resultado que no se sabe si es valido. <b>Se calculo</b> el "
            f"indice de Moran sobre los residuales y salio {C.moran} con p = {C.moran_p}. <b>Se "
            f"estimo</b> entonces un modelo de error espacial, con lambda = {C.lambda_espacial}. "
            "<b>Conclusion:</b> los coeficientes del modelo ordinario eran correctos, "
            "pero su inferencia no. Sin este paso, todas las significancias "
            "reportadas habrian sido optimistas.",
        ),

        p("7. Se midio la ubicacion despues de descontar los atributos", "h2"),
        p(
            "<b>Porque</b> comparar el precio por metro cuadrado entre barrios mezcla "
            "el efecto del barrio con el de que sus inmuebles sean distintos. <b>Se "
            "hizo</b> estimando el modelo sin efectos de barrio y agregando sus "
            f"residuales por zona. <b>Resultado:</b> una banda de {C.banda} puntos "
            f"porcentuales, de {C.sobreprecio_caro} en {C.barrio_caro} a "
            f"{C.sobreprecio_barato} en {C.barrio_barato}, atribuible a ubicacion y no a "
            "caracteristicas del inmueble.",
        ),

        p("8. Se dejo el proceso reproducible y observable", "h2"),
        p(
            "<b>Porque</b> un analisis que no se puede volver a correr no es "
            "verificable. <b>Se hizo</b> un almacen en tres capas con la respuesta "
            "cruda conservada, 25 pruebas de calidad de datos que corren en cada "
            "carga, 133 pruebas de codigo y un panel de seguimiento que permite ver "
            "el avance de una corrida sin interrumpirla.",
        ),

        p("Limitaciones que el trabajo declara", "h1"),
        vineta(
            "Son <b>precios pedidos</b>, no pactados. La diferencia entre lo que se "
            "pide y lo que se firma no es observable desde avisos publicos."
        ),
        vineta(
            "Es <b>un corte transversal</b>, no una serie temporal propia, por las "
            "razones expuestas en el punto 3."
        ),
        vineta(
            "Los avisos <b>no son una muestra aleatoria</b> del parque de vivienda: "
            "sobrerrepresentan la oferta formal e intermediada, y no capturan el "
            "arriendo informal ni el de boca en boca."
        ),
        vineta(
            "Las relaciones halladas son <b>asociaciones, no efectos causales</b>. El "
            "diseno no identifica causalidad y las conclusiones no deben leerse asi."
        ),
        vineta(
            "El estrato es el <b>declarado por el anunciante</b>, no el catastral. El "
            "cruce con el censo permite contrastarlo, y se observan discrepancias."
        ),
        Spacer(1, 0.5 * cm),
        p(
            "Declarar estos limites es parte del trabajo, no una concesion: un "
            "resultado cuyas fronteras se conocen vale mas que uno que las esconde.",
            "nota",
        ),
    ]
