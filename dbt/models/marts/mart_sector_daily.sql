select
    f.trade_date,
    d.sector,
    count(*)                                         as stocks,
    sum(case when f.pct_change > 0 then 1 else 0 end) as advancers,
    sum(case when f.pct_change < 0 then 1 else 0 end) as decliners,
    round(avg(f.pct_change), 2)                      as avg_pct_change,
    sum(f.value_traded)                              as value_traded
from {{ ref('fct_daily_prices') }} f
join {{ ref('dim_stock') }} d using (symbol)
where f.pct_change is not null
group by 1, 2
