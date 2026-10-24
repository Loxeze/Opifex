"""Connessione al database PostgreSQL con pool di connessioni."""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import impostazioni

pool = ConnectionPool(
    conninfo=impostazioni.database_url,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)


def apri_pool() -> None:
    pool.open()


def chiudi_pool() -> None:
    pool.close()


@contextmanager
def connessione():
    """Presta una connessione dal pool; conferma al termine, annulla in caso di errore."""
    with pool.connection() as conn:
        yield conn
