with activity as (
    select symbol,
           min(trade_date) as first_trade_date,
           max(trade_date) as last_trade_date,
           count(*)        as trading_days
    from {{ ref('stg_prices') }}
    group by symbol
)
select
    a.symbol,
    coalesce(s.company_name, a.symbol)  as company_name,
    coalesce(s.sector, 'Unknown')       as sector,
    a.first_trade_date,
    a.last_trade_date,
    a.trading_days,
    a.last_trade_date = (select max(trade_date) from {{ ref('stg_prices') }}) as is_active
from activity a
left join {{ ref('stg_stocks') }} s using (symbol)
