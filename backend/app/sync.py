import logging  # standard library logging, used for all status/error output
import sys  # used to direct log output to stdout (so `docker logs` captures it)

import pandas as pd  # streams query results from the source DB in chunks and writes them to the cache DB
from apscheduler.schedulers.blocking import BlockingScheduler  # runs this process forever, firing jobs on a schedule
from apscheduler.triggers.cron import CronTrigger  # cron-style trigger built from schedule_cron in config.yaml
from sqlalchemy import create_engine, text  # sync engine + raw SQL wrapper, used for both source and cache DB access

from app.config import app_config, settings  # parsed config.yaml dict, and the Settings instance with connection URLs

logging.basicConfig(                                  # configure the root logger once, at import time
    level=app_config.get("log_level", "INFO"),         # verbosity comes from config.yaml, defaults to INFO if missing
    format="%(asctime)s [%(levelname)s] %(message)s",  # timestamp + level + message in every log line
    stream=sys.stdout,                                  # write logs to stdout so docker captures them
)
log = logging.getLogger("sync")  # named logger for this module, so log lines are easy to filter

# Plain (sync) engines — simpler than async for a batch job using pandas
source_engine = create_engine(settings.source_db_url)    # connection to the real source database (read-only usage)
cache_engine = create_engine(settings.cache_db_url_sync)  # connection to the Postgres cache database (read/write usage)


def sync_table(source_query: str, target_table: str, batch_size: int) -> None:
    """Load one table into staging, then atomically swap it into place.

    The live table stays queryable by the API for the entire load — it's
    only swapped once the new data is fully written, and only dropped after
    the swap succeeds. If this raises partway through, the previous live
    table is untouched.
    """
    staging_table = f"{target_table}_staging"  # temporary table the new data is loaded into first
    log.info("Extracting '%s' -> staging table '%s'", source_query, staging_table)  # log what's about to happen

    with cache_engine.begin() as conn:                                # open a transaction against the cache DB
        conn.execute(text(f"DROP TABLE IF EXISTS {staging_table}"))   # clear any leftover staging table from a failed prior run

    total_rows = 0  # running count of rows processed, used only for the log line at the end
    for i, chunk in enumerate(pd.read_sql(source_query, source_engine, chunksize=batch_size)):  # stream the source query in batches, not all at once
        chunk.to_sql(                                   # write this batch of rows into the cache DB
            staging_table,                                # target table name (the staging one, not the live one)
            cache_engine,
            if_exists="append" if i > 0 else "replace",   # first chunk creates the table fresh, later chunks append
            index=False,                                   # don't write pandas's row index as a column
        )
        total_rows += len(chunk)  # add this batch's row count to the running total

    with cache_engine.begin() as conn:  # open a second transaction to perform the atomic swap
        conn.execute(text(f"DROP TABLE IF EXISTS {target_table}_old"))  # clear any leftover "_old" table from a prior run
        conn.execute(text(f"ALTER TABLE IF EXISTS {target_table} RENAME TO {target_table}_old"))  # move current live table aside (no-op if it doesn't exist yet)
        conn.execute(text(f"ALTER TABLE {staging_table} RENAME TO {target_table}"))  # promote the freshly loaded staging table to live
        conn.execute(text(f"DROP TABLE IF EXISTS {target_table}_old"))  # drop the old table now that the swap succeeded

    log.info("Synced %s rows into '%s'", total_rows, target_table)  # final confirmation log with the row count


def update_sync_metadata() -> None:
    with cache_engine.begin() as conn:  # open a transaction against the cache DB
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    id INT PRIMARY KEY DEFAULT 1,
                    last_synced_at TIMESTAMP
                )
                """
            )
        )  # ensure the metadata table exists (only matters on the very first run)
        conn.execute(
            text(
                """
                INSERT INTO sync_metadata (id, last_synced_at) VALUES (1, NOW())
                ON CONFLICT (id) DO UPDATE SET last_synced_at = NOW()
                """
            )
        )  # insert the single metadata row on first run, or refresh its timestamp on every later run


def run_sync() -> None:
    log.info("Sync run started")  # marks the start of a sync run in the logs
    sync_cfg = app_config.get("sync", {})           # pull the "sync" section out of config.yaml
    batch_size = sync_cfg.get("batch_size", 5000)   # rows to pull per chunk, default 5000 if not set

    any_success = False  # tracks whether at least one table synced, so metadata only updates if something happened
    for table_cfg in sync_cfg.get("tables", []):    # loop over every table listed in config.yaml
        try:
            sync_table(
                source_query=f"SELECT * FROM {table_cfg['source']}",  # simple SELECT * against the configured source table
                target_table=table_cfg["target"],                      # table name to create in the cache DB
                batch_size=batch_size,
            )
            any_success = True  # mark success so update_sync_metadata() runs below
        except Exception:
            # Keep going with the next table — a failure on one table
            # shouldn't block the rest, and the API keeps serving the
            # previous good data for the one that failed.
            log.exception("Failed to sync '%s' — previous cached data kept", table_cfg["source"])  # log the full traceback, don't crash the run

    if any_success:                # only stamp a new sync time if at least one table actually updated
        update_sync_metadata()
    log.info("Sync run finished")  # marks the end of a sync run in the logs


if __name__ == "__main__":  # only runs when executed directly (`python -m app.sync`), not when imported
    cron_expr = app_config.get("sync", {}).get("schedule_cron", "0 2 * * *")  # read the cron expression from config.yaml
    minute, hour, day, month, day_of_week = cron_expr.split()  # split the 5-field cron string into its components

    scheduler = BlockingScheduler()  # scheduler that runs in the foreground and blocks the process
    scheduler.add_job(
        run_sync,                                       # function to call on schedule
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week),  # fire per the parsed cron fields
    )
    log.info("Scheduler started — cron='%s'", cron_expr)  # confirm the scheduler is set up with the right schedule

    # Run once on startup so the cache isn't empty while waiting for the first scheduled run
    run_sync()  # immediately perform one sync when the container starts, instead of waiting until 2 AM

    scheduler.start()  # hand control to the scheduler — blocks forever, keeping the container alive
