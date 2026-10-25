"""Pagina «Memoria di lavoro»: proposte da approvare, voci approvate, inserimento manuale, modifica e cancellazione."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from . import memoria_lavoro, registro
from .db import connessione
from .permessi import divisioni_visibili, utente_corrente

router = APIRouter(prefix="/memoria", tags=["memoria"])
FASCE = ("pubblico", "interno", "riservato")


def _puo_approvare(conn, u: dict, divisione_id) -> bool:
    if u["ruolo_globale"] == "titolare":
        return True
    if divisione_id is None:
        return False
    return conn.execute("SELECT 1 FROM accessi_divisione WHERE utente_id = %s AND divisione_id = %s AND puo_approvare",
                        (u["id"], divisione_id)).fetchone() is not None


def _filtro(u: dict) -> tuple[str, list]:
    v = divisioni_visibili(u)
    if v is None:
        return "TRUE", []
    return "m.divisione_id = ANY(%s)", [list(v)]


CAMPI = """m.id, m.testo, m.tipo, m.stato, m.fascia_dati, m.azienda_id, m.progetto_id, m.divisione_id, m.fonte, m.sostituisce_id, m.creata_il, m.decisa_il,
           z.nome AS azienda, p.nome AS progetto, d.nome AS divisione, ag.nome AS proposta_da_agente, pu.nome AS proposta_da_utente, du.nome AS decisa_da"""
DA = """FROM memorie_lavoro m LEFT JOIN aziende z ON z.id = m.azienda_id LEFT JOIN progetti p ON p.id = m.progetto_id
        LEFT JOIN divisioni d ON d.id = m.divisione_id LEFT JOIN agenti ag ON ag.id = m.proposta_da_agente_id
        LEFT JOIN utenti pu ON pu.id = m.proposta_da_utente_id LEFT JOIN utenti du ON du.id = m.decisa_da_utente_id"""


@router.get("")
def elenco(stato: str = Query(default="proposta", pattern="^(proposta|approvata|scartata|superata|tutte)$"), q: str = Query(default="", max_length=100),
           u: dict = Depends(utente_corrente)):
    cond, par = _filtro(u)
    with connessione() as conn:
        righe = conn.execute(
            f"""SELECT {CAMPI} {DA} WHERE {cond} AND (%s = 'tutte' OR m.stato = %s) AND (%s = '' OR m.testo ILIKE '%%' || %s || '%%')
                ORDER BY m.id DESC LIMIT 300""", par + [stato, stato, q.strip(), q.strip()]).fetchall()
        for r in righe:
            r["puo_approvare"] = _puo_approvare(conn, u, r["divisione_id"])
        n = conn.execute(f"SELECT count(*) AS n FROM memorie_lavoro m WHERE {cond} AND m.stato = 'proposta'", par).fetchone()["n"]
        opz = {"aziende": conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall(),
               "progetti": conn.execute("SELECT id, nome FROM progetti WHERE NOT archiviato ORDER BY nome").fetchall(),
               "divisioni": conn.execute("SELECT id, nome FROM divisioni WHERE attiva ORDER BY nome").fetchall()}
        v = divisioni_visibili(u)
        if v is not None:
            opz["divisioni"] = [d for d in opz["divisioni"] if d["id"] in v]
    return {"voci": righe, "proposte": n, "opzioni": opz, "tipi": list(memoria_lavoro.TIPI)}


class Nuova(BaseModel):
    testo: str = Field(min_length=3, max_length=1200)
    tipo: str = "decisione"
    fascia_dati: str = "interno"
    azienda_id: int | None = None
    progetto_id: int | None = None
    divisione_id: int | None = None
    sostituisce_id: int | None = None


@router.post("", status_code=201)
def crea(d: Nuova, u: dict = Depends(utente_corrente)):
    """Inserimento diretto: la voce nasce gia' approvata (la scrive una persona autorizzata)."""
    with connessione() as conn:
        if not _puo_approvare(conn, u, d.divisione_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi registrare memoria per questo ambito (le voci generali le gestisce il titolare)")
        try:
            mid = memoria_lavoro.proponi(conn, d.testo, d.tipo, azienda_id=d.azienda_id, progetto_id=d.progetto_id, divisione_id=d.divisione_id,
                                         fascia_dati=d.fascia_dati, fonte="inserita da " + u["nome"], utente_id=u["id"], stato="approvata",
                                         decisa_da=u["id"], sostituisce_id=d.sostituisce_id)
        except memoria_lavoro.MemoriaNonValida as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        registro.registra(conn, u, "memoria", "voce registrata", d.testo[:200], "memoria", mid)
    return {"id": mid}


class Decisione(BaseModel):
    azione: str = Field(pattern="^(approva|scarta)$")
    testo: str | None = Field(default=None, min_length=3, max_length=1200)   # correzione prima di approvare


@router.post("/{mid}/decisione")
def decidi(mid: int, d: Decisione, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        m = conn.execute("SELECT * FROM memorie_lavoro WHERE id = %s", (mid,)).fetchone()
        v = divisioni_visibili(u)
        if m is None or (v is not None and m["divisione_id"] not in v):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Voce inesistente")
        if not _puo_approvare(conn, u, m["divisione_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi decidere su questa voce")
        if m["stato"] != "proposta":
            raise HTTPException(status.HTTP_409_CONFLICT, "La voce e' gia' stata decisa")
        testo = m["testo"]
        if d.azione == "approva" and d.testo:
            try:
                testo = memoria_lavoro.pulisci(d.testo)
            except memoria_lavoro.MemoriaNonValida as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        nuovo = "approvata" if d.azione == "approva" else "scartata"
        conn.execute("UPDATE memorie_lavoro SET stato = %s, testo = %s, decisa_da_utente_id = %s, decisa_il = NOW() WHERE id = %s AND stato = 'proposta'",
                     (nuovo, testo, u["id"], mid))
        if nuovo == "approvata" and m["sostituisce_id"]:
            conn.execute("UPDATE memorie_lavoro SET stato = 'superata' WHERE id = %s AND stato = 'approvata'", (m["sostituisce_id"],))
        registro.registra(conn, u, "memoria", "voce approvata" if nuovo == "approvata" else "voce scartata", testo[:200], "memoria", mid,
                          "" if testo == m["testo"] else "testo corretto prima dell'approvazione")
    return {"stato": nuovo}


class Modifica(BaseModel):
    testo: str | None = Field(default=None, min_length=3, max_length=1200)
    tipo: str | None = None
    fascia_dati: str | None = None


@router.put("/{mid}")
def modifica(mid: int, d: Modifica, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        m = conn.execute("SELECT * FROM memorie_lavoro WHERE id = %s", (mid,)).fetchone()
        v = divisioni_visibili(u)
        if m is None or (v is not None and m["divisione_id"] not in v):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Voce inesistente")
        if not _puo_approvare(conn, u, m["divisione_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi modificare questa voce")
        if d.tipo is not None and d.tipo not in memoria_lavoro.TIPI:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo non valido")
        if d.fascia_dati is not None and d.fascia_dati not in FASCE:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Riservatezza non valida")
        try:
            testo = memoria_lavoro.pulisci(d.testo) if d.testo is not None else m["testo"]
        except memoria_lavoro.MemoriaNonValida as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        conn.execute("UPDATE memorie_lavoro SET testo = %s, tipo = %s, fascia_dati = %s WHERE id = %s",
                     (testo, d.tipo or m["tipo"], d.fascia_dati or m["fascia_dati"], mid))
        registro.registra(conn, u, "memoria", "voce modificata", testo[:200], "memoria", mid)
    return {"stato": "ok"}


@router.delete("/{mid}")
def elimina(mid: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        m = conn.execute("SELECT testo, divisione_id FROM memorie_lavoro WHERE id = %s", (mid,)).fetchone()
        v = divisioni_visibili(u)
        if m is None or (v is not None and m["divisione_id"] not in v):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Voce inesistente")
        if not _puo_approvare(conn, u, m["divisione_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Non puoi cancellare questa voce")
        conn.execute("DELETE FROM memorie_lavoro WHERE id = %s", (mid,))
        registro.registra(conn, u, "memoria", "voce cancellata", m["testo"][:200], "memoria", mid)
    return {"stato": "ok"}
