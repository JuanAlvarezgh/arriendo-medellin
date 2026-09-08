-- Un aviso de Medellin fuera del bounding box del Valle de Aburra indica
-- error de geocodificacion en origen.
select clave_aviso, latitud, longitud
from {{ ref('hechos_arriendo') }}
where latitud not between 5.95 and 6.45
   or longitud not between -75.75 and -75.35
