-- Prueba singular: ningun aviso debe quedar fuera del rango de cordura.
-- Si esta prueba falla, o los rangos estan mal calibrados o entro basura.
select clave_aviso, precio, area, precio_m2
from {{ ref('hechos_arriendo') }}
where precio not between 200000 and 80000000
   or area not between 10 and 2000
   or precio_m2 not between 3000 and 400000
