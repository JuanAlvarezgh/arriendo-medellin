# Arriendos en Medellín

Análisis del mercado de arriendo residencial de Medellín a partir de avisos
recogidos de portales inmobiliarios, con un bot de extracción multi portal, un
modelo hedónico de precios y diagnóstico espacial.

La pregunta que responde es por qué subió el arriendo y, sobre todo, dónde. La
magnitud del alza en el tiempo viene del índice de precios del DANE; lo que
aporta este trabajo es la explicación geográfica: qué atributos encarecen un
inmueble y cuánto cuesta la ubicación por sí sola, una vez descontados esos
atributos.

## Qué se encontró

Sobre 17.345 avisos recogidos de cuatro portales, 99,3% utilizables:

- El modelo hedónico explica el **86,0% de la varianza** del precio pedido,
  sobre 7.274 avisos de los últimos 90 días. La elasticidad del área es
  **0,521**: un inmueble 10% más grande cuesta 5,2% más, no 10% más.
- Estar amoblado suma **31,6%**. Cada baño suma 7,3% y cada parqueadero 6,3%.
  Cada salto de banda de antigüedad resta 1,9%. El estrato 6 paga 46,9% más
  que el estrato 1.
- Los residuales del modelo están **espacialmente autocorrelacionados**
  (I de Moran = **+0,1128**, p = 0,001). El mínimo cuadrado ordinario está mal
  especificado. El modelo de error espacial estimado da **lambda = 0,673**: dos
  tercios de lo que no se explica en un inmueble tampoco se explica en sus
  vecinos.
- Descontando atributos, la ubicación mueve el precio en una banda de **56
  puntos porcentuales**: de **+38,4% en La Aguacatala** a **−18,0% en el
  Centro**.
- **El 29,0% del parque de vivienda no tiene un solo aviso publicado**: 527 de
  las 1.521 celdas de la ciudad, con 255.413 hogares censados. Medido contra el
  censo, el estrato 6 aparece trece veces más representado que el estrato 1.
  Todo lo anterior describe el mercado formal e intermediado, no su totalidad.
- Los conglomerados locales identifican 926 avisos en zonas caras rodeadas de
  caras y 1.498 en zonas baratas rodeadas de baratas.
- El **40% de los avisos declara un estrato distinto** al que el censo del DANE
  registra para su manzana.

### La renta corta

InsideAirbnb dejó de cubrir Medellín: de Colombia solo publica Bogotá. La
alternativa es el Registro Nacional de Turismo, obligatorio para toda vivienda
que se alquile a turistas.

Las viviendas turísticas registradas en Medellín pasaron de **521 en 2019 a
8.766 en 2024**: se multiplicaron por **16,8** en cinco años, y hoy equivalen al
**0,94% del parque de vivienda** de la ciudad. Bogotá alcanza cifras absolutas
parecidas con cerca del triple de población.

El registro no publica direcciones, así que la dimensión espacial sale de los
propios avisos: el 13,0% declara estar amoblado, y esos piden $71.052 por m²
frente a $46.666 de los demás. La densidad de oferta amoblada por barrio
correlaciona con el sobreprecio de ubicación: **rho de Spearman = +0,670,
p < 0,0001** sobre 51 barrios.

Como el modelo ya controla si cada inmueble está amoblado, lo que se mide es un
**efecto de entorno**: estar en un barrio con mucha oferta amoblada encarece
también a los arriendos que no lo están. Es asociación, no causa demostrada.

### El sesgo que invalidaba la serie temporal

Cada aviso trae su fecha de publicación, y es tentador agrupar por año para
reconstruir la historia de precios. No funciona, y conviene dejarlo escrito:

| Año de publicación | Mediana pedida |
|---|---|
| 2022 | $69.200 /m² |
| 2023 | $70.000 /m² |
| 2024 | $43.500 /m² |
| 2026 | $50.581 /m² |

La serie sugiere una caída que no ocurrió. Los avisos antiguos que siguen
activos son precisamente los que nadie tomó, típicamente por estar
sobrevalorados. Es sesgo de supervivencia, y por eso el modelo se estima sobre
una ventana de 90 días y la dimensión temporal se toma de fuente oficial.

### La dimensión temporal: qué dice el DANE

El raspado da el corte transversal; la magnitud del alza viene del índice de
precios oficial. Se descargaron los anexos mensuales del DANE de agosto de 2024
a julio de 2026, que es el periodo publicado en ese formato, y se extrajo la
subclase `04130100 Arriendo efectivo` más la división de alojamiento por ciudad.

El arriendo efectivo nacional acumuló **+10,5% en 24 meses**, y su variación
anual viene **desacelerando**: de 8,05% a 4,89%.

Medellín hace lo contrario. Su división de alojamiento tocó fondo en **4,45% en
julio de 2025** y desde entonces subió hasta **7,42% en julio de 2026**: casi
tres puntos de reaceleración. La brecha con el promedio nacional pasó de
**−0,09 a +2,02 puntos porcentuales**.

Ese es el anclaje que le faltaba al análisis transversal: **Medellín se desacopló
de la tendencia del país a mediados de 2025**, y el mapa de sobreprecio por
barrio muestra dónde se concentra ese desacople.

Advertencia necesaria: la subclase de arriendo puro solo se publica a nivel
nacional. Para Medellín, lo más fino disponible es la división completa, que
incluye agua, electricidad y gas. No es lo mismo, y no se presenta como si lo
fuera.

## El bot

No hay un raspador por sitio. Hay una **cascada de estrategias genéricas**, y
cada portal nuevo se resuelve con un archivo YAML de perfil.

| Capa | Técnica | Resuelve |
|---|---|---|
| api | API interna descubierta interceptando tráfico de red | aplicaciones de una sola página |
| a | ld+json, microdata, RDFa, OpenGraph | portales con marcado para buscadores |
| b | `__NEXT_DATA__`, `__NUXT__`, `__APOLLO_STATE__` | portales con estado embebido |
| d | heurística sobre el HTML: etiqueta a valor, patrones de precio y área | HTML servido sin datos estructurados |
| e | modelo de lenguaje sobre texto limpio, validado contra el esquema | lo que sobrevivió a todo lo anterior |

Se detiene en la primera capa que produzca precio y área. Las posteriores solo
rellenan huecos.

En Fincaraíz, la búsqueda automática del objeto del aviso encuentra los dieciséis
campos **sin configuración específica del sitio**: puntúa cada diccionario del
árbol JSON por cuántos conceptos del esquema reconoce y se queda con el mejor.

### El descubrimiento es la parte difícil

Distinguir una página de aviso de una de categoría no es trivial. Se decide con
dos señales independientes: la forma de la URL (profundidad, identificador
numérico, similitud con las ya confirmadas) y el contenido (un aviso tiene un
precio dominante, un listado tiene veinte). El clasificador se autocalibra por
dominio.

Un caso real que justifica el diseño: el filtro `-medellin/` capturaba las
páginas del directorio de una inmobiliaria llamada *Arrendamientos Medellín*.
El clasificador las rechazó por contenido antes de que ensuciaran los datos.

### Conducta

Cumple `robots.txt`, entra por los sitemaps que el sitio declara, limita el
ritmo por dominio, reintenta con espera creciente y corta el circuito si un
dominio empieza a fallar. Cachea en disco y es reanudable: si se interrumpe en
el aviso 9.000 de 17.258, retoma ahí. Sin sesión iniciada, sin resolver
CAPTCHA, sin rotar identidad.

No almacena nombre, teléfono ni datos de contacto del anunciante.

## Arquitectura

```
sitemaps declarados
        |
        v
  descubrimiento -> descarga -> cascada de extraccion -> normalizacion
        |                                                      |
        |                                                      v
        |                                          deduplicacion entre portales
        v                                                      |
  datos/crudo/*.jsonl  <-- registro a prueba de caidas         v
                                                    PostgreSQL 16
                                                    raw -> stg -> mart (dbt)
                                                               |
                                    geopandas + H3 + manzanas del DANE
                                                               |
                                    hedonico -> I de Moran -> modelo espacial
                                                               |
                                          mapas, tablero, informe
```

**Por qué JSONL y no CSV durante la corrida.** Las descripciones de los avisos
traen comas, comillas y saltos de línea; varios trabajadores concurrentes
corrompen un CSV; y un proceso que muere a mitad de escritura deja un CSV
inservible, mientras que en JSONL basta descartar la última línea. El CSV se
genera al final, con `exportar`, ya deduplicado y validado.

## Datos

Cobertura medida sobre la muestra recogida:

| Campo | Cobertura |
|---|---|
| precio, estrato, alcobas, baños, dirección, coordenadas, fechas | 100% |
| área privada | 84% |
| parqueaderos | 80% |
| antigüedad (banda ordinal, no año) | ~100% |
| número de piso | 45% |
| administración | 2% |

Dos consecuencias de diseño: el piso entra al modelo como indicador de
disponibilidad más su valor, nunca como regresor obligatorio; y la
administración se descarta.

El barrio sale del slug de la URL, sin geocodificar. La manzana del Marco
Geoestadístico del DANE aporta el contexto censal, y el 99,4% de los avisos cae
dentro de una. La rejilla H3 en resolución 9 da celdas de igual tamaño, que
evitan el problema de la unidad areal modificable de los barrios.

## Entregables

| Documento | Qué contiene |
|---|---|
| `informe_arriendos_medellin.pdf` | Informe de resultados, 12 páginas con 9 figuras |
| `metodologia_arriendos_medellin.pdf` | Metodología: la matemática de cada regla y estadístico, y la arquitectura del bot |
| `arriendos_medellin.csv` | Los 17.345 avisos, 31 columnas |
| `ipc_arriendo_dane.csv` | Serie mensual del IPC de arriendos, 24 meses |
| `sobreprecio_por_barrio.csv` | Residual del modelo por barrio |
| `amoblado_vs_sobreprecio.csv` | Densidad de oferta amoblada y sobreprecio por barrio |
| `rnt_viviendas_turisticas.csv` | Viviendas turísticas registradas, por año y ciudad |
| `figuras/` | Las nueve figuras en PNG |
| `resumen_modelo.json` | Las cifras del estudio, calculadas: de aquí las leen los documentos |
| `web/arriendos_medellin.html` | La página del análisis, un solo archivo |

### El orden importa

Cada paso escribe lo que consume el siguiente, y las cifras de los documentos
salen de `resumen_modelo.json`, que produce el paso de las figuras. Ejecutados
al revés, los PDF salen igual pero con los números de la corrida anterior:

```
python -m rastreador.cli exportar --formato parquet
python -m analisis.geo
python -m analisis.graficos
python -m analisis.rejilla
python -m analisis.mapas
python -m analisis.pagina
python -m analisis.informe
python -m analisis.generar_documento
```

## Cómo verlo

Lo principal es una página de un solo archivo, que se abre con doble clic:
`datos/salidas/web/arriendos_medellin.html`. Lleva el mapa por celdas
hexagonales sobre el callejero real, con cinco capas —precio, cobertura,
sobreprecio, conglomerados y viviendas censadas— y el resto del análisis debajo.
Lo único que necesita conexión son las teselas del mapa base; sin ellas los
hexágonos siguen dibujando la ciudad.

Y un tablero de ocho pestañas para explorar los datos crudos: resumen, el alza
del IPC, dónde está caro, qué lo encarece, la ubicación, conglomerados
espaciales, renta corta y un explorador de avisos con filtros.

```
streamlit run analisis/tablero.py
```

Y un panel aparte para seguir al bot mientras raspa, que se refresca solo cada
tres segundos. Responde de un vistazo la única pregunta que importa mientras una
corrida avanza —si sigue recogiendo o se quedó quieta— con un punto de estado,
una banda de velocidad de los últimos minutos y el conteo real de líneas del
archivo, que es más fiable que el contador del proceso:

```
streamlit run analisis/monitor.py --server.port 8600
```

Puede vigilar otra carpeta de datos, por ejemplo la de otra copia del proyecto,
apuntando `ARRIENDOS_DATOS` a ella.

Los dos paneles comparten el lenguaje visual de la página del informe. La paleta
y las tipografías van en `.streamlit/config.toml`, que es lo que Streamlit sabe
tematizar solo; el cristal esmerilado, las manchas del fondo y los componentes
propios van en `analisis/estilo.py`.

Los mapas también quedan como HTML autocontenidos en `datos/salidas/`:
coropleta por hexágono, sobreprecio por barrio y conglomerados.

Conjunto de datos exportado:

```
python -m rastreador.cli exportar --formato csv
```

## Cómo correrlo

Requiere Python 3.11 y PostgreSQL 16 en local.

```
python -m rastreador.cli portales
python -m rastreador.cli raspar --portal fincaraiz
python -m rastreador.cli cargar
```

Durante la corrida, `python -m rastreador.cli estado` informa desde otra
terminal si el bot sigue vivo, sin tocar el proceso.

Las transformaciones y sus pruebas de calidad:

```
cd transformaciones && dbt run && dbt test
```

## Estado

115 pruebas de Python y 22 pruebas de datos en dbt.

## Límites

Son **precios pedidos**, no pactados: la brecha entre lo que se pide y lo que se
firma no es observable desde avisos públicos. Es **un corte transversal**, no
una serie temporal propia. Los avisos **no son una muestra aleatoria** del
parque de vivienda, sobrerrepresentan la oferta formal e intermediada. Y las
relaciones halladas son **asociaciones, no efectos causales**.
