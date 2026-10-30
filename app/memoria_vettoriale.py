"""Memoria condivisa con ricerca per significato. Ogni pezzo di documento ha un vettore (embedding) che ne rappresenta il senso: la ricerca trova anche testi scritti
con parole diverse da quelle della domanda. Si unisce alla ricerca per parole gia' esistente; le regole su chi puo' vedere cosa restano quelle dei documenti.
Il testo esce verso il fornitore dei vettori (OpenAI) solo se la sua fascia di riservatezza e le garanzie lo consentono. Se qualcosa non funziona, si ricade
sulla sola ricerca per parole: la memoria non blocca mai un agente."""
import json
import re
import threading
import zipfile
from datetime import datetime, timezone
from io import BytesIO

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from . import fornitori
from .db import connessione
from .permessi import solo_titolare
from .riservatezza import puo_uscire

router = APIRouter(prefix="/gestione/memoria-vettoriale", tags=["memoria"])
SINCRONO = False
MODELLO = "text-embedding-3-small"
DIM = 512
LOTTO = 96
MAX_PER_GIRO = 480
MAX_VETTORI = 150_000
MAX_FILE = 300 * 1024 * 1024
_cache = {"firma": None, "pezzi": None, "docs": None, "M": None}
_blocco = threading.Lock()


class ErroreMemoria(Exception):
    pass


# ---------- vettori ----------
def _embed(testi: list[str]) -> list[list[float]]:
    chiave = fornitori.chiave("openai")
    if not chiave:
        raise ErroreMemoria("Chiave OpenAI non configurata")
    try:
        r = httpx.post("https://api.openai.com/v1/embeddings", headers={"Authorization": "Bearer " + chiave},
                       json={"model": MODELLO, "input": [t[:8000] for t in testi], "dimensions": DIM}, timeout=60)
    except httpx.HTTPError as e:
        raise ErroreMemoria(f"OpenAI non raggiungibile ({type(e).__name__})") from None
    if r.status_code != 200:
        raise ErroreMemoria(f"OpenAI ha risposto {r.status_code}")
    return [d["embedding"] for d in sorted(r.json()["data"], key=lambda x: x["index"])]


def _bytes(v: list[float]) -> bytes:
    import numpy as np
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a)) or 1.0
    return (a / n).astype(np.float16).tobytes()


def fasce_consentite(conn) -> list[str]:
    f = conn.execute("SELECT fascia_dati_max, non_conservazione_attiva, dpa_firmato FROM fornitori_ai WHERE nome = 'openai'").fetchone()
    if f is None:
        return []
    return [fa for fa in ("pubblico", "interno", "riservato") if puo_uscire(fa, "riservato", f["fascia_dati_max"], f["non_conservazione_attiva"], f["dpa_firmato"])[0]]


def stato(conn) -> dict:
    tot = conn.execute("SELECT count(*) AS n FROM pezzi_documenti").fetchone()["n"]
    ind = conn.execute("SELECT count(*) AS n FROM pezzi_vettori").fetchone()["n"]
    fasce = fasce_consentite(conn)
    da_fare = conn.execute("SELECT count(*) AS n FROM pezzi_documenti p JOIN documenti d ON d.id = p.documento_id LEFT JOIN pezzi_vettori v ON v.pezzo_id = p.id WHERE v.pezzo_id IS NULL AND d.fascia_dati = ANY(%s)", (fasce,)).fetchone()["n"]
    esclusi = conn.execute("SELECT count(*) AS n FROM pezzi_documenti p JOIN documenti d ON d.id = p.documento_id LEFT JOIN pezzi_vettori v ON v.pezzo_id = p.id WHERE v.pezzo_id IS NULL AND NOT d.fascia_dati = ANY(%s)", (fasce,)).fetchone()["n"]
    return {"pezzi": tot, "indicizzati": ind, "da_indicizzare": da_fare, "esclusi_per_riservatezza": esclusi, "fasce_consentite": fasce, "chiave": bool(fornitori.chiave("openai")), "modello": MODELLO}


def indicizza(conn, massimo: int = MAX_PER_GIRO) -> int:
    """Calcola i vettori dei pezzi che ne sono privi (solo documenti la cui fascia puo' uscire). Restituisce quanti ne ha fatti."""
    if conn.execute("SELECT count(*) AS n FROM pezzi_vettori").fetchone()["n"] >= MAX_VETTORI:
        return 0
    fasce = fasce_consentite(conn)
    if not fasce:
        return 0
    righe = conn.execute("""SELECT p.id, p.documento_id, p.testo FROM pezzi_documenti p JOIN documenti d ON d.id = p.documento_id LEFT JOIN pezzi_vettori v ON v.pezzo_id = p.id
                            WHERE v.pezzo_id IS NULL AND d.fascia_dati = ANY(%s) ORDER BY p.id LIMIT %s""", (fasce, massimo)).fetchall()
    fatti = 0
    for i in range(0, len(righe), LOTTO):
        gruppo = righe[i:i + LOTTO]
        vett = _embed([r["testo"] for r in gruppo])
        for r, v in zip(gruppo, vett):
            conn.execute("INSERT INTO pezzi_vettori (pezzo_id, documento_id, vettore, modello) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (r["id"], r["documento_id"], _bytes(v), MODELLO))
            fatti += 1
        conn.commit()
    return fatti


def _matrice(conn):
    import numpy as np
    firma = conn.execute("SELECT count(*) AS n, COALESCE(max(pezzo_id), 0) AS m FROM pezzi_vettori").fetchone()
    f = (firma["n"], firma["m"])
    with _blocco:
        if _cache["firma"] == f and _cache["M"] is not None:
            return _cache
        righe = conn.execute("SELECT pezzo_id, documento_id, vettore FROM pezzi_vettori ORDER BY pezzo_id").fetchall()
        if not righe:
            _cache.update(firma=f, pezzi=np.zeros(0, dtype=np.int64), docs=np.zeros(0, dtype=np.int64), M=np.zeros((0, DIM), dtype=np.float32))
        else:
            M = np.vstack([np.frombuffer(bytes(r["vettore"]), dtype=np.float16) for r in righe]).astype(np.float32)
            _cache.update(firma=f, pezzi=np.array([r["pezzo_id"] for r in righe], dtype=np.int64), docs=np.array([r["documento_id"] for r in righe], dtype=np.int64), M=M)
        return _cache


def cerca(conn, agente_id: int, messaggio: str, limite: int = 6) -> list[dict]:
    """Pezzi piu' vicini per significato al messaggio, solo tra i documenti che questo agente puo' vedere."""
    import numpy as np
    from . import memoria
    if not (messaggio or "").strip():
        return []
    c = _matrice(conn)
    if len(c["pezzi"]) == 0:
        return []
    visibili = np.array([d["id"] for d in memoria.documenti_visibili(conn, agente_id)], dtype=np.int64)
    if len(visibili) == 0:
        return []
    q = np.asarray(_embed([messaggio[:2000]])[0], dtype=np.float32)
    q /= (np.linalg.norm(q) or 1.0)
    maschera = np.isin(c["docs"], visibili)
    if not maschera.any():
        return []
    punteggi = c["M"] @ q
    punteggi = np.where(maschera, punteggi, -2.0)
    idx = np.argsort(-punteggi)[:limite]
    scelti = [(int(c["pezzi"][i]), float(punteggi[i])) for i in idx if punteggi[i] > 0.2]
    if not scelti:
        return []
    righe = conn.execute("""SELECT p.id, d.id AS documento_id, d.nome, d.fascia_dati, p.testo FROM pezzi_documenti p JOIN documenti d ON d.id = p.documento_id WHERE p.id = ANY(%s)""",
                         ([s[0] for s in scelti],)).fetchall()
    per_id = {r["id"]: r for r in righe}
    return [{**per_id[i], "punteggio": s} for i, s in scelti if i in per_id]


def unisci(per_parole: list[dict], per_significato: list[dict], limite: int) -> list[dict]:
    """Fusione per posizione (reciprocal rank fusion): chi compare in alto in entrambe le ricerche vince; nessun pezzo ripetuto."""
    punti, rif = {}, {}
    for elenco in (per_parole, per_significato):
        for pos, r in enumerate(elenco):
            k = (r["documento_id"], r["testo"][:80])
            punti[k] = punti.get(k, 0.0) + 1.0 / (60 + pos)
            rif.setdefault(k, r)
    return [rif[k] for k, _ in sorted(punti.items(), key=lambda x: -x[1])][:limite]


# ---------- importazione delle chat ----------
def _testo_chatgpt(conv: dict) -> str:
    m = conv.get("mapping") or {}
    nodo = conv.get("current_node")
    catena = []
    visti = set()
    while nodo and nodo in m and nodo not in visti:
        visti.add(nodo)
        catena.append(m[nodo])
        nodo = m[nodo].get("parent")
    out = []
    for n in reversed(catena):
        msg = n.get("message") or {}
        ruolo = (msg.get("author") or {}).get("role")
        if ruolo not in ("user", "assistant"):
            continue
        parti = (msg.get("content") or {}).get("parts") or []
        testo = "\n".join(p for p in parti if isinstance(p, str)).strip()
        if testo:
            out.append(("Lorenzo" if ruolo == "user" else "ChatGPT") + ": " + testo)
    return "\n\n".join(out)


def _testo_claude(conv: dict) -> str:
    out = []
    for msg in conv.get("chat_messages") or []:
        testo = (msg.get("text") or "").strip()
        if not testo:
            testo = "\n".join(c.get("text", "") for c in (msg.get("content") or []) if isinstance(c, dict) and c.get("type") == "text").strip()
        if testo:
            out.append(("Lorenzo" if msg.get("sender") == "human" else "Claude") + ": " + testo)
    return "\n\n".join(out)


def _data(v) -> str:
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), timezone.utc).strftime("%Y-%m-%d")
        return str(v or "")[:10]
    except Exception:  # noqa: BLE001
        return ""


def leggi_conversazioni(nome_file: str, dati: bytes) -> tuple[str, list[dict]]:
    """(origine, [{id, titolo, data, testo}]) da un file .zip o .json di esportazione di ChatGPT o di Claude."""
    pezzi_json = []
    if nome_file.lower().endswith(".zip"):
        try:
            z = zipfile.ZipFile(BytesIO(dati))
        except zipfile.BadZipFile:
            raise ErroreMemoria("Il file zip non e' valido") from None
        for n in z.namelist():
            base = n.rsplit("/", 1)[-1].lower()
            if re.fullmatch(r"conversations(-\d+)?\.json", base):
                pezzi_json.append(z.read(n))
        if not pezzi_json:
            raise ErroreMemoria("Nello zip non trovo conversations.json: e' l'esportazione di ChatGPT o di Claude?")
    else:
        pezzi_json.append(dati)
    conv, origine = [], None
    for blob in pezzi_json:
        try:
            lista = json.loads(blob.decode("utf-8", "replace"))
        except ValueError:
            raise ErroreMemoria("Il file non e' un JSON valido") from None
        if not isinstance(lista, list):
            raise ErroreMemoria("Formato non riconosciuto: mi aspetto un elenco di conversazioni")
        for c in lista:
            if not isinstance(c, dict):
                continue
            if "mapping" in c:
                origine = "ChatGPT"
                conv.append({"id": str(c.get("id") or c.get("conversation_id") or ""), "titolo": c.get("title") or "Senza titolo", "data": _data(c.get("create_time")), "testo": _testo_chatgpt(c)})
            elif "chat_messages" in c:
                origine = "Claude"
                conv.append({"id": str(c.get("uuid") or ""), "titolo": c.get("name") or "Senza titolo", "data": _data(c.get("created_at")), "testo": _testo_claude(c)})
    if origine is None:
        raise ErroreMemoria("Formato non riconosciuto: non sembra un'esportazione di ChatGPT o di Claude")
    return origine, conv


def importa(conn, utente_id: int, nome_file: str, dati: bytes, per_tutti: bool) -> int:
    from .documenti import dividi_in_pezzi
    origine, conv = leggi_conversazioni(nome_file, dati)
    iid = conn.execute("INSERT INTO importazioni_chat (origine, nome_file, conversazioni, per_tutti, creato_da_utente_id) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                       (origine, nome_file[:200], len(conv), per_tutti, utente_id)).fetchone()["id"]
    conn.commit()
    if SINCRONO:
        _importa(iid, origine, conv, per_tutti, utente_id)
    else:
        threading.Thread(target=_importa, args=(iid, origine, conv, per_tutti, utente_id), daemon=True).start()
    return iid


def _importa(iid: int, origine: str, conv: list[dict], per_tutti: bool, utente_id: int):
    from .documenti import dividi_in_pezzi
    try:
        with connessione() as conn:
            for i, c in enumerate(conv):
                testo = (c["testo"] or "").strip()
                chiave = f"{origine.lower()}:{c['id']}" if c["id"] else None
                if len(testo) < 200 or (chiave and conn.execute("SELECT 1 FROM documenti WHERE origine_chat = %s", (chiave,)).fetchone()):
                    conn.execute("UPDATE importazioni_chat SET saltate = saltate + 1 WHERE id = %s", (iid,))
                    continue
                nome = f"{origine}: {c['titolo'][:140]}" + (f" ({c['data']})" if c["data"] else "")
                did = conn.execute("""INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri, caricato_da, origine_chat) VALUES (%s,%s,'interno',%s,%s,%s,%s) RETURNING id""",
                                   (nome, f"{origine.lower()}-{c['id'][:12] or i}.txt", per_tutti, len(testo), utente_id, chiave)).fetchone()["id"]
                intestazione = f"[Conversazione {origine} del {c['data']}: {c['titolo']}]\n\n"
                for k, p in enumerate(dividi_in_pezzi(intestazione + testo)):
                    conn.execute("INSERT INTO pezzi_documenti (documento_id, ordine, testo) VALUES (%s,%s,%s)", (did, k, p))
                conn.execute("UPDATE importazioni_chat SET importate = importate + 1 WHERE id = %s", (iid,))
                if i % 20 == 0:
                    conn.commit()
            conn.execute("UPDATE importazioni_chat SET stato = 'conclusa' WHERE id = %s", (iid,))
    except Exception as e:  # noqa: BLE001
        with connessione() as conn:
            conn.execute("UPDATE importazioni_chat SET stato = 'errore', errore = %s WHERE id = %s", (str(e)[:300], iid))


# ---------- rotte ----------
@router.get("")
def vista(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {**stato(conn), "importazioni": conn.execute("SELECT id, origine, nome_file, stato, conversazioni, importate, saltate, errore, creato_il FROM importazioni_chat ORDER BY id DESC LIMIT 10").fetchall()}


@router.post("/indicizza")
def ora(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            n = indicizza(conn)
        except ErroreMemoria as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
        return {"fatti": n, **stato(conn)}


@router.post("/importa", status_code=202)
async def carica(file: UploadFile = File(...), per_tutti: bool = Form(True), u: dict = Depends(solo_titolare)):
    nome = (file.filename or "export.json").strip()
    if not nome.lower().endswith((".zip", ".json")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Carica il file .zip dell'esportazione oppure il suo conversations.json")
    dati = await file.read(MAX_FILE + 1)
    if len(dati) > MAX_FILE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File troppo grande (massimo 300 MB): carica solo conversations.json")
    from starlette.concurrency import run_in_threadpool
    def lavoro():
        with connessione() as conn:
            return importa(conn, u["id"], nome, dati, per_tutti)
    try:
        iid = await run_in_threadpool(lavoro)
    except ErroreMemoria as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return {"id": iid}
