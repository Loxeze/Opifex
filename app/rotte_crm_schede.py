"""CRM: schede dei contatti, interazioni, opportunita', pipeline e promemoria. Solo titolare."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, crm_modello, crm_schede as cs, registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/crm", tags=["crm"])


def _err(e: Exception):
    if isinstance(e, LookupError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    if isinstance(e, cassaforte.CassaforteNonConfigurata):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/contatti")
def elenco(q: str = "", filtro: str = "", u: dict = Depends(solo_titolare)):
    if filtro not in ("", "da_ricontattare", "mai_contattati", "con_opportunita"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Filtro non valido")
    with connessione() as conn:
        try:
            r = cs.elenco(conn, q, filtro, u["id"])
        except (cs.ErroreScheda, cassaforte.CassaforteNonConfigurata) as e:
            raise _err(e) from None
        r["aziende"] = conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall()
        r["utenti"] = conn.execute("SELECT id, nome FROM utenti WHERE attivo ORDER BY nome").fetchall()
        return r


class Contatto(BaseModel):
    nome: str | None = Field(default=None, max_length=200)
    ente: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=5000)
    tipo: str | None = Field(default=None, max_length=40)
    regione: str | None = Field(default=None, max_length=60)
    provincia: str | None = Field(default=None, max_length=60)
    settore: str | None = Field(default=None, max_length=80)
    comune: str | None = Field(default=None, max_length=100)
    genere: str | None = Field(default=None, max_length=20)
    attributi: dict | None = None
    azienda_id: int | None = None


@router.post("/contatti", status_code=201)
def crea(d: Contatto, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            i = cs.crea(conn, d.model_dump(), u["id"])
        except (cs.ErroreScheda, cassaforte.CassaforteNonConfigurata) as e:
            raise _err(e) from None
        registro.registra(conn, u, "collegamento", "Contatto CRM creato", f"contatto {i}", "crm_contatto", i)
    return {"id": i}


class Modifica(Contatto):
    relazione: str | None = Field(default=None, max_length=40)
    prossimo_passo: str | None = Field(default=None, max_length=300)
    prossimo_passo_il: date | None = None
    responsabile_utente_id: int | None = None


@router.get("/contatti/{cid}")
def apri(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            r = cs.scheda(conn, cid, u["id"])
        except (LookupError, cassaforte.CassaforteNonConfigurata) as e:
            raise _err(e) from None
        r["categorie_ammesse"] = crm_modello.categorie(conn)
        altro = "persona" if r["modello"]["genere"] == "organizzazione" else "organizzazione"
        r["possibili_relazioni"] = [{"id": x["id"], "nome": cassaforte.decifra(x["nome_cifrato"]) if altro == "persona" and x["nome_cifrato"] else (cassaforte.decifra(x["ente_cifrato"]) if x["ente_cifrato"] else cassaforte.decifra(x["nome_cifrato"]))}
                                    for x in conn.execute("SELECT id, nome_cifrato, ente_cifrato FROM crm_contatti WHERE genere = %s AND id <> %s AND (nome_cifrato IS NOT NULL OR ente_cifrato IS NOT NULL) ORDER BY id DESC LIMIT 1500", (altro, cid)).fetchall()]
        r["progetti"] = conn.execute("SELECT id, nome FROM progetti WHERE eliminato_il IS NULL ORDER BY nome").fetchall()
        r["aziende"] = conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall()
        r["utenti"] = conn.execute("SELECT id, nome FROM utenti WHERE attivo ORDER BY nome").fetchall()
        return r


@router.put("/contatti/{cid}")
def modifica(cid: int, d: Modifica, u: dict = Depends(solo_titolare)):
    campi = d.model_dump(exclude_unset=True)
    with connessione() as conn:
        try:
            cs.modifica(conn, cid, {k: v for k, v in campi.items() if k != 'attributi'}, u['id'])
            if campi.get('attributi'):
                crm_modello.imposta_attributi(conn, cid, campi['attributi'], u['id'])
        except (cs.ErroreScheda, crm_modello.ErroreModello, LookupError, cassaforte.CassaforteNonConfigurata) as e:
            raise _err(e) from None
        registro.registra(conn, u, "collegamento", "Contatto CRM modificato", f"contatto {cid}", "crm_contatto", cid, dettagli={"campi": sorted(campi)})
    return {"ok": True}


@router.delete("/contatti/{cid}")
def elimina(cid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("DELETE FROM crm_contatti WHERE id = %s RETURNING id", (cid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Contatto inesistente")
        registro.registra(conn, u, "collegamento", "Contatto CRM eliminato", f"contatto {cid}", "crm_contatto", cid)
    return {"ok": True}


class Interazione(BaseModel):
    canale: str
    direzione: str = "uscita"
    esito: str = "altro"
    oggetto: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=5000)
    quando: datetime | None = None
    progetto_id: int | None = None


@router.post("/contatti/{cid}/interazioni", status_code=201)
def interazione(cid: int, d: Interazione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            i = cs.nuova_interazione(conn, cid, d.model_dump(exclude_none=True), utente_id=u["id"])
        except (cs.ErroreScheda, LookupError, cassaforte.CassaforteNonConfigurata) as e:
            raise _err(e) from None
    return {"id": i}


@router.delete("/interazioni/{iid}")
def elimina_interazione(iid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("DELETE FROM crm_interazioni WHERE id = %s RETURNING id", (iid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Interazione inesistente")
    return {"ok": True}


class Opportunita(BaseModel):
    titolo: str = Field(min_length=3, max_length=200)
    tipo: str = "altro"
    stato: str = "nuova"
    valore_euro: float | None = Field(default=None, ge=0)
    azienda_id: int | None = None
    progetto_id: int | None = None
    responsabile_utente_id: int | None = None
    prossima_azione: str | None = Field(default=None, max_length=300)
    scadenza: date | None = None
    note: str | None = Field(default=None, max_length=5000)


@router.post("/contatti/{cid}/opportunita", status_code=201)
def nuova_opp(cid: int, d: Opportunita, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            i = cs.nuova_opportunita(conn, cid, d.model_dump())
        except (cs.ErroreScheda, LookupError, cassaforte.CassaforteNonConfigurata) as e:
            raise _err(e) from None
        registro.registra(conn, u, "collegamento", "Opportunità CRM creata", d.titolo[:100], "crm_opportunita", i)
    return {"id": i}


class ModificaOpp(BaseModel):
    titolo: str | None = Field(default=None, min_length=3, max_length=200)
    tipo: str | None = None
    stato: str | None = None
    valore_euro: float | None = Field(default=None, ge=0)
    azienda_id: int | None = None
    progetto_id: int | None = None
    responsabile_utente_id: int | None = None
    prossima_azione: str | None = Field(default=None, max_length=300)
    scadenza: date | None = None
    note: str | None = Field(default=None, max_length=5000)


@router.put("/opportunita/{oid}")
def modifica_opp(oid: int, d: ModificaOpp, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            cs.modifica_opportunita(conn, oid, d.model_dump(exclude_unset=True))
        except (cs.ErroreScheda, LookupError, cassaforte.CassaforteNonConfigurata) as e:
            raise _err(e) from None
        registro.registra(conn, u, "collegamento", "Opportunità CRM aggiornata", f"opportunità {oid}", "crm_opportunita", oid, dettagli=d.model_dump(exclude_unset=True, include={"stato"}))
    return {"ok": True}


@router.delete("/opportunita/{oid}")
def elimina_opp(oid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("DELETE FROM crm_opportunita WHERE id = %s RETURNING id", (oid,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunità inesistente")
        registro.registra(conn, u, "collegamento", "Opportunità CRM eliminata", f"opportunità {oid}", "crm_opportunita", oid)
    return {"ok": True}


@router.get("/pipeline")
def pipeline(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return cs.pipeline(conn, u["id"])
        except cassaforte.CassaforteNonConfigurata as e:
            raise _err(e) from None
