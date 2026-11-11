"""Rotte della scheda Finestre: solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .finestre import ErroreFinestre, PROFILO, gestore_finestre as G
from .permessi import solo_titolare

router = APIRouter(prefix="/finestre", dependencies=[Depends(solo_titolare)])


def _errore(e: ErroreFinestre):
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


class Apri(BaseModel):
    url: str = Field(max_length=2000)


class Azione(BaseModel):
    tipo: str = Field(pattern="^(click|doppio|scroll|testo|tasto|indietro|avanti|ricarica)$")
    x: float = 0
    y: float = 0
    dy: float = 0
    testo: str = Field(default="", max_length=2000)


class Condividi(BaseModel):
    si: bool


class Dove(BaseModel):
    destinazione: str = Field(pattern="^(server|pc)$")


@router.get("/dove")
def dove():
    from .ponte import stato_pc
    return stato_pc()


@router.put("/dove")
def imposta_dove(d: Dove):
    from .db import connessione
    if d.destinazione == "pc":
        from .ponte import stato_pc
        if not stato_pc()["collegato"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il computer non e' collegato: apri l'app Archivio sul PC e accedi a Opifex")
    with connessione() as c:
        c.execute("UPDATE ponte_pc SET destinazione = %s WHERE id = 1", (d.destinazione,))
        c.commit()
    return {"destinazione": d.destinazione}


@router.get("")
def elenco():
    try:
        return {"schede": G.elenco()}
    except ErroreFinestre as e:
        _errore(e)


@router.post("")
def apri(d: Apri):
    try:
        return {"id": G.apri(d.url)}
    except ErroreFinestre as e:
        _errore(e)


@router.delete("/{sid}")
def chiudi(sid: int):
    try:
        G.chiudi(sid)
        return {"ok": True}
    except ErroreFinestre as e:
        _errore(e)


@router.get("/{sid}/schermo")
def schermo(sid: int):
    try:
        return Response(G.schermo(sid), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except ErroreFinestre as e:
        _errore(e)


@router.get("/{sid}/selezione")
def selezione(sid: int):
    try:
        return {"testo": G.selezione(sid)}
    except ErroreFinestre as e:
        _errore(e)


@router.post("/{sid}/vai")
def vai(sid: int, d: Apri):
    try:
        G.vai(sid, d.url)
        return {"ok": True}
    except ErroreFinestre as e:
        _errore(e)


@router.post("/{sid}/azione")
def azione(sid: int, d: Azione):
    try:
        G.azione(sid, d.tipo, d.x, d.y, d.dy, d.testo)
        return {"ok": True}
    except ErroreFinestre as e:
        _errore(e)


@router.put("/{sid}/condividi")
def condividi(sid: int, d: Condividi):
    try:
        G.condividi(sid, d.si)
        return {"ok": True}
    except ErroreFinestre as e:
        _errore(e)


@router.get("/scaricati/elenco")
def scaricati():
    return {"file": G.scaricati()}


@router.get("/scaricati/{nome}")
def scarica(nome: str):
    p = (PROFILO / "scaricati" / nome).resolve()
    if p.parent != (PROFILO / "scaricati").resolve() or not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File non trovato")
    return FileResponse(p, filename=p.name)
