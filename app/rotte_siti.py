"""Siti e hosting: schede con credenziali cifrate, prova di connessione, agenti autorizzati, modifiche da approvare. Solo titolare."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, siti_hosting
from .db import connessione
from .permessi import solo_titolare
from .registro import registra

router = APIRouter(prefix="/gestione/siti", tags=["siti"])


class Scheda(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    tipo: str
    url: str | None = Field(default=None, max_length=300)
    host: str | None = Field(default=None, max_length=253)
    porta: int | None = Field(default=None, ge=1, le=65535)
    utente: str | None = Field(default=None, max_length=200)
    segreto: str | None = Field(default=None, max_length=8000)   # vuoto in modifica = lascia quello attuale
    percorso_base: str = Field(default="/", max_length=300)
    produzione: bool = True
    note: str | None = Field(default=None, max_length=1000)
    attivo: bool = True


def _pubblica(r: dict, agenti: list[int]) -> dict:
    return {k: r[k] for k in ("id", "nome", "tipo", "url", "host", "porta", "utente", "percorso_base", "produzione", "note", "attivo", "ultima_prova", "esito_prova")} | {
        "ha_segreto": bool(r["segreto_cifrato"]), "impronta_host": r["impronta_host"], "agenti": agenti}


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        ag = {}
        for r in conn.execute("SELECT sito_id, agente_id FROM siti_agenti").fetchall():
            ag.setdefault(r["sito_id"], []).append(r["agente_id"])
        return {"siti": [_pubblica(r, ag.get(r["id"], [])) for r in conn.execute("SELECT * FROM siti_hosting ORDER BY nome").fetchall()],
                "attesa": conn.execute("SELECT count(*) AS n FROM siti_scritture WHERE stato='in_attesa'").fetchone()["n"],
                "accesso_totale": [r["id"] for r in conn.execute("SELECT id FROM agenti WHERE siti_tutti ORDER BY nome").fetchall()],
                "solo_custode": siti_hosting.solo_custode(conn),
                "custode": conn.execute("SELECT id, nome, attivo FROM agenti WHERE ruolo_speciale = 'custode' LIMIT 1").fetchone()}


def _pulisci(d: Scheda) -> dict:
    try:
        return siti_hosting.valida_scheda(d.model_dump())
    except siti_hosting.ErroreSito as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


def _cifra(seg: str | None):
    try:
        return cassaforte.cifra(seg) if seg else None
    except cassaforte.CassaforteNonConfigurata as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.post("", status_code=201)
def crea(d: Scheda, u: dict = Depends(solo_titolare)):
    c = _pulisci(d)
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM siti_hosting WHERE lower(nome) = lower(%s)", (c["nome"],)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un sito con questo nome")
        sid = conn.execute("""INSERT INTO siti_hosting (nome, tipo, url, host, porta, utente, segreto_cifrato, percorso_base, produzione, note, attivo)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (c["nome"], c["tipo"], c["url"], c["host"], c["porta"], c["utente"], _cifra(d.segreto), c["percorso_base"], c["produzione"], c["note"], d.attivo)).fetchone()["id"]
        registra(conn, u, "siti", "sito aggiunto", c["nome"], "siti_hosting", sid, "")
        return {"id": sid}


class SoloCustode(BaseModel):
    attivo: bool


@router.put("/solo-custode")
def imposta_solo_custode(d: SoloCustode, u: dict = Depends(solo_titolare)):
    """Acceso: solo il Maestro di chiavi opera sui siti. Spento: valgono le assegnazioni ai singoli agenti."""
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('siti_solo_custode', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", ("1" if d.attivo else "0",))
        registra(conn, u, "siti", "accesso ai siti solo al Maestro di chiavi" if d.attivo else "accesso ai siti per assegnazione ai singoli agenti", "Tutti i siti")
        return {"solo_custode": d.attivo}


class AccessoTotale(BaseModel):
    agenti: list[int]


@router.put("/accesso-totale")
def accesso_totale(d: AccessoTotale, u: dict = Depends(solo_titolare)):
    """Gli agenti indicati vedono tutti i siti salvati (compresi quelli aggiunti dopo), senza assegnarli uno per uno."""
    with connessione() as conn:
        conn.execute("UPDATE agenti SET siti_tutti = (id = ANY(%s))", (list(set(d.agenti)),))
        registra(conn, u, "siti", "agenti con accesso a tutti i siti aggiornati", "Tutti i siti", dettagli={"agenti": len(set(d.agenti))})
        return {"accesso_totale": [r["id"] for r in conn.execute("SELECT id FROM agenti WHERE siti_tutti").fetchall()]}


@router.put("/{sid}")
def modifica(sid: int, d: Scheda, u: dict = Depends(solo_titolare)):
    c = _pulisci(d)
    with connessione() as conn:
        att = conn.execute("SELECT host, porta, tipo FROM siti_hosting WHERE id = %s", (sid,)).fetchone()
        if att is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sito inesistente")
        if conn.execute("SELECT 1 FROM siti_hosting WHERE lower(nome) = lower(%s) AND id <> %s", (c["nome"], sid)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un sito con questo nome")
        # se cambia il server, l'impronta SSH fissata non vale piu'
        cambia_server = (att["host"], att["porta"], att["tipo"]) != (c["host"], c["porta"], c["tipo"])
        conn.execute("""UPDATE siti_hosting SET nome=%s, tipo=%s, url=%s, host=%s, porta=%s, utente=%s, percorso_base=%s, produzione=%s, note=%s, attivo=%s,
                        impronta_host = CASE WHEN %s THEN NULL ELSE impronta_host END WHERE id=%s""",
                     (c["nome"], c["tipo"], c["url"], c["host"], c["porta"], c["utente"], c["percorso_base"], c["produzione"], c["note"], d.attivo, cambia_server, sid))
        if d.segreto:
            conn.execute("UPDATE siti_hosting SET segreto_cifrato=%s, ultima_prova=NULL, esito_prova=NULL WHERE id=%s", (_cifra(d.segreto), sid))
        registra(conn, u, "siti", "sito modificato" + (" (segreto sostituito)" if d.segreto else ""), c["nome"], "siti_hosting", sid, "")
    return {"stato": "ok"}


@router.delete("/{sid}")
def elimina(sid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM siti_hosting WHERE id = %s RETURNING nome", (sid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sito inesistente")
        registra(conn, u, "siti", "sito eliminato", r["nome"], "siti_hosting", sid, "")
    return {"stato": "ok"}


@router.post("/{sid}/prova")
def prova(sid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return siti_hosting.prova(conn, sid)
        except siti_hosting.ErroreSito as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
        except cassaforte.CassaforteNonConfigurata as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.post("/{sid}/dimentica-impronta")
def dimentica_impronta(sid: int, _: dict = Depends(solo_titolare)):
    """Dopo un cambio di server voluto: alla prossima prova si fissa la nuova impronta."""
    with connessione() as conn:
        conn.execute("UPDATE siti_hosting SET impronta_host = NULL WHERE id = %s", (sid,))
    return {"stato": "ok"}


class Agenti(BaseModel):
    agenti: list[int]


@router.put("/{sid}/agenti")
def autorizza(sid: int, d: Agenti, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        s = conn.execute("SELECT nome FROM siti_hosting WHERE id = %s", (sid,)).fetchone()
        if s is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sito inesistente")
        conn.execute("DELETE FROM siti_agenti WHERE sito_id = %s", (sid,))
        for a in set(d.agenti):
            conn.execute("INSERT INTO siti_agenti (sito_id, agente_id) SELECT %s, id FROM agenti WHERE id = %s", (sid, a))
        registra(conn, u, "siti", "agenti autorizzati aggiornati", s["nome"], "siti_hosting", sid, f"{len(set(d.agenti))} agenti")
    return {"stato": "ok"}


@router.get("/scritture")
def scritture(stato: str = "in_attesa", _: dict = Depends(solo_titolare)):
    if stato not in ("in_attesa", "applicata", "respinta", "errore"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stato non valido")
    with connessione() as conn:
        return conn.execute("""SELECT w.id, s.nome AS sito, a.nome AS agente, w.percorso, w.motivo, w.stato, w.errore, w.creata_il, left(w.contenuto, 4000) AS contenuto, length(w.contenuto) AS lunghezza,
                                      left(w.precedente, 4000) AS precedente
                               FROM siti_scritture w JOIN siti_hosting s ON s.id = w.sito_id LEFT JOIN agenti a ON a.id = w.agente_id
                               WHERE w.stato = %s ORDER BY w.creata_il DESC LIMIT 50""", (stato,)).fetchall()


class Decisione(BaseModel):
    approva: bool


@router.post("/scritture/{wid}/decisione")
def decidi(wid: int, d: Decisione, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            if not d.approva:
                siti_hosting.respingi(conn, wid, u["id"])
                registra(conn, u, "siti", "modifica respinta", "", "siti_scritture", wid, "")
                return {"stato": "respinta"}
            r = siti_hosting.applica(conn, wid, u["id"])
            registra(conn, u, "siti", "modifica approvata" if r["stato"] == "applicata" else "modifica approvata ma non riuscita", "", "siti_scritture", wid, r.get("errore", ""))
            return r
        except siti_hosting.ErroreSito as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
        except cassaforte.CassaforteNonConfigurata as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
