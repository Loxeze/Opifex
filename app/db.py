"""Connessione al database PostgreSQL con pool di connessioni."""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import impostazioni

pool = ConnectionPool(
    conninfo=impostazioni.database_url,
    min_size=1,
    max_size=40,      # ogni agente al lavoro tiene una connessione mentre aspetta il modello: servono margini
    timeout=60,
    # una connessione rimasta a meta' lavoro oltre 10 minuti viene chiusa dal database: non puo' piu' tenere in coda tutto il resto
    kwargs={"row_factory": dict_row, "options": "-c idle_in_transaction_session_timeout=600000"},
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
