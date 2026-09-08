{{ config(materialized='table') }}

-- Tabla de hechos del analisis: un aviso canonico por fila, con sus
-- atributos y las claves hacia las dimensiones.

with limpio as (
    select * from {{ ref('stg_avisos_limpios') }}
    where es_canonico
)

select
    portal || ':' || id_fuente                as clave_aviso,
    portal,
    id_fuente,
    url,
    barrio,
    comuna,
    tipo_inmueble,
    estrato,
    banda_antiguedad,
    antiguedad_ordinal,

    precio,
    precio_m2,
    ln(precio)                                as log_precio,
    area,
    ln(area)                                  as log_area,
    alcobas,
    banos,
    parqueaderos,
    piso,
    piso_conocido,
    n_amenidades,
    amenidades,

    latitud,
    longitud,

    creado_en,
    actualizado_en,
    capturado_en,
    dias_en_mercado,
    date_trunc('month', creado_en)::date      as mes_publicacion,

    -- El inventario antiguo que sigue activo es el que nadie tomo, y suele
    -- estar sobrevalorado. Marcarlo permite excluirlo del modelo.
    (dias_en_mercado <= 90)                   as reciente,
    capa,
    sin_marcas
from limpio
