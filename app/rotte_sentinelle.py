"""Casi di prova per agente e coda di proposte delle sentinelle."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import casi_prova, proposte_sentinelle
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione", tags=["sentinelle"])


@router.get("/prove/{agente_id}")
def stato_prove(agente_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        casi = conn.execute("SELECT id, richiesta, criteri, attivo, generato FROM casi_prova WHERE agente_id=%s ORDER BY id", (agente_id,)).fetchall()
        lotti = conn.execute("SELECT id, etichetta, stato, totale, fatti, media, errore, creato_il FROM prove_lotti WHERE agente_id=%s ORDER BY id DESC LIMIT 10", (agente_id,)).fetchall()
        return {"casi": casi, "lotti": [{**l, "media": float(l["media"]) if l["media"] is not None else None} for l in lotti], "confronto": casi_prova.confronto(conn, agente_id)}


class NuovoCaso(BaseModel):
    richiesta: str = Field(min_length=3, max_length=2000)
    criteri: str = Field(min_length=3, max_length=2000)


@router.post("/prove/{agente_id}/casi", status_code=201)
def aggiungi_caso(agente_id: int, d: NuovoCaso, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("SELECT count(*) AS n FROM casi_prova WHERE agente_id=%s AND attivo", (agente_id,)).fetchone()["n"] >= casi_prova.MAX_CASI:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Massimo {casi_prova.MAX_CASI} casi attivi")
        if conn.execute("SELECT 1 FROM agenti WHERE id=%s", (agente_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        return {"id": conn.execute("INSERT INTO casi_prova (agente_id, richiesta, criteri) VALUES (%s,%s,%s) RETURNING id", (agente_id, d.richiesta, d.criteri)).fetchone()["id"]}


class QuantiCasi(BaseModel):
    quanti: int = Field(default=10, ge=1, le=casi_prova.MAX_CASI)


@router.post("/prove/{agente_id}/genera")
def genera(agente_id: int, d: QuantiCasi, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"creati": casi_prova.genera_casi(conn, agente_id, d.quanti)}
        except casi_prova.ErroreProve as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Generazione non riuscita: " + str(e)[:160])


@router.put("/prove/casi/{caso_id}")
def attiva_caso(caso_id: int, attivo: bool, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("UPDATE casi_prova SET attivo=%s WHERE id=%s RETURNING id", (attivo, caso_id)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso inesistente")
    return {"stato": "ok"}


@router.delete("/prove/casi/{caso_id}")
def elimina_caso(caso_id: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("DELETE FROM casi_prova WHERE id=%s", (caso_id,))
    return {"stato": "ok"}


class Lancio(BaseModel):
    etichetta: str | None = Field(default=None, max_length=60)


@router.post("/prove/{agente_id}/lancia", status_code=202)
def lancia(agente_id: int, d: Lancio, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"lotto": casi_prova.avvia(conn, agente_id, d.etichetta)}
        except casi_prova.ErroreProve as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("/sentinelle/proposte")
def proposte(stato: str = "in_attesa", _: dict = Depends(solo_titolare)):
    if stato not in ("in_attesa", "approvata", "respinta"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stato non valido")
    with connessione() as conn:
        return conn.execute("""SELECT p.id, p.sentinella, p.tipo, p.titolo, p.motivazione, p.stato, p.creata_il, p.esito, a.nome AS agente
                               FROM proposte_sentinelle p LEFT JOIN agenti a ON a.id=p.agente_id WHERE p.stato=%s ORDER BY p.creata_il DESC LIMIT 100""", (stato,)).fetchall()


@router.post("/sentinelle/scansiona")
def scansiona(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return proposte_sentinelle.scansiona(conn)


class Decisione(BaseModel):
    approva: bool


@router.post("/sentinelle/proposte/{pid}/decisione")
def decidi(pid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return proposte_sentinelle.decidi(conn, pid, u["id"], d.approva)
        except LookupError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
