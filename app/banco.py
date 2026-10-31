"""Banco di lavoro (2.5.0): un PC di montaggio che esegue, per gli agenti, lavori su file veri: inventario (ffprobe), fotogrammi, silenzi, ffmpeg limitato.
Il programma sul PC (banco_connettore/opifex_banco.py) si collega SOLO in uscita a Opifex, prende un lavoro alla volta e restituisce testo e piccole immagini.
Gli agenti vedono i risultati (le immagini le descrive un modello con la vista). I file restano sul PC, in una sola cartella di lavoro."""
import hashlib
import json
import re
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .db import connessione
from .permessi import solo_titolare

CARTELLA = Path(__file__).parent / "banco_connettore"
router_banco = APIRouter(prefix="/banco")
router = APIRouter(prefix="/gestione/banco")
ATTESA_S = 90
MAX_FOTOGRAMMI = 24
MAX_IMMAGINE = 6 * 1024 * 1024
MAX_FILE_PER_LAVORO = 12
ESTENSIONI_USCITA = (".mp4", ".mov", ".mp3", ".wav", ".m4a", ".jpg", ".png", ".srt", ".txt", ".xml")


def _hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


# ---------------- postazione: autenticazione ----------------
def postazione_corrente(authorization: str = Header(default=""), x_versione: str = Header(default="")) -> dict:
    tok = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not tok.startswith("bn_") or len(tok) > 100:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chiave della postazione non valida")
    with connessione() as conn:
        p = conn.execute("SELECT id, nome FROM banco_postazioni WHERE token_hash = %s AND attiva", (_hash(tok),)).fetchone()
        if not p:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chiave della postazione non valida")
        conn.execute("UPDATE banco_postazioni SET ultimo_contatto = NOW(), versione = COALESCE(NULLIF(%s,''), versione) WHERE id = %s", (x_versione[:20], p["id"]))
        return p


@router_banco.get("/programma")
def programma(p: dict = Depends(postazione_corrente)):
    return Response((CARTELLA / "opifex_banco.py").read_bytes(), media_type="text/x-python", headers={"Cache-Control": "no-store"})


@router_banco.get("/ping")
def ping(p: dict = Depends(postazione_corrente)):
    return {"ok": True}


@router_banco.get("/lavoro")
def prossimo(p: dict = Depends(postazione_corrente)):
    """La postazione prende il lavoro piu' vecchio in attesa (o quello gia' suo rimasto in corso da troppo tempo)."""
    with connessione() as conn:
        conn.execute("UPDATE banco_lavori SET stato = 'errore', risultato = 'La postazione non ha risposto in tempo', finito_il = NOW() "
                     "WHERE stato = 'in_corso' AND iniziato_il < NOW() - interval '3 hours'")
        l = conn.execute("""UPDATE banco_lavori SET stato = 'in_corso', postazione_id = %s, iniziato_il = NOW()
                            WHERE id = (SELECT id FROM banco_lavori WHERE stato = 'in_attesa' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED)
                            RETURNING id, tipo, parametri""", (p["id"],)).fetchone()
        return {"lavoro": l}


@router_banco.post("/lavoro/{lid}/esito")
async def esito(lid: int, ok: bool = Form(...), testo: str = Form(""), file: list[UploadFile] = File(default=[]), p: dict = Depends(postazione_corrente)):
    with connessione() as conn:
        l = conn.execute("SELECT id FROM banco_lavori WHERE id = %s AND postazione_id = %s AND stato = 'in_corso'", (lid, p["id"])).fetchone()
        if not l:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavoro non in corso su questa postazione")
        for f in file[:MAX_FILE_PER_LAVORO]:
            dati = await f.read(MAX_IMMAGINE + 1)
            if len(dati) > MAX_IMMAGINE:
                continue
            conn.execute("INSERT INTO banco_file (lavoro_id, nome, mime, dati) VALUES (%s,%s,%s,%s)",
                         (lid, re.sub(r"[^\w.\-]", "_", f.filename or "file")[:80], f.content_type or "image/jpeg", dati))
        conn.execute("UPDATE banco_lavori SET stato = %s, risultato = %s, finito_il = NOW() WHERE id = %s", ("fatto" if ok else "errore", testo[:20000], lid))
    return {"ok": True}


# ---------------- gestione (titolare) ----------------
class NuovaPostazione(BaseModel):
    nome: str = Field(min_length=2, max_length=60)


@router.get("")
def stato_banco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {"postazioni": conn.execute("SELECT id, nome, attiva, versione, ultimo_contatto, (ultimo_contatto > NOW() - interval '3 minutes') AS online FROM banco_postazioni ORDER BY id").fetchall(),
                "lavori": conn.execute("""SELECT l.id, l.tipo, l.stato, l.creato_il, l.finito_il, a.nome AS agente, left(l.risultato, 200) AS risultato FROM banco_lavori l
                                          LEFT JOIN agenti a ON a.id = l.agente_id ORDER BY l.id DESC LIMIT 15""").fetchall()}


@router.post("/postazioni", status_code=201)
def nuova(d: NuovaPostazione, _: dict = Depends(solo_titolare)):
    tok = "bn_" + secrets.token_urlsafe(32)
    with connessione() as conn:
        pid = conn.execute("INSERT INTO banco_postazioni (nome, token_hash) VALUES (%s,%s) RETURNING id", (d.nome.strip(), _hash(tok))).fetchone()["id"]
    return {"id": pid, "token": tok}


def _pacchetto(url: str, token: str) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(CARTELLA / "opifex_banco.py", "opifex-banco/opifex_banco.py")
        z.write(CARTELLA / "LEGGIMI.txt", "opifex-banco/LEGGIMI.txt")
        z.writestr("opifex-banco/avvia.bat", "@echo off\r\nset OPIFEX_URL=%s\r\nset OPIFEX_TOKEN=%s\r\nset OPIFEX_CARTELLA=CARTELLA_DI_LAVORO\r\n"
                   "python opifex_banco.py\r\npause\r\n" % (url, token))
        z.writestr("opifex-banco/avvia.command", "#!/bin/bash\ncd \"$(dirname \"$0\")\"\nexport OPIFEX_URL='%s'\nexport OPIFEX_TOKEN='%s'\n"
                   "export OPIFEX_CARTELLA='CARTELLA_DI_LAVORO'\npython3 opifex_banco.py\n" % (url, token))
    return buf.getvalue()


@router.post("/postazioni/{pid}/pacchetto")
def pacchetto(pid: int, richiesta: Request, _: dict = Depends(solo_titolare)):
    """Chiave nuova (la vecchia smette di valere) e pacchetto da installare sul PC di montaggio."""
    tok = "bn_" + secrets.token_urlsafe(32)
    with connessione() as conn:
        if not conn.execute("UPDATE banco_postazioni SET token_hash = %s, attiva = TRUE WHERE id = %s RETURNING 1", (_hash(tok), pid)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Postazione inesistente")
    return Response(_pacchetto(str(richiesta.base_url).rstrip("/"), tok), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="opifex-banco.zip"', "Cache-Control": "no-store"})


@router.delete("/postazioni/{pid}")
def spegni(pid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("UPDATE banco_postazioni SET attiva = FALSE WHERE id = %s", (pid,))
    return {"ok": True}


# ---------------- strumenti degli agenti ----------------
def attivo(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM banco_postazioni WHERE attiva LIMIT 1").fetchone())


def _rel(p) -> str | None:
    """Percorso relativo alla cartella di lavoro della postazione: niente assoluti, niente '..', niente protocolli."""
    s = str(p or "").strip().replace("\\", "/")
    if not s or s.startswith("/") or ".." in s.split("/") or re.match(r"^[a-zA-Z]+:", s) or "\x00" in s:
        return None
    return s[:300]


def nuovo_lavoro(conn, agente_id: int, tipo: str, par: dict, progetto_id=None) -> int:
    return conn.execute("INSERT INTO banco_lavori (agente_id, progetto_id, tipo, parametri) VALUES (%s,%s,%s,%s::jsonb) RETURNING id",
                        (agente_id, progetto_id, tipo, json.dumps(par))).fetchone()["id"]


def valida(tipo: str, d: dict) -> tuple[dict | None, str]:
    if tipo == "inventario":
        r = _rel(d.get("cartella") or ".") if (d.get("cartella") or ".") != "." else "."
        return ({"cartella": r}, "") if r else (None, "cartella non valida (percorso relativo alla cartella di lavoro)")
    if tipo == "ffmpeg":
        args = d.get("argomenti")
        if not isinstance(args, list) or not args or len(args) > 80 or not all(isinstance(x, (str, int, float)) for x in args):
            return None, "argomenti: elenco di opzioni ffmpeg (senza la parola ffmpeg)"
        return {"argomenti": [str(x) for x in args], "descrizione": str(d.get("descrizione") or "")[:200]}, ""
    f = _rel(d.get("file"))
    if not f:
        return None, "file non valido (percorso relativo alla cartella di lavoro, es. RIPRESE/clip1.mp4)"
    if tipo == "fotogrammi":
        try:
            tempi = [round(float(x), 2) for x in (d.get("tempi") or [])][:MAX_FOTOGRAMMI]
        except (TypeError, ValueError):
            return None, "tempi non validi (secondi, es. [0, 5.5, 12])"
        if not tempi or any(t < 0 for t in tempi):
            return None, "servono da 1 a 24 tempi in secondi"
        return {"file": f, "tempi": tempi}, ""
    if tipo == "silenzi":
        try:
            return {"file": f, "soglia_db": max(-80.0, min(-10.0, float(d.get("soglia_db", -35)))), "durata_min": max(0.1, min(5.0, float(d.get("durata_min", 0.4))))}, ""
        except (TypeError, ValueError):
            return None, "soglia_db e durata_min devono essere numeri"
    return None, "tipo sconosciuto"


STRUMENTI = [
    {"name": "banco_inventario", "description": "Sul PC di montaggio: elenca i file audio/video di una cartella di lavoro con durata, risoluzione, fps, audio presente e un'impronta per trovare i duplicati. Senza 'cartella' parte dalla radice.",
     "input_schema": {"type": "object", "properties": {"cartella": {"type": "string"}}}},
    {"name": "banco_fotogrammi", "description": "Sul PC di montaggio: estrae fotogrammi di un video ai tempi indicati (secondi) e li guarda: descrive cosa si vede. 'domanda' dice cosa controllare (es. «c'e' una scossa? chi e' inquadrato?»).",
     "input_schema": {"type": "object", "properties": {"file": {"type": "string"}, "tempi": {"type": "array", "items": {"type": "number"}}, "domanda": {"type": "string"}}, "required": ["file", "tempi"]}},
    {"name": "banco_silenzi", "description": "Sul PC di montaggio: trova le pause di silenzio di un file (inizio, fine, durata). I tagli di montaggio vanno messi in queste pause.",
     "input_schema": {"type": "object", "properties": {"file": {"type": "string"}, "soglia_db": {"type": "number"}, "durata_min": {"type": "number"}}, "required": ["file"]}},
    {"name": "banco_ffmpeg", "description": "Sul PC di montaggio: esegue ffmpeg con le opzioni indicate (senza la parola ffmpeg). I file in ingresso sono quelli della cartella di lavoro (con -i), l'uscita DEVE stare in 'uscite/' (es. uscite/reel_a.mp4). "
     "Per ingrandire a 4K, tagliare, concatenare, normalizzare l'audio. Restituisce l'esito e dimensione/durata del file prodotto.",
     "input_schema": {"type": "object", "properties": {"argomenti": {"type": "array", "items": {"type": "string"}}, "descrizione": {"type": "string"}}, "required": ["argomenti"]}},
    {"name": "banco_risultato", "description": "Legge il risultato di un lavoro del banco rimasto in corso (id restituito da un altro strumento banco_).",
     "input_schema": {"type": "object", "properties": {"lavoro_id": {"type": "integer"}}, "required": ["lavoro_id"]}},
]
AVVISO = ("\n\nBANCO DI LAVORO: hai un PC di montaggio con ffmpeg (strumenti banco_*). Metodo: banco_inventario, trascrizione, banco_silenzi per scegliere i tagli nelle pause, "
          "banco_ffmpeg per produrre in uscite/, poi banco_fotogrammi per RIGUARDARE il risultato prima di consegnarlo. Se un lavoro e' ancora in corso richiama banco_risultato con il suo id.")


def _attendi(lid: int, secondi: int = ATTESA_S) -> dict:
    fine = time.time() + secondi
    while time.time() < fine:
        with connessione() as conn:
            l = conn.execute("SELECT id, tipo, stato, risultato, parametri FROM banco_lavori WHERE id = %s", (lid,)).fetchone()
        if l and l["stato"] in ("fatto", "errore"):
            return l
        time.sleep(2)
    return {"id": lid, "stato": "in_corso", "risultato": "", "tipo": "", "parametri": {}}


def _descrivi(lid: int, domanda: str) -> str:
    from . import visione
    with connessione() as conn:
        img = conn.execute("SELECT nome, mime, dati FROM banco_file WHERE lavoro_id = %s ORDER BY id LIMIT 6", (lid,)).fetchall()
    if not img:
        return ""
    try:
        t = visione.chiedi([(i["mime"], bytes(i["dati"])) for i in img],
                           "Descrivi con precisione cosa si vede nei fotogrammi di un video, nell'ordine dato. Per ognuno: inquadratura, persone, testi leggibili, difetti (sfocato, scosso, tagliato). Nessuna invenzione.",
                           (domanda or "Descrivi i fotogrammi.") + "\nOrdine dei fotogrammi: " + ", ".join(i["nome"] for i in img), "interno", "", 900)
    except Exception as e:  # noqa: BLE001
        return f"\n[Non ho potuto far guardare i fotogrammi: {type(e).__name__}]"
    return "\nCosa si vede nei fotogrammi:\n" + t


def _esito_testo(l: dict, domanda: str = "") -> str:
    if l["stato"] == "in_corso":
        return f"Lavoro #{l['id']} ancora in corso sul PC: richiama banco_risultato con lavoro_id={l['id']} tra un po'."
    if l["stato"] == "errore":
        return f"ERRORE dal PC di montaggio: {l['risultato']}"
    extra = _descrivi(l["id"], domanda) if l["tipo"] == "fotogrammi" else ""
    return (l["risultato"] or "(nessun testo)") + extra


def gestore(connessione_, agente_id: int):
    def f(nome, dati):
        try:
            dati = dati or {}
            with connessione_() as conn:
                if nome == "banco_risultato":
                    l = conn.execute("SELECT id, tipo, stato, risultato FROM banco_lavori WHERE id = %s AND agente_id = %s", (int(dati.get("lavoro_id") or 0), agente_id)).fetchone()
                    return _esito_testo(l) if l else "ERRORE: lavoro inesistente"
                if not attivo(conn):
                    return "ERRORE: nessun PC di montaggio collegato (Impostazioni → Banco di lavoro). Dillo a Lorenzo con questa frase."
                tipo = nome[len("banco_"):]
                par, err = valida(tipo, dati)
                if par is None:
                    return "ERRORE: " + err
                pr = conn.execute("SELECT p.id FROM progetti p JOIN progetti_agenti x ON x.progetto_id = p.id WHERE x.agente_id = %s AND NOT p.archiviato ORDER BY p.id DESC LIMIT 1", (agente_id,)).fetchone()
                lid = nuovo_lavoro(conn, agente_id, tipo, par, pr["id"] if pr else None)
            l = _attendi(lid)
            return _esito_testo(l, str(dati.get("domanda") or ""))
        except Exception as e:  # noqa: BLE001
            return f"ERRORE: banco non riuscito ({type(e).__name__})"
    return f
