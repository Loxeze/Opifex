"""Trascrizione vocale sul server (alternativa al riconoscimento del browser): l'audio va a OpenAI solo se la riservatezza lo consente."""
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from . import fornitori
from .db import connessione
from .permessi import utente_corrente
from .riservatezza import puo_uscire

router = APIRouter(prefix="/voce")
MAX_BYTE = 10 * 1024 * 1024
FORMATI = {"webm", "ogg", "mp4", "m4a", "wav", "mp3", "mpeg", "mpga"}
MAX_ORA = 60


@router.post("/trascrivi")
def trascrivi(audio: UploadFile = File(...), fascia_dati: str = Form("pubblico"), utente: dict = Depends(utente_corrente)):
    if fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    estensione = (audio.filename or "voce.webm").rsplit(".", 1)[-1].lower()
    if estensione not in FORMATI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Formato audio non supportato")
    dati = audio.file.read(MAX_BYTE + 1)
    if len(dati) > MAX_BYTE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Registrazione troppo lunga")
    if len(dati) < 1000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Registrazione vuota")
    with connessione() as conn:
        f = conn.execute("SELECT fascia_dati_max, non_conservazione_attiva, dpa_firmato FROM fornitori_ai WHERE nome = 'openai'").fetchone()
        ok, motivo = puo_uscire(fascia_dati, "riservato", f["fascia_dati_max"], f["non_conservazione_attiva"], f["dpa_firmato"])
        if not ok:
            raise HTTPException(status.HTTP_409_CONFLICT, "Trascrizione sul server non consentita per questo tipo di dati: " + str(motivo) +
                                ". Usa la dettatura del browser oppure dichiara le garanzie di OpenAI in Sicurezza e garanzie.")
        recenti = conn.execute("SELECT count(*) AS n FROM registro_azioni WHERE azione='voce_trascritta' AND utente_id=%s AND creata_il >= NOW() - interval '1 hour'",
                               (utente["id"],)).fetchone()["n"]
        if recenti >= MAX_ORA:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Troppe trascrizioni in un'ora: riprova piu' tardi")
    chiave = fornitori.chiave("openai")
    if not chiave:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chiave OpenAI non configurata: inseriscila in Impostazioni → Sicurezza e garanzie")
    try:
        r = httpx.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": "Bearer " + chiave},
                       data={"model": "whisper-1", "language": "it", "response_format": "json"},
                       files={"file": ("voce." + estensione, dati, audio.content_type or "application/octet-stream")}, timeout=60)
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"OpenAI non raggiungibile ({type(e).__name__})") from None
    if r.status_code != 200:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"OpenAI ha risposto {r.status_code}")
    testo = (r.json().get("text") or "").strip()
    with connessione() as conn:
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('voce_trascritta', %s::jsonb, %s)",
                     ('{"byte": %d}' % len(dati), utente["id"]))
    if not testo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Non ho capito nulla nella registrazione: riprova parlando piu' vicino al microfono")
    return {"testo": testo}
