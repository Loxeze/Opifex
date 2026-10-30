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



# ---------- relazioni tra documenti ----------
SOGLIA_TEMA = 0.6
SOGLIA_PAROLE = 0.3
VICINI = 5
MAX_DOC_RELAZIONI = 4000


def relaziona_parole(conn) -> int:
    """Senza vettori (nessuna chiave OpenAI o documenti riservati): collega i documenti per le parole che hanno in comune (TF-IDF). Meno fine, ma funziona sempre."""
    import numpy as np
    from collections import Counter
    f = "p:" + "{}:{}".format(*conn.execute("SELECT count(*), COALESCE(sum(caratteri),0) FROM documenti").fetchone().values())
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'relazioni_firma'").fetchone()
    if r and r["valore"] == f:
        return 0
    docs = [d["id"] for d in conn.execute("SELECT id FROM documenti WHERE fascia_dati <> 'riservato' ORDER BY id LIMIT %s", (MAX_DOC_RELAZIONI,)).fetchall()]
    conteggi = []
    for d in docs:
        testo = " ".join(p["testo"] for p in conn.execute("SELECT testo FROM pezzi_documenti WHERE documento_id = %s ORDER BY id LIMIT 60", (d,)).fetchall())
        conteggi.append(Counter(re.findall(r"[^\W\d_]{5,}", testo.lower())))
    n = len(docs)
    if n < 2:
        return 0
    df = Counter(w for c in conteggi for w in c)
    vocab = [w for w, k in df.most_common() if k >= 2 and k <= max(2, n // 2)][:6000]
    if not vocab:
        return 0
    indice = {w: i for i, w in enumerate(vocab)}
    M = np.zeros((n, len(vocab)), dtype=np.float32)
    for i, c in enumerate(conteggi):
        for w, k in c.items():
            j = indice.get(w)
            if j is not None:
                M[i, j] = (1 + np.log(k)) * np.log(n / df[w])
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    S = M @ M.T
    np.fill_diagonal(S, -1)
    coppie = {}
    for i in range(n):
        for j in np.argsort(-S[i])[:VICINI]:
            if S[i, j] >= SOGLIA_PAROLE:
                a, b = sorted((docs[i], docs[int(j)]))
                coppie[(a, b)] = float(S[i, j])
    conn.execute("DELETE FROM documenti_relazioni")
    for (a, b), v in coppie.items():
        conn.execute("INSERT INTO documenti_relazioni (documento_a, documento_b, somiglianza) VALUES (%s,%s,%s)", (a, b, v))
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('relazioni_firma', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (f,))
    conn.commit()
    return len(coppie)


def relaziona(conn) -> int:
    """Cerca i documenti che trattano lo stesso tema (vettore medio di ogni documento) e ne salva le coppie piu' vicine. Si rifa solo se la memoria e' cambiata."""
    import numpy as np
    firma = conn.execute("SELECT count(*) AS n, COALESCE(max(pezzo_id),0) AS m, count(DISTINCT documento_id) AS d FROM pezzi_vettori").fetchone()
    f = f"{firma['n']}:{firma['m']}:{firma['d']}"
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'relazioni_firma'").fetchone()
    if r and r["valore"] == f:
        return 0
    c = _matrice(conn)
    if len(c["pezzi"]) == 0:
        return relaziona_parole(conn)
    ids = np.unique(c["docs"])[:MAX_DOC_RELAZIONI]
    D = np.zeros((len(ids), DIM), dtype=np.float32)
    for i, d in enumerate(ids):
        v = c["M"][c["docs"] == d].mean(axis=0)
        D[i] = v / (np.linalg.norm(v) or 1.0)
    S = D @ D.T
    np.fill_diagonal(S, -1)
    coppie = {}
    for i in range(len(ids)):
        for j in np.argsort(-S[i])[:VICINI]:
            if S[i, j] >= SOGLIA_TEMA:
                a, b = sorted((int(ids[i]), int(ids[j])))
                coppie[(a, b)] = float(S[i, j])
    conn.execute("DELETE FROM documenti_relazioni")
    for (a, b), v in coppie.items():
        conn.execute("INSERT INTO documenti_relazioni (documento_a, documento_b, somiglianza) VALUES (%s,%s,%s)", (a, b, v))
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('relazioni_firma', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (f,))
    conn.commit()
    return len(coppie)


def correlati(conn, agente_id: int, doc_ids: list[int], limite: int = 5) -> list[str]:
    """Nomi dei documenti sullo stesso tema di quelli dati, tra quelli che l'agente puo' vedere (e che non sta gia' usando)."""
    if not doc_ids:
        return []
    from . import memoria
    visibili = {d["id"]: d["nome"] for d in memoria.documenti_visibili(conn, agente_id)}
    righe = conn.execute("""SELECT CASE WHEN documento_a = ANY(%(d)s) THEN documento_b ELSE documento_a END AS altro, somiglianza FROM documenti_relazioni
                            WHERE documento_a = ANY(%(d)s) OR documento_b = ANY(%(d)s) ORDER BY somiglianza DESC""", {"d": doc_ids}).fetchall()
    out = []
    for r in righe:
        if r["altro"] in visibili and r["altro"] not in doc_ids and visibili[r["altro"]] not in out:
            out.append(visibili[r["altro"]])
    return out[:limite]


def temi(conn, massimo: int = 12) -> list[dict]:
    """Gruppi di documenti collegati tra loro (almeno 3), per mostrare a Lorenzo su quali argomenti ci sono piu' fonti."""
    padre = {}
    def trova(x):
        while padre.setdefault(x, x) != x:
            padre[x] = padre[padre[x]]; x = padre[x]
        return x
    for r in conn.execute("SELECT documento_a, documento_b FROM documenti_relazioni").fetchall():
        padre[trova(r["documento_a"])] = trova(r["documento_b"])
    gruppi = {}
    for x in list(padre):
        gruppi.setdefault(trova(x), []).append(x)
    nomi = {d["id"]: d["nome"] for d in conn.execute("SELECT id, nome FROM documenti").fetchall()}
    return [{"documenti": [nomi.get(i, "?") for i in sorted(g)][:12], "quanti": len(g)} for g in sorted(gruppi.values(), key=len, reverse=True) if len(g) >= 3][:massimo]

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
        return {**stato(conn), "temi": temi(conn), "relazioni": conn.execute("SELECT count(*) AS n FROM documenti_relazioni").fetchone()["n"], "importazioni": conn.execute("SELECT id, origine, nome_file, stato, conversazioni, importate, saltate, errore, creato_il FROM importazioni_chat ORDER BY id DESC LIMIT 10").fetchall()}


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
