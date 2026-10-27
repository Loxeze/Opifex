"""Chat a conversazioni: una per agente, ordinate per ultima attivita'. Tutto sta sul server (cronologia, non letti, bozza),
cosi' dopo un aggiornamento o una chiusura della pagina si riparte da dove si era. Piu' i dati d'uso anonimi per la sentinella dell'usabilita'."""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .db import connessione
from .permessi import divisioni_visibili, utente_corrente

router = APIRouter()
MAX_BOZZA = 20_000


def _agente_ok(conn, agente_id: int, utente: dict):
    a = conn.execute("SELECT id, nome, ruolo, divisione_id, attivo FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
    visibili = divisioni_visibili(utente)
    if visibili is not None and a["divisione_id"] not in visibili:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Agente fuori dalle tue divisioni")
    return a


@router.get("/chat/conversazioni")
def conversazioni(utente: dict = Depends(utente_corrente)):
    """Le conversazioni dell'utente, la piu' recente in alto (ultimo messaggio scritto o ultima risposta arrivata)."""
    visibili = divisioni_visibili(utente)
    with connessione() as conn:
        righe = conn.execute("""
          SELECT a.id AS agente_id, a.nome, a.ruolo, a.attivo, u.ultimo_id, u.ultima_attivita, u.in_attesa, u.totale,
                 (SELECT left(c.messaggio, 160) FROM chat_coda c WHERE c.id = u.ultimo_id) AS ultimo_messaggio,
                 (SELECT left(c.risultato->>'risposta', 160) FROM chat_coda c WHERE c.id = u.ultimo_id) AS ultima_risposta,
                 (SELECT c.stato FROM chat_coda c WHERE c.id = u.ultimo_id) AS ultimo_stato,
                 (SELECT count(*) FROM chat_coda c WHERE c.utente_id = %(u)s AND c.agente_id = a.id AND c.stato IN ('finito', 'errore')
                    AND c.finito_il > COALESCE(l.letto_il, 'epoch'::timestamptz)) AS non_letti,
                 (b.testo IS NOT NULL AND btrim(b.testo) <> '') AS ha_bozza
          FROM agenti a
          LEFT JOIN LATERAL (SELECT max(id) AS ultimo_id, max(GREATEST(creato_il, COALESCE(finito_il, creato_il))) AS ultima_attivita,
                                    count(*) FILTER (WHERE stato IN ('in_coda', 'in_lavoro')) AS in_attesa, count(*) AS totale
                             FROM chat_coda WHERE utente_id = %(u)s AND agente_id = a.id) u ON TRUE
          LEFT JOIN chat_letture l ON l.utente_id = %(u)s AND l.agente_id = a.id
          LEFT JOIN chat_bozze b ON b.utente_id = %(u)s AND b.agente_id = a.id
          WHERE (u.totale > 0 OR (b.testo IS NOT NULL AND btrim(b.testo) <> ''))
            AND (%(v)s::int[] IS NULL OR a.divisione_id = ANY(%(v)s::int[]))
          ORDER BY GREATEST(u.ultima_attivita, COALESCE(b.aggiornato_il, 'epoch'::timestamptz)) DESC NULLS LAST, a.nome""",
          {"u": utente["id"], "v": sorted(visibili) if visibili is not None else None}).fetchall()
    return righe


@router.get("/chat/non-letti")
def non_letti(utente: dict = Depends(utente_corrente)):
    with connessione() as conn:
        r = conn.execute("""SELECT count(*) AS n FROM chat_coda c LEFT JOIN chat_letture l ON l.utente_id = c.utente_id AND l.agente_id = c.agente_id
                            WHERE c.utente_id = %s AND c.stato IN ('finito', 'errore') AND c.finito_il > COALESCE(l.letto_il, 'epoch'::timestamptz)""", (utente["id"],)).fetchone()
    return {"totale": r["n"]}


def _messaggio(r: dict) -> dict:
    x = r["risultato"] or {}
    return {"id": r["id"], "canale": r["canale"], "messaggio": r["messaggio"], "stato": r["stato"], "errore": r["errore"], "creato_il": r["creato_il"], "finito_il": r["finito_il"],
            "secondi": float(r["secondi"]) if r["secondi"] is not None else None,
            "risposta": x.get("risposta"), "file": x.get("file_creati") or [], "token": (x.get("token_input") or 0) + (x.get("token_output") or 0),
            "usati": x.get("documenti_usati") or [], "esclusi": x.get("documenti_esclusi_per_riservatezza") or [], "avvisi": x.get("avvisi") or [],
            "allegati": x.get("allegati_letti") or [], "allegati_troncati": x.get("allegati_troncati") or []}


@router.get("/chat/conversazioni/{agente_id}")
def apri(agente_id: int, prima_di: int | None = None, limite: int = 40, utente: dict = Depends(utente_corrente)):
    """Gli ultimi messaggi della conversazione (dal piu' vecchio al piu' recente), con la bozza non ancora inviata."""
    limite = max(1, min(limite, 200))
    with connessione() as conn:
        a = _agente_ok(conn, agente_id, utente)
        righe = conn.execute("""SELECT id, messaggio, stato, risultato, errore, creato_il, finito_il, secondi, canale FROM chat_coda
                                WHERE utente_id = %s AND agente_id = %s AND (%s::int IS NULL OR id < %s) ORDER BY id DESC LIMIT %s""",
                             (utente["id"], agente_id, prima_di, prima_di, limite + 1)).fetchall()
        b = conn.execute("SELECT testo, fascia FROM chat_bozze WHERE utente_id = %s AND agente_id = %s", (utente["id"], agente_id)).fetchone()
    altri = len(righe) > limite
    return {"agente": {"id": a["id"], "nome": a["nome"], "ruolo": a["ruolo"], "attivo": a["attivo"]}, "altri": altri,
            "messaggi": [_messaggio(r) for r in reversed(righe[:limite])], "bozza": (b or {}).get("testo") or "", "fascia": (b or {}).get("fascia")}


@router.post("/chat/conversazioni/{agente_id}/letto")
def segna_letto(agente_id: int, utente: dict = Depends(utente_corrente)):
    with connessione() as conn:
        _agente_ok(conn, agente_id, utente)
        conn.execute("""INSERT INTO chat_letture (utente_id, agente_id, letto_il) VALUES (%s, %s, NOW())
                        ON CONFLICT (utente_id, agente_id) DO UPDATE SET letto_il = NOW()""", (utente["id"], agente_id))
    return {"ok": True}


class Bozza(BaseModel):
    testo: str = Field("", max_length=MAX_BOZZA)
    fascia: str | None = None


@router.put("/chat/conversazioni/{agente_id}/bozza")
def salva_bozza(agente_id: int, d: Bozza, utente: dict = Depends(utente_corrente)):
    """La bozza si salva mentre si scrive: se si chiude la pagina non si perde. Vuota = cancellata."""
    if d.fascia not in (None, "pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    with connessione() as conn:
        _agente_ok(conn, agente_id, utente)
        if not d.testo.strip():
            conn.execute("DELETE FROM chat_bozze WHERE utente_id = %s AND agente_id = %s", (utente["id"], agente_id))
        else:
            conn.execute("""INSERT INTO chat_bozze (utente_id, agente_id, testo, fascia, aggiornato_il) VALUES (%s, %s, %s, %s, NOW())
                            ON CONFLICT (utente_id, agente_id) DO UPDATE SET testo = EXCLUDED.testo, fascia = EXCLUDED.fascia, aggiornato_il = NOW()""",
                         (utente["id"], agente_id, d.testo, d.fascia))
    return {"ok": True}


# ---------- dati d'uso anonimi (nomi delle pagine, mai i contenuti) ----------
_NOME_VISTA = re.compile(r"^[a-z0-9_:\-]{1,60}$")


class Evento(BaseModel):
    vista: str
    azione: str


class Eventi(BaseModel):
    eventi: list[Evento] = Field(default_factory=list, max_length=30)


@router.post("/uso")
def registra_uso(d: Eventi, utente: dict = Depends(utente_corrente)):
    valide = [(e.vista, e.azione) for e in d.eventi if e.azione in ("vista", "errore") and _NOME_VISTA.match(e.vista)]
    if valide:
        with connessione() as conn:
            for v, az in valide:
                conn.execute("INSERT INTO uso_eventi (utente_id, vista, azione) VALUES (%s, %s, %s)", (utente["id"], v, az))
    return {"registrati": len(valide)}
