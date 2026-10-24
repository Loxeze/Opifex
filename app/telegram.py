"""Canale Telegram: Lorenzo parla con Aurora (il referente) da Telegram e riceve gli avvisi.

Sicurezza:
 - il token del bot sta cifrato nella cassaforte e non compare mai in log, risposte o messaggi di errore;
 - il bot risponde SOLO alla chat abbinata (un solo abbinamento, con codice monouso che scade in 10 minuti);
   a chiunque altro non risponde nulla;
 - i messaggi verso Aurora passano dallo stesso controllo di riservatezza della chat dell'interfaccia
   (livello predefinito: dati pubblici, modificabile con /fascia).
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import httpx

from . import cassaforte, richieste as modulo_richieste
from .db import connessione
from .esecuzione import EsecuzioneBloccata, esegui_agente
from .fornitori import ErroreFornitore
from .navigatore import ErroreNavigazione

FASCE = ("pubblico", "interno", "riservato")
MAX_MSG = 3800


class ErroreTelegram(Exception):
    pass


def _chiama(token: str, metodo: str, attesa_http: int = 15, **parametri) -> dict:
    """Chiamata all'API Telegram. Il token e' nell'indirizzo (lo vuole Telegram): nessun errore lo riporta."""
    try:
        r = httpx.post(f"https://api.telegram.org/bot{token}/{metodo}", json=parametri, timeout=attesa_http)
        d = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise ErroreTelegram("Telegram non raggiungibile (" + type(e).__name__ + ")") from None
    if not d.get("ok"):
        raise ErroreTelegram("Telegram: " + str(d.get("description", "errore"))[:150])
    return d["result"]


def _riga(conn) -> dict:
    return conn.execute("SELECT * FROM canale_telegram WHERE id = 1").fetchone()


def _token(conn) -> str:
    r = _riga(conn)
    return cassaforte.decifra(r["token_cifrato"]) if r["token_cifrato"] else ""


def stato(conn) -> dict:
    r = _riga(conn)
    return {"configurato": bool(r["token_cifrato"]), "bot": r["bot_username"], "collegato": r["chat_id"] is not None,
            "fascia_dati": r["fascia_dati"], "ultimo_errore": r["ultimo_errore"],
            "codice_attivo": bool(r["codice_scade"] and r["codice_scade"] > datetime.now(timezone.utc))}


def imposta_token(conn, token: str) -> str:
    token = token.strip()
    info = _chiama(token, "getMe")
    conn.execute("UPDATE canale_telegram SET token_cifrato=%s, bot_username=%s, chat_id=NULL, offset_aggiornamenti=0, "
                 "codice_hash=NULL, codice_scade=NULL, ultimo_errore=NULL, collegato_il=NULL WHERE id=1",
                 (cassaforte.cifra(token), info.get("username")))
    try:  # niente webhook attivi: usiamo la richiesta periodica
        _chiama(token, "deleteWebhook")
    except ErroreTelegram:
        pass
    return info.get("username") or ""


def rimuovi(conn):
    conn.execute("UPDATE canale_telegram SET token_cifrato=NULL, bot_username=NULL, chat_id=NULL, codice_hash=NULL, "
                 "codice_scade=NULL, ultimo_errore=NULL, collegato_il=NULL WHERE id=1")


def nuovo_codice(conn) -> str:
    codice = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    conn.execute("UPDATE canale_telegram SET codice_hash=%s, codice_scade=%s, codice_tentativi=0 WHERE id=1",
                 (hashlib.sha256(codice.encode()).hexdigest(), datetime.now(timezone.utc) + timedelta(minutes=10)))
    return codice


def scollega(conn):
    conn.execute("UPDATE canale_telegram SET chat_id=NULL, collegato_il=NULL WHERE id=1")


def imposta_fascia(conn, fascia: str):
    if fascia not in FASCE:
        raise ErroreTelegram("Livello non valido")
    conn.execute("UPDATE canale_telegram SET fascia_dati=%s WHERE id=1", (fascia,))


def invia(token: str, chat_id: int, testo: str):
    testo = (testo or "(vuoto)")
    for i in range(0, len(testo), MAX_MSG):
        _chiama(token, "sendMessage", chat_id=chat_id, text=testo[i:i + MAX_MSG])


# ---------- elaborazione dei messaggi ricevuti ----------
AIUTO = ("Sono il canale di Aurora. Scrivimi normalmente e ti risponde Aurora.\n"
         "/richieste - cosa serve agli agenti\n/rispondi NUMERO testo - rispondi a una richiesta\n"
         "/briefing - l'ultimo briefing\n/stato - situazione in breve\n"
         "/fascia pubblico|interno|riservato - che dati possono uscire verso l'AI in questa chat")


def _titolare_id(conn):
    r = conn.execute("SELECT id FROM utenti WHERE ruolo_globale = 'titolare' AND attivo ORDER BY id LIMIT 1").fetchone()
    return r["id"] if r else None


def _comando(conn, testo: str, r: dict) -> str | None:
    """Risposta a un comando; None se non e' un comando."""
    if not testo.startswith("/"):
        return None
    parti = testo.split(maxsplit=2)
    cmd = parti[0].lower().split("@")[0]
    if cmd in ("/start", "/aiuto", "/help"):
        return AIUTO
    if cmd == "/richieste":
        righe = conn.execute(
            """SELECT r.id, a.nome, r.domanda, r.bloccante FROM richieste_informazioni r JOIN agenti a ON a.id = r.agente_id
               WHERE r.stato = 'aperta' ORDER BY r.bloccante DESC, r.id LIMIT 15""").fetchall()
        if not righe:
            return "Nessuna richiesta aperta."
        return "\n\n".join(f"#{x['id']}{' [BLOCCANTE]' if x['bloccante'] else ''} {x['nome']}: {x['domanda']}" for x in righe) \
            + "\n\nRispondi con /rispondi NUMERO testo"
    if cmd == "/rispondi":
        if len(parti) < 3 or not parti[1].lstrip("#").isdigit():
            return "Uso: /rispondi NUMERO la tua risposta"
        n = conn.execute("UPDATE richieste_informazioni SET stato='risposta', risposta=%s, risposta_il=NOW() "
                         "WHERE id=%s AND stato='aperta' RETURNING id", (parti[2].strip()[:4000], int(parti[1].lstrip("#")))).fetchone()
        return "Risposta registrata: l'agente la riceve al prossimo lavoro." if n else "Richiesta non trovata o gia' chiusa."
    if cmd == "/briefing":
        b = conn.execute("SELECT contenuto, creato_il FROM briefing ORDER BY id DESC LIMIT 1").fetchone()
        return b["contenuto"] if b else "Nessun briefing ancora."
    if cmd == "/stato":
        c = conn.execute("""SELECT (SELECT count(*) FROM agenti WHERE attivo) AS agenti,
                                   (SELECT count(*) FROM richieste_informazioni WHERE stato='aperta') AS richieste,
                                   (SELECT count(*) FROM approvazioni WHERE decisione IS NULL) AS approvazioni,
                                   (SELECT COALESCE(SUM(costo_stimato),0) FROM costi_api WHERE creato_il >= date_trunc('day', NOW())) AS costo""").fetchone()
        from .versione import versione_corrente
        return (f"Opifex {versione_corrente()}: {c['agenti']} agenti attivi, {c['richieste']} richieste aperte, "
                f"{c['approvazioni']} da approvare, costo AI di oggi {float(c['costo']):.2f}. Dati in chat: {r['fascia_dati']}.")
    if cmd == "/fascia":
        if len(parti) < 2 or parti[1].lower() not in FASCE:
            return "Uso: /fascia pubblico | interno | riservato. Ora: " + r["fascia_dati"]
        imposta_fascia(conn, parti[1].lower())
        return "Da ora i messaggi di questa chat sono trattati come dati " + parti[1].lower() + "."
    return "Comando non riconosciuto. /aiuto"


def _verso_aurora(conn, testo: str, fascia: str) -> str:
    aurora = conn.execute("SELECT id FROM agenti WHERE nome = 'Aurora' AND tipo = 'sistema'").fetchone()
    if aurora is None:
        return "Aurora non c'e' tra gli agenti."
    uid = _titolare_id(conn)
    conn.commit()
    try:
        return esegui_agente(aurora["id"], testo, fascia, uid, memorizza=True)["risposta"]
    except EsecuzioneBloccata as e:
        return "Aurora non puo' rispondere: " + str(e)
    except (ErroreFornitore, cassaforte.CassaforteNonConfigurata, ErroreNavigazione) as e:
        return "Errore nel contattare l'AI: " + str(e)[:200]


def gestisci_messaggio(conn, token: str, upd: dict):
    m = upd.get("message") or {}
    chat = m.get("chat") or {}
    cid = chat.get("id")
    if cid is None or chat.get("type") != "private":
        return  # gruppi e canali: mai
    testo = (m.get("text") or "").strip()
    r = _riga(conn)

    # abbinamento (unica cosa permessa a chi non e' ancora collegato)
    if r["chat_id"] is None:
        if testo.lower().startswith("/collega"):
            codice = (testo.split(maxsplit=1) + [""])[1].strip().upper()
            valido = (r["codice_hash"] and r["codice_scade"] and r["codice_scade"] > datetime.now(timezone.utc)
                      and r["codice_tentativi"] < 5)
            if valido and hmac.compare_digest(hashlib.sha256(codice.encode()).hexdigest(), r["codice_hash"]):
                conn.execute("UPDATE canale_telegram SET chat_id=%s, collegato_il=NOW(), codice_hash=NULL, codice_scade=NULL WHERE id=1", (cid,))
                invia(token, cid, "Collegato. D'ora in poi parli con Aurora da qui. /aiuto per i comandi.")
            else:
                if valido:
                    conn.execute("UPDATE canale_telegram SET codice_tentativi = codice_tentativi + 1 WHERE id=1")
                invia(token, cid, "Codice non valido o scaduto.")
        elif testo.lower().startswith("/start"):
            invia(token, cid, "Per collegarmi usa /collega CODICE: il codice lo genera Opifex nella scheda Canali.")
        return  # tutto il resto: silenzio

    if cid != r["chat_id"]:
        return  # chiunque altro: nessuna risposta
    if not testo:
        invia(token, cid, "Per ora gestisco solo messaggi di testo.")
        return
    risp = _comando(conn, testo, r)
    if risp is None:
        try: _chiama(token, "sendChatAction", chat_id=cid, action="typing")
        except ErroreTelegram: pass
        risp = _verso_aurora(conn, testo, r["fascia_dati"])
    invia(token, cid, risp)


def invia_notifiche(conn, token: str, chat_id: int) -> int:
    n = 0
    for x in conn.execute("SELECT id, testo, urgente FROM notifiche WHERE inviata_il IS NULL ORDER BY id LIMIT 20").fetchall():
        invia(token, chat_id, ("URGENTE - " if x["urgente"] else "") + x["testo"])
        conn.execute("UPDATE notifiche SET inviata_il = NOW(), canale = 'telegram' WHERE id = %s", (x["id"],))
        conn.commit()
        n += 1
    return n


def giro(timeout: int = 20) -> bool:
    """Un giro: legge i messaggi nuovi e invia le notifiche in coda. False se il canale non e' configurato."""
    with connessione() as conn:
        r = _riga(conn)
        if not r["token_cifrato"]:
            return False
        token = cassaforte.decifra(r["token_cifrato"])
        offset = r["offset_aggiornamenti"]
    try:
        aggiornamenti = _chiama(token, "getUpdates", timeout + 10, offset=offset, timeout=timeout, allowed_updates=["message"])
        with connessione() as conn:
            for u in aggiornamenti:
                conn.execute("UPDATE canale_telegram SET offset_aggiornamenti=%s WHERE id=1", (u["update_id"] + 1,))
                conn.commit()  # prima segno come letto: un messaggio che manda in errore non si ripete all'infinito
                try:
                    gestisci_messaggio(conn, token, u)
                except ErroreTelegram:
                    raise
                except Exception:
                    conn.rollback()
            r = _riga(conn)
            if r["chat_id"] is not None:
                invia_notifiche(conn, token, r["chat_id"])
            conn.execute("UPDATE canale_telegram SET ultimo_errore=NULL WHERE id=1")
    except ErroreTelegram as e:
        with connessione() as conn:
            conn.execute("UPDATE canale_telegram SET ultimo_errore=%s WHERE id=1", (str(e),))
        raise
    return True
