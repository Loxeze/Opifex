"""CRM: campi personalizzati, categorie, relazioni, recapiti, fonte e verifica, storico. Solo titolare."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, crm_modello as cm
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/crm", tags=["crm"])


def _err(e: Exception):
    if isinstance(e, LookupError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    if isinstance(e, cassaforte.CassaforteNonConfigurata):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


ERRORI = (cm.ErroreModello, LookupError, cassaforte.CassaforteNonConfigurata)


class Campo(BaseModel):
    tipo: str = Field(default="", max_length=40)
    chiave: str = Field(min_length=2, max_length=40)
    etichetta: str = Field(min_length=1, max_length=60)
    dato: str = "testo"
    scelte: list[str] = []
    ordine: int = 0


class ModCampo(BaseModel):
    etichetta: str | None = Field(default=None, max_length=60)
    scelte: list[str] | None = None
    ordine: int | None = None


@router.get("/campi")
def campi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"campi": cm.definizioni(conn), "tipi_in_uso": [x["tipo"] for x in conn.execute("SELECT tipo, count(*) FROM crm_contatti GROUP BY tipo ORDER BY count(*) DESC LIMIT 100").fetchall()]}


@router.post("/campi", status_code=201)
def crea_campo(d: Campo, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"id": cm.crea_definizione(conn, d.model_dump())}
        except ERRORI as e:
            raise _err(e) from None


@router.put("/campi/{did}")
def modifica_campo(did: int, d: ModCampo, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.modifica_definizione(conn, did, d.model_dump(exclude_unset=True))
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


@router.delete("/campi/{did}")
def elimina_campo(did: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.elimina_definizione(conn, did)
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


@router.get("/categorie")
def categorie(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"categorie": cm.categorie(conn)}


class NuovaCategoria(BaseModel):
    nome: str = Field(min_length=2, max_length=60)
    descrizione: str | None = Field(default=None, max_length=200)


@router.post("/categorie", status_code=201)
def nuova_categoria(d: NuovaCategoria, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.nuova_categoria(conn, d.nome, d.descrizione)
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


class Attributi(BaseModel):
    valori: dict


@router.put("/contatti/{cid}/attributi")
def attributi(cid: int, d: Attributi, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"attributi": cm.imposta_attributi(conn, cid, d.valori, u["id"])}
        except ERRORI as e:
            raise _err(e) from None


class Assegna(BaseModel):
    categoria: str = Field(max_length=60)
    motivazione: str = Field(min_length=3, max_length=300)


@router.post("/contatti/{cid}/categorie", status_code=201)
def assegna(cid: int, d: Assegna, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.assegna_categoria(conn, cid, d.categoria, d.motivazione, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


@router.delete("/contatti/{cid}/categorie/{categoria}")
def togli(cid: int, categoria: str, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.togli_categoria(conn, cid, categoria, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


class Relazione(BaseModel):
    persona_id: int
    organizzazione_id: int
    ruolo: str | None = Field(default=None, max_length=120)
    dal: date | None = None
    al: date | None = None
    fonte: str | None = Field(default=None, max_length=300)


@router.post("/relazioni", status_code=201)
def relazione(d: Relazione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"id": cm.aggiungi_relazione(conn, d.model_dump(), u["id"])}
        except ERRORI as e:
            raise _err(e) from None


class Fine(BaseModel):
    al: date | None = None


@router.put("/relazioni/{rid}/termina")
def termina(rid: int, d: Fine, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.termina_relazione(conn, rid, d.al, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


@router.delete("/relazioni/{rid}")
def elimina_relazione(rid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.elimina_relazione(conn, rid)
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


class Recapito(BaseModel):
    tipo: str
    valore: str = Field(min_length=1, max_length=300)
    fonte: str | None = Field(default=None, max_length=300)
    verificato_il: date | None = None


@router.post("/contatti/{cid}/recapiti", status_code=201)
def recapito(cid: int, d: Recapito, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"id": cm.aggiungi_recapito(conn, cid, d.tipo, d.valore, d.fonte, d.verificato_il, u["id"])}
        except ERRORI as e:
            raise _err(e) from None


@router.delete("/recapiti/{rid}")
def togli_recapito(rid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.togli_recapito(conn, rid, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


class Fonte(BaseModel):
    fonte_editore: str | None = Field(default=None, max_length=300)
    fonte_licenza: str | None = Field(default=None, max_length=300)
    fonte_url: str | None = Field(default=None, max_length=300)
    fonte_data: date | None = None


@router.put("/contatti/{cid}/fonte")
def fonte(cid: int, d: Fonte, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.imposta_fonte(conn, cid, d.model_dump(exclude_unset=True), u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


class Verifica(BaseModel):
    nota: str | None = Field(default=None, max_length=300)


@router.post("/contatti/{cid}/verifica")
def verifica(cid: int, d: Verifica, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm.verifica(conn, cid, d.nota, u["id"])
        except ERRORI as e:
            raise _err(e) from None
    return {"ok": True}


@router.get("/contatti/{cid}/storico")
def storico(cid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cm._esiste(conn, cid)
            return {"storico": cm.elenco_storico(conn, cid)}
        except ERRORI as e:
            raise _err(e) from None
