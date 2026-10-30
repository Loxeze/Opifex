"""Giro di aggiornamento: ogni tanto Aurora e i manager (a nome anche dei loro sottoposti) pongono a Lorenzo poche domande brevissime sulle strutture e sui
progetti (relazioni con un ente, livello di sviluppo di un progetto...). Le risposte diventano fatti condivisi che tutti gli agenti ricevono nel contesto."""
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/giro", tags=["giro"])
SINCRONO = False
MAX_DOMANDE_PER_AGENTE = 2
MAX_DOMANDE_GIRO = 12
SCADENZA_GIORNI = 3
FATTI_IN_CONTESTO = 12
FATTI_PERTINENTI = 6


class ErroreGiro(Exception):
    pass


def _imp(conn, chiave: str, default: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return r["valore"] if r else default


def giorni(conn) -> int:
    try:
        return max(0, min(90, int(_imp(conn, "giro_giorni", "7"))))
    except ValueError:
        return 7


def aperto(conn):
    return conn.execute("SELECT * FROM giri_aggiornamento WHERE stato = 'aperto' ORDER BY id DESC LIMIT 1").fetchone()


def chiudi_se_finito(conn, gid: int):
    if not conn.execute("SELECT 1 FROM domande_giro WHERE giro_id = %s AND stato = 'attesa'", (gid,)).fetchone():
        conn.execute("UPDATE giri_aggiornamento SET stato = 'chiuso', chiuso_il = NOW() WHERE id = %s AND stato = 'aperto'", (gid,))


def giro(conn):
    """Dal lavoro di fondo: chiude i giri dimenticati e, se e' ora, ne avvia uno nuovo."""
    conn.execute("UPDATE domande_giro SET stato = 'saltata' WHERE stato = 'attesa' AND giro_id IN (SELECT id FROM giri_aggiornamento WHERE stato = 'aperto' AND creato_il < NOW() - make_interval(days => %s))", (SCADENZA_GIORNI,))
    conn.execute("UPDATE giri_aggiornamento SET stato = 'chiuso', chiuso_il = NOW() WHERE stato = 'aperto' AND creato_il < NOW() - make_interval(days => %s)", (SCADENZA_GIORNI,))
    g = giorni(conn)
    if g == 0 or aperto(conn):
        return
    ultimo = conn.execute("SELECT creato_il > NOW() - make_interval(days => %s) AS recente FROM giri_aggiornamento ORDER BY id DESC LIMIT 1", (g,)).fetchone()
    if ultimo and ultimo["recente"]:
        return
    conn.commit()
    try:
        avvia(conn, "automatico")
    except ErroreGiro:
        pass   # nessuna domanda utile oggi: riprova al prossimo giro


def _fatti_testo(conn) -> str:
    return "\n".join("- " + r["testo"] for r in conn.execute("SELECT testo FROM fatti_condivisi WHERE attivo ORDER BY id DESC LIMIT 30").fetchall()) or "(nessuno ancora)"


def _prompt(a: dict, noti: str, gia: str) -> str:
    return (f"Sei {a['nome']} ({a['ruolo']}). Fai il giro di aggiornamento con Lorenzo, che ha poco tempo. Raccogli i dubbi tuoi e di chi lavora con te e scegli al massimo "
            f"{MAX_DOMANDE_PER_AGENTE} domande BREVISSIME (massimo 15 parole l'una, risposta in una frase) su cose che non sai o non sei sicuro di sapere nel tuo ambito: "
            "che relazione c'e' con un certo ente o persona, a che punto e' un progetto, chi decide, quale scadenza vale. Non chiedere cio' che e' gia' scritto nei tuoi documenti, "
            "nelle schede o tra i fatti noti, e non ripetere domande gia' poste.\n\nFatti gia' noti:\n" + noti + "\n\nDomande gia' poste di recente:\n" + gia +
            "\n\nRispondi solo con le domande, una per riga, ognuna che finisce con «?». Se non hai davvero nulla da chiedere rispondi esattamente: NESSUNA")


def _estrai(testo: str) -> list[str]:
    out = []
    for riga in str(testo or "").splitlines():
        riga = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", riga).strip()
        if riga.endswith("?") and 8 <= len(riga) <= 200 and riga.lower() not in (x.lower() for x in out):
            out.append(riga)
    return out[:MAX_DOMANDE_PER_AGENTE]


def avvia(conn, origine: str = "manuale") -> int:
    from .esecuzione import esegui_agente
    if aperto(conn):
        raise ErroreGiro("C'e' gia' un giro aperto: rispondi alle domande o saltale")
    chi = conn.execute("""SELECT id, nome, ruolo FROM agenti WHERE attivo AND ruolo_speciale IS NULL AND NOT COALESCE(sentinella, FALSE)
                          AND (nome = 'Aurora' OR livello = 'manager') ORDER BY (nome = 'Aurora') DESC, id LIMIT 8""").fetchall()
    if not chi:
        raise ErroreGiro("Non ci sono manager attivi a cui far fare domande")
    noti = _fatti_testo(conn)
    gia = "\n".join("- " + r["domanda"] for r in conn.execute("SELECT domanda FROM domande_giro ORDER BY id DESC LIMIT 40").fetchall()) or "(nessuna)"
    nuove = []
    for a in chi:
        if len(nuove) >= MAX_DOMANDE_GIRO:
            break
        try:
            ris = esegui_agente(a["id"], _prompt(a, noti, gia), "interno", None, max_token=400)
        except Exception:  # noqa: BLE001 - un manager che non risponde non ferma il giro
            continue
        for d in _estrai(ris.get("risposta", "")):
            if d.lower() not in (x[1].lower() for x in nuove) and d.lower() not in gia.lower():
                nuove.append((a["id"], d))
    if not nuove:
        raise ErroreGiro("Nessuna domanda nuova: gli agenti non hanno dubbi in questo momento")
    gid = conn.execute("INSERT INTO giri_aggiornamento (origine) VALUES (%s) RETURNING id", (origine,)).fetchone()["id"]
    for aid, d in nuove[:MAX_DOMANDE_GIRO]:
        conn.execute("INSERT INTO domande_giro (giro_id, agente_id, domanda) VALUES (%s,%s,%s)", (gid, aid, d))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Giro di aggiornamento: {len(nuove[:MAX_DOMANDE_GIRO])} domande brevi per te (Sistema → Giro di aggiornamento).",))
    conn.commit()
    return gid


def fatti_per_agente(conn, testo: str) -> str:
    """Blocco di contesto: gli ultimi fatti dati da Lorenzo piu' quelli pertinenti al messaggio."""
    ultimi = conn.execute("SELECT id, testo FROM fatti_condivisi WHERE attivo ORDER BY id DESC LIMIT %s", (FATTI_IN_CONTESTO,)).fetchall()
    if not ultimi:
        return ""
    righe = {r["id"]: r["testo"] for r in ultimi}
    from .documenti import query_ricerca
    q = query_ricerca(testo or "")
    if q:
        for r in conn.execute("SELECT id, testo FROM fatti_condivisi WHERE attivo AND to_tsvector('italian', testo) @@ to_tsquery('italian', %s) ORDER BY id DESC LIMIT %s", (q, FATTI_PERTINENTI)).fetchall():
            righe.setdefault(r["id"], r["testo"])
    return "Cose che Lorenzo ha detto di recente sulle strutture e sui progetti (sono vere e aggiornate: fidati di queste piu' che di documenti piu' vecchi):\n" + "\n".join("- " + righe[i] for i in sorted(righe, reverse=True))


# ---------- rotte ----------
class Risposta(BaseModel):
    risposta: str = Field(min_length=1, max_length=600)


class Fatto(BaseModel):
    testo: str = Field(min_length=5, max_length=500)


class Impostazioni(BaseModel):
    giorni: int = Field(ge=0, le=90)


@router.get("")
def vista(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        g = aperto(conn)
        return {"giorni": giorni(conn), "aperto": g,
                "domande": conn.execute("SELECT d.id, d.domanda, d.stato, a.nome AS agente FROM domande_giro d LEFT JOIN agenti a ON a.id = d.agente_id WHERE d.giro_id = %s ORDER BY d.id", (g["id"],)).fetchall() if g else [],
                "fatti": conn.execute("SELECT id, testo, creato_il FROM fatti_condivisi WHERE attivo ORDER BY id DESC LIMIT 40").fetchall()}


@router.post("/avvia", status_code=201)
def avvia_ora(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"id": avvia(conn, "manuale")}
        except ErroreGiro as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None


@router.post("/domande/{did}/risposta")
def rispondi(did: int, d: Risposta, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        q = conn.execute("SELECT d.*, a.nome AS agente FROM domande_giro d LEFT JOIN agenti a ON a.id = d.agente_id WHERE d.id = %s FOR UPDATE OF d", (did,)).fetchone()
        if q is None or q["stato"] != "attesa":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Domanda non trovata o gia' chiusa")
        r = d.risposta.strip()
        conn.execute("UPDATE domande_giro SET risposta = %s, stato = 'risposta', risposta_il = NOW() WHERE id = %s", (r, did))
        conn.execute("INSERT INTO fatti_condivisi (testo, domanda_id) VALUES (%s,%s)", (f"{q['domanda']} → {r}", did))
        chiudi_se_finito(conn, q["giro_id"])
        return {"ok": True}


@router.post("/domande/{did}/salta")
def salta(did: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        q = conn.execute("SELECT giro_id, stato FROM domande_giro WHERE id = %s FOR UPDATE", (did,)).fetchone()
        if q is None or q["stato"] != "attesa":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Domanda non trovata o gia' chiusa")
        conn.execute("UPDATE domande_giro SET stato = 'saltata' WHERE id = %s", (did,))
        chiudi_se_finito(conn, q["giro_id"])
        return {"ok": True}


@router.post("/fatti", status_code=201)
def aggiungi(d: Fatto, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"id": conn.execute("INSERT INTO fatti_condivisi (testo) VALUES (%s) RETURNING id", (d.testo.strip(),)).fetchone()["id"]}


@router.delete("/fatti/{fid}")
def togli(fid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("UPDATE fatti_condivisi SET attivo = FALSE WHERE id = %s AND attivo RETURNING 1", (fid,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fatto non trovato")
        return {"ok": True}


@router.put("/impostazioni")
def imposta(d: Impostazioni, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('giro_giorni', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (str(d.giorni),))
        return {"giorni": d.giorni}
