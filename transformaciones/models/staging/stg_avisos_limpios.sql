{{ config(materialized='view') }}

-- Capa de limpieza: tipa, acota y descarta lo que no puede entrar al analisis.
-- Las reglas de rango replican las del esquema Pydantic del bot, de modo que
-- un registro que se cuele por otra via reciba el mismo trato.

with base as (

    select
        portal,
        id_fuente,
        url,
        tipo_inmueble,
        operacion,
        precio,
        moneda,
        administracion,
        coalesce(area_privada, area_construida)          as area,
        area_privada,
        area_construida,
        alcobas,
        banos,
        parqueaderos,
        estrato,
        banda_antiguedad,
        piso,
        direccion,
        latitud,
        longitud,
        barrio,
        comuna,
        creado_en,
        actualizado_en,
        capturado_en,
        titulo,
        descripcion,
        amenidades,
        capa,
        sospechoso,
        id_grupo,
        es_canonico
    from {{ source('stg', 'avisos') }}
    where precio is not null
      and operacion = 'arriendo'
      -- Solo vivienda. Algunos portales mezclan bodegas, oficinas y locales en
      -- los mismos listados de arriendo, y sus precios por metro cuadrado no
      -- son comparables con los residenciales.
      and tipo_inmueble in ('apartamento', 'apartaestudio', 'casa', 'habitacion')

),

calculado as (

    select
        *,
        precio / nullif(area, 0)                                   as precio_m2,
        (capturado_en::date - creado_en)                           as dias_en_mercado,
        cardinality(coalesce(amenidades, '{}'))                    as n_amenidades,
        case
            when banda_antiguedad = 'menor_a_1'  then 0
            when banda_antiguedad = '1_a_8'      then 1
            when banda_antiguedad = '9_a_15'     then 2
            when banda_antiguedad = '16_a_30'    then 3
            when banda_antiguedad = 'mayor_a_30' then 4
        end                                                        as antiguedad_ordinal,
        (piso is not null)                                         as piso_conocido,
        cardinality(coalesce(sospechoso, '{}')) = 0                as sin_marcas
    from base

)

select *
from calculado
where area between 10 and 2000
  and precio between 200000 and 80000000
  and precio_m2 between 3000 and 400000
  -- Las coordenadas son opcionales. Hay portales que publican el barrio pero
  -- no la posicion; esos avisos sirven igual para el modelo con efectos fijos
  -- de barrio, y solo quedan fuera del analisis espacial. Exigirlas aqui
  -- descartaba portales enteros que eran perfectamente validos.
  and (latitud is null or latitud between 5.95 and 6.45)
  and (longitud is null or longitud between -75.75 and -75.35)
