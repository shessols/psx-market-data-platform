-- Each day's biggest losers and gainers among liquid stocks.
-- Feeds the daily post, the Power BI "Movers" page and the strategy.
with eligible as (
    select f.*, d.company_name, d.sector
    from {{ ref('fct_daily_prices') }} f
    join {{ ref('dim_stock') }} d using (symbol)
    where f.pct_change is not null
      and f.close_price >= {{ var('min_price') }}
      and f.volume      >= {{ var('min_volume') }}
)
select
    trade_date, symbol, company_name, sector,
    close_price, pct_change, volume, value_traded, is_limit_down, is_limit_up,
    rank() over (partition by trade_date order by pct_change asc)  as loser_rank,
    rank() over (partition by trade_date order by pct_change desc) as gainer_rank
from eligible
