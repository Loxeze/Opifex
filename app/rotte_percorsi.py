"""Percorsi di lavoro a fasi: avvio, elenco, dettaglio e decisioni (approva / chiedi modifiche / annulla)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import percorsi
from . import registro
from .db import connessione
from .esecuzione import EsecuzioneBloccata
from .permessi import divisioni_visibili, utente_corrente

router = APIRouter(prefix="/percorsi", tags=["percorsi"])

CAMPI = """p.id, p.titolo, p.stato, p.fase_corrente, jsonb_array_length(p.fasi) AS n_fasi, p.errore, p.fascia_dati,
           p.creato_il, p.aggiornato_il, a.id AS agente_id, a.nome AS agente, p.progetto_id, pr.nome AS progetto"""
DA = "FROM percorsi_lavoro p JOIN agenti a ON a.id = p.agente_id LEFT JOIN progetti pr ON pr.id = p.progetto_id"


def _filtro(utente: dict) -> tuple[str, list]:
    v = divisioni_visibili(utente)
    if v is None:
        return "TRUE", []
    return "a.divisione_id = ANY(%s)", [list(v)]


def _carica(conn, pid: int, utente: dict) -> dict:
    cond, par = _filtro(utente)
    r = conn.execute(f"SELECT {CAMPI}, p.brief, p.fasi {DA} WHERE p.id = %s AND {cond}", [pid] + par).fetchone()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Percorso non trovato")
    return r


@router.get("/opzioni")
def opzioni(utente: dict = Depends(utente_corrente)):
    cond, par = _filtro(utente)
    with connessione() as conn:
        return {
            "agenti": conn.execute(
                f"""SELECT a.id, a.nome, a.ruolo, (SELECT count(*) FROM fasi_agente f WHERE f.agente_id = a.id)::int AS n_fasi
                    FROM agenti a WHERE a.attivo AND {cond}
                      AND EXISTS (SELECT 1 FROM fasi_agente f WHERE f.agente_id = a.id) ORDER BY a.nome""", par).fetchall(),
            "progetti": conn.execute("SELECT id, nome FROM progetti WHERE NOT archiviato ORDER BY nome").fetchall(),
        }


@router.get("")
def elenco(utente: dict = Depends(utente_corrente)):
    cond, par = _filtro(utente)
    with connessione() as conn:
        return conn.execute(f"SELECT {CAMPI} {DA} WHERE {cond} ORDER BY (p.stato = 'in_attesa') DESC, p.aggiornato_il DESC LIMIT 100", par).fetchall()


class Avvio(BaseModel):
    agente_id: int
    titolo: str = Field(min_length=1, max_length=150)
    brief: str = Field(min_length=1, max_length=8000)
    fascia_dati: str = "interno"
    progetto_id: int | None = None


@router.post("", status_code=201)
def avvia(d: Avvio, utente: dict = Depends(utente_corrente)):
    if d.fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    v = divisioni_visibili(utente)
    with connessione() as conn:
        a = conn.execute("SELECT divisione_id, attivo FROM agenti WHERE id = %s", (d.agente_id,)).fetchone()
        if a is None or (v is not None and a["divisione_id"] not in v):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Agente fuori dalle tue divisioni")
        if not a["attivo"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Agente spento")
        if d.progetto_id and not conn.execute("SELECT 1 FROM progetti WHERE id = %s", (d.progetto_id,)).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Progetto inesistente")
        try:
            pid = percorsi.avvia(conn, d.agente_id, d.titolo.strip(), d.brief.strip(), d.fascia_dati, d.progetto_id, utente["id"])
        except EsecuzioneBloccata as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return {"id": pid}


@router.get("/{pid}")
def dettaglio(pid: int, utente: dict = Depends(utente_corrente)):
    with connessione() as conn:
        p = _carica(conn, pid, utente)
        p["esiti"] = conn.execute(
            """SELECT e.id, e.posizione, e.tentativo, e.testo, e.parere_superiore, e.decisione, e.nota, e.creato_il, e.deciso_il, u.nome AS deciso_da
               FROM esiti_fasi e LEFT JOIN utenti u ON u.id = e.decisa_da_utente_id WHERE e.percorso_id = %s ORDER BY e.id""", (pid,)).fetchall()
    return p


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|modifiche|annulla|riprova)$")
    nota: str = Field(default="", max_length=4000)


@router.post("/{pid}/decisione")
def decisione(pid: int, d: Decisione, utente: dict = Depends(utente_corrente)):
    if d.azione == "modifiche" and not d.nota.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scrivi cosa vuoi cambiare")
    with connessione() as conn:
        p = _carica(conn, pid, utente)
        try:
            nuovo = percorsi.decidi(conn, pid, d.azione, d.nota.strip(), utente["id"])
        except EsecuzioneBloccata as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        registro.registra(conn, utente, "fase_percorso", {"approva": "approvata", "modifiche": "modifiche richieste", "annulla": "percorso annullato",
                                                          "riprova": "ripetuta dopo errore"}[d.azione],
                          p.get("titolo") or f"Percorso {pid}", "percorso", pid, d.nota.strip(), {"fase": p.get("fase_corrente"), "stato_dopo": nuovo})
    return {"stato": nuovo}
