"""CRM: imprese del gruppo e reparti di Opifex associati a un contatto. Solo titolare."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, crm_imprese as ci
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/crm", tags=["crm"])
ERRORI = (ci.ErroreImprese, LookupError, cassaforte.CassaforteNonConfigurata)


def _err(e: Exception):
    if isinstance(e, LookupError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


class Associa(BaseModel):
    azienda_id: int
    motivo: str = Field(min_length=5, max_length=500)
    dal: date | None = None


class Reparto(BaseModel):
    divisione_id: int
    nota: str = Field(min_length=3, max_length=500)


@router.get("/contatti/{cid}/imprese")
def vedi(cid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return ci.scheda(conn, cid)
        except ERRORI as e:
            raise _err(e) from None


@router.post("/contatti/{cid}/imprese", status_code=201)
def associa(cid: int, d: Associa, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return ci.associa_impresa(conn, cid, d.azienda_id, d.motivo, d.dal, u["id"])
        except ERRORI as e:
            raise _err(e) from None


@router.delete("/contatti/{cid}/imprese/{azienda_id}")
def togli(cid: int, azienda_id: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            ci.togli_impresa(conn, cid, azienda_id, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


@router.put("/contatti/{cid}/reparti")
def reparto(cid: int, d: Reparto, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            ci.imposta_reparto(conn, cid, d.divisione_id, d.nota, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


@router.delete("/contatti/{cid}/reparti/{divisione_id}")
def togli_reparto(cid: int, divisione_id: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            ci.togli_reparto(conn, cid, divisione_id, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


class Verifica(BaseModel):
    contatti: list[int] = Field(max_length=5000)
    azienda_id: int


@router.post("/contatti/puo-contattare")
def verifica(d: Verifica, _: dict = Depends(solo_titolare)):
    """Prima di un invio a nome di un'impresa: quali contatti dell'elenco NON le sono associati."""
    with connessione() as conn:
        return {"non_associati": ci.non_associati(conn, d.contatti, d.azienda_id)}
