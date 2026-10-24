"""Rotte per parlare con gli agenti e per le proposte di sviluppo dell'Architetto tecnico."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .db import connessione
from .esecuzione import EsecuzioneBloccata, esegui_agente
from .cassaforte import CassaforteNonConfigurata
from .fornitori import ErroreFornitore
from .navigatore import ErroreNavigazione
from .permessi import divisioni_visibili, solo_titolare, utente_corrente

router = APIRouter()


class Domanda(BaseModel):
    messaggio: str
    fascia_dati: str = "interno"


@router.post("/agenti/{agente_id}/chat")
def chat_con_agente(agente_id: int, d: Domanda, utente: dict = Depends(utente_corrente)):
    if d.fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    visibili = divisioni_visibili(utente)
    if visibili is not None:
        with connessione() as conn:
            a = conn.execute("SELECT divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
        if a is None or a["divisione_id"] not in visibili:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Agente fuori dalle tue divisioni")
    try:
        return esegui_agente(agente_id, d.messaggio, d.fascia_dati, utente["id"])
    except EsecuzioneBloccata as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except (ErroreFornitore, CassaforteNonConfigurata, ErroreNavigazione) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


class NuovaProposta(BaseModel):
    titolo: str
    motivazione: str
    tipo: str = "miglioramento"
    gravita: str = "media"
    codice_proposto: str | None = None
    piano_collaudo: str | None = None


@router.post("/proposte", status_code=201)
def crea_proposta(p: NuovaProposta, utente: dict = Depends(solo_titolare)):
    """Lorenzo propone all'Architetto uno sviluppo (l'Architetto propone a lui con la stessa struttura)."""
    if p.tipo not in ("falla_sicurezza", "miglioramento", "nuova_funzione", "prestazioni"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo non valido")
    if p.gravita not in ("info", "media", "alta", "critica"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Gravita' non valida")
    with connessione() as conn:
        riga = conn.execute(
            """INSERT INTO proposte_sviluppo
               (proposta_da_utente, titolo, motivazione, tipo, gravita, codice_proposto, piano_collaudo)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (utente["id"], p.titolo, p.motivazione, p.tipo, p.gravita, p.codice_proposto, p.piano_collaudo),
        ).fetchone()
    return {"id": riga["id"]}


@router.get("/proposte")
def elenco_proposte(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            "SELECT id, titolo, tipo, gravita, stato, creata_il FROM proposte_sviluppo ORDER BY creata_il DESC"
        ).fetchall()


class Decisione(BaseModel):
    decisione: str  # 'approvata' | 'respinta'
    note: str | None = None


@router.post("/proposte/{proposta_id}/decisione")
def decidi_proposta(proposta_id: int, d: Decisione, utente: dict = Depends(solo_titolare)):
    """Solo il titolare approva o respinge. Un'approvazione porta la proposta in collaudo, mai direttamente in produzione."""
    if d.decisione not in ("approvata", "respinta"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Decisione non valida")
    with connessione() as conn:
        riga = conn.execute("SELECT stato FROM proposte_sviluppo WHERE id = %s", (proposta_id,)).fetchone()
        if riga is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposta inesistente")
        if riga["stato"] not in ("proposta", "in_discussione", "da_approvare"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Proposta gia' decisa")
        conn.execute(
            "UPDATE proposte_sviluppo SET stato = %s, note_lorenzo = %s, decisa_da = %s, decisa_il = NOW() WHERE id = %s",
            (d.decisione, d.note, utente["id"], proposta_id),
        )
    return {"stato": d.decisione}
