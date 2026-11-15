-- Quick SQL view of the idea: average forward return per side, overall and by year.
-- (The full money simulation with fees and tax lives in backtest/backtest.py.)
select
    side,
    extract(year from signal_date)          as signal_year,
    count(*)                                as signals,
    round(avg(fwd_ret_1d), 2)               as avg_ret_1d,
    round(avg(fwd_ret_5d), 2)               as avg_ret_5d,
    round(avg(fwd_ret_21d), 2)              as avg_ret_21d,
    round(100.0 * avg(case when fwd_ret_5d > 0 then 1 else 0 end), 1) as pct_up_after_5d
from {{ ref('mart_mover_forward_returns') }}
group by 1, 2
