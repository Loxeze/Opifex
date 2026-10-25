"""Contatti (CRM): liste, importazione da CSV, riepilogo aggregato e ricerca. Solo titolare. Gli agenti non passano da qui: usano solo i conteggi."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from . import cassaforte, crm, registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/crm", tags=["crm"])
MAX_BYTE = 25 * 1024 * 1024


@router.get("/liste")
def liste(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"liste": conn.execute(
            """SELECT l.*, z.nome AS azienda, (SELECT count(*) FROM crm_contatti c WHERE c.lista_id = l.id) AS contatti
               FROM crm_liste l LEFT JOIN aziende z ON z.id = l.azienda_id ORDER BY l.id""").fetchall(),
            "aziende": conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall(), "minimo": crm.MINIMO}


class NuovaLista(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    fonte: str | None = Field(default=None, max_length=200)
    azienda_id: int | None = None
    natura: str = Field(pattern="^(pubblico|personale)$")
    base_giuridica: str | None = Field(default=None, max_length=200)


@router.post("/liste", status_code=201)
def crea(d: NuovaLista, u: dict = Depends(solo_titolare)):
    if d.natura == "personale" and not (d.base_giuridica or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Per i dati di persone indica la base giuridica (consenso, contratto, interesse legittimo…)")
    with connessione() as conn:
        r = conn.execute("INSERT INTO crm_liste (nome, fonte, azienda_id, natura, base_giuridica) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                         (d.nome.strip(), d.fonte, d.azienda_id, d.natura, d.base_giuridica)).fetchone()
        registro.registra(conn, u, "collegamento", "Lista contatti creata", d.nome, "crm_lista", r["id"], dettagli={"natura": d.natura})
    return {"id": r["id"]}


@router.post("/liste/{lid}/importa")
def importa(lid: int, file: UploadFile = File(...), u: dict = Depends(solo_titolare)):
    dati = file.file.read(MAX_BYTE + 1)
    if len(dati) > MAX_BYTE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File troppo grande (massimo 25 MB)")
    with connessione() as conn:
        try:
            esito = crm.importa_csv(conn, lid, dati)
        except crm.ErroreCrm as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
        except cassaforte.CassaforteNonConfigurata as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
        registro.registra(conn, u, "collegamento", "Contatti importati", f"lista {lid}", "crm_lista", lid, dettagli=esito)
    return esito


@router.delete("/liste/{lid}")
def elimina(lid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM crm_liste WHERE id = %s RETURNING nome", (lid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lista inesistente")
        registro.registra(conn, u, "collegamento", "Lista contatti eliminata", r["nome"], "crm_lista", lid)
    return {"ok": True}


@router.get("/riepilogo")
def riepilogo(per: str = "regione", u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return crm.conta(conn, {}, per, utente_id=u["id"])
        except crm.ErroreCrm as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None


@router.get("/cerca")
def cerca(q: str, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"risultati": crm.cerca(conn, q, u["id"])}
        except crm.ErroreCrm as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
        except cassaforte.CassaforteNonConfigurata as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
