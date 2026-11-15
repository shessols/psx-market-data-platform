-- Clean daily prices: one row per stock per day, bad rows removed.
select
    upper(trim(symbol))      as symbol,
    cast(date as date)       as trade_date,
    cast(open   as double)   as open_price,
    cast(high   as double)   as high_price,
    cast(low    as double)   as low_price,
    cast(close  as double)   as close_price,
    cast(volume as bigint)   as volume
from {{ source('raw', 'daily_prices') }}
where close > 0
  and high >= low
qualify row_number() over (partition by upper(trim(symbol)), cast(date as date) order by volume desc) = 1
