"""Feed e conversazioni tra agenti, avvio di un dialogo e limiti (solo titolare)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from . import dialoghi
from .db import connessione
from .fornitori import ErroreFornitore
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/dialoghi")


@router.get("/feed")
def feed(dopo_id: int | None = Query(default=None, ge=0), limite: int = Query(default=60, ge=1, le=200),
         _: dict = Depends(solo_titolare)):
    """Messaggi tra agenti in ordine cronologico. Con dopo_id restituisce solo i nuovi (aggiornamento in tempo reale)."""
    base = """SELECT m.id, m.conversazione_id, c.titolo, m.testo, m.modello, m.creato_il,
                     da.id AS da_id, da.nome AS da, a.id AS a_id, a.nome AS a
              FROM messaggi_agenti m JOIN conversazioni c ON c.id = m.conversazione_id
              LEFT JOIN agenti da ON da.id = m.da_agente_id LEFT JOIN agenti a ON a.id = m.a_agente_id """
    with connessione() as conn:
        if dopo_id is None:
            righe = conn.execute(base + "ORDER BY m.id DESC LIMIT %s", (limite,)).fetchall()
            return list(reversed(righe))
        return conn.execute(base + "WHERE m.id > %s ORDER BY m.id ASC LIMIT %s", (dopo_id, limite)).fetchall()


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT c.id, c.titolo, c.fascia_dati, c.stato, c.creata_il, c.ultimo_messaggio_il,
                      (SELECT count(*) FROM messaggi_agenti m WHERE m.conversazione_id = c.id) AS messaggi,
                      COALESCE((SELECT string_agg(DISTINCT x.nome, ', ') FROM (
                          SELECT ag.nome FROM messaggi_agenti m JOIN agenti ag ON ag.id IN (m.da_agente_id, m.a_agente_id)
                          WHERE m.conversazione_id = c.id) x), '') AS partecipanti
               FROM conversazioni c ORDER BY c.ultimo_messaggio_il DESC LIMIT 100""").fetchall()


@router.get("/limiti")
def leggi_limiti(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {k: dialoghi.impostazione(conn, k, d) for k, d in LIMITI.items()}


LIMITI = {"dialoghi_max_messaggi": "8", "dialoghi_max_domande": "3",
          "dialoghi_budget_token_giornaliero": "200000", "modello_dialogo_predefinito": "claude-haiku-5-5"}


class Limiti(BaseModel):
    dialoghi_max_messaggi: int = Field(ge=2, le=30)
    dialoghi_max_domande: int = Field(ge=0, le=10)
    dialoghi_budget_token_giornaliero: int = Field(ge=1000, le=50_000_000)
    modello_dialogo_predefinito: str


@router.put("/limiti")
def salva_limiti(d: Limiti, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (d.modello_dialogo_predefinito,)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Modello non registrato")
        for k, v in d.model_dump().items():
            conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) "
                         "ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (k, str(v)))
    return {"stato": "ok"}


class NuovoDialogo(BaseModel):
    da_agente_id: int
    a_agente_id: int
    argomento: str = Field(min_length=3, max_length=1000)
    messaggi: int = Field(default=4, ge=2, le=30)
    fascia_dati: str = "pubblico"


@router.post("", status_code=201)
def avvia(d: NuovoDialogo, utente: dict = Depends(solo_titolare)):
    if d.fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello di riservatezza non valido")
    try:
        cid = dialoghi.dialogo_avviato_da_utente(d.da_agente_id, d.a_agente_id, d.argomento, d.messaggi, d.fascia_dati, utente["id"])
    except dialoghi.DialogoBloccato as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ErroreFornitore as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"id": cid}


@router.get("/{conv_id}")
def dettaglio(conv_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        c = conn.execute("SELECT id, titolo, fascia_dati, stato, creata_il FROM conversazioni WHERE id = %s", (conv_id,)).fetchone()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversazione inesistente")
        c["messaggi"] = conn.execute(
            """SELECT m.id, m.testo, m.modello, m.creato_il, da.nome AS da, a.nome AS a
               FROM messaggi_agenti m LEFT JOIN agenti da ON da.id = m.da_agente_id LEFT JOIN agenti a ON a.id = m.a_agente_id
               WHERE m.conversazione_id = %s ORDER BY m.id""", (conv_id,)).fetchall()
    return c
