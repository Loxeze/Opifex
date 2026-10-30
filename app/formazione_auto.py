"""Formazione automatica. Quando la coda degli studi di Padre Casati si svuota, Padre Casati fa un giro tra gli agenti: ognuno dice quali competenze
vorrebbe approfondire e quali sono necessarie al suo ruolo. I desideri diventano richieste in Ginnasio. Chi non ha ancora almeno il livello 1 (Junior)
in una competenza necessaria passa avanti a tutti: nella graduatoria della formazione quelle richieste hanno la precedenza assoluta."""
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import ginnasio as g
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/formazione-auto", tags=["formazione"])
SINCRONO = False
MAX_AGENTI_GIRO = 60
MAX_NECESSARIE = 6
MAX_DESIDERI = 2
_blocco = threading.Lock()


def _imp(conn, chiave, default):
    return g.impostazione(conn, chiave, default)


def giorni(conn) -> int:
    try:
        return max(0, min(90, int(_imp(conn, "desideri_giorni", "7"))))
    except ValueError:
        return 7


def minimo_attivo(conn) -> bool:
    return _imp(conn, "minimo_attivo", "1") == "1"


# ---------- livello minimo ----------
def mancanti(conn) -> list[dict]:
    """Competenze necessarie a un agente in cui non ha ancora il livello 1."""
    out = []
    for r in conn.execute("""SELECT n.agente_id, n.nome, a.nome AS agente FROM competenze_necessarie n JOIN agenti a ON a.id = n.agente_id
                             WHERE a.attivo ORDER BY n.agente_id, n.nome""").fetchall():
        c = conn.execute("SELECT id FROM competenze WHERE lower(nome) = lower(%s)", (r["nome"],)).fetchone()
        if c and conn.execute("SELECT 1 FROM agenti_competenze WHERE agente_id = %s AND competenza_id = %s AND livello >= 1", (r["agente_id"], c["id"])).fetchone():
            continue
        out.append(r)
    return out


def richiedi_minimi(conn) -> int:
    """Per ogni competenza necessaria mancante c'e' una richiesta di livello 1 in coda, con precedenza assoluta."""
    if not minimo_attivo(conn):
        return 0
    nuove = 0
    for m in mancanti(conn):
        try:
            r = g.richiedi(conn, m["nome"], 1, agente_id=m["agente_id"], origine="minimo", urgenza=3,
                           motivo=f"Livello minimo: «{m['nome']}» e' necessaria al ruolo di {m['agente']} e non ha ancora nemmeno il livello 1 (Junior).")
        except g.ErroreGinnasio:
            continue
        if r.get("id"):
            conn.execute("UPDATE richieste_formazione SET minimo = TRUE WHERE id = %s", (r["id"],))
            nuove += 0 if r.get("unita") else 1
    conn.commit()
    return nuove


# ---------- giro dei desideri ----------
def _prompt(conn, a: dict) -> str:
    miei = g.competenze_agente(conn, a["id"])
    nec = [r["nome"] for r in conn.execute("SELECT nome FROM competenze_necessarie WHERE agente_id = %s ORDER BY nome", (a["id"],)).fetchall()]
    esistenti = [r["nome"] for r in conn.execute("SELECT nome FROM competenze ORDER BY nome LIMIT 80").fetchall()]
    p = (f"Sei {a['nome']} ({a['ruolo']}). Padre Casati fa il giro di formazione e ti chiede, in poche righe, cosa ti serve per lavorare meglio.\n"
         "Le tue competenze oggi: " + (", ".join(f"{c['nome']} (livello {c['livello']})" for c in miei) or "nessuna ancora") + ".\n")
    if nec:
        p += "Competenze che hai indicato come necessarie al tuo ruolo: " + ", ".join(nec) + ".\n"
    else:
        p += (f"1) Elenca le competenze NECESSARIE al tuo ruolo, al massimo {MAX_NECESSARIE}: quelle senza le quali non puoi lavorare bene. Una per riga, nel formato\n"
              "NECESSARIA: nome della competenza\n")
    p += (f"2) Elenca al massimo {MAX_DESIDERI} competenze che desideri APPROFONDIRE (anche tra quelle che hai gia') solo se ti servono davvero nel lavoro che fai. Una per riga, nel formato\n"
          "DESIDERIO: nome della competenza | motivo concreto in almeno 30 caratteri (quale lacuna hai visto, in quale lavoro)\n"
          + ("Se un nome esiste gia' usa quello: " + "; ".join(esistenti[:80]) + ".\n" if esistenti else "")
          + "Se non hai nulla da chiedere rispondi solo: NIENTE. Non scrivere altro.")
    return p


def _leggi(testo: str) -> tuple[list[str], list[tuple[str, str]]]:
    nec, des = [], []
    for riga in str(testo or "").splitlines():
        riga = re.sub(r"^\s*[-*•\d.)]*\s*", "", riga).strip()
        m = re.match(r"(?i)NECESSARIA\s*:\s*(.+)$", riga)
        if m:
            n = g._nome(m.group(1).split("|")[0])
            if 3 <= len(n) <= 100 and n.lower() not in (x.lower() for x in nec):
                nec.append(n)
            continue
        m = re.match(r"(?i)DESIDERIO\s*:\s*([^|]+)\|\s*(.+)$", riga)
        if m:
            n, mot = g._nome(m.group(1)), m.group(2).strip()
            if 3 <= len(n) <= 100 and len(mot) >= 30 and n.lower() not in (x[0].lower() for x in des):
                des.append((n, mot))
    return nec[:MAX_NECESSARIE], des[:MAX_DESIDERI]


def _prossimo_livello(conn, agente_id: int, nome: str) -> int:
    r = conn.execute("""SELECT x.livello FROM agenti_competenze x JOIN competenze c ON c.id = x.competenza_id WHERE x.agente_id = %s AND lower(c.nome) = lower(%s)""", (agente_id, nome)).fetchone()
    return min(5, (r["livello"] + 1) if r else 1)


def giro_desideri(giro_id: int):
    from .esecuzione import esegui_agente
    try:
        with connessione() as conn:
            cas = conn.execute("SELECT id FROM agenti WHERE ruolo_speciale = 'formatore' AND attivo LIMIT 1").fetchone()
            if not cas:
                raise g.ErroreGinnasio("Padre Casati non e' attivo")
            # prima chi non e' mai stato interrogato, poi chi lo e' stato meno di recente
            agenti = conn.execute("""SELECT a.id, a.nome, a.ruolo FROM agenti a LEFT JOIN desideri_agenti d ON d.agente_id = a.id
                                     WHERE a.attivo AND a.ruolo_speciale IS NULL AND NOT COALESCE(a.sentinella, FALSE)
                                     ORDER BY d.ultimo_il NULLS FIRST, a.id LIMIT %s""", (MAX_AGENTI_GIRO,)).fetchall()
        fatti = richieste = 0
        for a in agenti:
            try:
                with connessione() as conn:
                    prompt = _prompt(conn, a)
                ris = esegui_agente(a["id"], prompt, "interno", None, max_token=500)
                nec, des = _leggi(ris.get("risposta", ""))
                with connessione() as conn:
                    for n in nec:
                        conn.execute("INSERT INTO competenze_necessarie (agente_id, nome) VALUES (%s,%s) ON CONFLICT DO NOTHING", (a["id"], n))
                    for n, mot in des:
                        try:
                            r = g.richiedi(conn, n, _prossimo_livello(conn, a["id"], n), agente_id=a["id"], motivo=mot, origine="desiderio", da_agente_id=a["id"], urgenza=1)
                            if r.get("id") and not r.get("unita"):
                                richieste += 1
                        except g.ErroreGinnasio:
                            pass
                    conn.execute("INSERT INTO desideri_agenti (agente_id, esito) VALUES (%s,%s) ON CONFLICT (agente_id) DO UPDATE SET ultimo_il = NOW(), esito = EXCLUDED.esito",
                                 (a["id"], f"{len(nec)} necessarie, {len(des)} desideri"))
                    fatti += 1
            except Exception:  # noqa: BLE001 - un agente che non risponde non ferma il giro
                continue
        with connessione() as conn:
            richiedi_minimi(conn)
            conn.execute("UPDATE desideri_giri SET stato = 'concluso', interrogati = %s, richieste = %s, concluso_il = NOW() WHERE id = %s", (fatti, richieste, giro_id))
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                         (f"Giro di formazione concluso: {fatti} agenti interrogati, {richieste} richieste nuove in Ginnasio.",))
    except Exception as e:  # noqa: BLE001
        with connessione() as conn:
            conn.execute("UPDATE desideri_giri SET stato = 'errore', errore = %s, concluso_il = NOW() WHERE id = %s", (str(e)[:300], giro_id))


def avvia(conn, forza: bool = False) -> int | None:
    """Avvia il giro se la coda degli studi e' vuota ed e' passato abbastanza tempo (o se forzato). Un solo giro alla volta."""
    with _blocco:
        if conn.execute("SELECT 1 FROM desideri_giri WHERE stato = 'in_corso' AND avviato_il > NOW() - interval '3 hours'").fetchone():
            return None
        if not forza:
            gg = giorni(conn)
            if gg == 0:
                return None
            if conn.execute("SELECT 1 FROM studi WHERE stato IN ('approvato','in_corso')").fetchone():
                return None
            if conn.execute("SELECT 1 FROM desideri_giri WHERE avviato_il > NOW() - make_interval(days => %s)", (gg,)).fetchone():
                return None
        conn.execute("UPDATE desideri_giri SET stato = 'errore', errore = 'Interrotto', concluso_il = NOW() WHERE stato = 'in_corso'")
        gid = conn.execute("INSERT INTO desideri_giri DEFAULT VALUES RETURNING id").fetchone()["id"]
        conn.commit()
    if SINCRONO:
        giro_desideri(gid)
    else:
        threading.Thread(target=giro_desideri, args=(gid,), daemon=True).start()
    return gid


def dopo_coda():
    with connessione() as conn:
        avvia(conn)


def giro(conn):
    """Dal lavoro di fondo (ogni 10 minuti): i livelli minimi mancanti diventano richieste con precedenza; se la coda e' vuota e' ora, giro dei desideri."""
    richiedi_minimi(conn)
    avvia(conn)


# ---------- rotte ----------
class Impostazioni(BaseModel):
    studi_automatici: bool
    giorni: int = Field(ge=0, le=90)
    minimo_attivo: bool


@router.get("")
def vista(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"studi_automatici": conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'studi_automatici'").fetchone() is None or _imp(conn, "studi_automatici", "1") == "1",
                "giorni": giorni(conn), "minimo_attivo": minimo_attivo(conn), "ginnasio_attivo": g.stato_generale(conn)["attivo"],
                "studi_in_coda": conn.execute("SELECT count(*) AS n FROM studi WHERE stato IN ('approvato','in_corso')").fetchone()["n"],
                "giri": conn.execute("SELECT id, stato, interrogati, richieste, errore, avviato_il, concluso_il FROM desideri_giri ORDER BY id DESC LIMIT 5").fetchall(),
                "minimi_mancanti": [{"agente": m["agente"], "competenza": m["nome"]} for m in mancanti(conn)][:60]}


@router.put("/impostazioni")
def imposta(d: Impostazioni, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        g.imposta(conn, "studi_automatici", "1" if d.studi_automatici else "0")
        g.imposta(conn, "desideri_giorni", str(d.giorni))
        g.imposta(conn, "minimo_attivo", "1" if d.minimo_attivo else "0")
        return {"ok": True}


@router.post("/giro", status_code=202)
def giro_ora(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        gid = avvia(conn, forza=True)
        if gid is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Un giro e' gia' in corso")
        return {"id": gid}
