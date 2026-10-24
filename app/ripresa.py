"""Ripresa immediata del lavoro: quando Lorenzo risponde a una richiesta l'agente riparte subito, in background."""
import threading
import time

from .db import connessione

SINCRONO = False          # nei collaudi si esegue nello stesso thread
_LAVORANDO: dict[int, dict] = {}
_blocco = threading.Lock()


def stato_lavoro() -> list[dict]:
    with _blocco:
        ora = time.time()
        return [{"agente_id": k, "agente": v["nome"], "da_secondi": int(ora - v["inizio"]), "motivo": v["motivo"]}
                for k, v in _LAVORANDO.items()]


def _lavora(agente_id: int, nome: str, messaggio: str, utente_id: int | None, motivo: str):
    from .esecuzione import esegui_agente  # import tardivo: evita cicli
    t0 = time.time()
    with _blocco:
        _LAVORANDO[agente_id] = {"nome": nome, "inizio": t0, "motivo": motivo}
    try:
        r = esegui_agente(agente_id, messaggio, "interno", utente_id=utente_id, memorizza=True, max_token=1500)
        sec = int(time.time() - t0)
        testo = f"{nome} ha ripreso il lavoro ({motivo}) in {sec}s: {r['risposta'][:300]}"
    except Exception as e:  # noqa: BLE001 - l'errore va comunque notificato
        testo = f"{nome} non ha potuto riprendere il lavoro ({motivo}): {str(e)[:200]}"
    finally:
        with _blocco:
            _LAVORANDO.pop(agente_id, None)
    with connessione() as conn:
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (testo,))


def riprendi(agente_id: int, utente_id: int | None, motivo: str = "risposta di Lorenzo"):
    """Avvia subito l'agente: le risposte non ancora consegnate vengono aggiunte da esegui_agente."""
    with connessione() as conn:
        a = conn.execute("SELECT nome FROM agenti WHERE id = %s AND attivo", (agente_id,)).fetchone()
    if a is None:
        return
    with _blocco:
        if agente_id in _LAVORANDO:
            return  # sta gia' lavorando: vedra' la risposta nella sua esecuzione corrente o alla prossima
    msg = "Lorenzo ha risposto alla tua richiesta di informazioni. Riprendi il lavoro da dove eri rimasto, usando le sue risposte."
    if SINCRONO:
        _lavora(agente_id, a["nome"], msg, utente_id, motivo)
    else:
        threading.Thread(target=_lavora, args=(agente_id, a["nome"], msg, utente_id, motivo), daemon=True).start()
