"""Misure dei consumi: dove vanno i token e quanto costa ogni parte."""
from fastapi import APIRouter, Depends, Query

from . import misure
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione", tags=["misure"])


@router.get("/misure")
def rapporto(giorni: int = Query(7, ge=1, le=90), _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return misure.rapporto(conn, giorni)
