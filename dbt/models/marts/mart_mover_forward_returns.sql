-- Research table: after a stock is the day's #1 LOSER or #1 GAINER, what happens next?
-- Returns measured from the NEXT day's open (when you could actually buy).
-- side = 'loser' / 'gainer': analyse separately, or together by ignoring side.
with prices as (
    select
        symbol, trade_date,
        lead(open_price, 1)   over (partition by symbol order by trade_date) as entry_open,
        lead(trade_date, 1)   over (partition by symbol order by trade_date) as entry_date,
        lead(close_price, 1)  over (partition by symbol order by trade_date) as close_d1,
        lead(close_price, 5)  over (partition by symbol order by trade_date) as close_d5,
        lead(close_price, 10) over (partition by symbol order by trade_date) as close_d10,
        lead(close_price, 21) over (partition by symbol order by trade_date) as close_d21
    from {{ ref('fct_daily_prices') }}
),
signals as (
    select 'loser'  as side, * from {{ ref('mart_daily_movers') }} where loser_rank  = 1
    union all
    select 'gainer' as side, * from {{ ref('mart_daily_movers') }} where gainer_rank = 1
)
select
    s.side,
    s.trade_date as signal_date,
    s.symbol, s.sector, s.pct_change as signal_pct, s.is_limit_down, s.is_limit_up,
    p.entry_date, p.entry_open,
    round(100 * (p.close_d1  / nullif(p.entry_open, 0) - 1), 2) as fwd_ret_1d,
    round(100 * (p.close_d5  / nullif(p.entry_open, 0) - 1), 2) as fwd_ret_5d,
    round(100 * (p.close_d10 / nullif(p.entry_open, 0) - 1), 2) as fwd_ret_10d,
    round(100 * (p.close_d21 / nullif(p.entry_open, 0) - 1), 2) as fwd_ret_21d
from signals s
join prices p on p.symbol = s.symbol and p.trade_date = s.trade_date
