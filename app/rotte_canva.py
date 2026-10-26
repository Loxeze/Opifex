"""Collegamento a Canva. Solo titolare, tranne il ritorno di Canva (vale lo stato monouso)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import canva
from .db import connessione
from .permessi import solo_titolare

router = APIRouter()


@router.get("/gestione/canva")
def stato_canva(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return canva.stato(conn)


class Client(BaseModel):
    client_id: str = Field(min_length=5, max_length=300)
    client_secret: str | None = Field(default=None, max_length=300)


@router.put("/gestione/canva/client")
def imposta_client(d: Client, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        canva.imposta_client(conn, d.client_id, d.client_secret)
    return {"ok": True}


@router.post("/gestione/canva/autorizza")
def autorizza(_: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            canva._scrivi(conn, "canva_ultimo_esito", "")
            return {"url": canva.url_autorizzazione(conn)}
    except canva.ErroreCanva as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("/gestione/canva/callback", include_in_schema=False)
def ritorno(code: str | None = Query(default=None, max_length=2000), state: str | None = Query(default=None, max_length=200),
            error: str | None = Query(default=None, max_length=100)):
    with connessione() as conn:
        if error or not code or not state:
            canva._scrivi(conn, "canva_ultimo_esito", "Collegamento annullato o rifiutato da Canva.")
        else:
            try:
                canva._scrivi(conn, "canva_ultimo_esito", "ok:" + canva.completa_autorizzazione(conn, code, state))
            except canva.ErroreCanva as e:
                canva._scrivi(conn, "canva_ultimo_esito", str(e))
    return RedirectResponse("/app/", status_code=303)


@router.post("/gestione/canva/prova")
def prova(_: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            return {"esito": canva.prova(conn)}
    except canva.ErroreCanva as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.delete("/gestione/canva")
def scollega(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        canva.scollega(conn)
    return {"ok": True}
