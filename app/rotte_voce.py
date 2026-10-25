"""Trascrizione vocale sul server (alternativa al riconoscimento del browser): l'audio va a OpenAI solo se la riservatezza lo consente."""
import httpx  # noqa: F401 - i collaudi sostituiscono httpx.post
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from . import trascrizione
from .permessi import utente_corrente

router = APIRouter(prefix="/voce")
MAX_BYTE = trascrizione.MAX_BYTE


@router.post("/trascrivi")
def trascrivi(audio: UploadFile = File(...), fascia_dati: str = Form("pubblico"), utente: dict = Depends(utente_corrente)):
    if fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    estensione = (audio.filename or "voce.webm").rsplit(".", 1)[-1].lower()
    dati = audio.file.read(MAX_BYTE + 1)
    try:
        return {"testo": trascrizione.trascrivi(dati, estensione, fascia_dati, utente["id"], audio.content_type or "application/octet-stream")}
    except trascrizione.ErroreTrascrizione as e:
        raise HTTPException(e.codice, str(e)) from None
