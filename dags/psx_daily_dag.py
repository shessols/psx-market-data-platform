"""Airflow DAG: the whole daily pipeline, after PSX closes.

extract (Python) -> [upload to S3] -> load Snowflake -> dbt build (models + tests)
    -> backtest, today's picks, daily movers post

Runs Mon-Fri at 18:00 Karachi time (PSX closes by 16:30 at the latest).
Set PSX_PIPELINE_HOME to the folder that holds this project.
"""
from __future__ import annotations

import os
from pathlib import Path

import pendulum
import yaml
from airflow import DAG
from airflow.operators.bash import BashOperator

HOME = os.environ.get("PSX_PIPELINE_HOME", "/opt/airflow/psx-pipeline")
MODE = yaml.safe_load(Path(HOME, "config.yaml").read_text())["storage"]["mode"]


def step(task_id: str, cmd: str) -> BashOperator:
    return BashOperator(task_id=task_id, bash_command=f"cd {HOME} && {cmd}")


with DAG(
    dag_id="psx_daily_pipeline",
    schedule="0 18 * * 1-5",
    start_date=pendulum.datetime(2026, 11, 16, tz="Asia/Karachi"),
    catchup=False,
    default_args={"retries": 2, "retry_delay": pendulum.duration(minutes=10)},
    tags=["psx", "stocks", "dbt"],
    doc_md=__doc__,
) as dag:
    extract = step("extract_psx_prices", "python ingest/extract_psx.py --days 7")
    load = step("load_snowflake", "python ingest/load_snowflake.py")
    dbt_build = step("dbt_build", "cd dbt && dbt build --target snowflake")
    backtest = step("run_backtest", "python backtest/backtest.py")
    picks = step("todays_picks", "python backtest/backtest.py --picks-only")
    post = step("daily_movers_post", "python publish/daily_movers.py")

    if MODE == "s3":
        upload = step("upload_s3", "python ingest/upload_s3.py")
        extract >> upload >> load
    else:
        extract >> load

    load >> dbt_build >> [backtest, picks, post]
