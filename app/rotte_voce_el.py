"""Impostazioni della voce ElevenLabs e lettura ad alta voce dei testi. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from . import cassaforte, registro, voce_elevenlabs as ve
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(tags=["voce"])


@router.get("/gestione/voce")
def leggi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        c = ve.configurazione(conn)
        out = {**c, "voci": [], "errore": None}
        if c["chiave"]:
            try:
                out["voci"] = ve.voci(conn)
            except ve.ErroreVoce as e:
                out["errore"] = str(e)
        return out


class Config(BaseModel):
    chiave: str | None = Field(default=None, max_length=300)   # mai restituita; vuota = lascia quella attuale
    voce_id: str | None = Field(default=None, max_length=60)
    garanzie: bool = False
    telegram_voce: bool = False


@router.put("/gestione/voce")
def salva(d: Config, u: dict = Depends(solo_titolare)):
    k = (d.chiave or "").strip()
    if k and (len(k) < 20 or " " in k):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La chiave non sembra valida")
    with connessione() as conn:
        try:
            ve.salva(conn, k or None, d.voce_id, d.garanzie, d.telegram_voce)
        except cassaforte.CassaforteNonConfigurata as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
        registro.registra(conn, u, "collegamento", "Voce ElevenLabs aggiornata", "ElevenLabs", "elevenlabs", "voce",
                          dettagli={"chiave_cambiata": bool(k), "garanzie": d.garanzie, "telegram_voce": d.telegram_voce})
    return {"ok": True}


@router.delete("/gestione/voce/chiave")
def scollega(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        ve.rimuovi_chiave(conn)
        registro.registra(conn, u, "collegamento", "ElevenLabs scollegato", "ElevenLabs", "elevenlabs", "voce")
    return {"ok": True}


class Testo(BaseModel):
    testo: str = Field(min_length=1, max_length=20000)


@router.post("/voce/leggi")
def leggi_testo(d: Testo, u: dict = Depends(solo_titolare)):
    try:
        audio = ve.sintetizza(d.testo, "interno", u["id"])
    except ve.ErroreVoce as e:
        raise HTTPException(e.codice, str(e)) from None
    except cassaforte.CassaforteNonConfigurata as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    return Response(content=audio, media_type="audio/mpeg")
