"""Verifica di preparazione: Padre Casati interroga gli agenti sulle competenze che ha loro dato e misura quanto sono davvero preparati.
Per ogni coppia agente/competenza: Casati scrive 3 domande pratiche dal testo del livello approvato, l'agente risponde con le proprie istruzioni (senza strumenti),
Casati corregge e da' un voto 0-10 con le lacune. Voto alto: richiesta del livello successivo. Voto basso: segnalata come da ripassare."""
import re
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import ginnasio as g
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/ginnasio/preparazione", tags=["ginnasio"])
NOTTE = (1, 6)
IGNORA_NOTTE = False
SINCRONO = False
SOGLIA_OTTIMO = 8.5
SOGLIA_BASSA = 6.0


def _imp(conn, k, d):
    return g.impostazione(conn, k, d)


def attiva(conn) -> bool:
    return _imp(conn, "verifica_attiva", "1") == "1"


def ogni_giorni(conn) -> int:
    try:
        return max(1, min(90, int(_imp(conn, "verifica_giorni", "7"))))
    except ValueError:
        return 7


def per_giro(conn) -> int:
    try:
        return max(1, min(30, int(_imp(conn, "verifica_per_giro", "6"))))
    except ValueError:
        return 6


def testo_livelli(conn, competenza_id: int, livello: int, massimo: int = 6000) -> str:
    righe = conn.execute("SELECT livello, corpo FROM competenze_livelli WHERE competenza_id = %s AND livello <= %s AND stato = 'approvata' ORDER BY livello", (competenza_id, livello)).fetchall()
    return "\n\n".join(f"[Livello {r['livello']}]\n{r['corpo']}" for r in righe)[:massimo]


def prompt_domande(nome: str, livello: int, testo: str) -> str:
    return (f"Prepara una verifica su «{nome}» per un agente al livello {livello} su 5. Scrivi ESATTAMENTE 3 domande pratiche (casi concreti da risolvere, non definizioni da ripetere a memoria) "
            f"la cui risposta si trova o si deduce dal materiale qui sotto. Una per riga, nel formato:\nD1: ...\nD2: ...\nD3: ...\nNiente altro.\n\nMATERIALE:\n{testo}")


def prompt_esame(nome: str, domande: str) -> str:
    return (f"VERIFICA DI PREPARAZIONE su «{nome}». Rispondi a ogni domanda usando solo quello che sai fare e le competenze che hai (niente strumenti, niente ricerche), in massimo 100 parole ciascuna, "
            f"con la stessa numerazione (R1, R2, R3). Se non sai, scrivilo.\n\n{domande}")


def prompt_correzione(nome: str, livello: int, testo: str, domande: str, risposte: str) -> str:
    return (f"Correggi la verifica su «{nome}» (livello {livello}/5). Per ogni domanda dai un voto da 0 a 10 secondo il materiale (10 = completa e corretta, 5 = parziale, 0 = sbagliata o assente). "
            f"Formato esatto, una riga ciascuno:\nV1: <voto>\nV2: <voto>\nV3: <voto>\nLACUNE: <in una riga, cosa manca o e' sbagliato; 'nessuna' se tutto bene>\n\n"
            f"MATERIALE:\n{testo}\n\nDOMANDE:\n{domande}\n\nRISPOSTE DELL'AGENTE:\n{risposte}")


def leggi_voti(t: str) -> tuple[float | None, str]:
    v = [float(x.replace(",", ".")) for x in re.findall(r"^\s*V[123]\s*[:=]\s*(\d{1,2}(?:[.,]\d)?)", t, re.M | re.I)]
    v = [min(10.0, max(0.0, x)) for x in v][:3]
    m = re.search(r"^\s*LACUNE\s*:\s*(.+)$", t, re.M | re.I)
    return (round(sum(v) / len(v), 1) if len(v) == 3 else None), (m.group(1).strip()[:600] if m else "")


def verifica(agente_id: int, competenza_id: int) -> dict:
    from .esecuzione import esegui_agente
    with connessione() as conn:
        cas = conn.execute("SELECT id FROM agenti WHERE ruolo_speciale = 'formatore' AND attivo LIMIT 1").fetchone()
        r = conn.execute("""SELECT c.nome, ac.livello FROM agenti_competenze ac JOIN competenze c ON c.id = ac.competenza_id WHERE ac.agente_id = %s AND ac.competenza_id = %s""",
                         (agente_id, competenza_id)).fetchone()
        if not cas or not r:
            raise g.ErroreGinnasio("Padre Casati non e' attivo o l'agente non ha questa competenza")
        testo = testo_livelli(conn, competenza_id, r["livello"])
        vid = conn.execute("INSERT INTO verifiche_competenza (agente_id, competenza_id, competenza_nome, livello) VALUES (%s,%s,%s,%s) RETURNING id", (agente_id, competenza_id, r["nome"], r["livello"])).fetchone()["id"]
    try:
        if not testo.strip():
            raise g.ErroreGinnasio("Nessun testo approvato da cui trarre le domande")
        dom = esegui_agente(cas["id"], prompt_domande(r["nome"], r["livello"], testo), "interno", None, max_token=700).get("risposta", "")
        if len(re.findall(r"^\s*D[123]\s*:", dom, re.M)) < 3:
            raise g.ErroreGinnasio("Casati non ha prodotto 3 domande")
        ris = esegui_agente(agente_id, prompt_esame(r["nome"], dom), "interno", None, max_token=900).get("risposta", "")
        cor = esegui_agente(cas["id"], prompt_correzione(r["nome"], r["livello"], testo, dom, ris), "interno", None, max_token=500).get("risposta", "")
        voto, lac = leggi_voti(cor)
        if voto is None:
            raise g.ErroreGinnasio("Correzione non leggibile")
        esito = "lacune" if voto < SOGLIA_BASSA else "ok"
        with connessione() as conn:
            conn.execute("""UPDATE verifiche_competenza SET domande=%s, risposte=%s, correzione=%s, lacune=%s, voto=%s, esito=%s, conclusa_il=NOW() WHERE id=%s""",
                         (dom[:3000], ris[:4000], cor[:1500], lac, voto, esito, vid))
            if voto >= SOGLIA_OTTIMO and r["livello"] < 5:
                try:
                    g.richiedi(conn, r["nome"], r["livello"] + 1, agente_id=agente_id, motivo=f"Verifica di preparazione: voto {voto}/10 al livello {r['livello']}, pronto per il livello successivo.",
                               origine="manuale", urgenza=1)
                except g.ErroreGinnasio:
                    pass
            if esito == "lacune":
                conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Verifica di preparazione: voto {voto}/10 su «{r['nome']}». Lacune: {lac or 'vedi Ginnasio'}",))
        return {"id": vid, "voto": voto, "esito": esito, "lacune": lac}
    except Exception as e:  # noqa: BLE001
        with connessione() as conn:
            conn.execute("UPDATE verifiche_competenza SET esito='errore', errore=%s, conclusa_il=NOW() WHERE id=%s", (str(e)[:300], vid))
        return {"id": vid, "esito": "errore", "errore": str(e)[:300]}


def candidati(conn, quanti: int):
    return conn.execute("""SELECT ac.agente_id, ac.competenza_id FROM agenti_competenze ac JOIN agenti a ON a.id = ac.agente_id
        LEFT JOIN LATERAL (SELECT max(creata_il) AS u FROM verifiche_competenza v WHERE v.agente_id = ac.agente_id AND v.competenza_id = ac.competenza_id AND v.esito <> 'errore') l ON TRUE
        WHERE a.attivo AND a.ruolo_speciale IS NULL AND NOT COALESCE(a.sentinella, FALSE)
          AND (l.u IS NULL OR l.u < NOW() - make_interval(days => %s))
          AND NOT EXISTS (SELECT 1 FROM verifiche_competenza v WHERE v.agente_id = ac.agente_id AND v.competenza_id = ac.competenza_id AND v.esito='errore' AND v.creata_il > NOW() - interval '1 day')
        ORDER BY l.u NULLS FIRST, ac.agente_id LIMIT %s""", (ogni_giorni(conn), quanti)).fetchall()


def _giro_dati(coppie):
    for p in coppie:
        verifica(p["agente_id"], p["competenza_id"])


def giro(conn):
    """Dal lavoro di fondo: di notte, poche verifiche per volta ai piu' 'vecchi' tra agenti e competenze."""
    if not attiva(conn) or not (IGNORA_NOTTE or NOTTE[0] <= datetime.now().hour < NOTTE[1]):
        return None
    if conn.execute("SELECT 1 FROM verifiche_competenza WHERE esito='in_corso' AND creata_il > NOW() - interval '2 hours'").fetchone():
        return None
    if not conn.execute("SELECT 1 FROM agenti WHERE ruolo_speciale = 'formatore' AND attivo").fetchone():
        return None
    coppie = candidati(conn, per_giro(conn))
    if not coppie:
        return None
    if SINCRONO:
        _giro_dati(coppie)
    else:
        threading.Thread(target=_giro_dati, args=(coppie,), daemon=True).start()
    return len(coppie)


# ---------- rotte ----------
class Impostazioni(BaseModel):
    attiva: bool
    giorni: int = Field(ge=1, le=90)
    per_giro: int = Field(ge=1, le=30)


class Richiesta(BaseModel):
    agente_id: int
    competenza_id: int


@router.get("")
def vista(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        agenti = conn.execute("""SELECT a.id, a.nome, a.ruolo, count(v.id) AS verifiche, round(avg(v.voto), 1) AS media,
                                        count(*) FILTER (WHERE v.esito = 'lacune') AS con_lacune, max(v.conclusa_il) AS ultima
                                 FROM agenti a JOIN (SELECT DISTINCT ON (agente_id, competenza_id) * FROM verifiche_competenza WHERE esito IN ('ok','lacune') ORDER BY agente_id, competenza_id, creata_il DESC) v ON v.agente_id = a.id
                                 GROUP BY a.id, a.nome, a.ruolo ORDER BY avg(v.voto) NULLS LAST""").fetchall()
        ultime = conn.execute("""SELECT v.id, v.agente_id, a.nome AS agente, v.competenza_id, v.competenza_nome, v.livello, v.voto, v.esito, v.lacune, v.errore, v.conclusa_il
                                 FROM verifiche_competenza v JOIN agenti a ON a.id = v.agente_id ORDER BY v.id DESC LIMIT 40""").fetchall()
        return {"attiva": attiva(conn), "giorni": ogni_giorni(conn), "per_giro": per_giro(conn), "agenti": agenti, "ultime": ultime,
                "da_verificare": conn.execute("SELECT count(*) AS n FROM agenti_competenze").fetchone()["n"]}


@router.put("")
def imposta(d: Impostazioni, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        g.imposta(conn, "verifica_attiva", "1" if d.attiva else "0")
        g.imposta(conn, "verifica_giorni", str(d.giorni))
        g.imposta(conn, "verifica_per_giro", str(d.per_giro))
        return {"ok": True}


@router.get("/{vid}")
def dettaglio(vid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT * FROM verifiche_competenza WHERE id = %s", (vid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Verifica inesistente")
        return r


@router.post("", status_code=202)
def avvia(d: Richiesta, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM agenti_competenze WHERE agente_id=%s AND competenza_id=%s", (d.agente_id, d.competenza_id)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "L'agente non ha questa competenza")
        if not conn.execute("SELECT 1 FROM agenti WHERE ruolo_speciale = 'formatore' AND attivo").fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Padre Casati non e' attivo")
    if SINCRONO:
        return verifica(d.agente_id, d.competenza_id)
    threading.Thread(target=verifica, args=(d.agente_id, d.competenza_id), daemon=True).start()
    return {"avviata": True}
