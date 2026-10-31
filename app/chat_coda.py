"""Chat senza attesa: il messaggio viene preso in carico subito e l'agente risponde in sottofondo, appena e' libero.
Per ogni agente le richieste vanno una dopo l'altra, cosi' la cronologia resta ordinata."""
import json
import threading
import time

from .cassaforte import CassaforteNonConfigurata
from .db import connessione
from .esecuzione import EsecuzioneBloccata, esegui_agente
from .fornitori import ErroreFornitore
from .navigatore import ErroreNavigazione

_blocchi: dict[int, threading.Lock] = {}
_g = threading.Lock()


def _blocco(agente_id: int) -> threading.Lock:
    with _g:
        return _blocchi.setdefault(agente_id, threading.Lock())


def _lavora(coda_id: int, agente_id: int, utente_id: int, messaggio: str, fascia: str, allegati, extra: dict):
    with _blocco(agente_id):
        t0 = time.monotonic()
        with connessione() as conn:
            conn.execute("UPDATE chat_coda SET stato='in_lavoro', iniziato_il=NOW() WHERE id=%s", (coda_id,))
        try:
            r = esegui_agente(agente_id, messaggio, fascia, utente_id, memorizza=True, allegati=allegati)
            r.update(extra)
            stato, errore = "finito", None
        except EsecuzioneBloccata as e:
            r, stato, errore = None, "errore", str(e)
        except (ErroreFornitore, CassaforteNonConfigurata, ErroreNavigazione) as e:
            r, stato, errore = None, "errore", str(e)
        except Exception as e:  # noqa: BLE001
            r, stato, errore = None, "errore", "Risposta non riuscita (" + type(e).__name__ + ")"
        with connessione() as conn:
            conn.execute("UPDATE chat_coda SET stato=%s, risultato=%s::jsonb, errore=%s, finito_il=NOW(), secondi=%s WHERE id=%s",
                         (stato, json.dumps(r, default=str) if r is not None else None, errore, round(time.monotonic() - t0, 1), coda_id))


def accoda(agente_id: int, utente_id: int, messaggio: str, fascia: str, allegati=None, extra: dict | None = None, sincrono: bool = False, canale: str = "web") -> int:
    with connessione() as conn:
        cid = conn.execute("INSERT INTO chat_coda (agente_id, utente_id, messaggio, canale, fascia, con_allegati) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                           (agente_id, utente_id, messaggio, canale, fascia, bool(allegati))).fetchone()["id"]
    args = (cid, agente_id, utente_id, messaggio, fascia, allegati, extra or {})
    if sincrono:
        _lavora(*args)
    else:
        threading.Thread(target=_lavora, args=args, daemon=True).start()
    return cid


def riavvio(conn):
    """Al riavvio i messaggi rimasti a meta' ripartono da soli, una volta sola, se erano recenti e senza allegati (gli allegati non si conservano);
    gli altri si segnano come interrotti con il motivo."""
    ripartono = conn.execute(
        """UPDATE chat_coda SET stato = 'in_coda', riprese = riprese + 1, errore = NULL
           WHERE stato IN ('in_coda','in_lavoro') AND NOT con_allegati AND riprese < 1 AND canale IN ('web','voce') AND creato_il > NOW() - interval '3 hours'
           RETURNING id, agente_id, utente_id, messaggio, fascia""").fetchall()
    conn.execute("UPDATE chat_coda SET stato='errore', errore='Interrotta da un riavvio del sistema: reinvia il messaggio', finito_il=NOW() WHERE stato IN ('in_coda','in_lavoro') AND id <> ALL(%s)",
                 ([r["id"] for r in ripartono] or [0],))
    for r in ripartono:
        threading.Thread(target=_lavora, args=(r["id"], r["agente_id"], r["utente_id"], r["messaggio"], r["fascia"], None, {}), daemon=True).start()
    return len(ripartono)
