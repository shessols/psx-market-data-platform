select
    upper(trim(symbol))             as symbol,
    name                            as company_name,
    coalesce(sector, 'Unknown')     as sector
from {{ source('raw', 'stocks') }}
qualify row_number() over (partition by upper(trim(symbol)) order by name) = 1
