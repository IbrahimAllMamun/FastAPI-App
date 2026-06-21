import os  # reads environment variables and checks file existence

import yaml  # parses the YAML config file into a Python dict
from pydantic_settings import BaseSettings  # base class that auto-loads env vars / .env into typed fields

# Path to the non-secret config file; can be overridden via the CONFIG_PATH env var,
# otherwise defaults to a local "config/config.yaml" relative to the working directory
CONFIG_PATH = os.getenv("CONFIG_PATH", "config/config.yaml")


def load_yaml_config() -> dict:
    """Non-secret settings: sync schedule, table list, API options, etc."""
    if os.path.exists(CONFIG_PATH):         # only attempt to read the file if it actually exists
        with open(CONFIG_PATH) as f:        # open the YAML file for reading
            return yaml.safe_load(f) or {}  # parse into a dict; fall back to {} if the file is empty
    return {}                               # no config file found — empty dict lets callers safely use .get()


class Settings(BaseSettings):
    # Cache DB (Postgres) — used by both the api and sync services
    cache_db_host: str = "postgres"          # hostname of the cache DB container; matches the compose service name
    cache_db_port: int = 5432                # Postgres's default port
    cache_db_name: str = "app_cache"         # database name inside the cache DB
    cache_db_user: str = "app_user"          # username for the cache DB
    cache_db_password: str = ""              # password for the cache DB; blank by default, set via env/.env

    # Source DB — used only by the sync job
    source_db_host: str = ""                 # hostname/IP of the real source database server
    source_db_port: int = 1433               # SQL Server's default port
    source_db_name: str = ""                 # name of the source database
    source_db_user: str = ""                 # username with read access to the source database
    source_db_password: str = ""             # password for that user

    class Config:
        env_file = ".env"                    # also read values from a local .env file, not just real env vars

    @property
    def cache_db_url(self) -> str:
        """Async URL — used by the FastAPI app."""
        # SQLAlchemy connection URL using the asyncpg driver, required for async database sessions
        return (
            f"postgresql+asyncpg://{self.cache_db_user}:{self.cache_db_password}"   # driver + credentials
            f"@{self.cache_db_host}:{self.cache_db_port}/{self.cache_db_name}"      # host, port, database name
        )

    @property
    def cache_db_url_sync(self) -> str:
        """Sync URL — used by the batch sync job (plain psycopg2, simpler for pandas)."""
        # same connection details as above, but with the synchronous psycopg2 driver,
        # since pandas.to_sql() doesn't work with async engines
        return (
            f"postgresql+psycopg2://{self.cache_db_user}:{self.cache_db_password}"  # driver + credentials
            f"@{self.cache_db_host}:{self.cache_db_port}/{self.cache_db_name}"      # host, port, database name
        )

    @property
    def source_db_url(self) -> str:
        """pymssql connection string for the source SQL Server — precompiled
        wheel, no ODBC driver manager or driver install required."""
        # SQLAlchemy connection URL using the pymssql driver to reach the source SQL Server
        return (
            f"mssql+pymssql://{self.source_db_user}:{self.source_db_password}"      # driver + credentials
            f"@{self.source_db_host}:{self.source_db_port}/{self.source_db_name}"   # host, port, database name
        )


settings = Settings()                # instantiate once — reads env vars/.env immediately at import time
app_config = load_yaml_config()      # load the non-secret YAML config once — reused by main.py and sync.py
