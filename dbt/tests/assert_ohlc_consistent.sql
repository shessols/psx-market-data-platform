-- High must be the top of the day and low the bottom.
select * from {{ ref('stg_prices') }}
where high_price < greatest(open_price, close_price) - 0.01
   or low_price  > least(open_price, close_price) + 0.01
