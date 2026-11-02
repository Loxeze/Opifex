#!/usr/bin/env python3
"""Indice dell'archivio (v0.2) - memoria personale ricercabile.

Legge le tue cartelle SENZA mai modificarle e costruisce un indice (un solo file SQLite) con: nome e percorso, testo dei documenti,
trascrizione di audio e video (faster-whisper), vettori di immagini e fotogrammi video (CLIP multilingue). Poi si cerca con parole chiave
e con frasi in italiano ("interno del castello al tramonto"). Le funzioni pesanti sono opzionali: senza i pacchetti indicizza comunque nomi e testi.

Uso:
  python indice.py scansiona CARTELLA [CARTELLA ...] [--db indice.db] [--limite N] [--passo-video 30]
  python indice.py cerca "frase" [--db indice.db] [-n 10]
  python indice.py stato [--db indice.db]
  python indice.py servi [--db indice.db] [--porta 8765] [--ascolta 127.0.0.1] [--chiave SEGRETO]
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import numpy as np
except ImportError:
    np = None

log = logging.getLogger("indice")
if sys.platform == "win32":   # le librerie CUDA di PyTorch servono anche a Whisper
    for _p in sys.path:
        _d = os.path.join(_p, "torch", "lib")
        if os.path.isdir(_d):
            try:
                os.add_dll_directory(_d)
                os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
            except OSError:
                pass
EST_TESTO = {".txt", ".md", ".csv", ".srt", ".vtt", ".html", ".htm", ".json", ".xml", ".tex", ".rtf"}
EST_IMG = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
EST_VID = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".mts", ".m2ts", ".mpg", ".mpeg", ".webm", ".m4v"}
EST_AUD = {".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac", ".aac", ".ogg"}
IGNORA_DIR = {"$recycle.bin", "system volume information", "@eadir", "#recycle", ".git", "node_modules", "__pycache__", "proxy", "cache"}
BLOCCO_TESTO = 1200
MODELLO_CLIP = os.environ.get("INDICE_CLIP", "xlm-roberta-base-ViT-B-32|laion5b_s13b_b90k")
MODELLO_WHISPER = os.environ.get("INDICE_WHISPER", "medium")

SCHEMA = """
CREATE TABLE IF NOT EXISTS file (id INTEGER PRIMARY KEY, radice TEXT NOT NULL, rel TEXT NOT NULL, tipo TEXT, dimensione INTEGER, mtime REAL,
  durata REAL, larghezza INTEGER, altezza INTEGER, data_ripresa TEXT, stato TEXT NOT NULL DEFAULT 'nuovo', errore TEXT, indicizzato REAL,
  UNIQUE (radice, rel));
CREATE VIRTUAL TABLE IF NOT EXISTS testi USING fts5(testo, file_id UNINDEXED, tipo UNINDEXED, pos UNINDEXED, tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS vettore (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL, pos REAL, dim INTEGER, v BLOB);
CREATE INDEX IF NOT EXISTS vettore_file ON vettore(file_id);
CREATE TABLE IF NOT EXISTS radici (percorso TEXT PRIMARY KEY, aggiunta REAL);
"""


def apri(db: str) -> sqlite3.Connection:
    c = sqlite3.connect(db, check_same_thread=False, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


# ---------- strumenti opzionali (caricati solo se servono) ----------
class Finto:
    """Solo per i test: vettori e trascrizioni deterministici, senza modelli."""
    dim = 64

    def _v(self, s: str):
        h = hashlib.sha256(s.lower().encode()).digest()
        a = np.frombuffer(h[: self.dim], dtype=np.uint8).astype("float32") - 127.5
        return a / (np.linalg.norm(a) or 1)

    def immagini(self, percorsi):
        return [self._v(Path(p).stem.split("_")[0]) for p in percorsi]

    def testo(self, s):
        return self._v(s)

    def trascrivi(self, wav):
        return [(0.0, "trascrizione di prova castello torre")]


class Modelli:
    def __init__(self, finto=False):
        self.finto = Finto() if finto else None
        self._clip = self._whisper = None
        self.clip_ok = self.whisper_ok = None

    def _carica_clip(self):
        if self._clip or self.clip_ok is False:
            return self._clip
        try:
            import open_clip
            import torch
            nome, pre = MODELLO_CLIP.split("|")
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            m, _, prep = open_clip.create_model_and_transforms(nome, pretrained=pre, device=dev)
            self._clip = (m.eval(), prep, open_clip.get_tokenizer(nome), dev, torch)
            self.clip_ok = True
            log.info("CLIP caricato su %s", dev)
        except Exception as e:  # noqa: BLE001
            self.clip_ok = False
            log.warning("Vettori di immagini non disponibili (%s): installa open_clip_torch, torch e pillow", type(e).__name__)
        return self._clip

    def immagini(self, percorsi):
        if self.finto:
            return self.finto.immagini(percorsi)
        c = self._carica_clip()
        if not c:
            return []
        from PIL import Image
        m, prep, _, dev, torch = c
        out = []
        for i in range(0, len(percorsi), 16):
            imgs = []
            for p in percorsi[i:i + 16]:
                try:
                    imgs.append(prep(Image.open(p).convert("RGB")))
                except Exception:  # noqa: BLE001
                    imgs.append(torch.zeros(3, 224, 224))
            with torch.no_grad():
                v = m.encode_image(torch.stack(imgs).to(dev)).float()
                v = v / v.norm(dim=-1, keepdim=True)
            out.extend(list(v.cpu().numpy()))
        return out

    def testo(self, s):
        if self.finto:
            return self.finto.testo(s)
        c = self._carica_clip()
        if not c:
            return None
        m, _, tok, dev, torch = c
        with torch.no_grad():
            v = m.encode_text(tok([s]).to(dev)).float()
            v = v / v.norm(dim=-1, keepdim=True)
        return v[0].cpu().numpy()

    def trascrivi(self, wav):
        if self.finto:
            return self.finto.trascrivi(wav)
        if self.whisper_ok is False:
            return []
        try:
            if not self._whisper:
                from faster_whisper import WhisperModel
                try:
                    self._whisper = WhisperModel(MODELLO_WHISPER, device="cuda", compute_type="int8_float16")
                except Exception:  # noqa: BLE001
                    self._whisper = WhisperModel(MODELLO_WHISPER, device="cpu", compute_type="int8")
                self.whisper_ok = True
            try:
                seg, _ = self._whisper.transcribe(wav, vad_filter=True)
                return [(float(s.start), s.text.strip()) for s in seg if s.text.strip()]
            except RuntimeError as e:   # tipico: librerie CUDA mancanti -> si continua sul processore
                log.warning("Scheda video non utilizzabile per Whisper (%s): passo al processore", str(e)[:80])
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(MODELLO_WHISPER, device="cpu", compute_type="int8")
                seg, _ = self._whisper.transcribe(wav, vad_filter=True)
                return [(float(s.start), s.text.strip()) for s in seg if s.text.strip()]
        except ImportError:
            self.whisper_ok = False
            log.warning("Trascrizione non disponibile: installa faster-whisper")
            return []


def ffmpeg() -> str:
    for c in (os.environ.get("FFMPEG"), "ffmpeg"):
        if c:
            try:
                subprocess.run([c, "-version"], capture_output=True, check=True)
                return c
            except Exception:  # noqa: BLE001
                continue
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        raise SystemExit("ffmpeg non trovato: installalo o imposta la variabile FFMPEG") from None


def sonda(p: Path) -> dict:
    t = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(p)], capture_output=True, text=True, errors="replace").stderr
    d = {}
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", t)
    if m:
        d["durata"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    v = re.search(r"Video:[^\n]*?,\s*(\d{2,5})x(\d{2,5})", t)
    if v:
        d["larghezza"], d["altezza"] = int(v[1]), int(v[2])
    c = re.search(r"creation_time\s*:\s*(\S+)", t)
    if c:
        d["data_ripresa"] = c[1][:19]
    return d


# ---------- estrazione ----------
def testo_di(p: Path, est: str) -> str:
    if est in EST_TESTO:
        t = p.read_bytes()[:3_000_000].decode("utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", t) if est in (".html", ".htm", ".xml") else t
    if est == ".docx":
        with zipfile.ZipFile(p) as z:
            x = z.read("word/document.xml").decode("utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", x.replace("</w:p>", "\n"))
    if est == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages[:300])
    return ""


def blocchi(t: str) -> list[str]:
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t).strip()
    out, cur = [], ""
    for riga in t.split("\n"):
        if len(cur) + len(riga) > BLOCCO_TESTO and cur:
            out.append(cur)
            cur = ""
        cur += (" " if cur else "") + riga
    if cur:
        out.append(cur)
    return out[:2000]


def fotogrammi(p: Path, passo: int, cartella: Path, durata: float) -> list[tuple[float, str]]:
    """Un fotogramma ogni `passo` secondi con ricerca diretta (-ss prima di -i): non decodifica tutto il video, quindi e' veloce anche su file enormi."""
    n = max(1, min(int((durata or passo) // passo) + 1, 600))
    out = []
    for i in range(n):
        t = i * passo
        if durata and t >= durata:
            break
        f = cartella / f"f_{i:05d}.jpg"
        subprocess.run([ffmpeg(), "-v", "error", "-ss", str(t), "-i", str(p), "-frames:v", "1", "-vf", "scale=336:-2", "-q:v", "4", "-y", str(f)], capture_output=True, timeout=300)
        if f.exists() and f.stat().st_size > 0:
            out.append((float(t), str(f)))
    return out


def salva_vettori(c, fid, pos_v):
    for pos, v in pos_v:
        a = np.asarray(v, dtype="float16")
        c.execute("INSERT INTO vettore (file_id, pos, dim, v) VALUES (?,?,?,?)", (fid, pos, int(a.shape[0]), a.tobytes()))


def indicizza_file(c, mod: Modelli, riga, radice: Path, passo: int):
    p = radice / riga["rel"]
    est = p.suffix.lower()
    fid = riga["id"]
    c.execute("DELETE FROM testi WHERE file_id = ?", (fid,))
    c.execute("DELETE FROM vettore WHERE file_id = ?", (fid,))
    c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (riga["rel"].replace("/", " ").replace("_", " ").replace("-", " "), fid, "nome", 0))
    info = {}
    if est in EST_TESTO or est in (".docx", ".pdf"):
        for i, b in enumerate(blocchi(testo_di(p, est))):
            c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (b, fid, "testo", i))
    elif est in EST_IMG:
        try:
            from PIL import Image
            with Image.open(p) as im:
                info["larghezza"], info["altezza"] = im.size
                ex = im.getexif()
                if ex.get(36867) or ex.get(306):
                    info["data_ripresa"] = str(ex.get(36867) or ex.get(306))[:19]
        except Exception:  # noqa: BLE001
            pass
        if np is not None:
            salva_vettori(c, fid, [(0.0, v) for v in mod.immagini([str(p)])])
    elif est in EST_VID or est in EST_AUD:
        info = sonda(p)
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "a.wav")
            r = subprocess.run([ffmpeg(), "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000", wav], capture_output=True, timeout=7200)
            if r.returncode == 0 and os.path.exists(wav):
                for t0, tx in mod.trascrivi(wav):
                    c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (tx, fid, "parlato", t0))
            if est in EST_VID and np is not None:
                fr = fotogrammi(p, passo, Path(tmp), info.get("durata") or 0)
                if fr:
                    salva_vettori(c, fid, list(zip([t for t, _ in fr], mod.immagini([f for _, f in fr]))))
    c.execute("UPDATE file SET stato='ok', errore=NULL, indicizzato=?, durata=?, larghezza=?, altezza=?, data_ripresa=? WHERE id=?",
              (time.time(), info.get("durata"), info.get("larghezza"), info.get("altezza"), info.get("data_ripresa"), fid))


PROG = {"in_corso": False, "fatti": 0, "da_fare": 0, "corrente": "", "ferma": False, "esito": ""}


def scansiona(db, cartelle, limite=0, passo=30, finto=False):
    c = apri(db)
    mod = Modelli(finto)
    nuovi = 0
    for rad in cartelle:
        radice = Path(rad).resolve()
        for dp, dn, fn in os.walk(radice):
            dn[:] = [d for d in dn if d.lower() not in IGNORA_DIR and not d.startswith(".")]
            for f in fn:
                est = Path(f).suffix.lower()
                if f.startswith(".") or est not in (EST_TESTO | EST_IMG | EST_VID | EST_AUD | {".docx", ".pdf"}):
                    continue
                p = Path(dp) / f
                try:
                    st = p.stat()
                except OSError:
                    continue
                rel = p.relative_to(radice).as_posix()
                tipo = "testo" if est in EST_TESTO or est in (".docx", ".pdf") else "immagine" if est in EST_IMG else "video" if est in EST_VID else "audio"
                r = c.execute("SELECT id, dimensione, mtime, stato FROM file WHERE radice=? AND rel=?", (str(radice), rel)).fetchone()
                if r and r["stato"] == "ok" and r["dimensione"] == st.st_size and abs(r["mtime"] - st.st_mtime) < 1:
                    continue
                if r:
                    c.execute("UPDATE file SET dimensione=?, mtime=?, stato='nuovo' WHERE id=?", (st.st_size, st.st_mtime, r["id"]))
                else:
                    c.execute("INSERT INTO file (radice, rel, tipo, dimensione, mtime) VALUES (?,?,?,?,?)", (str(radice), rel, tipo, st.st_size, st.st_mtime))
                nuovi += 1
        c.commit()
    coda = c.execute("SELECT * FROM file WHERE stato IN ('nuovo') ORDER BY CASE tipo WHEN 'testo' THEN 0 WHEN 'immagine' THEN 1 WHEN 'audio' THEN 2 ELSE 3 END, id").fetchall()
    log.info("%d file da indicizzare", len(coda))
    fatti = 0
    PROG.update(da_fare=len(coda), fatti=0)
    for riga in coda:
        if (limite and fatti >= limite) or PROG["ferma"]:
            break
        PROG["corrente"] = riga["rel"]
        t0 = time.time()
        try:
            indicizza_file(c, mod, riga, Path(riga["radice"]), passo)
        except Exception as e:  # noqa: BLE001 - un file rotto non ferma l'archivio
            c.execute("UPDATE file SET stato='errore', errore=? WHERE id=?", (f"{type(e).__name__}: {e}"[:300], riga["id"]))
            log.warning("%s: %s", riga["rel"], e)
        c.commit()
        fatti += 1
        PROG["fatti"] = fatti
        log.info("[%d/%d] %s (%.1f s)", fatti, len(coda), riga["rel"], time.time() - t0)
    return {"da_fare": len(coda), "fatti": fatti}


# ---------- ricerca ----------
def _fts_query(q: str) -> str:
    parole = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]
    return " OR ".join(f'"{w}"*' for w in parole[:12])


SOGLIA_SIM = float(os.environ.get("INDICE_SOGLIA", "0.20"))   # sotto questa somiglianza CLIP un fotogramma non e' una risposta


def cerca(db, q, n=10, finto=False):
    c = apri(db)
    punti: dict = {}

    def aggiungi(fid, pos, tipo, testo, rango, peso):
        k = (fid, tipo)
        p = punti.setdefault(k, {"file_id": fid, "tipo": tipo, "pos": pos, "testo": testo, "score": 0.0})
        p["score"] += peso / (60 + rango)
    fq = _fts_query(q)
    if fq:
        for i, r in enumerate(c.execute("SELECT file_id, tipo, pos, snippet(testi, 0, '[', ']', ' … ', 18) AS s FROM testi WHERE testi MATCH ? ORDER BY bm25(testi) LIMIT ?", (fq, n * 4))):
            aggiungi(r["file_id"], r["pos"], r["tipo"], r["s"], i, 1.0)
    if np is not None and c.execute("SELECT 1 FROM vettore LIMIT 1").fetchone():
        v = Modelli(finto).testo(q)
        if v is not None:
            righe = c.execute("SELECT file_id, pos, dim, v FROM vettore").fetchall()
            ok = [r for r in righe if r["dim"] == len(v)]
            if ok:
                m = np.stack([np.frombuffer(r["v"], dtype="float16").astype("float32") for r in ok])
                s = m @ (np.asarray(v, dtype="float32"))
                soglia = 0.6 if finto else SOGLIA_SIM
                for rango, i in enumerate([k for k in np.argsort(-s)[: n * 4] if s[k] >= soglia]):
                    aggiungi(ok[i]["file_id"], ok[i]["pos"], "immagine", f"somiglianza visiva {float(s[i]):.2f}", rango, 0.8)
    ris = sorted(punti.values(), key=lambda x: -x["score"])
    visti, out = set(), []
    for r in ris:
        if r["file_id"] in visti:
            continue
        visti.add(r["file_id"])
        f = c.execute("SELECT radice, rel, tipo, durata, data_ripresa FROM file WHERE id=?", (r["file_id"],)).fetchone()
        out.append({"file": f["rel"], "radice": f["radice"], "percorso": str(Path(f["radice"]) / f["rel"]), "tipo": f["tipo"], "dove": r["tipo"],
                    "secondo": round(r["pos"], 1) if r["tipo"] in ("parlato", "immagine") and f["tipo"] in ("video", "audio") else None,
                    "estratto": r["testo"], "data": f["data_ripresa"], "punteggio": round(r["score"] * 100, 2)})
        if len(out) >= n:
            break
    return out


def stato(db):
    c = apri(db)
    return {"file": {r["stato"]: r["n"] for r in c.execute("SELECT stato, count(*) n FROM file GROUP BY stato")},
            "per_tipo": {r["tipo"]: r["n"] for r in c.execute("SELECT tipo, count(*) n FROM file GROUP BY tipo")},
            "vettori": c.execute("SELECT count(*) n FROM vettore").fetchone()["n"],
            "blocchi_di_testo": c.execute("SELECT count(*) n FROM testi").fetchone()["n"],
            "errori": [dict(r) for r in c.execute("SELECT rel, errore FROM file WHERE stato='errore' LIMIT 20")]}


# ---------- cartelle: cosa e' indicizzato e cosa no ----------
def _nc(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def radici_elenco(db):
    c = apri(db)
    r = [x["percorso"] for x in c.execute("SELECT percorso FROM radici ORDER BY percorso")]
    for x in c.execute("SELECT DISTINCT radice FROM file"):   # indici creati prima dell'elenco
        if x["radice"] not in r:
            c.execute("INSERT OR IGNORE INTO radici (percorso, aggiunta) VALUES (?,?)", (x["radice"], time.time())); r.append(x["radice"])
    c.commit()
    return sorted(r)


def radice_aggiungi(db, p: str):
    p = str(Path(p).resolve())
    if not os.path.isdir(p):
        raise ValueError("Questa cartella non esiste su questo computer")
    c = apri(db)
    c.execute("INSERT OR IGNORE INTO radici (percorso, aggiunta) VALUES (?,?)", (p, time.time())); c.commit()
    return p


def radice_togli(db, p: str):
    """Toglie la cartella dall'indice (cancella solo i dati dell'indice, mai i tuoi file)."""
    c = apri(db)
    ids = [x["id"] for x in c.execute("SELECT id FROM file WHERE radice=?", (p,))]
    for i in range(0, len(ids), 500):
        blocco = ids[i:i + 500]
        q = ",".join("?" * len(blocco))
        c.execute(f"DELETE FROM testi WHERE file_id IN ({q})", blocco)
        c.execute(f"DELETE FROM vettore WHERE file_id IN ({q})", blocco)
    c.execute("DELETE FROM file WHERE radice=?", (p,))
    c.execute("DELETE FROM radici WHERE percorso=?", (p,))
    c.commit()
    return len(ids)


def _conteggi(c, radice: str, rel_dir: str):
    """Per ogni sottocartella diretta di rel_dir: file per stato. La chiave '' = file direttamente nella cartella."""
    pre = (rel_dir + "/") if rel_dir else ""
    out: dict[str, dict] = {}
    for r in c.execute("""SELECT fig, stato, count(*) n FROM (
            SELECT CASE WHEN instr(substr(rel, ?), '/') > 0 THEN substr(rel, ?, instr(substr(rel, ?), '/') - 1) ELSE '' END AS fig, stato
            FROM file WHERE radice = ? AND substr(rel, 1, ?) = ?) GROUP BY fig, stato""",
                       (len(pre) + 1, len(pre) + 1, len(pre) + 1, radice, len(pre), pre)):
        out.setdefault(r["fig"], {})[r["stato"]] = r["n"]
    return out


def _etichetta(cnt: dict):
    n = sum(cnt.values())
    if n == 0:
        return "vuota"
    if cnt.get("errore"):
        return "errori"
    if cnt.get("nuovo"):
        return "in_coda"
    return "indicizzata"


def cartelle(db, percorso: str = ""):
    c = apri(db)
    rad = radici_elenco(db)
    def somma(radice, rel):
        tot: dict = {}
        pre = (rel + "/") if rel else ""
        for r in c.execute("SELECT stato, count(*) n FROM file WHERE radice=? AND substr(rel,1,?)=? GROUP BY stato", (radice, len(pre), pre)):
            tot[r["stato"]] = r["n"]
        return tot
    if not percorso:
        voci = []
        for r in rad:
            t = somma(r, "")
            voci.append({"nome": r, "percorso": r, "stato": _etichetta(t), "conteggi": t, "radice": True, "esiste": os.path.isdir(r)})
        unita = []
        if sys.platform == "win32":
            unita = [f"{l}:\\" for l in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.isdir(f"{l}:\\")]
        else:
            unita = ["/"] + [str(Path.home())]
        return {"percorso": "", "su": None, "voci": voci, "unita": unita}
    p = Path(percorso)
    if not p.is_dir():
        raise ValueError("Cartella non raggiungibile da questo computer")
    pn = _nc(p)
    dentro = next((r for r in rad if pn == _nc(r) or pn.startswith(_nc(r) + os.sep)), None)
    cnt = {}
    if dentro:
        rel = "" if pn == _nc(dentro) else Path(os.path.relpath(str(p), dentro)).as_posix()
        cnt = _conteggi(c, dentro, rel)
    voci = []
    try:
        figli = sorted((e for e in os.scandir(p) if e.is_dir(follow_symlinks=False)), key=lambda e: e.name.lower())
    except OSError as e:
        raise ValueError(f"Non posso leggere questa cartella ({type(e).__name__})")
    for e in figli:
        nome = e.name
        if nome.startswith(".") or nome.lower() in IGNORA_DIR:
            voci.append({"nome": nome, "percorso": e.path, "stato": "esclusa", "conteggi": {}}); continue
        if dentro:
            t = cnt.get(nome, {})
            voci.append({"nome": nome, "percorso": e.path, "stato": _etichetta(t) if t else "indicizzata_vuota", "conteggi": t})
        else:
            en = _nc(e.path)
            sua = next((r for r in rad if _nc(r) == en), None)
            if sua:
                t = somma(sua, "")
                voci.append({"nome": nome, "percorso": e.path, "stato": _etichetta(t) if t else "indicizzata_vuota", "conteggi": t, "radice": True}); continue
            contiene = next((r for r in rad if _nc(r).startswith(en + os.sep)), None)
            voci.append({"nome": nome, "percorso": e.path, "stato": "contiene" if contiene else "fuori", "conteggi": {}})
    su = str(p.parent) if p.parent != p else ""
    return {"percorso": str(p), "su": su, "dentro_radice": dentro, "file_qui": cnt.get("", {}) if dentro else {}, "voci": voci}


PAGINA = r"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Indice dell'archivio</title>
<style>:root{--bg:#1d1612;--fg:#f1e6da;--mu:#b39d89;--ac:#e8924a;--ca:rgba(255,255,255,.06);--li:rgba(255,255,255,.14);color-scheme:dark}
body{margin:0;background:radial-gradient(1200px 700px at 70% -10%,#5a3a22 0%,#1d1612 60%) fixed;color:var(--fg);font:16px system-ui,sans-serif}main{max-width:860px;margin:0 auto;padding:24px 16px 60px}h1{font-size:1.5rem;margin:0 0 4px}p.s{color:var(--mu);margin:0 0 20px}
section{backdrop-filter:blur(18px);background:var(--ca);border:1px solid var(--li);border-radius:22px;padding:18px;margin-bottom:16px}h2{font-size:1rem;margin:0 0 10px}textarea,input{width:100%;box-sizing:border-box;padding:9px;border:1px solid var(--li);border-radius:7px;background:var(--bg);color:var(--fg);font:inherit}
button{background:var(--ac);color:#2a1608;font-weight:600;border:0;border-radius:7px;padding:9px 16px;font:inherit;cursor:pointer;margin:8px 8px 0 0}button.g{background:transparent;color:var(--fg);border:1px solid var(--li)}
.barra{height:8px;background:var(--li);border-radius:5px;overflow:hidden;margin:10px 0 4px}.barra i{display:block;height:100%;background:var(--ac);width:0}.r{border-top:1px solid var(--li);padding:10px 0}.r b{word-break:break-all}.m{color:var(--mu);font-size:.9rem}.f{display:flex;align-items:center;gap:10px;border-top:1px solid var(--li);padding:8px 2px}.f .n{flex:1;min-width:0;word-break:break-all;cursor:pointer}.f.d .n{cursor:default;color:var(--mu)}.t{font-size:.78rem;border-radius:20px;padding:2px 9px;border:1px solid var(--li);white-space:nowrap}.t.ok{background:#1f6b5a22;color:var(--ac)}.t.cd{background:#c9a02722}.t.er{background:#b4402a22}.t.fu{color:var(--mu)}a{color:var(--ac)}button.p{padding:4px 11px;margin:0;font-size:.85rem}.sc{display:flex;gap:8px;margin-bottom:16px}.sc button{margin:0}.cz{max-height:46vh;overflow:auto;margin:12px 0;display:flex;flex-direction:column;gap:8px}.mt{padding:9px 12px;border-radius:12px;max-width:88%;white-space:pre-wrap;word-break:break-word}.mt.u{align-self:flex-end;background:var(--ac);color:#2a1608}.mt.a{align-self:flex-start;background:var(--bg);border:1px solid var(--li)}</style></head>
<body><main><h1>Opifex · Archivio</h1><p class="s">Legge le tue cartelle senza modificarle e le rende ricercabili; qui puoi anche dialogare con gli agenti di Opifex. L'indice resta su questo computer.</p>
<div class="sc"><button id="t1">Archivio</button><button id="t2" class="g">Dialogo con Opifex</button></div>
<div id="v1"><section><h2>1. Cartelle</h2><div class="m">Sfoglia il computer: vedi cosa e' gia' nell'indice, cosa e' in coda e cosa e' ancora fuori.</div>
<div id="cr" class="m" style="margin:10px 0 4px"></div><div id="cl"></div>
<div style="display:flex;gap:8px;margin-top:10px"><input id="np" placeholder="Oppure scrivi un percorso, per esempio D:\Montarrenti o Z:\Archivio\Video"><button id="na" class="g" style="margin:0;white-space:nowrap">Aggiungi</button></div>
<button id="av">Indicizza tutto</button><button id="fe" class="g">Ferma</button><div class="barra"><i id="b"></i></div><div class="m" id="p">Pronto.</div></section>
<section><h2>2. Cerca</h2><input id="q" placeholder="Per esempio: interno del castello al tramonto, oppure una frase detta nell'intervista"><button id="ce">Cerca</button><div id="ri"></div></section></div>
<div id="v2" hidden>
<section id="ac"><h2>Collegati a Opifex</h2><div class="m">Le stesse credenziali con cui entri dal sito. La password non viene salvata: resta collegato finche' tieni aperta la finestra.</div>
<input id="ou" placeholder="Indirizzo di Opifex" style="margin-top:10px"><input id="oe" placeholder="Email" style="margin-top:8px"><input id="op" type="password" placeholder="Password" style="margin-top:8px">
<input id="oc" placeholder="Codice a 6 cifre (secondo fattore)" style="margin-top:8px" hidden><button id="ol">Entra</button><div class="m" id="om"></div><div class="m" id="pn" style="margin-top:6px"></div></section>
<section id="dl" hidden><h2>Dialogo <span class="m" id="on"></span></h2>
<div style="display:flex;gap:8px"><select id="oa" style="flex:1;padding:9px;border-radius:7px;border:1px solid var(--li);background:var(--bg);color:var(--fg)"></select>
<select id="of" style="padding:9px;border-radius:7px;border:1px solid var(--li);background:var(--bg);color:var(--fg)"><option value="pubblico">Solo dati pubblici</option><option value="interno" selected>Dati interni</option><option value="riservato">Riservato</option></select></div>
<div id="oz" class="cz"></div>
<textarea id="ot" rows="3" placeholder="Scrivi all'agente… (Invio per inviare, Maiusc+Invio per andare a capo)"></textarea>
<label class="m" style="display:block;margin-top:6px"><input type="checkbox" id="oar" style="width:auto"> Allega ciò che trovo nell'archivio su questo computer (percorsi ed estratti)</label>
<button id="oi">Invia</button><button id="oq" class="g">Esci da Opifex</button></section></div></main>
<script>const $=i=>document.getElementById(i);async function j(u,o){const r=await fetch(u,o);return r.json()}
const E=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));let qui='';
$('av').onclick=async()=>{const r=await j('/api/avvia',{method:'POST',body:JSON.stringify({})});if(r.errore)alert(r.errore);else carica(qui)};
$('na').onclick=async()=>{const v=$('np').value.trim();if(!v)return;const r=await j('/api/radice',{method:'POST',body:JSON.stringify({aggiungi:v})});if(r.errore)return alert(r.errore);$('np').value='';carica(qui)};
async function azione(corpo){const r=await j('/api/radice',{method:'POST',body:JSON.stringify(corpo)});if(r.errore)alert(r.errore);carica(qui)}
const ET={indicizzata:['ok','Indicizzata'],indicizzata_vuota:['ok','Nessun file supportato'],in_coda:['cd','In coda'],errori:['er','Con errori'],vuota:['fu','Vuota'],fuori:['fu','Non indicizzata'],contiene:['cd','Contiene cartelle indicizzate'],esclusa:['fu','Esclusa (di sistema)']};
function num(c){const o=[];if(c.ok)o.push(c.ok+' fatti');if(c.nuovo)o.push(c.nuovo+' in coda');if(c.errore)o.push(c.errore+' errori');return o.join(' - ')}
async function carica(p){qui=p||'';const r=await j('/api/cartelle?percorso='+encodeURIComponent(qui));if(r.errore){$('cl').innerHTML='<div class="m">'+E(r.errore)+'</div>';return}
 const rad=!r.percorso;$('cr').innerHTML=rad?'Cartelle nell\'indice':'<a href="#" id="su">&larr; indietro</a> &nbsp; <b>'+E(r.percorso)+'</b>'+(r.file_qui&&num(r.file_qui)?' <span class="m">- qui dentro: '+E(num(r.file_qui))+'</span>':'');
 let h='';for(const v of r.voci){const e=ET[v.stato]||['fu',v.stato];const mie=v.radice;
  h+=`<div class="f${v.stato==='esclusa'?' d':''}"><div class="n" data-p="${E(v.percorso)}">&#128193; ${E(v.nome)}</div><span class="m">${E(num(v.conteggi||{}))}</span><span class="t ${e[0]}">${e[1]}</span>`+
  (mie?`<button class="g p" data-t="${E(v.percorso)}">Togli</button>`:(v.stato==='fuori'?`<button class="p" data-a="${E(v.percorso)}">Aggiungi</button>`:''))+'</div>'}
 if(rad){h=(h||'<div class="m">Nessuna cartella aggiunta.</div>')+'<div class="m" style="margin-top:10px">Sfoglia da: '+(r.unita||[]).map(u=>`<a href="#" data-p="${E(u)}">${E(u)}</a>`).join(' &nbsp; ')+'</div>'}
 $('cl').innerHTML=h;$('cl').querySelectorAll('[data-p]').forEach(x=>x.onclick=ev=>{ev.preventDefault();if(!x.classList.contains('d')&&!x.parentElement.classList.contains('d'))carica(x.dataset.p)});
 $('cl').querySelectorAll('[data-a]').forEach(x=>x.onclick=()=>azione({aggiungi:x.dataset.a}));
 $('cl').querySelectorAll('[data-t]').forEach(x=>x.onclick=()=>{if(confirm('Togliere questa cartella dall\'indice? I tuoi file restano dove sono.'))azione({togli:x.dataset.t})});
 if($('su'))$('su').onclick=ev=>{ev.preventDefault();carica(r.su||'')}}
carica('');setInterval(()=>{if(!qui)carica('')},15000);
$('fe').onclick=()=>j('/api/ferma',{method:'POST'});
async function agg(){try{const r=await j('/api/progresso');const pc=r.da_fare?Math.round(100*r.fatti/r.da_fare):0;$('b').style.width=pc+'%';
$('p').textContent=r.in_corso?`Indicizzo ${r.fatti} di ${r.da_fare} file (${pc}%) - ${r.corrente}`:(r.esito||'Pronto.')+(r.totale?` Nell'indice: ${r.totale} file.`:'')}catch(e){}}
setInterval(agg,2000);agg();
$('t1').onclick=()=>sc(1);$('t2').onclick=()=>sc(2);
function sc(n){$('v1').hidden=n!==1;$('v2').hidden=n!==2;$('t1').className=n===1?'':'g';$('t2').className=n===2?'':'g';if(n===2)opStato()}
let passo2=false;
async function opStato(){const r=await j('/api/opifex/stato');$('ou').value=$('ou').value||r.url||'https://app.opifex.space';$('oe').value=$('oe').value||r.email||'';
 $('ac').hidden=!!r.collegato;$('dl').hidden=!r.collegato;if(r.collegato){$('on').textContent='· '+(r.nome||'');if(!$('oa').options.length)opAgenti()}$('pn').textContent=r.collegato?('Browser per Opifex sul tuo computer: '+(r.ponte||'')):''}
setInterval(()=>{if(!$('dl').hidden)opStato()},6000);
async function opAgenti(){const r=await j('/api/opifex/agenti');if(r.errore){$('om').textContent=r.errore;return}
 $('oa').innerHTML=(r.agenti||[]).map(a=>`<option value="${a.id}">${E(a.nome)} - ${E(a.ruolo||'')}</option>`).join('')}
$('ol').onclick=async()=>{$('om').textContent='Accedo…';let r;
 if(!passo2)r=await j('/api/opifex/login',{method:'POST',body:JSON.stringify({url:$('ou').value.trim(),email:$('oe').value.trim(),password:$('op').value})});
 else r=await j('/api/opifex/2fa',{method:'POST',body:JSON.stringify({codice:$('oc').value.trim()})});
 if(r.errore){$('om').textContent=r.errore;return}
 if(r.passo==='codice'){passo2=true;$('oc').hidden=false;$('op').hidden=true;$('om').textContent='Inserisci il codice del tuo secondo fattore.';return}
 passo2=false;$('oc').hidden=true;$('op').hidden=false;$('op').value='';$('oc').value='';$('om').textContent='';opStato()};
$('oq').onclick=async()=>{await j('/api/opifex/esci',{method:'POST'});$('oz').innerHTML='';$('oa').innerHTML='';opStato()};
function bolla(t,c){const d=document.createElement('div');d.className='mt '+c;d.textContent=t;$('oz').appendChild(d);$('oz').scrollTop=1e9;return d}
async function invia(){const m=$('ot').value.trim();if(!m||!$('oa').value)return;$('ot').value='';bolla(m,'u');const att=bolla('…','a');
 const r=await j('/api/opifex/chat',{method:'POST',body:JSON.stringify({agente_id:Number($('oa').value),messaggio:m,fascia:$('of').value,archivio:$('oar').checked})});
 if(r.errore){att.textContent='⚠ '+r.errore;return}
 for(let i=0;i<150;i++){await new Promise(z=>setTimeout(z,2000));const s=await j('/api/opifex/coda?id='+r.coda_id);
  if(s.errore){att.textContent='⚠ '+s.errore;return}
  if(s.stato==='finito'){const x=s.risultato||{};att.textContent=x.risposta||x.testo||JSON.stringify(x);$('oz').scrollTop=1e9;return}
  if(s.stato==='errore'){att.textContent='⚠ '+(s.errore||'Errore');return}}
 att.textContent='⚠ L\'agente sta ancora lavorando: la risposta comparira\' in Opifex, nella Chat.'}
$('oi').onclick=invia;$('ot').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();invia()}};
const batti=()=>fetch('/api/vivo').catch(()=>{});batti();setInterval(batti,5000);addEventListener('pagehide',()=>{try{navigator.sendBeacon('/api/chiudi')}catch(e){}});
async function cerca(){const q=$('q').value.trim();if(!q)return;$('ri').textContent='Cerco...';const r=await j('/cerca?n=15&q='+encodeURIComponent(q));const e=t=>t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
$('ri').innerHTML=(r.risultati||[]).map(x=>`<div class="r"><b>${e(x.percorso)}</b>${x.secondo!=null?` <span class="m">al secondo ${x.secondo}</span>`:''}<div class="m">${e(x.tipo)} - ${e(x.dove)}</div><div>${e(x.estratto||'')}</div></div>`).join('')||'<div class="m">Nessun risultato.</div>'}
$('ce').onclick=cerca;$('q').onkeydown=e=>{if(e.key==='Enter')cerca()}</script></body></html>"""


OPI = {"url": "", "token": "", "nome": "", "sfida": "", "email": ""}
BATTITO = {"ultimo": 0.0, "chiuso": 0.0}


def _conf_file(db):
    return Path(db).with_name("opifex.json")


def _url_valido(u: str) -> str:
    from urllib.parse import urlparse as _p
    p = _p(u.strip())
    if not p.hostname or p.scheme not in ("https", "http") or p.username or p.password:
        raise ValueError("Indirizzo di Opifex non valido")
    if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("Per sicurezza serve un indirizzo https")
    return f"{p.scheme}://{p.netloc}"


def _opifex(metodo, percorso, corpo=None, auth=True, timeout=60):
    import urllib.request
    import urllib.error
    if not OPI["url"]:
        raise ValueError("Non sei collegato a Opifex")
    rq = urllib.request.Request(OPI["url"] + percorso, method=metodo, data=json.dumps(corpo).encode() if corpo is not None else None,
                                headers={"Content-Type": "application/json", "User-Agent": "Opifex-Archivio"})
    if auth and OPI["token"]:
        rq.add_header("Authorization", "Bearer " + OPI["token"])
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            det = json.loads(e.read()).get("detail")
        except Exception:  # noqa: BLE001
            det = None
        if e.code == 401 and auth:
            OPI["token"] = ""
            raise ValueError("Sessione scaduta: rientra in Opifex")
        raise ValueError(str(det)[:200] if det else f"Opifex ha risposto {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"Opifex non raggiungibile ({getattr(e, 'reason', e)})")


def _accesso_esito(r):
    if r.get("passo") == "ok":
        OPI.update(token=r["token"], nome=r.get("nome", ""), sfida="")
        return {"passo": "ok"}
    if r.get("passo") == "codice":
        OPI["sfida"] = r["sfida"]
        return {"passo": "codice"}
    return {"errore": "Completa prima l'accesso dal sito (attivazione del secondo fattore o cambio della password), poi riprova qui."}


def opifex_api(db, metodo, percorso, q, corpo):
    try:
        if percorso == "/api/opifex/stato":
            cf = {}
            try:
                cf = json.loads(_conf_file(db).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            return {"ponte": PONTE["stato"], "collegato": bool(OPI["token"]), "nome": OPI["nome"], "url": OPI["url"] or cf.get("url", ""), "email": OPI["email"] or cf.get("email", "")}
        if percorso == "/api/opifex/login":
            OPI.update(url=_url_valido(str(corpo.get("url", ""))), email=str(corpo.get("email", "")).strip(), token="", sfida="")
            try:
                _conf_file(db).write_text(json.dumps({"url": OPI["url"], "email": OPI["email"]}), encoding="utf-8")
            except OSError:
                pass
            return _accesso_esito(_opifex("POST", "/login", {"email": OPI["email"], "password": str(corpo.get("password", ""))}, auth=False))
        if percorso == "/api/opifex/2fa":
            if not OPI["sfida"]:
                return {"errore": "Ricomincia dall'accesso"}
            return _accesso_esito(_opifex("POST", "/login/2fa", {"sfida": OPI["sfida"], "codice": str(corpo.get("codice", ""))}, auth=False))
        if percorso == "/api/opifex/esci":
            OPI.update(token="", nome="", sfida="")
            return {"ok": True}
        if percorso == "/api/opifex/agenti":
            r = _opifex("GET", "/agenti")
            return {"agenti": [{"id": a["id"], "nome": a["nome"], "ruolo": a.get("ruolo")} for a in r if a.get("attivo") and a.get("tipo") != "sistema"]}
        if percorso == "/api/opifex/chat":
            m = str(corpo.get("messaggio", "")).strip()
            if not m or len(m) > 8000:
                return {"errore": "Messaggio vuoto o troppo lungo"}
            fascia = corpo.get("fascia") if corpo.get("fascia") in ("pubblico", "interno", "riservato") else "interno"
            if corpo.get("archivio"):
                trovati = cerca(db, m, 5)
                if trovati:
                    m += "\n\n[Dall'archivio sul computer di Lorenzo, ricerca per questo messaggio:]\n" + "\n".join(
                        f"- {x['percorso']}" + (f" (al secondo {x['secondo']})" if x.get("secondo") is not None else "") + f": {(x.get('estratto') or '')[:300]}" for x in trovati)
            r = _opifex("POST", f"/agenti/{int(corpo.get('agente_id'))}/chat", {"messaggio": m, "fascia_dati": fascia, "asincrono": True})
            return {"coda_id": r["coda_id"]}
        if percorso == "/api/opifex/coda":
            return _opifex("GET", f"/chat-coda/{int((q.get('id') or ['0'])[0])}")
    except (ValueError, TypeError, KeyError) as e:
        return {"errore": str(e)[:200]}
    return {"errore": "?"}


PONTE = {"stato": "in attesa dell'accesso a Opifex", "modulo": None}
PONTE_METODI = {"elenco", "apri", "chiudi", "schermo", "vai", "azione", "condividi", "leggi", "agente_apri", "agente_chiudi", "agente_leggi", "agente_clic", "agente_scrivi", "agente_scarica", "agente_lunghezza", "agente_tasto"}


def _ponte_modulo(db):
    """Scarica da Opifex il modulo del browser (lo stesso che gira sul server) e lo carica; None se non si puo' (es. Playwright mancante)."""
    import importlib.util
    import urllib.request
    if PONTE["modulo"] is not None:
        return PONTE["modulo"]
    if importlib.util.find_spec("playwright") is None:
        PONTE["stato"] = "manca il componente Playwright (si installa da solo alla prossima apertura dell'app)"
        return None
    try:
        m = _opifex("GET", "/desktop/manifesto", auth=False, timeout=15)
        f = (m or {}).get("finestre")
        if not f or not str(f.get("url", "")).startswith("/desktop/"):
            PONTE["stato"] = "Opifex non offre ancora il browser per il computer"
            return None
        dest = Path(db).with_name("finestre_pc.py")
        if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != f["sha256"]:
            with urllib.request.urlopen(urllib.request.Request(OPI["url"] + f["url"], headers={"User-Agent": "Opifex-Archivio"}), timeout=30) as r:
                dati = r.read()
            if hashlib.sha256(dati).hexdigest() != f["sha256"]:
                PONTE["stato"] = "aggiornamento del browser non verificato"
                return None
            dest.write_bytes(dati)
        os.environ["OPIFEX_PC"] = "1"
        spec = importlib.util.spec_from_file_location("finestre_pc", dest)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        PONTE["modulo"] = mod
        return mod
    except Exception as e:  # noqa: BLE001
        PONTE["stato"] = "browser non pronto (" + type(e).__name__ + ")"
        return None


def _ponte_esegui(mod, p):
    import base64
    if p.get("metodo") not in PONTE_METODI:
        raise ValueError("Operazione non ammessa")
    r = getattr(mod._locale, p["metodo"])(*(p.get("args") or []), **(p.get("kw") or {}))
    if isinstance(r, (bytes, bytearray)):
        return {"_bytes": base64.b64encode(bytes(r)).decode()}
    return r


def ponte_ciclo(db):
    """Chiede a Opifex i lavori da fare su questo computer (browser delle Finestre) e consegna i risultati."""
    while True:
        try:
            if not OPI["token"]:
                PONTE["stato"] = "in attesa dell'accesso a Opifex"
                time.sleep(3)
                continue
            mod = _ponte_modulo(db)
            PONTE["stato"] = "pronto" if mod else PONTE["stato"]
            lavoro = _opifex("GET", "/ponte/prossimo?attesa=20&finestre=" + ("true" if mod else "false"), timeout=40)
            if not lavoro or lavoro.get("nessuno"):
                continue
            esito = {"ok": True, "dati": None, "errore": ""}
            try:
                if lavoro["tipo"] != "finestre" or mod is None:
                    raise ValueError("Questo computer non puo' eseguire il lavoro")
                PONTE["stato"] = "al lavoro"
                esito["dati"] = _ponte_esegui(mod, lavoro["parametri"])
                PONTE["stato"] = "pronto"
            except Exception as e:  # noqa: BLE001
                esito.update(ok=False, errore=(str(e) if mod and isinstance(e, mod.ErroreFinestre) or isinstance(e, ValueError) else "Operazione non riuscita (" + type(e).__name__ + ")")[:400])
            try:
                _opifex("POST", f"/ponte/{lavoro['id']}/risultato", esito, timeout=30)
            except ValueError:
                pass
        except ValueError as e:
            PONTE["stato"] = str(e)[:120]
            time.sleep(4)
        except Exception:  # noqa: BLE001
            time.sleep(4)


def servi(db, porta, ascolta, chiave, finto=False, interfaccia=False, finestra=False):
    class H(BaseHTTPRequestHandler):
        def _r(self, cod, obj, tipo="application/json; charset=utf-8"):
            b = obj.encode() if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(cod); self.send_header("Content-Type", tipo); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def _ok(self, q):
            return not chiave or self.headers.get("Authorization", "") == "Bearer " + chiave or (q.get("chiave") or [""])[0] == chiave

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if interfaccia and u.path == "/":
                return self._r(200, PAGINA, "text/html; charset=utf-8")
            if interfaccia and u.path == "/api/vivo":
                BATTITO["ultimo"] = time.time()
                return self._r(200, {"ok": True})
            if interfaccia and u.path.startswith("/api/opifex/"):
                return self._r(200, opifex_api(db, "GET", u.path, q, {}))
            if not self._ok(q):
                return self._r(401, {"errore": "chiave mancante o errata"})
            try:
                if u.path == "/cerca":
                    return self._r(200, {"risultati": cerca(db, (q.get("q") or [""])[0], int((q.get("n") or ["10"])[0]), finto)})
                if u.path == "/stato":
                    return self._r(200, stato(db))
                if u.path == "/api/cartelle" and interfaccia:
                    try:
                        return self._r(200, cartelle(db, (q.get("percorso") or [""])[0]))
                    except ValueError as e:
                        return self._r(200, {"errore": str(e)})
                if u.path == "/api/progresso":
                    tot = sum(stato(db)["file"].values())
                    return self._r(200, {**PROG, "totale": tot})
                self._r(404, {"errore": "usa /cerca?q=... oppure /stato"})
            except Exception as e:  # noqa: BLE001
                self._r(500, {"errore": f"{type(e).__name__}: {e}"[:200]})

        def do_POST(self):
            if not interfaccia or not self._ok({}):
                return self._r(403, {"errore": "non consentito"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._r(400, {"errore": "richiesta non valida"})
            if self.path == "/api/chiudi":
                BATTITO["chiuso"] = time.time()
                return self._r(200, {"ok": True})
            if self.path.startswith("/api/opifex/"):
                return self._r(200, opifex_api(db, "POST", self.path, {}, corpo))
            if self.path == "/api/ferma":
                PROG["ferma"] = True
                return self._r(200, {"ok": True})
            if self.path == "/api/radice":
                try:
                    if corpo.get("togli"):
                        if PROG["in_corso"]:
                            return self._r(200, {"errore": "Prima ferma l'indicizzazione"})
                        return self._r(200, {"ok": True, "tolti": radice_togli(db, str(corpo["togli"]))})
                    return self._r(200, {"ok": True, "radice": radice_aggiungi(db, str(corpo.get("aggiungi", "")))})
                except ValueError as e:
                    return self._r(200, {"errore": str(e)})
            if self.path == "/api/avvia":
                if PROG["in_corso"]:
                    return self._r(200, {"errore": "Sto gia' indicizzando"})
                richieste = [str(x) for x in (corpo.get("cartelle") or []) if os.path.isdir(str(x))]
                for x in richieste:
                    radice_aggiungi(db, x)
                cart = [r for r in radici_elenco(db) if os.path.isdir(r)]
                if not cart:
                    return self._r(200, {"errore": "Aggiungi prima almeno una cartella che esiste su questo computer"})

                def lavoro():
                    PROG.update(in_corso=True, ferma=False, esito="", fatti=0, da_fare=0)
                    try:
                        r = scansiona(db, cart, 0, int(corpo.get("passo") or 30), finto)
                        PROG["esito"] = "Fermato." if PROG["ferma"] else f"Finito: {r['fatti']} file indicizzati."
                    except Exception as e:  # noqa: BLE001
                        PROG["esito"] = f"Errore: {type(e).__name__}: {e}"[:200]
                    PROG.update(in_corso=False, corrente="")
                threading.Thread(target=lavoro, daemon=True).start()
                return self._r(200, {"ok": True})
            self._r(404, {"errore": "?"})

        def log_message(self, *a):
            pass
    if ascolta not in ("127.0.0.1", "localhost") and not chiave:
        raise SystemExit("Per ascoltare fuori dal PC serve --chiave SEGRETO")
    if finestra:
        # la finestra dell'app si e' chiusa (nessun segnale da un po'): il programma si ferma, ma non durante un'indicizzazione
        def guardiano():
            while True:
                time.sleep(2)
                if not BATTITO["ultimo"] or PROG["in_corso"]:
                    continue
                if (BATTITO["chiuso"] > BATTITO["ultimo"] and time.time() - BATTITO["chiuso"] > 5) or time.time() - BATTITO["ultimo"] > 180:
                    os._exit(0)
        threading.Thread(target=guardiano, daemon=True).start()
    log.info("Servizio su http://%s:%d", ascolta, porta)
    if interfaccia:
        threading.Thread(target=ponte_ciclo, args=(db,), daemon=True).start()
    ThreadingHTTPServer((ascolta, porta), H).serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("scansiona", "cerca", "stato", "servi", "interfaccia"):
        s = sp.add_parser(nome)
        s.add_argument("--db", default="indice.db")
        s.add_argument("--finto", action="store_true", help=argparse.SUPPRESS)
        if nome == "scansiona":
            s.add_argument("cartelle", nargs="+"); s.add_argument("--limite", type=int, default=0); s.add_argument("--passo-video", type=int, default=30)
        if nome == "cerca":
            s.add_argument("frase"); s.add_argument("-n", type=int, default=10)
        if nome == "interfaccia":
            s.add_argument("--porta", type=int, default=8765); s.add_argument("--non-aprire", action="store_true"); s.add_argument("--finestra", action="store_true", help="si ferma quando la finestra dell'app si chiude")
        if nome == "servi":
            s.add_argument("--porta", type=int, default=8765); s.add_argument("--ascolta", default="127.0.0.1"); s.add_argument("--chiave", default=os.environ.get("INDICE_CHIAVE", ""))
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
    if a.cmd == "scansiona":
        print(json.dumps(scansiona(a.db, a.cartelle, a.limite, a.passo_video, a.finto), ensure_ascii=False))
    elif a.cmd == "cerca":
        for r in cerca(a.db, a.frase, a.n, a.finto):
            print(f"{r['punteggio']:6.2f}  {r['percorso']}" + (f"  @{r['secondo']}s" if r["secondo"] is not None else "") + f"\n        {r['estratto'][:160]}")
    elif a.cmd == "stato":
        print(json.dumps(stato(a.db), ensure_ascii=False, indent=1))
    elif a.cmd == "interfaccia":
        apri(a.db).close()
        if not a.non_aprire:
            import webbrowser
            threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{a.porta}/")).start()
        servi(a.db, a.porta, "127.0.0.1", "", a.finto, True, a.finestra)
    else:
        servi(a.db, a.porta, a.ascolta, a.chiave, a.finto)


if __name__ == "__main__":
    main()
