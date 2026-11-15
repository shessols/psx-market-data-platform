select
    trade_date,
    count(*)                                          as stocks_traded,
    sum(case when pct_change > 0 then 1 else 0 end)   as advancers,
    sum(case when pct_change < 0 then 1 else 0 end)   as decliners,
    sum(case when pct_change = 0 then 1 else 0 end)   as unchanged,
    sum(case when is_limit_down then 1 else 0 end)    as limit_down,
    sum(case when is_limit_up then 1 else 0 end)      as limit_up,
    round(avg(pct_change), 2)                         as avg_pct_change,
    sum(value_traded)                                 as value_traded
from {{ ref('fct_daily_prices') }}
where pct_change is not null
group by 1
