"""Progetti (cartelle su Drive) e account Google collegati. Solo titolare, tranne il ritorno di Google."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import google
from .db import connessione
from .permessi import solo_titolare

router = APIRouter()


def _err(e: Exception):
    return HTTPException(status.HTTP_409_CONFLICT, str(e))


# ---------- Account Google ----------
@router.get("/gestione/google")
def stato_google(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        s = google.stato(conn)
        s["esito"] = google._leggi(conn, "google_ultimo_esito")
        return s


class Client(BaseModel):
    client_id: str = Field(min_length=10, max_length=300)
    client_secret: str | None = Field(default=None, max_length=300)   # mai restituito


@router.put("/gestione/google/client")
def imposta_client(d: Client, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        google.imposta_client(conn, d.client_id, d.client_secret)
    return {"ok": True}


class Collega(BaseModel):
    etichetta: str = Field(min_length=1, max_length=60)
    servizi: list[str]


@router.post("/gestione/google/autorizza")
def autorizza(d: Collega, _: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            google._scrivi(conn, "google_ultimo_esito", "")
            return {"url": google.url_autorizzazione(conn, d.etichetta, d.servizi)}
    except google.ErroreGoogle as e:
        raise _err(e)


@router.get("/gestione/google/callback", include_in_schema=False)
def ritorno(code: str | None = Query(default=None, max_length=2000), state: str | None = Query(default=None, max_length=200),
            error: str | None = Query(default=None, max_length=100)):
    """Pagina aperta da Google dopo il consenso. Non serve l'accesso: vale lo stato monouso creato dal titolare."""
    with connessione() as conn:
        if error or not code or not state:
            google._scrivi(conn, "google_ultimo_esito", "Collegamento annullato o rifiutato da Google.")
        else:
            try:
                r = google.completa_autorizzazione(conn, code, state)
                google._scrivi(conn, "google_ultimo_esito", "ok:" + r["email"])
            except google.ErroreGoogle as e:
                google._scrivi(conn, "google_ultimo_esito", str(e))
    return RedirectResponse("/app/", status_code=303)


@router.delete("/gestione/google/account/{aid}")
def scollega(aid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        google.scollega(conn, aid)
    return {"ok": True}


@router.post("/gestione/google/account/{aid}/prova")
def prova(aid: int, _: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            return {"esito": google.prova(conn, aid)}
    except google.ErroreGoogle as e:
        raise _err(e)


class ScelteDrive(BaseModel):
    account_id: int | None = None
    radice_id: str | None = Field(default=None, max_length=200, pattern=r"^[A-Za-z0-9_-]*$")


@router.put("/gestione/google/drive")
def scelte_drive(d: ScelteDrive, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if d.account_id is not None:
            if d.account_id and not conn.execute("SELECT 1 FROM account_google WHERE id=%s AND 'drive'=ANY(servizi)", (d.account_id,)).fetchone():
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'account scelto non ha il permesso Drive")
            google._scrivi(conn, "drive_account_id", str(d.account_id or ""))
        if d.radice_id is not None:
            google._scrivi(conn, "drive_radice_id", d.radice_id)
    return {"ok": True}


# ---------- Progetti ----------
def _elenco(conn):
    righe = conn.execute("""SELECT p.id, p.nome, p.descrizione, p.archiviato, p.drive_cartella_id, p.drive_stato, p.drive_errore, p.creato_il,
                                   COALESCE((SELECT array_agg(agente_id ORDER BY agente_id) FROM progetti_agenti WHERE progetto_id=p.id), '{}') AS agenti
                            FROM progetti p ORDER BY p.archiviato, p.id""").fetchall()
    for r in righe:
        r["drive_url"] = "https://drive.google.com/drive/folders/" + r["drive_cartella_id"] if r["drive_cartella_id"] else None
    return righe


@router.get("/gestione/progetti")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        agenti = conn.execute("SELECT id, nome, ruolo FROM agenti WHERE attivo ORDER BY id").fetchall()
        return {"progetti": _elenco(conn), "agenti": agenti, "drive_pronto": bool(google._leggi(conn, "drive_account_id"))}


class NuovoProgetto(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    descrizione: str = Field(default="", max_length=500)
    agenti: list[int] | None = None   # vuoto/assente = tutti gli agenti attivi


def _imposta_agenti(conn, pid: int, ids: list[int] | None):
    attivi = {r["id"] for r in conn.execute("SELECT id FROM agenti WHERE attivo").fetchall()}
    scelti = attivi if not ids else set(ids)
    if not scelti <= attivi:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Agente inesistente o spento")
    conn.execute("DELETE FROM progetti_agenti WHERE progetto_id=%s AND NOT agente_id = ANY(%s)", (pid, list(scelti)))
    for a in scelti:
        conn.execute("INSERT INTO progetti_agenti (progetto_id, agente_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (pid, a))


@router.post("/gestione/progetti", status_code=201)
def crea(d: NuovoProgetto, _: dict = Depends(solo_titolare)):
    nome = " ".join(d.nome.split())
    if "/" in nome or "\\" in nome:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il nome non puo' contenere / o \\")
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM progetti WHERE lower(nome)=lower(%s)", (nome,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un progetto con questo nome")
        pid = conn.execute("INSERT INTO progetti (nome, descrizione) VALUES (%s,%s) RETURNING id", (nome, d.descrizione.strip())).fetchone()["id"]
        _imposta_agenti(conn, pid, d.agenti)
        esito = google.sincronizza_progetto(conn, pid) if google._leggi(conn, "drive_account_id") else \
            {"ok": False, "errore": "Cartelle Drive non ancora create: collega un account Google con Drive nella scheda Collegamenti"}
    return {"id": pid, "drive": esito}


@router.post("/gestione/progetti/{pid}/sincronizza")
def sincronizza(pid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM progetti WHERE id=%s", (pid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        return google.sincronizza_progetto(conn, pid)


class AgentiProgetto(BaseModel):
    agenti: list[int]


@router.put("/gestione/progetti/{pid}/agenti")
def agenti(pid: int, d: AgentiProgetto, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM progetti WHERE id=%s", (pid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        _imposta_agenti(conn, pid, d.agenti)
        conn.execute("UPDATE progetti SET drive_stato='da_sincronizzare' WHERE id=%s AND drive_stato='ok'", (pid,))
    return {"ok": True}


class Archivia(BaseModel):
    archiviato: bool


@router.put("/gestione/progetti/{pid}/archivia")
def archivia(pid: int, d: Archivia, _: dict = Depends(solo_titolare)):
    """Il progetto si archivia soltanto: le cartelle su Drive non vengono mai cancellate dalla piattaforma."""
    with connessione() as conn:
        if not conn.execute("UPDATE progetti SET archiviato=%s WHERE id=%s RETURNING 1", (d.archiviato, pid)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
    return {"ok": True}
