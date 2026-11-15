-- Core fact table: prices plus the derived numbers analysts need.
with p as (
    select
        *,
        lag(close_price) over (partition by symbol order by trade_date)                                   as prev_close,
        avg(volume)      over (partition by symbol order by trade_date
                               rows between 19 preceding and current row) as avg_volume_20d,
        avg(close_price) over (partition by symbol order by trade_date
                               rows between 19 preceding and current row) as sma_20
    from {{ ref('stg_prices') }}
)
select
    symbol,
    trade_date,
    open_price, high_price, low_price, close_price, volume,
    prev_close,
    round(100 * (close_price / nullif(prev_close, 0) - 1), 2)     as pct_change,
    round(100 * (open_price  / nullif(prev_close, 0) - 1), 2)     as gap_pct,
    round(close_price * volume)                                   as value_traded,
    round(avg_volume_20d)                                         as avg_volume_20d,
    round(sma_20, 2)                                              as sma_20,
    -- PSX daily limit is about 10%; flag days that hit it
    case when close_price / nullif(prev_close, 0) - 1 <= -0.095 then true else false end as is_limit_down,
    case when close_price / nullif(prev_close, 0) - 1 >=  0.095 then true else false end as is_limit_up
from p
