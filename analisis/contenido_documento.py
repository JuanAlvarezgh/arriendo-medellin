"""Contenido del documento metodologico: partes I a IV."""

from __future__ import annotations

from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Spacer

from .cifras import cargar as cargar_cifras
from .documento import bloque, formula, p, tabla, vineta

# Cifras del resumen que escribe `analisis.graficos`. Ver analisis/cifras.py.
C = cargar_cifras()

A = 16.4 * cm  # ancho util


def portada():
    return [
        Spacer(1, 3.4 * cm),
        p("Por que subio el precio de los arriendos en Medellin", "titulo"),
        p(
            "Documento metodologico: como se recogieron los datos, que se calcula "
            "en cada paso y por que. Incluye la arquitectura del bot de extraccion "
            "y la justificacion de cada regla y cada estadistico empleado.",
            "subtitulo",
        ),
        tabla(
            [
                ["Avisos recogidos", C.avisos],
                ["Portales", "4 (Fincaraiz, Coninsa, Doomos, Ciencuadras)"],
                ["Cobertura", "Municipio de Medellin"],
                ["Muestra del modelo", f"{C.avisos_modelo} avisos de los ultimos 90 dias"],
                ["Ajuste del modelo", f"R cuadrado ajustado = {C.r2}"],
                ["Autocorrelacion espacial", f"I de Moran = {C.moran} (p = {C.moran_p})"],
            ],
            [5.2 * cm, 11.2 * cm],
            cabecera=False,
        ),
        Spacer(1, 0.9 * cm),
        p(
            "Todo numero que aparece en este documento proviene de la ejecucion real "
            "del proyecto, no de un ejemplo. Las cifras se pueden reproducir con los "
            "comandos que se indican en cada seccion.",
            "nota",
        ),
        PageBreak(),
    ]


def parte_bot():
    return [
        p("Parte I. El bot de extraccion", "h1"),
        p(
            "La primera decision del proyecto fue no escribir un raspador por sitio. "
            "Un raspador especifico se rompe cada vez que el portal cambia su "
            "maquetado, y anadir un portal nuevo cuesta un dia de trabajo. En su "
            "lugar se construyo una <b>cascada de estrategias genericas</b>: cinco "
            "tecnicas ordenadas de mas barata a mas cara, que se prueban en orden "
            "hasta que una devuelve un aviso valido. Anadir un portal cuesta un "
            "archivo de configuracion, no codigo.",
        ),

        p("1.1 Donde esta y como esta organizado", "h2"),
        p(
            "El proyecto vive en <font face='Metodo-Mono'>Desktop\\Proyectos\\arriendos-medellin</font>. "
            "El paquete <font face='Metodo-Mono'>rastreador</font> contiene el bot; "
            "<font face='Metodo-Mono'>analisis</font>, la parte estadistica; "
            "<font face='Metodo-Mono'>transformaciones</font>, el proyecto de calidad de datos.",
        ),
        p(
            "rastreador/<br/>"
            "&nbsp;&nbsp;descubrimiento/&nbsp;&nbsp;robots.py &nbsp;sitemaps.py &nbsp;clasificador_url.py<br/>"
            "&nbsp;&nbsp;descarga/&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;cliente.py &nbsp;limite.py &nbsp;cache.py &nbsp;navegador.py<br/>"
            "&nbsp;&nbsp;extraccion/&nbsp;&nbsp;&nbsp;&nbsp;estructurados.py &nbsp;estado_js.py &nbsp;api_interna.py<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;heuristica.py &nbsp;modelo.py &nbsp;cascada.py<br/>"
            "&nbsp;&nbsp;normalizacion/&nbsp;esquema.py &nbsp;moneda.py &nbsp;area.py<br/>"
            "&nbsp;&nbsp;deduplicacion/&nbsp;similitud.py<br/>"
            "&nbsp;&nbsp;persistencia/&nbsp;&nbsp;almacen.py<br/>"
            "&nbsp;&nbsp;perfiles/&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;fincaraiz.yaml &nbsp;coninsa.yaml &nbsp;doomos.yaml ...",
            "codigo",
        ),

        p("1.2 Las tres categorias de portal", "h2"),
        p(
            "Antes de disenar la cascada se examinaron los portales uno a uno. "
            "Resulta que en la practica solo existen tres formas de servir un aviso, "
            "y esa taxonomia es la que estructura todo el bot:",
        ),
        tabla(
            [
                ["Categoria", "Que trae el HTML servido", "Ejemplo"],
                ["A. Estado embebido",
                 "El objeto completo del aviso viaja en un bloque JSON dentro de la pagina "
                 "(__NEXT_DATA__, __NUXT__, __APOLLO_STATE__)", "Fincaraiz"],
                ["B. HTML de servidor",
                 "Los datos estan visibles en el HTML, pero sin marcado estructurado: hay "
                 "que leerlos del maquetado", "Coninsa"],
                ["C. Aplicacion de una sola pagina",
                 "El HTML no trae ni precios ni areas; todo lo pinta JavaScript en el "
                 "navegador", "Ciencuadras"],
            ],
            [3.6 * cm, 8.6 * cm, 4.2 * cm],
        ),
        Spacer(1, 0.35 * cm),
        p(
            "En arriendo.com la comprobacion fue elocuente: las unicas apariciones de "
            "la expresion metros cuadrados en su HTML eran coordenadas de iconos "
            "vectoriales, no datos. El texto visible de la pagina decia unicamente "
            "Cargando.",
            "nota",
        ),

        p("1.3 La cascada de extraccion", "h2"),
        p(
            "Cada capa es generica: ninguna sabe nada de un portal concreto. Se "
            "detienen en la primera que entregue precio y alguna medida de area; las "
            "posteriores solo rellenan huecos y nunca sobreescriben lo ya obtenido.",
        ),
        tabla(
            [
                ["Capa", "Tecnica", "Resuelve", "Avisos", "%"],
                ["api", "Endpoint JSON interno, descubierto observando el trafico de red",
                 "Categoria C con API accesible", "0", "0,00"],
                ["a", "Datos estructurados: ld+json, microdata, RDFa, OpenGraph",
                 "Portales con marcado para buscadores", "571", "3,29"],
                ["b", "Estado embebido por el framework de la pagina",
                 "Categoria A", "16.725", "96,43"],
                ["d", "Heuristica sobre el HTML: proximidad etiqueta-valor y patrones",
                 "Categoria B", "49", "0,28"],
                ["e", "Modelo de lenguaje sobre el texto limpio, con salida validada",
                 "Lo que sobrevivio a todo lo anterior", "0", "0,00"],
            ],
            [1.5 * cm, 6.0 * cm, 4.9 * cm, 2.2 * cm, 1.4 * cm],
            alineacion_derecha=[3, 4],
        ),
        Spacer(1, 0.35 * cm),
        p(
            "Las capas api y e no llegaron a activarse porque las anteriores "
            "resolvieron el 100 % de los avisos. Esa es exactamente su funcion: "
            "existir como red de seguridad y costar cero cuando no hacen falta. La "
            "capa e, que consulta un modelo de lenguaje, es la unica con costo "
            "monetario, y se invoca solo tras el fallo de las cuatro anteriores.",
        ),

        p("1.4 Como encuentra los avisos sin buscar en Google", "h2"),
        p(
            "El bot no consulta buscadores. Para cada dominio lee su archivo "
            "<font face='Metodo-Mono'>robots.txt</font>, sigue los sitemaps que el propio "
            "sitio declara y descubre las direcciones de aviso que contienen. Es la "
            "via autorizada por el sitio y evita paginar a ciegas.",
        ),
        p(
            "El problema dificil no es descargar, sino <b>distinguir una pagina de "
            "aviso de una pagina de categoria</b>. Una sonda ingenua confunde ambas y "
            "extrae basura. Se resuelve puntuando dos senales independientes.",
        ),
        p("<b>Senal de forma.</b> Depende solo de la direccion:", "cuerpo"),
        formula(
            "S_forma = 2,0·[ruta de detalle] − 2,5·[ruta de listado]<br/>"
            "+ 2,0·[termina en identificador de 5 o mas digitos]<br/>"
            "+ 0,5·[profundidad ≥ 2] − 1,0·[profundidad ≤ 1] − 0,5·[tiene parametros]"
        ),
        p("<b>Senal de contenido.</b> Depende de la pagina descargada:", "cuerpo"),
        formula(
            "S_contenido = +2,0 si hay entre 1 y 3 precios;  −2,0 si hay mas de 8<br/>"
            "+1,0 si hay entre 1 y 4 areas;  −1,5 si hay mas de 12<br/>"
            "+2,5 si declara RealEstateListing;  −1,0 si declara ItemList"
        ),
        p(
            "La intuicion es simple y robusta: <b>una pagina de aviso tiene un precio "
            "dominante; una de resultados tiene veinte.</b> Se clasifica como aviso "
            "cuando la suma supera 0,5, y la confianza se reporta como "
            "min(|S| / 5, 1).",
        ),
        p(
            "Ademas el clasificador se autocalibra. Reduce cada direccion a su forma "
            "—por ejemplo <font face='Metodo-Mono'>/texto/numero</font>— y tras veinte "
            "avisos confirmados en un dominio predice por mayoria de esa forma, sin "
            "volver a puntuar.",
        ),
        bloque(
            "<b>Un caso real que justifica el diseno.</b> El filtro inicial aceptaba "
            "cualquier direccion que contuviera <font face='Metodo-Mono'>-medellin/</font>. "
            "Eso capturaba las paginas del directorio de una agencia llamada "
            "Arrendamientos Medellin, que son categorias de venta y no avisos. La senal "
            "de contenido las rechazo antes de que contaminaran los datos."
        ),

        p("1.5 Conducta frente a los portales", "h2"),
        p(
            "El bot respeta <font face='Metodo-Mono'>robots.txt</font>, entra por los "
            "sitemaps declarados, limita el ritmo por dominio entre 0,3 y 1,8 "
            "peticiones por segundo segun el sitio, reintenta con espera creciente y "
            "abre un cortacircuitos tras diez fallos seguidos. Cachea en disco y es "
            "reanudable. No usa sesion iniciada, no resuelve CAPTCHA y no rota "
            "identidad. Tampoco almacena nombre, telefono ni datos de contacto del "
            "anunciante: son datos personales que no aportan al analisis.",
        ),
        bloque(
            "<b>El error mas instructivo del proyecto.</b> El agente se identificaba "
            "como <i>rastreador-academico (proyecto universitario; respeta robots.txt)</i>. "
            "Fincaraiz bloqueaba todas las peticiones. La causa: su lista de bots "
            "vetados incluye uno llamado <b>OBot</b>, y la comparacion es por "
            "subcadena. La secuencia <i>obot</i> aparece dentro de la palabra "
            "<i>robots</i>. El bot se prohibia a si mismo por prometer que respetaba "
            "robots.txt. Sin detectarlo, el proyecto habria recogido cero avisos."
        ),

        p("1.6 Que se obtiene de cada aviso", "h2"),
        tabla(
            [
                ["Campo", "Cobertura", "Observacion"],
                ["Precio, area privada, descripcion", "100,0 %", "Nucleo del analisis"],
                ["Banos", "99,9 %", ""],
                ["Direccion, coordenadas", "99,8 %", "Permiten el cruce espacial"],
                ["Fecha de publicacion", "99,5 %", "Da el tiempo en mercado"],
                ["Alcobas", "99,1 %", ""],
                ["Estrato", "98,8 %", "Declarado por el anunciante"],
                ["Banda de antiguedad", "81,5 %", "Cinco niveles, no anio exacto"],
                ["Parqueaderos", "79,3 %", ""],
                ["Area construida", "76,9 %", "Respaldo del area privada"],
                ["Numero de piso", "41,9 %", "Obliga a un tratamiento especial"],
            ],
            [6.4 * cm, 2.6 * cm, 7.4 * cm],
            alineacion_derecha=[1],
        ),
        Spacer(1, 0.35 * cm),
        p(
            "Dos hallazgos condicionaron el diseno. <b>La antiguedad no existe como "
            "anio</b>: los portales la publican en bandas (menor a 1 ano, 1 a 8, 9 a "
            "15, 16 a 30, mas de 30), de modo que entra al modelo como variable "
            "ordinal. Y <b>el numero de piso solo aparece en el 41,9 % de los "
            "avisos</b>, lo que impide usarlo como regresor obligatorio sin perder "
            "mas de la mitad de la muestra.",
        ),
        p(
            "Las amenidades no se raspan: se extraen del texto de la descripcion con "
            "expresiones regulares, lo que anade catorce variables sin coste "
            "adicional de descarga. Las mas frecuentes son balcon (45,8 %), porteria "
            "(43,7 %), zonas verdes (37,5 %) y piscina (35,0 %).",
        ),
        PageBreak(),
    ]
