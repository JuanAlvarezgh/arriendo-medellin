-- La deduplicacion debe dejar una sola fila canonica por URL.
select url, count(*) as veces
from {{ ref('hechos_arriendo') }}
group by url
having count(*) > 1
