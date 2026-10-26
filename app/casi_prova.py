"""Casi di prova: richieste tipiche per ogni agente con i criteri di una buona risposta. Si lanciano prima e dopo una modifica
(istruzioni, modello) e si confrontano i punteggi, cosi' un cambiamento non peggiora l'agente senza che nessuno se ne accorga."""
import hashlib
import json
import re
import threading

from . import catalogo_modelli
from .db import connessione
from .fornitori import chiama_modello
from .esecuzione import esegui_agente

MAX_CASI = 20


class ErroreProve(Exception):
    pass


def _modello(conn, agente_id: int):
    a = conn.execute("SELECT id, nome, modello, fascia_dati_max, accesso_web FROM agenti WHERE id=%s", (agente_id,)).fetchone()
    if a is None:
        raise ErroreProve("Agente inesistente")
    nome = catalogo_modelli.scegli_per_dialogo(conn, dict(a)) or a["modello"]
    f = conn.execute("SELECT f.nome AS f FROM modelli_ai m JOIN fornitori_ai f ON f.id=m.fornitore_id WHERE m.nome=%s", (nome,)).fetchone()
    if f is None:
        raise ErroreProve("Nessun modello utilizzabile per le prove")
    return f["f"], nome


def _json(testo: str):
    m = re.search(r"[\[{].*[\]}]", testo or "", re.S)
    if not m:
        raise ErroreProve("risposta del modello non leggibile")
    try:
        return json.loads(m.group(0))
    except ValueError:
        raise ErroreProve("risposta del modello non leggibile") from None


def impronta(conn, agente_id: int) -> str:
    a = conn.execute("SELECT istruzioni, modello, ruolo FROM agenti WHERE id=%s", (agente_id,)).fetchone()
    return hashlib.sha256(f"{a['ruolo']}|{a['modello']}|{a['istruzioni']}".encode()).hexdigest()[:12]


def genera_casi(conn, agente_id: int, quanti: int = 10) -> int:
    quanti = max(1, min(quanti, MAX_CASI))
    a = conn.execute("SELECT nome, ruolo, istruzioni FROM agenti WHERE id=%s", (agente_id,)).fetchone()
    if a is None:
        raise ErroreProve("Agente inesistente")
    esistenti = conn.execute("SELECT count(*) AS n FROM casi_prova WHERE agente_id=%s AND attivo", (agente_id,)).fetchone()["n"]
    quanti = min(quanti, MAX_CASI - esistenti)
    if quanti <= 0:
        raise ErroreProve(f"Ci sono gia' {MAX_CASI} casi attivi: disattivane qualcuno")
    f, m = _modello(conn, agente_id)
    r = chiama_modello(f, m, "Prepari casi di prova per valutare un agente AI. Rispondi SOLO con JSON.",
                       f"Agente: {a['nome']} — {a['ruolo']}\nIstruzioni:\n{a['istruzioni'][:2500]}\n\nScrivi {quanti} richieste realistiche e varie che un utente potrebbe fare a questo agente, "
                       'ciascuna con i criteri che una buona risposta deve rispettare. Formato: [{"richiesta":"...","criteri":"..."}]', 2500)
    n = 0
    for c in _json(r.testo)[:quanti]:
        if isinstance(c, dict) and str(c.get("richiesta", "")).strip() and str(c.get("criteri", "")).strip():
            conn.execute("INSERT INTO casi_prova (agente_id, richiesta, criteri, generato) VALUES (%s,%s,%s,TRUE)", (agente_id, str(c["richiesta"])[:2000], str(c["criteri"])[:2000]))
            n += 1
    return n


def giudica(conn, agente_id: int, caso: dict, risposta: str) -> tuple[int, str]:
    f, m = _modello(conn, agente_id)
    r = chiama_modello(f, m, "Sei un valutatore severo e imparziale. Rispondi SOLO con JSON.",
                       f"Richiesta: {caso['richiesta']}\nCriteri di una buona risposta: {caso['criteri']}\n\nRisposta dell'agente:\n{risposta[:4000]}\n\n"
                       'Dai un punteggio da 0 a 10 e una motivazione in una frase. Formato: {"punteggio":7,"giudizio":"..."}', 400)
    j = _json(r.testo)
    return max(0, min(10, int(j.get("punteggio", 0)))), str(j.get("giudizio", ""))[:500]


def _lavora(lotto_id: int, agente_id: int):
    try:
        with connessione() as conn:
            casi = [dict(c) for c in conn.execute("SELECT id, richiesta, criteri FROM casi_prova WHERE agente_id=%s AND attivo ORDER BY id", (agente_id,)).fetchall()]
        for c in casi:
            with connessione() as conn:
                try:
                    ris = esegui_agente(agente_id, c["richiesta"], "interno", None, memorizza=False)["risposta"]
                    p, g = giudica(conn, agente_id, c, ris)
                except Exception as e:  # noqa: BLE001
                    ris, p, g = None, None, "non eseguito: " + str(e)[:200]
                conn.execute("INSERT INTO prove_esiti (lotto_id, caso_id, risposta, punteggio, giudizio) VALUES (%s,%s,%s,%s,%s)", (lotto_id, c["id"], ris, p, g))
                conn.execute("UPDATE prove_lotti SET fatti = fatti + 1 WHERE id=%s", (lotto_id,))
        with connessione() as conn:
            conn.execute("""UPDATE prove_lotti SET stato='finito', media=(SELECT round(avg(punteggio)::numeric, 2) FROM prove_esiti WHERE lotto_id=%s AND punteggio IS NOT NULL)
                            WHERE id=%s""", (lotto_id, lotto_id))
    except Exception as e:  # noqa: BLE001
        with connessione() as conn:
            conn.execute("UPDATE prove_lotti SET stato='errore', errore=%s WHERE id=%s", (str(e)[:300], lotto_id))


def avvia(conn, agente_id: int, etichetta: str | None = None, sincrono: bool = False) -> int:
    casi = conn.execute("SELECT count(*) AS n FROM casi_prova WHERE agente_id=%s AND attivo", (agente_id,)).fetchone()["n"]
    if not casi:
        raise ErroreProve("Nessun caso di prova attivo per questo agente")
    if conn.execute("SELECT 1 FROM prove_lotti WHERE agente_id=%s AND stato='in_corso' AND creato_il > NOW() - INTERVAL '1 hour'", (agente_id,)).fetchone():
        raise ErroreProve("C'e' gia' una prova in corso per questo agente")
    lid = conn.execute("INSERT INTO prove_lotti (agente_id, etichetta, impronta, totale) VALUES (%s,%s,%s,%s) RETURNING id",
                       (agente_id, (etichetta or "")[:60] or None, impronta(conn, agente_id), casi)).fetchone()["id"]
    conn.commit()
    if sincrono:
        _lavora(lid, agente_id)
    else:
        threading.Thread(target=_lavora, args=(lid, agente_id), daemon=True).start()
    return lid


def confronto(conn, agente_id: int) -> dict:
    """Ultimi due lotti finiti: media, differenza e, per ogni caso, il punteggio prima/dopo."""
    lotti = [dict(r) for r in conn.execute("SELECT id, etichetta, impronta, media, creato_il FROM prove_lotti WHERE agente_id=%s AND stato='finito' ORDER BY id DESC LIMIT 2", (agente_id,)).fetchall()]
    if len(lotti) < 2:
        return {"lotti": lotti, "casi": [], "differenza": None, "cambiato": None}
    dopo, prima = lotti[0], lotti[1]
    pt = {r["caso_id"]: r for r in conn.execute("SELECT caso_id, punteggio, giudizio FROM prove_esiti WHERE lotto_id=%s", (prima["id"],)).fetchall()}
    casi = []
    for r in conn.execute("""SELECT e.caso_id, c.richiesta, e.punteggio, e.giudizio FROM prove_esiti e JOIN casi_prova c ON c.id=e.caso_id WHERE e.lotto_id=%s ORDER BY e.caso_id""", (dopo["id"],)).fetchall():
        p = pt.get(r["caso_id"])
        casi.append({"caso_id": r["caso_id"], "richiesta": r["richiesta"], "prima": p["punteggio"] if p else None, "dopo": r["punteggio"], "giudizio": r["giudizio"]})
    d = (float(dopo["media"]) - float(prima["media"])) if dopo["media"] is not None and prima["media"] is not None else None
    return {"lotti": lotti, "casi": casi, "differenza": round(d, 2) if d is not None else None, "cambiato": dopo["impronta"] != prima["impronta"]}
