{{ config(materialized='table') }}

-- Dimension de barrio con sus indicadores de mercado.

with avisos as (
    select * from {{ ref('stg_avisos_limpios') }}
    where barrio is not null and es_canonico
)

select
    barrio,
    count(*)                                            as avisos,
    percentile_cont(0.5) within group (order by precio)     as precio_mediano,
    percentile_cont(0.5) within group (order by precio_m2)  as precio_m2_mediano,
    percentile_cont(0.25) within group (order by precio_m2) as precio_m2_q1,
    percentile_cont(0.75) within group (order by precio_m2) as precio_m2_q3,
    percentile_cont(0.5) within group (order by area)       as area_mediana,
    round(avg(alcobas)::numeric, 2)                     as alcobas_medias,
    mode() within group (order by estrato)               as estrato_moda,
    percentile_cont(0.5) within group (order by dias_en_mercado) as dias_en_mercado_mediano,
    round(avg(n_amenidades)::numeric, 2)                as amenidades_medias,
    avg(latitud)                                        as latitud_media,
    avg(longitud)                                       as longitud_media
from avisos
group by barrio
having count(*) >= 5
