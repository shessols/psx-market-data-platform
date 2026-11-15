{# On the local DuckDB target, build the RAW layer from CSVs so the same
   models run with no cloud account. Does nothing on Snowflake. #}
{% macro load_local_raw() %}
  {% if target.type == 'duckdb' %}
    create schema if not exists raw;
    create or replace table raw.daily_prices as
      select * from read_csv_auto('{{ var("prices_csv") }}');
    create or replace table raw.stocks as
      select * from read_csv_auto('{{ var("stocks_csv") }}');
  {% endif %}
{% endmacro %}
