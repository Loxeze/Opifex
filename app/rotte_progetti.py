"""Progetti (cartelle su Drive) e account Google collegati. Solo titolare, tranne il ritorno di Google."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import google, pm, registro
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
    righe = conn.execute("""SELECT p.id, p.nome, p.descrizione, p.allineamento, p.allineamento_il, p.archiviato, p.drive_cartella_id, p.drive_stato, p.drive_errore, p.creato_il,
                                   p.azienda_id, z.nome AS azienda, z.colore AS azienda_colore, COALESCE(p.colore, z.colore) AS colore, p.colore AS colore_proprio, p.eliminato_il,
                                   COALESCE((SELECT array_agg(agente_id ORDER BY agente_id) FROM progetti_agenti WHERE progetto_id=p.id), '{}') AS agenti,
                                   (SELECT count(*) FROM task t WHERE t.progetto_id = p.id) AS n_task
                            FROM progetti p LEFT JOIN aziende z ON z.id = p.azienda_id ORDER BY p.eliminato_il NULLS FIRST, p.archiviato, z.nome, p.id""").fetchall()
    for r in righe:
        r["drive_url"] = "https://drive.google.com/drive/folders/" + r["drive_cartella_id"] if r["drive_cartella_id"] else None
    return righe


@router.get("/gestione/progetti")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        agenti = conn.execute("SELECT id, nome, ruolo FROM agenti WHERE attivo ORDER BY id").fetchall()
        return {"progetti": _elenco(conn), "agenti": agenti, "aziende": conn.execute("SELECT id, nome, colore FROM aziende WHERE attiva ORDER BY nome").fetchall(),
                "drive_pronto": bool(google._leggi(conn, "drive_account_id"))}


class NuovoProgetto(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    descrizione: str = Field(default="", max_length=500)
    azienda_id: int
    colore: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    agenti: list[int] | None = None   # vuoto/assente = tutti gli agenti attivi


def _imposta_agenti(conn, pid: int, ids: list[int] | None):
    attivi = {r["id"] for r in conn.execute("SELECT id FROM agenti WHERE attivo").fetchall()}
    altri_pm = {r["pm_agente_id"] for r in conn.execute("SELECT pm_agente_id FROM progetti WHERE pm_agente_id IS NOT NULL AND id <> %s", (pid,)).fetchall()}
    scelti = (attivi - altri_pm) if not ids else set(ids)   # di default tutti, tranne i project manager degli altri progetti
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
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un progetto con questo nome (anche tra gli eliminati)")
        if not conn.execute("SELECT 1 FROM aziende WHERE id=%s AND attiva", (d.azienda_id,)).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli l'impresa a cui appartiene il progetto")
        pid = conn.execute("INSERT INTO progetti (nome, descrizione, azienda_id, colore) VALUES (%s,%s,%s,%s) RETURNING id",
                           (nome, d.descrizione.strip(), d.azienda_id, d.colore)).fetchone()["id"]
        _imposta_agenti(conn, pid, d.agenti)
        if pm.abilitato():
            pm.crea_per(conn, pid)
        esito = google.sincronizza_progetto(conn, pid) if google._leggi(conn, "drive_account_id") else \
            {"ok": False, "errore": "Cartelle Drive non ancora create: collega un account Google con Drive nella scheda Collegamenti"}
    return {"id": pid, "drive": esito}


class ModificaProgetto(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    descrizione: str = Field(default="", max_length=500)
    allineamento: str = Field(default="", max_length=20000)
    azienda_id: int | None = None
    colore: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")
    azzera_colore: bool = False


@router.put("/gestione/progetti/{pid}")
def modifica(pid: int, d: ModificaProgetto, _: dict = Depends(solo_titolare)):
    """Cambia nome, descrizione e documento di allineamento. Se il nome cambia, rinomina anche la cartella su Drive."""
    nome = " ".join(d.nome.split())
    if "/" in nome or "\\" in nome:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il nome non puo' contenere / o \\")
    with connessione() as conn:
        p = conn.execute("SELECT * FROM progetti WHERE id=%s", (pid,)).fetchone()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        if conn.execute("SELECT 1 FROM progetti WHERE lower(nome)=lower(%s) AND id<>%s", (nome, pid)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un progetto con questo nome")
        if d.azienda_id is not None and not conn.execute("SELECT 1 FROM aziende WHERE id=%s AND attiva", (d.azienda_id,)).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Impresa inesistente o spenta")
        conn.execute("UPDATE progetti SET azienda_id = COALESCE(%s, azienda_id), colore = CASE WHEN %s THEN NULL ELSE COALESCE(%s, colore) END WHERE id=%s",
                     (d.azienda_id, d.azzera_colore, d.colore, pid))
        cambia_al = d.allineamento.strip() != (p["allineamento"] or "")
        conn.execute("""UPDATE progetti SET nome=%s, descrizione=%s, allineamento=%s,
                        allineamento_il = CASE WHEN %s THEN NOW() ELSE allineamento_il END WHERE id=%s""",
                     (nome, d.descrizione.strip(), d.allineamento.strip(), cambia_al, pid))
        pm.rinomina(conn, pid)
        drive = None
        if nome != p["nome"] and p["drive_cartella_id"]:
            try:
                account = int(google._leggi(conn, "drive_account_id") or 0)
                if not account:
                    raise google.ErroreGoogle("nessun account Drive collegato")
                google.rinomina_cartella(google.token_accesso(conn, account), p["drive_cartella_id"], nome)
                drive = {"ok": True}
            except google.ErroreGoogle as e:
                drive = {"ok": False, "errore": "Progetto rinominato qui, ma la cartella su Drive non e' stata rinominata: " + str(e)}
    return {"ok": True, "drive": drive}


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
        if not conn.execute("UPDATE progetti SET archiviato=%s, eliminato_il = CASE WHEN %s THEN eliminato_il END WHERE id=%s RETURNING 1", (d.archiviato, d.archiviato, pid)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
    return {"ok": True}


@router.delete("/gestione/progetti/{pid}")
def elimina(pid: int, u: dict = Depends(solo_titolare)):
    """«Elimina» toglie il progetto dalla vista e lo archivia: task, memoria, agenti e cartelle su Drive restano dove sono. Si recupera da «Eliminati»."""
    with connessione() as conn:
        p = conn.execute("SELECT nome FROM progetti WHERE id=%s AND eliminato_il IS NULL", (pid,)).fetchone()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        conn.execute("UPDATE progetti SET archiviato = TRUE, eliminato_il = NOW() WHERE id=%s", (pid,))
        registro.registra(conn, u, "organizzazione", "progetto eliminato (recuperabile)", p["nome"][:150], "progetto", pid)
    return {"ok": True}


@router.post("/gestione/progetti/{pid}/recupera")
def recupera(pid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = conn.execute("SELECT nome FROM progetti WHERE id=%s AND eliminato_il IS NOT NULL", (pid,)).fetchone()
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Questo progetto non e' tra gli eliminati")
        conn.execute("UPDATE progetti SET archiviato = FALSE, eliminato_il = NULL WHERE id=%s", (pid,))
        registro.registra(conn, u, "organizzazione", "progetto recuperato", p["nome"][:150], "progetto", pid)
    return {"ok": True}
