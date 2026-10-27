"""Maestro di chiavi: stato dei backup notturni, avvio a mano, deposito file. Solo titolare. La chiave di backup non ha alcuna rotta."""
import base64
import binascii
import threading

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from . import custode
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/custode", tags=["custode"])
_IN_CORSO = threading.Lock()


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return custode.stato(conn) | {"in_corso": _IN_CORSO.locked()}


class Attivo(BaseModel):
    attivo: bool


@router.put("/backup")
def attiva(d: Attivo, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('custode_backup_attivo', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", ("1" if d.attivo else "0",))
    return {"attivo": d.attivo}


def _lavoro():
    try:
        with connessione() as conn:
            custode.backup_tutti(conn)
    finally:
        _IN_CORSO.release()


@router.post("/backup-ora", status_code=202)
def ora(_: dict = Depends(solo_titolare)):
    """Parte in sottofondo: un backup grande richiede minuti."""
    if not _IN_CORSO.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un backup e' gia' in corso")
    threading.Thread(target=_lavoro, daemon=True).start()
    return {"avviato": True}


@router.get("/deposito/{fid}/scarica")
def scarica(fid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT nome, tipo, contenuto FROM custode_file WHERE id = %s", (fid,)).fetchone()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Elemento non trovato")
    nome = "".join(ch for ch in r["nome"] if ch.isalnum() or ch in "._- ") or "file"
    return Response(content=bytes(r["contenuto"]), media_type="application/zip" if r["tipo"] == "zip" else "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


class Carico(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    contenuto_base64: str = Field(min_length=1, max_length=70_000_000)


@router.post("/deposito", status_code=201)
def carica(d: Carico, _: dict = Depends(solo_titolare)):
    """Lorenzo mette un file (o uno zip) nel deposito; poi chiede al Maestro di caricarlo su un sito."""
    try:
        dati = base64.b64decode(d.contenuto_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Contenuto non valido")
    with connessione() as conn:
        try:
            fid = custode.deposita(conn, d.nome, dati, "zip" if d.nome.lower().endswith(".zip") else "file", None, "caricato da Lorenzo")
        except custode.ErroreCustode as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return {"id": fid}


@router.delete("/deposito/{fid}")
def elimina(fid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("DELETE FROM custode_file WHERE id = %s", (fid,))
    return {"ok": True}
