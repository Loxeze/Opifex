"""Studi di Padre Casati: proposte da approvare, studi in corso, schede concluse. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import registro, studio
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/studi", tags=["studi"])


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        righe = conn.execute(
            """SELECT s.id, s.tema, s.motivo, s.origine, s.riferimento, s.stato, s.errore, s.token_usati, s.memoria_id, s.creato_il, s.concluso_il,
                      dv.nome AS reparto, a.nome AS richiesto_da, (s.scheda IS NOT NULL) AS ha_scheda, m.stato AS stato_voce
               FROM studi s LEFT JOIN divisioni dv ON dv.id = s.divisione_id LEFT JOIN agenti a ON a.id = s.agente_richiedente_id
                    LEFT JOIN memorie_lavoro m ON m.id = s.memoria_id
               ORDER BY (s.stato = 'proposto') DESC, s.id DESC LIMIT 100""").fetchall()
        return {"studi": righe, "da_approvare": sum(1 for r in righe if r["stato"] == "proposto"),
                "divisioni": conn.execute("SELECT id, nome FROM divisioni ORDER BY nome").fetchall()}


class Nuovo(BaseModel):
    tema: str = Field(min_length=5, max_length=200)
    motivo: str | None = Field(default=None, max_length=1500)
    divisione_id: int | None = None


@router.post("", status_code=201)
def crea(d: Nuovo, u: dict = Depends(solo_titolare)):
    """Un approfondimento voluto da Lorenzo: parte subito."""
    with connessione() as conn:
        try:
            i = studio.proponi(conn, d.tema, "manuale", d.motivo, divisione_id=d.divisione_id, da_utente=True)
        except studio.ErroreStudio as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        registro.registra(conn, u, "biblioteca", "studio avviato", d.tema[:150], "studio", i)
    studio.avvia(i)
    return {"id": i}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|scarta)$")


@router.post("/{studio_id}/decisione")
def decidi(studio_id: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            nuovo = studio.decidi(conn, studio_id, d.azione == "approva")
        except studio.ErroreStudio as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        t = conn.execute("SELECT tema FROM studi WHERE id = %s", (studio_id,)).fetchone()["tema"]
        registro.registra(conn, u, "biblioteca", "studio approvato" if nuovo == "approvato" else "studio scartato", t[:150], "studio", studio_id)
    if nuovo == "approvato":
        studio.avvia(studio_id)
    return {"stato": nuovo}


@router.get("/{studio_id}")
def scheda(studio_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT id, tema, stato, scheda, errore, token_usati FROM studi WHERE id = %s", (studio_id,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Studio inesistente")
        return r
