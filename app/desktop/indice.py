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
    if "meta" not in {r[1] for r in c.execute("PRAGMA table_info(file)")}:
        c.execute("ALTER TABLE file ADD COLUMN meta TEXT")   # metadati letti dai file (archivi creati con versioni precedenti)
    c.execute("CREATE TABLE IF NOT EXISTS impostazioni (chiave TEXT PRIMARY KEY, valore TEXT)")
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

    def trascrivi(self, wav, avanza=None, durata=0):
        if avanza:
            avanza(1.0)
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

    def trascrivi(self, wav, avanza=None, durata=0):
        if self.finto:
            return self.finto.trascrivi(wav, avanza, durata)
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
                return _raccogli(seg, avanza, durata)
            except RuntimeError as e:   # tipico: librerie CUDA mancanti -> si continua sul processore
                log.warning("Scheda video non utilizzabile per Whisper (%s): passo al processore", str(e)[:80])
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(MODELLO_WHISPER, device="cpu", compute_type="int8")
                seg, _ = self._whisper.transcribe(wav, vad_filter=True)
                return _raccogli(seg, avanza, durata)
        except ImportError:
            self.whisper_ok = False
            log.warning("Trascrizione non disponibile: installa faster-whisper")
            return []


def _raccogli(seg, avanza, durata):
    """Legge i segmenti di Whisper man mano che arrivano, cosi' si sa a che punto e' la trascrizione."""
    out = []
    for s in seg:
        if s.text.strip():
            out.append((float(s.start), s.text.strip()))
        if avanza and durata:
            avanza(min(1.0, float(s.end) / durata))
    return out


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


# ---------- metadati ----------
def ffinfo(p: Path) -> str:
    return subprocess.run([ffmpeg(), "-hide_banner", "-i", str(p)], capture_output=True, text=True, errors="replace").stderr


def sonda_testo(t: str) -> dict:
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


def sonda(p: Path) -> dict:
    return sonda_testo(ffinfo(p))


def etichetta_risoluzione(w, h) -> str:
    if not w or not h:
        return ""
    lato = max(w, h)
    return "8K" if lato >= 7600 else "4K" if lato >= 3800 else "2K" if lato >= 2500 else "Full HD" if lato >= 1900 else "HD" if lato >= 1270 else "SD"


def meta_av(t: str) -> dict:
    """Dettagli tecnici e di ripresa letti da ffmpeg: codec, fotogrammi al secondo, bitrate, audio, macchina, luogo."""
    m = {}
    d = re.search(r"Duration:[^\n]*?bitrate:\s*(\d+) kb/s", t)
    if d:
        m["Bitrate totale"] = f"{int(d[1]) / 1000:.1f} Mb/s"
    v = re.search(r"Stream #[^\n]*?Video: ([^\n]*)", t)
    if v:
        riga = v[1]
        cod = re.match(r"([\w\-]+)(?: \(([^)]*)\))?", riga)
        if cod:
            m["Codec video"] = cod[1] + (f" ({cod[2]})" if cod[2] else "")
        fps = re.search(r"([\d.]+) fps", riga)
        if fps:
            m["Fotogrammi al secondo"] = fps[1]
        br = re.search(r"(\d+) kb/s", riga)
        if br:
            m["Bitrate video"] = f"{int(br[1]) / 1000:.1f} Mb/s"
        px = re.search(r",\s*((?:yuvj?|rgb|bgr|gbr|nv|gray|p0)\w*)", riga)
        if px:
            m["Formato colore"] = px[1]
    a = re.search(r"Stream #[^\n]*?Audio: ([^\n]*)", t)
    if a:
        riga = a[1]
        cod = re.match(r"([\w\-]+)", riga)
        hz = re.search(r"(\d+) Hz", riga)
        can = re.search(r"Hz,\s*([^,]+)", riga)
        m["Audio"] = ", ".join(x for x in (cod[1] if cod else "", f"{int(hz[1]) / 1000:g} kHz" if hz else "", can[1].strip() if can else "") if x)
    for chiave, et in (("com.apple.quicktime.make", "Marca"), ("make", "Marca"), ("com.apple.quicktime.model", "Modello"), ("model", "Modello"),
                       ("encoder", "Software"), ("timecode", "Timecode"), ("title", "Titolo"), ("artist", "Artista"), ("album", "Album"), ("comment", "Commento")):
        if et in m:
            continue
        x = re.search(rf"^\s*{re.escape(chiave)}\s*:\s*(.+?)\s*$", t, re.M | re.I)
        if x:
            m[et] = x[1][:120]
    loc = re.search(r"location(?:-eng)?\s*:\s*([+-]\d+\.?\d*)([+-]\d+\.?\d*)", t)
    if loc:
        m["Posizione GPS"] = f"{float(loc[1]):.5f}, {float(loc[2]):.5f}"
    rot = re.search(r"rotation of (-?[\d.]+) degrees", t) or re.search(r"rotate\s*:\s*(-?\d+)", t)
    if rot and abs(float(rot[1])) > 1:
        m["Rotazione"] = f"{abs(float(rot[1])):g} gradi"
    return m


def _razionale(x):
    try:
        return float(x)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def meta_immagine(p: Path) -> tuple[dict, dict]:
    """Esif della foto: macchina, obiettivo, ISO, diaframma, tempo, focale, data di scatto, posizione GPS."""
    from PIL import Image
    m, info = {}, {}
    with Image.open(p) as im:
        info["larghezza"], info["altezza"] = im.size
        m["Formato"] = str(im.format or p.suffix.lstrip(".")).upper()
        m["Megapixel"] = f"{im.size[0] * im.size[1] / 1e6:.1f}"
        ex = im.getexif()
        try:
            sub = ex.get_ifd(0x8769)
        except Exception:  # noqa: BLE001
            sub = {}
        for k, et in ((271, "Marca"), (272, "Modello"), (305, "Software"), (315, "Autore"), (33432, "Copyright")):
            if ex.get(k):
                m[et] = str(ex.get(k)).strip("\x00 ")[:120]
        if sub.get(42036):
            m["Obiettivo"] = str(sub[42036]).strip("\x00 ")[:120]
        iso = sub.get(34855)
        if iso:
            m["ISO"] = str(iso[0] if isinstance(iso, (tuple, list)) else iso)
        f = _razionale(sub.get(33437))
        if f:
            m["Diaframma"] = f"f/{f:g}"
        te = _razionale(sub.get(33434))
        if te:
            m["Tempo di posa"] = f"1/{round(1 / te)} s" if te < 1 else f"{te:g} s"
        fo = _razionale(sub.get(37386))
        if fo:
            m["Lunghezza focale"] = f"{fo:g} mm"
        dt = sub.get(36867) or ex.get(306)
        if dt:
            m["Data di scatto"] = str(dt)[:19]
            info["data_ripresa"] = str(dt)[:19].replace(":", "-", 2)
        try:
            gps = ex.get_ifd(0x8825)
        except Exception:  # noqa: BLE001
            gps = {}
        if gps.get(2) and gps.get(4):
            def gradi(v):
                g = [_razionale(z) or 0.0 for z in v]
                return g[0] + g[1] / 60 + g[2] / 3600
            la = gradi(gps[2]) * (-1 if gps.get(1) == "S" else 1)
            lo = gradi(gps[4]) * (-1 if gps.get(3) == "W" else 1)
            m["Posizione GPS"] = f"{la:.5f}, {lo:.5f}"
    return m, info


def meta_documento(p: Path, est: str) -> dict:
    m = {}
    try:
        if est == ".pdf":
            from pypdf import PdfReader
            r = PdfReader(str(p))
            m["Pagine"] = str(len(r.pages))
            md = r.metadata or {}
            if md.get("/Title"):
                m["Titolo"] = str(md["/Title"])[:150]
            if md.get("/Author"):
                m["Autore"] = str(md["/Author"])[:100]
        elif est == ".docx":
            with zipfile.ZipFile(p) as z:
                x = z.read("docProps/core.xml").decode("utf-8", "ignore")
            for tag, et in (("dc:title", "Titolo"), ("dc:creator", "Autore"), ("dcterms:modified", "Modificato")):
                r = re.search(rf"<{tag}[^>]*>([^<]+)</{tag}>", x)
                if r:
                    m[et] = r[1][:150]
    except Exception:  # noqa: BLE001
        pass
    return m


def leggi_metadati(p: Path, tipo: str) -> tuple[dict, dict]:
    """(metadati da mostrare, info per le colonne). Non usa i modelli AI: e' veloce."""
    est = p.suffix.lower()
    meta, info = {}, {}
    try:
        if tipo == "immagine":
            meta, info = meta_immagine(p)
        elif tipo in ("video", "audio"):
            t = ffinfo(p)
            info = sonda_testo(t)
            meta = meta_av(t)
            if tipo == "video" and info.get("larghezza"):
                meta["Risoluzione"] = f"{info['larghezza']}x{info['altezza']} ({etichetta_risoluzione(info['larghezza'], info['altezza'])})"
        else:
            meta = meta_documento(p, est)
    except Exception as e:  # noqa: BLE001 - un file illeggibile non ferma l'archivio
        log.debug("metadati %s: %s", p, e)
    return meta, info


def testo_meta(meta: dict, info: dict, tipo: str) -> str:
    """Il testo con cui i metadati diventano ricercabili (per esempio «4K», «Sony», «HEVC», «50 fps»)."""
    parti = [f"{k} {v}" for k, v in meta.items() if k != "Posizione GPS"]
    et = etichetta_risoluzione(info.get("larghezza"), info.get("altezza")) if tipo == "video" else ""
    if et:
        parti.append(et + (" UHD ultra hd" if et in ("4K", "8K") else ""))
    return " . ".join(parti)


def salva_meta(c, fid, meta, info, tipo):
    c.execute("DELETE FROM testi WHERE file_id = ? AND tipo = 'meta'", (fid,))
    tm = testo_meta(meta, info, tipo)
    if tm:
        c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (tm, fid, "meta", 0))
    c.execute("UPDATE file SET meta=?, durata=COALESCE(?, durata), larghezza=COALESCE(?, larghezza), altezza=COALESCE(?, altezza), "
              "data_ripresa=COALESCE(?, data_ripresa) WHERE id=?",
              (json.dumps(meta, ensure_ascii=False), info.get("durata"), info.get("larghezza"), info.get("altezza"), info.get("data_ripresa"), fid))


def riempi_metadati(c):
    """Legge i metadati dei file gia' indicizzati che non li hanno ancora (archivi fatti con versioni precedenti)."""
    righe = c.execute("SELECT id, radice, rel, tipo FROM file WHERE meta IS NULL AND stato='ok'").fetchall()
    if not righe:
        return
    PROG.update(fase_scan="Leggo i metadati dei file gia' indicizzati", meta_fatti=0, meta_da_fare=len(righe))
    for i, r in enumerate(righe):
        if PROG["ferma"]:
            break
        p = Path(r["radice"]) / r["rel"]
        PROG["corrente"] = r["rel"]
        if p.exists():
            meta, info = leggi_metadati(p, r["tipo"])
            salva_meta(c, r["id"], meta, info, r["tipo"])
        PROG["meta_fatti"] = i + 1
        if i % 40 == 39:
            c.commit()
    c.commit()


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


def fotogrammi(p: Path, passo: int, cartella: Path, durata: float, avanza=None) -> list[tuple[float, str]]:
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
        if avanza:
            avanza((i + 1) / n)
    return out


def salva_vettori(c, fid, pos_v):
    for pos, v in pos_v:
        a = np.asarray(v, dtype="float16")
        c.execute("INSERT INTO vettore (file_id, pos, dim, v) VALUES (?,?,?,?)", (fid, pos, int(a.shape[0]), a.tobytes()))


def indicizza_file(c, mod: Modelli, riga, radice: Path, passo: int):
    p = radice / riga["rel"]
    est = p.suffix.lower()
    fid = riga["id"]
    tipo = riga["tipo"]
    c.execute("DELETE FROM testi WHERE file_id = ?", (fid,))
    c.execute("DELETE FROM vettore WHERE file_id = ?", (fid,))
    c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (riga["rel"].replace("/", " ").replace("_", " ").replace("-", " "), fid, "nome", 0))
    fase("Leggo i metadati", 3)
    meta, info = leggi_metadati(p, tipo)
    if est in EST_TESTO or est in (".docx", ".pdf"):
        fase("Leggo il testo", 20)
        for i, b in enumerate(blocchi(testo_di(p, est))):
            c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (b, fid, "testo", i))
    elif est in EST_IMG:
        if np is not None:
            fase("Analizzo l'immagine", 40)
            salva_vettori(c, fid, [(0.0, v) for v in mod.immagini([str(p)])])
    elif est in EST_VID or est in EST_AUD:
        durata = info.get("durata") or 0
        with tempfile.TemporaryDirectory() as tmp:
            fase("Estraggo l'audio", 8)
            wav = os.path.join(tmp, "a.wav")
            r = subprocess.run([ffmpeg(), "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000", wav], capture_output=True, timeout=7200)
            video = est in EST_VID and np is not None
            if r.returncode == 0 and os.path.exists(wav):
                fine_tr = 70 if video else 97
                fase("Trascrivo il parlato", 10)
                for t0, tx in mod.trascrivi(wav, lambda f: fase("Trascrivo il parlato", 10 + f * (fine_tr - 10)), durata):
                    c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (tx, fid, "parlato", t0))
            if video:
                fase("Estraggo i fotogrammi", 72)
                fr = fotogrammi(p, passo, Path(tmp), durata, lambda f: fase("Estraggo i fotogrammi", 72 + f * 13))
                if fr:
                    fase("Analizzo le immagini", 86)
                    salva_vettori(c, fid, list(zip([t for t, _ in fr], mod.immagini([f for _, f in fr]))))
    fase("Salvo", 99)
    salva_meta(c, fid, meta, info, tipo)
    c.execute("UPDATE file SET stato='ok', errore=NULL, indicizzato=? WHERE id=?", (time.time(), fid))


PROG = {"in_corso": False, "fatti": 0, "da_fare": 0, "corrente": "", "ferma": False, "esito": "", "fase_scan": "", "visti": 0,
        "file": {}, "prossimi": [], "recenti": [], "eta_s": None, "inizio": None, "avvisi": []}


def fase(nome, pct):
    """Dove sta lavorando ora l'indice, per il file in corso (si vede nella finestra)."""
    f = PROG.setdefault("file", {})
    f["fase"], f["pct"] = nome, int(max(0, min(99, pct)))


def avvia_scansione(db, cartelle=None, passo=30, finto=False):
    """Fa partire l'indicizzazione di tutte le cartelle ricordate. Restituisce il testo dell'errore, oppure None se e' partita."""
    if PROG["in_corso"]:
        return "Sto gia' indicizzando"
    for x in (cartelle or []):
        if os.path.isdir(str(x)):
            radice_aggiungi(db, str(x))
    cart = [r for r in radici_elenco(db) if os.path.isdir(r)]
    if not cart:
        return "Aggiungi prima almeno una cartella che esiste su questo computer"
    PROG.update(in_corso=True, ferma=False, esito="", fatti=0, da_fare=0)

    def lavoro():
        try:
            r = scansiona(db, cart, 0, passo, finto)
            PROG["esito"] = "Fermato." if PROG["ferma"] else f"Finito: {r['fatti']} file indicizzati."
        except Exception as e:  # noqa: BLE001
            PROG["esito"] = f"Errore: {type(e).__name__}: {e}"[:200]
        PROG.update(in_corso=False, corrente="", file={}, prossimi=[], fase_scan="")
    threading.Thread(target=lavoro, daemon=True).start()
    return None


def scansiona(db, cartelle, limite=0, passo=30, finto=False):
    c = apri(db)
    mod = Modelli(finto)
    PROG.update(visti=0, meta_fatti=0, meta_da_fare=0, fase_scan="Cerco i file nelle cartelle", prossimi=[], recenti=[], file={}, eta_s=None, avvisi=[], inizio=time.time())
    for rad in cartelle:
        if not os.path.isdir(rad):
            PROG["avvisi"].append(f"Cartella non raggiungibile ora (disco scollegato?): {rad}")
            continue
        radice = Path(rad).resolve()
        for dp, dn, fn in os.walk(radice):
            if PROG["ferma"]:
                break
            dn[:] = [d for d in dn if d.lower() not in IGNORA_DIR and not d.startswith(".")]
            PROG["corrente"] = dp
            for f in fn:
                est = Path(f).suffix.lower()
                if f.startswith(".") or est not in (EST_TESTO | EST_IMG | EST_VID | EST_AUD | {".docx", ".pdf"}):
                    continue
                p = Path(dp) / f
                try:
                    st = p.stat()
                except OSError:
                    continue
                PROG["visti"] += 1
                rel = p.relative_to(radice).as_posix()
                tipo = "testo" if est in EST_TESTO or est in (".docx", ".pdf") else "immagine" if est in EST_IMG else "video" if est in EST_VID else "audio"
                r = c.execute("SELECT id, dimensione, mtime, stato FROM file WHERE radice=? AND rel=?", (str(radice), rel)).fetchone()
                if r and r["stato"] == "ok" and r["dimensione"] == st.st_size and abs(r["mtime"] - st.st_mtime) < 1:
                    continue
                if r:
                    c.execute("UPDATE file SET dimensione=?, mtime=?, stato='nuovo' WHERE id=?", (st.st_size, st.st_mtime, r["id"]))
                else:
                    c.execute("INSERT INTO file (radice, rel, tipo, dimensione, mtime) VALUES (?,?,?,?,?)", (str(radice), rel, tipo, st.st_size, st.st_mtime))
        c.commit()
    if not PROG["ferma"]:
        riempi_metadati(c)
    PROG["fase_scan"] = ""
    coda = [] if PROG["ferma"] else c.execute("SELECT * FROM file WHERE stato IN ('nuovo') ORDER BY CASE tipo WHEN 'testo' THEN 0 WHEN 'immagine' THEN 1 WHEN 'audio' THEN 2 ELSE 3 END, id").fetchall()
    log.info("%d file da indicizzare", len(coda))
    fatti = 0
    PROG.update(da_fare=len(coda), fatti=0)
    tempi: dict = {}   # tipo -> [numero, secondi]: serve a stimare il tempo che manca
    restano: dict = {}
    for r in coda:
        restano[r["tipo"]] = restano.get(r["tipo"], 0) + 1
    for i, riga in enumerate(coda):
        if (limite and fatti >= limite) or PROG["ferma"]:
            break
        PROG["corrente"] = riga["rel"]
        PROG["file"] = {"rel": riga["rel"], "tipo": riga["tipo"], "dimensione": riga["dimensione"], "fase": "Comincio", "pct": 1}
        PROG["prossimi"] = [{"rel": r["rel"], "tipo": r["tipo"], "dimensione": r["dimensione"]} for r in coda[i + 1:i + 11]]
        t0 = time.time()
        esito = True
        try:
            indicizza_file(c, mod, riga, Path(riga["radice"]), passo)
        except Exception as e:  # noqa: BLE001 - un file rotto non ferma l'archivio
            esito = False
            c.execute("UPDATE file SET stato='errore', errore=? WHERE id=?", (f"{type(e).__name__}: {e}"[:300], riga["id"]))
            log.warning("%s: %s", riga["rel"], e)
        c.commit()
        fatti += 1
        sec = time.time() - t0
        PROG["fatti"] = fatti
        PROG["recenti"] = ([{"rel": riga["rel"], "tipo": riga["tipo"], "sec": round(sec, 1), "ok": esito}] + PROG["recenti"])[:8]
        t = tempi.setdefault(riga["tipo"], [0, 0.0])
        t[0] += 1
        t[1] += sec
        media = sum(x[1] for x in tempi.values()) / max(1, sum(x[0] for x in tempi.values()))
        restano[riga["tipo"]] -= 1
        PROG["eta_s"] = int(sum(n * ((tempi[k][1] / tempi[k][0]) if k in tempi else media) for k, n in restano.items()))
        log.info("[%d/%d] %s (%.1f s)", fatti, len(coda), riga["rel"], sec)
    PROG["file"] = {}
    return {"da_fare": len(coda), "fatti": fatti}


# ---------- ricerca ----------
def _fts_query(q: str) -> str:
    parole = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]
    return " OR ".join(f'"{w}"*' for w in parole[:12])


SOGLIA_SIM = float(os.environ.get("INDICE_SOGLIA", "0.20"))   # sotto questa somiglianza CLIP un fotogramma non e' una risposta
COLONNE = "id, radice, rel, tipo, dimensione, mtime, durata, larghezza, altezza, data_ripresa, meta"


def _scheda(f, dove=None, pos=None, estratto=None, punteggio=None):
    """Una riga del catalogo, con tutto quello che serve a mostrarla (percorso, misure, metadati)."""
    try:
        meta = json.loads(f["meta"]) if f["meta"] else {}
    except ValueError:
        meta = {}
    rel = f["rel"]
    video_audio = f["tipo"] in ("video", "audio")
    return {"id": f["id"], "file": rel, "nome": rel.rsplit("/", 1)[-1], "cartella": str(Path(f["radice"]) / rel.rsplit("/", 1)[0]) if "/" in rel else f["radice"],
            "radice": f["radice"], "percorso": str(Path(f["radice"]) / rel), "tipo": f["tipo"], "dove": dove,
            "secondo": round(pos, 1) if dove in ("parlato", "immagine") and video_audio and pos is not None else None,
            "estratto": estratto, "data": f["data_ripresa"], "punteggio": punteggio, "dimensione": f["dimensione"], "mtime": f["mtime"],
            "durata": f["durata"], "larghezza": f["larghezza"], "altezza": f["altezza"], "meta": meta,
            "risoluzione": etichetta_risoluzione(f["larghezza"], f["altezza"]) if f["tipo"] == "video" else ""}


ORDINI_SQL = {"recenti": "indicizzato DESC", "data": "COALESCE(data_ripresa, datetime(mtime, 'unixepoch')) DESC", "nome": "rel COLLATE NOCASE ASC",
              "dimensione": "dimensione DESC"}


def sfoglia(db, n=30, offset=0, tipo=None, ordine="recenti", min_larghezza=0):
    """Il catalogo senza una frase di ricerca: i file piu' recenti (o ordinati come si preferisce) con i loro metadati."""
    c = apri(db)
    dove, par = ["stato='ok'"], []
    if tipo:
        dove.append("tipo=?"); par.append(tipo)
    if min_larghezza:
        dove.append("larghezza>=?"); par.append(int(min_larghezza))
    o = ORDINI_SQL.get(ordine, ORDINI_SQL["recenti"])
    righe = c.execute(f"SELECT {COLONNE} FROM file WHERE {' AND '.join(dove)} ORDER BY {o} LIMIT ? OFFSET ?", (*par, n, offset)).fetchall()  # nosec B608 - parti fisse
    return [_scheda(f) for f in righe]


def cerca(db, q, n=10, finto=False, tipo=None, ordine="rilevanza", offset=0, min_larghezza=0):
    if not (q or "").strip():
        return sfoglia(db, n, offset, tipo, "recenti" if ordine == "rilevanza" else ordine, min_larghezza)
    c = apri(db)
    punti: dict = {}
    pool = (n + offset) * (8 if (tipo or min_larghezza) else 4)

    def aggiungi(fid, pos, tipo_, testo, rango, peso):
        k = (fid, tipo_)
        p = punti.setdefault(k, {"file_id": fid, "tipo": tipo_, "pos": pos, "testo": testo, "score": 0.0})
        p["score"] += peso / (60 + rango)
    fq = _fts_query(q)
    if fq:
        for i, r in enumerate(c.execute("SELECT file_id, tipo, pos, snippet(testi, 0, '[', ']', ' … ', 18) AS s FROM testi WHERE testi MATCH ? ORDER BY bm25(testi) LIMIT ?", (fq, pool))):
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
                for rango, i in enumerate([k for k in np.argsort(-s)[:pool] if s[k] >= soglia]):
                    aggiungi(ok[i]["file_id"], ok[i]["pos"], "immagine", f"somiglianza visiva {float(s[i]):.2f}", rango, 0.8)
    ris = sorted(punti.values(), key=lambda x: -x["score"])
    visti, out = set(), []
    for r in ris:
        if r["file_id"] in visti:
            continue
        f = c.execute(f"SELECT {COLONNE} FROM file WHERE id=?", (r["file_id"],)).fetchone()
        if f is None or (tipo and f["tipo"] != tipo) or (min_larghezza and (f["larghezza"] or 0) < int(min_larghezza)):
            continue
        visti.add(r["file_id"])
        out.append(_scheda(f, r["tipo"], r["pos"], r["testo"], round(r["score"] * 100, 2)))
    if ordine in ("data", "nome", "dimensione"):
        out.sort(key=(lambda x: x["data"] or "") if ordine == "data" else (lambda x: x["nome"].lower()) if ordine == "nome" else (lambda x: -(x["dimensione"] or 0)),
                 reverse=(ordine == "data"))
    return out[offset:offset + n]


def dettaglio(db, fid: int):
    c = apri(db)
    f = c.execute(f"SELECT {COLONNE}, stato, errore, indicizzato FROM file WHERE id=?", (fid,)).fetchone()
    if f is None:
        raise ValueError("File non trovato nell'indice")
    d = _scheda(f)
    d.update(stato=f["stato"], errore=f["errore"], indicizzato=f["indicizzato"], raggiungibile=os.path.exists(d["percorso"]))
    d["testi"] = [{"pos": r["pos"], "tipo": r["tipo"], "testo": r["testo"]} for r in
                  c.execute("SELECT pos, tipo, testo FROM testi WHERE file_id=? AND tipo IN ('parlato','testo') ORDER BY CAST(pos AS REAL) LIMIT 400", (fid,))]
    return d


def _percorso_di(db, fid: int) -> Path:
    f = apri(db).execute("SELECT radice, rel FROM file WHERE id=?", (fid,)).fetchone()
    if f is None:
        raise ValueError("File non trovato nell'indice")
    return Path(f["radice"]) / f["rel"]


def miniatura(db, fid: int, t=None, w=360):
    """Anteprima JPEG di un file indicizzato (foto ridotta o fotogramma del video), tenuta in una cartella di cache accanto all'indice."""
    c = apri(db)
    f = c.execute("SELECT radice, rel, tipo, durata FROM file WHERE id=?", (fid,)).fetchone()
    if f is None or f["tipo"] not in ("immagine", "video"):
        return None
    p = Path(f["radice"]) / f["rel"]
    if not p.exists():
        return None
    w = max(80, min(int(w), 1600))
    sec = float(t) if t is not None else (min(f["durata"] * 0.1, 600) if f["durata"] else 0.0)
    cache = Path(db).resolve().parent / "miniature"
    cache.mkdir(exist_ok=True)
    dest = cache / f"{fid}_{int(sec)}_{w}.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    if f["tipo"] == "immagine":
        try:
            from PIL import Image, ImageOps
            with Image.open(p) as im:
                im.draft("RGB", (w * 2, w * 2))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((w, w * 2))
                im.save(dest, "JPEG", quality=78)
        except Exception:  # noqa: BLE001
            return None
    else:
        subprocess.run([ffmpeg(), "-v", "error", "-ss", str(sec), "-i", str(p), "-frames:v", "1", "-vf", f"scale={w}:-2", "-q:v", "5", "-y", str(dest)],
                       capture_output=True, timeout=120)
    return dest.read_bytes() if dest.exists() and dest.stat().st_size > 0 else None


def apri_file(db, fid: int, mostra=False):
    """Apre il file col programma predefinito del computer, oppure mostra la sua cartella."""
    p = _percorso_di(db, fid)
    if not p.exists():
        raise ValueError("Il file non e' raggiungibile ora (disco o NAS scollegato?)")
    if sys.platform == "win32":
        if mostra:
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            os.startfile(str(p))   # noqa: S606 - file gia' presente nell'indice dell'utente, scelto da lui
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p.parent if mostra else p)])


def stato(db):
    c = apri(db)
    return {"file": {r["stato"]: r["n"] for r in c.execute("SELECT stato, count(*) n FROM file GROUP BY stato")},
            "per_tipo": {r["tipo"]: r["n"] for r in c.execute("SELECT tipo, count(*) n FROM file GROUP BY tipo")},
            "dimensione": c.execute("SELECT COALESCE(sum(dimensione),0) n FROM file").fetchone()["n"],
            "vettori": c.execute("SELECT count(*) n FROM vettore").fetchone()["n"],
            "blocchi_di_testo": c.execute("SELECT count(*) n FROM testi").fetchone()["n"],
            "errori": [dict(r) for r in c.execute("SELECT rel, errore FROM file WHERE stato='errore' LIMIT 20")]}


# ---------- impostazioni e cartelle ricordate ----------
def imp_leggi(db, chiave, default=""):
    r = apri(db).execute("SELECT valore FROM impostazioni WHERE chiave=?", (chiave,)).fetchone()
    return r["valore"] if r else default


def imp_scrivi(db, chiave, valore):
    c = apri(db)
    c.execute("INSERT INTO impostazioni (chiave, valore) VALUES (?,?) ON CONFLICT(chiave) DO UPDATE SET valore=excluded.valore", (chiave, str(valore)))
    c.commit()


def _copie_radici(db):
    """Le cartelle ricordate vengono salvate anche in due file di testo: se l'indice viene ricreato, non si perdono."""
    return [Path(db).resolve().parent / "radici.json", Path.home() / ".opifex-archivio-cartelle.json"]


def radici_salva(db):
    elenco = [x["percorso"] for x in apri(db).execute("SELECT percorso FROM radici ORDER BY percorso")]
    for f in _copie_radici(db):
        try:
            f.write_text(json.dumps(elenco, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def radici_ripristina(db):
    c = apri(db)
    if c.execute("SELECT 1 FROM radici LIMIT 1").fetchone():
        return
    for f in _copie_radici(db):
        try:
            for p in json.loads(f.read_text(encoding="utf-8")):
                c.execute("INSERT OR IGNORE INTO radici (percorso, aggiunta) VALUES (?,?)", (str(p), time.time()))
            c.commit()
            if c.execute("SELECT 1 FROM radici LIMIT 1").fetchone():
                return
        except (OSError, ValueError, TypeError):
            continue


# ---------- cartelle: cosa e' indicizzato e cosa no ----------
def _nc(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def radici_elenco(db):
    radici_ripristina(db)
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
    radici_salva(db)
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
    radici_salva(db)
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
<style>:root{--sfondo:#1A120D;--testo:#F1EBE3;--tenue:#BDB0A3;--bordo:rgba(255,255,255,.13);--pri:#E8924A;--pri-t:#1A110A;--ok:#6FD6B8;--no:#F0866A;--avv:#F3C46A;--serif:'Newsreader','Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;color-scheme:dark}
*{box-sizing:border-box}html{scrollbar-color:rgba(255,255,255,.25) transparent}
body{margin:0;background:#1A120D;color:var(--testo);font:15px/1.45 'Inter Tight',Inter,system-ui,-apple-system,'Segoe UI',sans-serif;min-height:100vh}
body::before{content:"";position:fixed;inset:0;z-index:-2;pointer-events:none;background:radial-gradient(48% 38% at 74% 14%,rgba(255,196,128,.42),transparent 66%),radial-gradient(36% 30% at 12% 82%,rgba(150,84,44,.62),transparent 70%),radial-gradient(30% 22% at 52% 62%,rgba(196,120,64,.20),transparent 70%),linear-gradient(180deg,#2d1f16 0%,#1d140e 48%,#2a1b12 100%)}
::selection{background:rgba(232,146,74,.30)}*:focus-visible{outline:2px solid var(--pri);outline-offset:2px}
a{color:#F2A862}a:hover{color:#F7B97A}
header.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:18px;flex-wrap:wrap;padding:12px max(18px,env(safe-area-inset-left));background:rgba(26,18,13,.72);-webkit-backdrop-filter:blur(22px);backdrop-filter:blur(22px);border-bottom:1px solid rgba(255,255,255,.1)}
.marchio{display:flex;align-items:center;gap:10px;font-family:var(--serif);font-size:22px;font-weight:500;letter-spacing:-.01em}
.marchio i{width:26px;height:26px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#F7B97A,#E8924A 55%,#8a4a22);box-shadow:0 0 0 3px rgba(232,146,74,.18)}
nav.sc{display:flex;gap:4px;background:rgba(255,255,255,.06);border:1px solid var(--bordo);border-radius:999px;padding:3px}
nav.sc button{background:transparent;border:0;color:#D9CFC4;border-radius:999px;padding:7px 16px;font:inherit;font-weight:600;cursor:pointer}
nav.sc button:hover{background:rgba(255,255,255,.10)}nav.sc button.on{background:var(--pri);color:var(--pri-t)}
#stato-alto{margin-left:auto;font-size:13px;color:var(--tenue)}
main{max-width:1240px;margin:0 auto;padding:22px max(18px,env(safe-area-inset-left)) 90px}
h2{font-family:var(--serif);font-weight:500;font-size:24px;letter-spacing:-.01em;margin:0 0 4px}
h3{margin:0 0 8px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--tenue);font-weight:700}
.m{color:var(--tenue);font-size:13px}
.carta{background:linear-gradient(150deg,rgba(255,255,255,.115),rgba(255,255,255,.045));border:1px solid rgba(255,255,255,.12);border-radius:26px;-webkit-backdrop-filter:blur(22px) saturate(1.25);backdrop-filter:blur(22px) saturate(1.25);box-shadow:0 22px 50px -24px rgba(0,0,0,.7),inset 0 1px 0 rgba(255,255,255,.14);padding:20px;margin-bottom:16px}
input,textarea,select{width:100%;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.18);color:var(--testo);border-radius:12px;padding:10px 12px;font:inherit}
input::placeholder,textarea::placeholder{color:#8F847A}select{width:auto}option{background:#2a1b12}
button{font:inherit;cursor:pointer}
button.p{background:var(--pri);color:var(--pri-t);border:0;border-radius:999px;font-weight:600;min-height:40px;padding:9px 20px}button.p:hover{background:#F2A862}
button.s{background:transparent;color:var(--testo);border:1px solid rgba(255,255,255,.18);border-radius:999px;font-weight:600;min-height:40px;padding:9px 18px}button.s:hover{background:rgba(255,255,255,.10)}
button.piccolo{min-height:30px;padding:4px 13px;font-size:13px}button:disabled{opacity:.5;cursor:default}
.riga{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.chip{background:rgba(255,255,255,.10);border:1px solid transparent;color:#D9CFC4;border-radius:999px;padding:5px 13px;font-size:13px;font-weight:600;cursor:pointer}
.chip:hover{background:rgba(255,255,255,.16)}.chip.on{background:rgba(232,146,74,.22);border-color:var(--pri);color:#F7B97A}
.et{display:inline-block;font-size:12px;border-radius:999px;padding:2px 10px;background:rgba(255,255,255,.10);color:#D9CFC4;white-space:nowrap}
.et.ok{background:rgba(111,214,184,.16);color:var(--ok)}.et.cd{background:rgba(243,196,106,.16);color:var(--avv)}.et.er{background:rgba(240,134,106,.18);color:var(--no)}
/* cartelle */
.f{display:flex;align-items:center;gap:10px;border-top:1px solid var(--bordo);padding:9px 2px}.f .n{flex:1;min-width:0;word-break:break-all;cursor:pointer}.f .n:hover{color:#F7B97A}.f.d .n{cursor:default;color:var(--tenue)}
/* avanzamento */
.barra{height:9px;background:rgba(255,255,255,.12);border-radius:6px;overflow:hidden}.barra i{display:block;height:100%;width:0;background:linear-gradient(90deg,#C77A38,#F2A862);border-radius:6px;transition:width .5s}
.barra.sottile{height:5px}.barra.indef i{width:35%!important;animation:scorri 1.3s ease-in-out infinite}
@keyframes scorri{0%{margin-left:-35%}100%{margin-left:100%}}
.grandi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.num{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:12px 14px}.num b{display:block;font-family:var(--serif);font-weight:500;font-size:26px;color:var(--pri)}
.lav{display:flex;gap:14px;align-items:center;padding:14px;border-radius:18px;background:rgba(232,146,74,.10);border:1px solid rgba(232,146,74,.35)}
.lav .ic,.coda .ic{width:38px;height:38px;border-radius:12px;background:rgba(255,255,255,.10);display:grid;place-items:center;flex:none;color:#F2A862}
.lav .tx,.coda .tx{flex:1;min-width:0}.nomefile{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.coda{display:flex;gap:12px;align-items:center;padding:8px 2px;border-top:1px solid var(--bordo)}.coda .ic{width:30px;height:30px;border-radius:10px}.coda .sx{width:90px;flex:none;text-align:right}
.coda .barra{margin-top:5px}
/* esplora */
.cerca{display:flex;gap:10px;align-items:center;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);border-radius:999px;padding:6px 6px 6px 20px}
.cerca input{background:transparent;border:0;padding:8px 0;font-size:17px}.cerca input:focus-visible{outline:0}
.cerca:focus-within{border-color:var(--pri);box-shadow:0 0 0 3px rgba(232,146,74,.2)}
.filtri{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:14px 0 18px}.filtri .sp{flex:1}
.griglia{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.griglia.elenco{grid-template-columns:1fr}
.sch{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:20px;overflow:hidden;cursor:pointer;display:flex;flex-direction:column;transition:border-color .15s,transform .15s}
.sch:hover{border-color:var(--pri);transform:translateY(-2px)}
.anteprima{position:relative;aspect-ratio:16/10;background:rgba(0,0,0,.28);display:grid;place-items:center;overflow:hidden}
.anteprima img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.anteprima .grande{color:rgba(242,168,98,.7)}
.badge{position:absolute;font-size:11px;font-weight:700;border-radius:8px;padding:2px 7px;background:rgba(20,13,9,.78);color:#F1EBE3}
.badge.sx{left:8px;top:8px}.badge.dx{right:8px;bottom:8px}.badge.ris{left:8px;bottom:8px;background:var(--pri);color:var(--pri-t)}
.corpo{padding:11px 13px 13px;display:flex;flex-direction:column;gap:3px;min-width:0}
.corpo .nomefile{font-size:14px}.corpo .dove{font-size:12px;color:var(--tenue);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;direction:rtl;text-align:left}
.corpo .dati{font-size:12.5px;color:#D9CFC4}.estratto{font-size:13px;color:#E6DCD0;margin-top:4px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
mark{background:rgba(232,146,74,.35);color:#FFE2C4;border-radius:4px;padding:0 2px}
.elenco .sch{flex-direction:row;align-items:stretch}.elenco .anteprima{width:190px;aspect-ratio:auto;min-height:106px;flex:none}.elenco .corpo{flex:1;justify-content:center}
.vuoto{padding:50px 10px;text-align:center;color:var(--tenue)}
/* dettaglio */
#vela{position:fixed;inset:0;z-index:40;background:rgba(0,0,0,.55);display:none}#vela.on{display:block}
#dr{position:fixed;top:0;right:0;bottom:0;z-index:41;width:min(640px,100vw);background:rgba(26,18,13,.88);-webkit-backdrop-filter:blur(26px);backdrop-filter:blur(26px);border-left:1px solid rgba(255,255,255,.14);border-radius:22px 0 0 22px;box-shadow:-30px 0 60px -30px rgba(0,0,0,.6);transform:translateX(105%);transition:transform .25s;overflow:auto;padding:20px}
#dr.on{transform:none}
.prev{border-radius:18px;overflow:hidden;background:rgba(0,0,0,.35);display:grid;place-items:center;min-height:160px;margin:12px 0}
.prev img,.prev video{width:100%;max-height:52vh;object-fit:contain;display:block}.prev audio{width:100%;margin:30px 10px}
table.mt{width:100%;border-collapse:collapse;font-size:13.5px}table.mt td{padding:6px 4px;border-bottom:1px solid var(--bordo);vertical-align:top}table.mt td:first-child{color:var(--tenue);width:38%}table.mt td:last-child{word-break:break-word}
.tr{display:flex;gap:10px;padding:6px 4px;border-bottom:1px solid var(--bordo);font-size:13.5px}.tr.clic{cursor:pointer}.tr.clic:hover{background:rgba(255,255,255,.07)}.tr b{color:var(--pri);flex:none;font-variant-numeric:tabular-nums}
#sb{position:fixed;left:50%;bottom:14px;transform:translateX(-50%) translateY(140%);transition:transform .3s;z-index:30;width:min(560px,calc(100vw - 28px));background:rgba(40,28,20,.9);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);border:1px solid rgba(232,146,74,.5);border-radius:18px;padding:10px 14px;cursor:pointer;box-shadow:0 18px 40px -16px rgba(0,0,0,.7)}
#sb.on{transform:translateX(-50%)}
.cz{max-height:46vh;overflow:auto;margin:12px 0;display:flex;flex-direction:column;gap:8px}.mb{padding:9px 12px;border-radius:14px;max-width:88%;white-space:pre-wrap;word-break:break-word}.mb.u{align-self:flex-end;background:var(--pri);color:var(--pri-t)}.mb.a{align-self:flex-start;background:rgba(255,255,255,.08);border:1px solid var(--bordo)}
.avviso{background:rgba(243,196,106,.14);color:var(--avv);border-radius:12px;padding:8px 12px;margin:8px 0;font-size:13px}
.interr{display:flex;align-items:center;gap:8px;cursor:pointer}.interr input{width:auto;accent-color:var(--pri)}
</style>
</head>
<body>
<header class="top"><div class="marchio"><i></i>Opifex · Archivio</div>
<nav class="sc"><button id="t-esplora" class="on">Esplora</button><button id="t-indice">Indicizzazione</button><button id="t-dialogo">Dialogo con Opifex</button></nav>
<div id="stato-alto"></div></header>
<main>
<div id="v-esplora">
 <div class="cerca"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#BDB0A3" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
 <input id="q" autocomplete="off" placeholder="Cerca per frase, luogo, persona, camera, codec: per esempio «interno del castello al tramonto» o «4K Sony»"><button class="p" id="ce">Cerca</button></div>
 <div class="filtri" id="filtri">
  <button class="chip on" data-tipo="">Tutto</button><button class="chip" data-tipo="immagine">Foto</button><button class="chip" data-tipo="video">Video</button><button class="chip" data-tipo="audio">Audio</button><button class="chip" data-tipo="testo">Documenti</button>
  <button class="chip" id="f4k">Solo 4K o più</button><span class="sp"></span>
  <select id="ord"><option value="rilevanza">Più pertinenti</option><option value="data">Più recenti (data di ripresa)</option><option value="nome">Nome</option><option value="dimensione">Più grandi</option></select>
  <button class="chip on" id="vg" title="Griglia">Griglia</button><button class="chip" id="ve" title="Elenco">Elenco</button></div>
 <div class="m" id="intest" style="margin-bottom:10px"></div>
 <div class="griglia" id="gr"></div><div style="text-align:center;margin-top:18px"><button class="s" id="altri" hidden>Mostra altri</button></div>
</div>
<div id="v-indice" hidden>
 <div class="carta"><h2>Cartelle</h2><div class="m">Sfoglia il computer: vedi cosa è già nell'indice, cosa è in coda e cosa è ancora fuori. Le cartelle che aggiungi restano ricordate anche dopo aver chiuso l'app.</div>
 <div id="cr" class="m" style="margin:12px 0 4px"></div><div id="cl"></div>
 <div class="riga" style="margin-top:12px"><input id="np" style="flex:1;min-width:220px" placeholder="Oppure scrivi un percorso, per esempio D:\Montarrenti o Z:\Archivio\Video"><button id="na" class="s">Aggiungi</button></div></div>
 <div class="carta"><div class="riga" style="justify-content:space-between"><h2 style="margin:0">Indicizzazione</h2>
 <div class="riga"><label class="interr m"><input type="checkbox" id="auto"> Riprendi da solo quando apro l'app</label><button id="av" class="p">Indicizza tutto</button><button id="fe" class="s">Ferma</button></div></div>
 <div id="avvisi"></div>
 <div style="margin-top:14px"><div class="barra" id="bt"><i id="b"></i></div><div class="m" id="p" style="margin-top:6px">Pronto.</div></div>
 <div class="grandi" id="numeri"></div>
 <div id="lavoro"></div>
 <div id="prossimi"></div><div id="recenti"></div></div>
</div>
<div id="v-dialogo" hidden>
<div class="carta" id="ac"><h2>Collegati a Opifex</h2><div class="m">Le stesse credenziali con cui entri dal sito. La password non viene salvata: resta collegato finché tieni aperta la finestra.</div>
<input id="ou" placeholder="Indirizzo di Opifex" style="margin-top:10px"><input id="oe" placeholder="Email" style="margin-top:8px"><input id="op" type="password" placeholder="Password" style="margin-top:8px">
<input id="oc" placeholder="Codice a 6 cifre (secondo fattore)" style="margin-top:8px" hidden><div class="riga" style="margin-top:10px"><button id="ol" class="p">Entra</button></div><div class="m" id="om"></div><div class="m" id="pn" style="margin-top:6px"></div></div>
<div class="carta" id="dl" hidden><h2>Dialogo <span class="m" id="on"></span></h2>
<div class="riga"><select id="oa" style="flex:1"></select><select id="of"><option value="pubblico">Solo dati pubblici</option><option value="interno" selected>Dati interni</option><option value="riservato">Riservato</option></select></div>
<div id="oz" class="cz"></div><textarea id="ot" rows="3" placeholder="Scrivi all'agente… (Invio per inviare, Maiusc+Invio per andare a capo)"></textarea>
<label class="interr m" style="margin-top:8px"><input type="checkbox" id="oar"> Allega ciò che trovo nell'archivio su questo computer (percorsi ed estratti)</label>
<div class="riga" style="margin-top:10px"><button id="oi" class="p">Invia</button><button id="oq" class="s">Esci da Opifex</button></div></div>
</div>
</main>
<div id="vela"></div><aside id="dr" aria-label="Dettaglio file"></aside>
<div id="sb"><div class="riga" style="justify-content:space-between"><b style="font-size:13px" id="sb-t">Indicizzo…</b><span class="m" id="sb-p"></span></div><div class="barra sottile" style="margin-top:6px"><i id="sb-b"></i></div></div>
<script>
const $=i=>document.getElementById(i);
async function j(u,o){const r=await fetch(u,o);return r.json()}
const E=t=>String(t==null?'':t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const IC={immagine:'<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="M21 16l-5-5-8 8"/>',video:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.5-2.5z"/>',audio:'<path d="M9 18V6l10-2v12"/><circle cx="7" cy="18" r="2.5"/><circle cx="17" cy="16" r="2.5"/>',testo:'<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>'};
const NT={immagine:'Foto',video:'Video',audio:'Audio',testo:'Documento'};
const icona=(t,s)=>`<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${IC[t]||IC.testo}</svg>`;
function dur(s){s=Math.round(s||0);const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return(h?h+':'+String(m).padStart(2,'0'):m)+':'+String(x).padStart(2,'0')}
function mb(b){if(!b)return'';const u=['B','KB','MB','GB','TB'];let i=0;while(b>=1024&&i<4){b/=1024;i++}return(b>=100||i===0?Math.round(b):b.toFixed(1))+' '+u[i]}
function dataIt(x){if(!x)return'';const d=typeof x==='number'?new Date(x*1000):new Date(String(x).replace(' ','T'));return isNaN(d)?'':d.toLocaleDateString('it-IT',{day:'numeric',month:'short',year:'numeric'})}
function tempo(s){if(s==null)return'';if(s<90)return s+' s';if(s<5400)return Math.round(s/60)+' min';const h=Math.floor(s/3600);return h+' h '+Math.round(s%3600/60)+' min'}
function evid(t){return E(t).replace(/\[([^\]]+)\]/g,'<mark>$1</mark>')}
let qui='';
/* ---------- schede ---------- */
function vai(n){for(const k of['esplora','indice','dialogo']){$('v-'+k).hidden=k!==n;$('t-'+k).className=k===n?'on':''}
 if(n==='indice'){carica(qui);agg()}if(n==='dialogo')opStato();if(n!=='esplora')chiudiDett()}
['esplora','indice','dialogo'].forEach(k=>$('t-'+k).onclick=()=>vai(k));
$('sb').onclick=()=>vai('indice');
/* ---------- cartelle ---------- */
const ET={indicizzata:['ok','Indicizzata'],indicizzata_vuota:['ok','Nessun file supportato'],in_coda:['cd','In coda'],errori:['er','Con errori'],vuota:['','Vuota'],fuori:['','Non indicizzata'],contiene:['cd','Contiene cartelle indicizzate'],esclusa:['','Esclusa (di sistema)']};
function num(c){const o=[];if(c.ok)o.push(c.ok+' fatti');if(c.nuovo)o.push(c.nuovo+' in coda');if(c.errore)o.push(c.errore+' errori');return o.join(' · ')}
async function azione(c){const r=await j('/api/radice',{method:'POST',body:JSON.stringify(c)});if(r.errore)alert(r.errore);carica(qui)}
$('na').onclick=async()=>{const v=$('np').value.trim();if(!v)return;const r=await j('/api/radice',{method:'POST',body:JSON.stringify({aggiungi:v})});if(r.errore)return alert(r.errore);$('np').value='';carica(qui)};
async function carica(p){qui=p||'';const r=await j('/api/cartelle?percorso='+encodeURIComponent(qui));
 if(r.errore){$('cl').innerHTML='<div class="m">'+E(r.errore)+'</div>';return}
 const rad=!r.percorso;$('cr').innerHTML=rad?'Cartelle ricordate':'<a href="#" id="su">&larr; indietro</a> &nbsp; <b>'+E(r.percorso)+'</b>'+(r.file_qui&&num(r.file_qui)?' <span class="m">· qui dentro: '+E(num(r.file_qui))+'</span>':'');
 let h='';for(const v of r.voci){const e=ET[v.stato]||['',v.stato];const mie=v.radice;const assente=mie&&v.esiste===false;
  h+=`<div class="f${v.stato==='esclusa'?' d':''}"><div class="n" data-p="${E(v.percorso)}">&#128193; ${E(v.nome)}</div><span class="m">${E(num(v.conteggi||{}))}</span>`+
  (assente?'<span class="et er">Non raggiungibile ora</span>':`<span class="et ${e[0]}">${e[1]}</span>`)+
  (mie?`<button class="s piccolo" data-t="${E(v.percorso)}">Togli</button>`:(v.stato==='fuori'?`<button class="p piccolo" data-a="${E(v.percorso)}">Aggiungi</button>`:''))+'</div>'}
 if(rad){h=(h||'<div class="m">Nessuna cartella aggiunta.</div>')+'<div class="m" style="margin-top:10px">Sfoglia da: '+(r.unita||[]).map(u=>`<a href="#" data-p="${E(u)}">${E(u)}</a>`).join(' &nbsp; ')+'</div>'}
 $('cl').innerHTML=h;$('cl').querySelectorAll('[data-p]').forEach(x=>x.onclick=ev=>{ev.preventDefault();if(!x.classList.contains('d')&&!x.parentElement.classList.contains('d'))carica(x.dataset.p)});
 $('cl').querySelectorAll('[data-a]').forEach(x=>x.onclick=()=>azione({aggiungi:x.dataset.a}));
 $('cl').querySelectorAll('[data-t]').forEach(x=>x.onclick=()=>{if(confirm('Togliere questa cartella dall\'indice? I tuoi file restano dove sono.'))azione({togli:x.dataset.t})});
 if($('su'))$('su').onclick=ev=>{ev.preventDefault();carica(r.su||'')}}
setInterval(()=>{if(!qui&&!$('v-indice').hidden)carica('')},15000);
/* ---------- avanzamento ---------- */
$('av').onclick=async()=>{const r=await j('/api/avvia',{method:'POST',body:JSON.stringify({})});if(r.errore)alert(r.errore);else{carica(qui);agg()}};
$('fe').onclick=()=>j('/api/ferma',{method:'POST'});
$('auto').onchange=()=>j('/api/impostazioni',{method:'POST',body:JSON.stringify({riprendi_da_solo:$('auto').checked})});
j('/api/impostazioni').then(r=>{$('auto').checked=!!r.riprendi_da_solo}).catch(()=>{});
const nomeDi=r=>r.split('/').pop(),cartDi=r=>r.includes('/')?r.slice(0,r.lastIndexOf('/')):'';
function voceCoda(x,stato){const pc=stato==='fatto'?100:0;
 return `<div class="coda"><div class="ic">${icona(x.tipo,18)}</div><div class="tx"><div class="nomefile" title="${E(x.rel)}">${E(nomeDi(x.rel))}</div><div class="m" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${E(cartDi(x.rel))}</div><div class="barra sottile"><i style="width:${pc}%;${x.ok===false?'background:var(--no)':''}"></i></div></div>`+
 `<div class="sx m">${stato==='fatto'?(x.ok===false?'<span style="color:var(--no)">Errore</span>':'✓ '+x.sec+' s'):'In attesa<br>'+mb(x.dimensione)}</div></div>`}
let PR={};
async function agg(){let r;try{r=await j('/api/progresso')}catch(e){return}PR=r;
 const f=r.file||{};let pc=0,ind=false,testo;
 if(r.in_corso){
  if(r.fase_scan){if(r.meta_da_fare&&/metadati/.test(r.fase_scan)){pc=100*(r.meta_fatti||0)/r.meta_da_fare;testo=`${r.fase_scan}: ${r.meta_fatti||0} di ${r.meta_da_fare}`}
   else{ind=true;testo=`${r.fase_scan}… ${r.visti||0} file trovati finora`}}
  else if(r.da_fare){pc=100*((r.fatti||0)+(f.pct||0)/100)/r.da_fare;testo=`Indicizzo ${r.fatti} di ${r.da_fare} file (${Math.floor(pc)}%)`+(r.eta_s!=null?` · mancano circa ${tempo(r.eta_s)}`:'')}
  else testo='Preparo la coda…'}
 else testo=(r.esito||'Pronto.')+(r.totale?` Nell'indice: ${r.totale.toLocaleString('it-IT')} file.`:'');
 $('b').style.width=Math.min(100,pc)+'%';$('bt').classList.toggle('indef',ind);$('p').textContent=testo;
 $('av').disabled=!!r.in_corso;$('fe').disabled=!r.in_corso;
 $('avvisi').innerHTML=(r.avvisi||[]).map(a=>`<div class="avviso">${E(a)}</div>`).join('');
 const pt=r.per_tipo||{};
 $('numeri').innerHTML=[['Nell\'indice',(r.totale||0).toLocaleString('it-IT')],['Foto',(pt.immagine||0).toLocaleString('it-IT')],['Video',(pt.video||0).toLocaleString('it-IT')],['Audio',(pt.audio||0).toLocaleString('it-IT')],['Documenti',(pt.testo||0).toLocaleString('it-IT')],['Dimensione',mb(r.dimensione)||'0 B']].map(a=>`<div class="num"><b>${a[1]}</b><span class="m">${a[0]}</span></div>`).join('');
 $('lavoro').innerHTML=r.in_corso&&f.rel?`<h3 style="margin-top:6px">In lavorazione ora</h3><div class="lav"><div class="ic">${icona(f.tipo,22)}</div><div class="tx"><div class="nomefile" title="${E(f.rel)}">${E(nomeDi(f.rel))}</div><div class="m">${E(f.fase||'')} · ${f.pct||0}%${f.dimensione?' · '+mb(f.dimensione):''}</div><div class="barra sottile" style="margin-top:6px"><i style="width:${f.pct||0}%"></i></div></div></div>`:'';
 $('prossimi').innerHTML=(r.prossimi||[]).length?'<h3 style="margin-top:16px">Prossimi in coda</h3>'+r.prossimi.map(x=>voceCoda(x,'attesa')).join(''):'';
 $('recenti').innerHTML=(r.recenti||[]).length?'<h3 style="margin-top:16px">Completati di recente</h3>'+r.recenti.map(x=>voceCoda(x,'fatto')).join(''):'';
 $('stato-alto').textContent=r.in_corso?'Indicizzazione in corso…':(r.totale?`${r.totale.toLocaleString('it-IT')} file nell'indice`:'');
 const mostra=r.in_corso&&$('v-indice').hidden;$('sb').classList.toggle('on',!!mostra);
 if(mostra){$('sb-t').textContent=f.rel?`${nomeDi(f.rel)} · ${f.fase||''}`:testo;$('sb-p').textContent=r.da_fare?`${r.fatti}/${r.da_fare}`:'';$('sb-b').style.width=Math.min(100,pc)+'%'}}
setInterval(agg,1500);
/* ---------- esplora ---------- */
const S={tipo:'',k4:false,vista:'g',da:0,n:24,ris:[],q:'',corr:-1};
document.querySelectorAll('#filtri [data-tipo]').forEach(b=>b.onclick=()=>{S.tipo=b.dataset.tipo;document.querySelectorAll('#filtri [data-tipo]').forEach(x=>x.classList.toggle('on',x===b));cercaOra()});
$('f4k').onclick=()=>{S.k4=!S.k4;$('f4k').classList.toggle('on',S.k4);cercaOra()};
$('ord').onchange=()=>cercaOra();
$('vg').onclick=()=>{S.vista='g';$('vg').classList.add('on');$('ve').classList.remove('on');$('gr').classList.remove('elenco')};
$('ve').onclick=()=>{S.vista='e';$('ve').classList.add('on');$('vg').classList.remove('on');$('gr').classList.add('elenco')};
$('ce').onclick=()=>cercaOra();$('q').onkeydown=e=>{if(e.key==='Enter')cercaOra()};
function datiRiga(x){const m=x.meta||{},o=[];
 if(x.larghezza&&x.tipo!=='audio')o.push(x.larghezza+'×'+x.altezza+(m.Megapixel?' ('+m.Megapixel+' MP)':''));
 if(x.tipo==='video'&&m['Fotogrammi al secondo'])o.push(m['Fotogrammi al secondo']+' fps');
 if(m.Pagine)o.push(m.Pagine+' pag.');
 if(m.Modello)o.push(m.Modello);
 if(x.dimensione)o.push(mb(x.dimensione));
 const d=dataIt(x.data||x.mtime);if(d)o.push(d);return o.join(' · ')}
function etichettaTrovato(x){
 if(x.dove==='parlato')return`<b style="color:var(--pri)">${dur(x.secondo)}</b> ${evid(x.estratto||'')}`;
 if(x.dove==='immagine')return x.secondo!=null?`Immagine simile al minuto <b style="color:var(--pri)">${dur(x.secondo)}</b>`:'Immagine simile alla tua descrizione';
 if(x.dove==='meta')return'Trovato nei metadati: '+evid(x.estratto||'');
 if(x.dove==='nome')return'';
 return evid(x.estratto||'')}
function scheda(x,i){
 const t=x.secondo!=null?x.secondo:'';const vis=x.tipo==='immagine'||x.tipo==='video';
 const th=vis?`<img loading="lazy" alt="" src="/api/miniatura?id=${x.id}${t!==''?'&t='+t:''}&w=420" onerror="this.remove()">`:'';
 const tr=etichettaTrovato(x);
 return`<div class="sch" data-i="${i}"><div class="anteprima"><span class="grande">${icona(x.tipo,46)}</span>${th}<span class="badge sx">${NT[x.tipo]||x.tipo}</span>`+
 (x.risoluzione?`<span class="badge ris">${x.risoluzione}</span>`:'')+((x.tipo==='video'||x.tipo==='audio')&&x.durata?`<span class="badge dx">${dur(x.durata)}</span>`:'')+
 `</div><div class="corpo"><div class="nomefile" title="${E(x.percorso)}">${E(x.nome)}</div><div class="dove" title="${E(x.cartella)}"><bdi>${E(x.cartella)}</bdi></div><div class="dati">${E(datiRiga(x))}</div>${tr?`<div class="estratto">${tr}</div>`:''}</div></div>`}
async function cercaOra(altri){
 if(!altri){S.da=0;S.ris=[]}
 const q=$('q').value.trim();S.q=q;$('intest').textContent='Cerco…';
 let r;try{r=await j('/api/cerca?q='+encodeURIComponent(q)+'&tipo='+S.tipo+'&ordine='+$('ord').value+'&da='+S.da+'&n='+S.n+'&larghezza_min='+(S.k4?3800:0))}catch(e){$('intest').textContent='Non riesco a leggere l\'indice.';return}
 const nuovi=r.risultati||[];S.ris=S.ris.concat(nuovi);
 $('gr').innerHTML=S.ris.map(scheda).join('')||`<div class="vuoto" style="grid-column:1/-1">${q?'Nessun risultato. Prova con altre parole, o con una descrizione di ciò che si vede.':'L\'indice è vuoto: vai su «Indicizzazione», aggiungi una cartella e avvia.'}</div>`;
 $('gr').querySelectorAll('.sch').forEach(el=>el.onclick=()=>apriDett(Number(el.dataset.i)));
 $('altri').hidden=nuovi.length<S.n;
 $('intest').textContent=S.ris.length?(q?`${S.ris.length}${nuovi.length===S.n?'+':''} risultati per «${q}»`:'File indicizzati di recente (cerca per vedere i risultati più pertinenti)'):''}
$('altri').onclick=()=>{S.da+=S.n;cercaOra(true)};
/* ---------- dettaglio ---------- */
function chiudiDett(){$('dr').classList.remove('on');$('vela').classList.remove('on');$('dr').innerHTML=''}
$('vela').onclick=chiudiDett;
document.addEventListener('keydown',e=>{if(!$('dr').classList.contains('on')||/INPUT|TEXTAREA|SELECT/.test((e.target||{}).tagName))return;
 if(e.key==='Escape')chiudiDett();else if(e.key==='ArrowRight'&&S.corr<S.ris.length-1)apriDett(S.corr+1);else if(e.key==='ArrowLeft'&&S.corr>0)apriDett(S.corr-1)});
async function apriDett(i){S.corr=i;const x=S.ris[i];if(!x)return;$('vela').classList.add('on');$('dr').classList.add('on');$('dr').innerHTML='<div class="m">Carico…</div>';
 const d=await j('/api/dettaglio?id='+x.id);if(d.errore){$('dr').innerHTML='<div class="avviso">'+E(d.errore)+'</div>';return}
 const sec=x.secondo!=null?x.secondo:0,id=d.id;let pv='';
 if(d.tipo==='immagine')pv=`<img src="/api/media?id=${id}" alt="" onerror="this.onerror=function(){this.replaceWith(document.createTextNode('Anteprima non disponibile per questo formato: usa Apri.'))};this.src='/api/miniatura?id=${id}&w=1200'">`;
 else if(d.tipo==='video')pv=`<video id="pv" controls preload="metadata" poster="/api/miniatura?id=${id}&w=900${sec?'&t='+sec:''}" src="/api/media?id=${id}"></video>`;
 else if(d.tipo==='audio')pv=`<audio id="pv" controls preload="metadata" src="/api/media?id=${id}"></audio>`;
 else pv=`<div style="padding:30px;color:var(--pri)">${icona('testo',56)}</div>`;
 const righe=[['Percorso',d.percorso],['Dimensione',mb(d.dimensione)],['Modificato',dataIt(d.mtime)]];
 if(d.durata)righe.push(['Durata',dur(d.durata)]);
 if(d.larghezza&&d.tipo!=='audio'&&!(d.meta||{}).Risoluzione)righe.push(['Dimensioni',d.larghezza+'×'+d.altezza+(d.risoluzione?' ('+d.risoluzione+')':'')]);
 if(d.data)righe.push(['Data di ripresa',dataIt(d.data)+' '+String(d.data).slice(11,16)]);
 for(const[k,v]of Object.entries(d.meta||{}))righe.push([k,v]);
 const av=d.tipo==='video'||d.tipo==='audio';
 const testi=(d.testi||[]).map(t=>av&&t.tipo==='parlato'?`<div class="tr clic" data-s="${t.pos}"><b>${dur(t.pos)}</b><span>${E(t.testo)}</span></div>`:`<div class="tr"><span>${E(t.testo)}</span></div>`).join('');
 $('dr').innerHTML=`<div class="riga" style="justify-content:space-between"><div class="riga"><button class="s piccolo" id="dp" ${i<1?'disabled':''}>&larr;</button><button class="s piccolo" id="ds" ${i>=S.ris.length-1?'disabled':''}>&rarr;</button></div><button class="s piccolo" id="dx">Chiudi ✕</button></div>`+
 `<h2 style="margin-top:14px;word-break:break-word">${E(d.nome)}</h2><div class="m" style="word-break:break-all">${E(d.cartella)}</div><div class="prev">${pv}</div>`+
 (d.raggiungibile?'':'<div class="avviso">Il file non è raggiungibile ora: disco o NAS scollegato. Restano i dati dell\'indice.</div>')+(d.errore?`<div class="avviso">Errore in indicizzazione: ${E(d.errore)}</div>`:'')+
 `<div class="riga" style="margin:6px 0 14px"><button class="p piccolo" id="da">Apri col programma predefinito</button><button class="s piccolo" id="dm">Mostra nella cartella</button><button class="s piccolo" id="dc">Copia percorso</button></div><div class="m" id="dmsg"></div>`+
 `<h3>Informazioni</h3><table class="mt">${righe.map(r=>`<tr><td>${E(r[0])}</td><td>${E(r[1])}</td></tr>`).join('')}</table>`+
 (testi?`<h3 style="margin-top:18px">${av?'Trascrizione (tocca un passaggio per andarci)':'Testo'}</h3>${testi}`:'');
 $('dx').onclick=chiudiDett;$('dp').onclick=()=>apriDett(i-1);$('ds').onclick=()=>apriDett(i+1);
 const msg=t=>{$('dmsg').textContent=t};
 $('da').onclick=async()=>{const r=await j('/api/apri',{method:'POST',body:JSON.stringify({id})});msg(r.errore||'Aperto.')};
 $('dm').onclick=async()=>{const r=await j('/api/apri',{method:'POST',body:JSON.stringify({id,mostra:true})});msg(r.errore||'Cartella aperta.')};
 $('dc').onclick=()=>{const t=d.percorso;const fb=()=>{const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();try{document.execCommand('copy')}catch(e){}a.remove();msg('Percorso copiato.')};
  (navigator.clipboard?navigator.clipboard.writeText(t).then(()=>msg('Percorso copiato.')).catch(fb):Promise.resolve(fb()))};
 const el=$('pv');if(el){el.onerror=()=>{msg('Il lettore non riesce a riprodurre questo formato: usa «Apri col programma predefinito».')};if(sec)el.addEventListener('loadedmetadata',()=>{el.currentTime=sec},{once:true})}
 $('dr').querySelectorAll('[data-s]').forEach(t=>t.onclick=()=>{if(el){el.currentTime=Number(t.dataset.s);el.play().catch(()=>{})}})}
/* ---------- dialogo con Opifex ---------- */
let passo2=false;
async function opStato(){const r=await j('/api/opifex/stato');$('ou').value=$('ou').value||r.url||'https://app.opifex.space';$('oe').value=$('oe').value||r.email||'';
 $('ac').hidden=!!r.collegato;$('dl').hidden=!r.collegato;if(r.collegato){$('on').textContent='· '+(r.nome||'');if(!$('oa').options.length)opAgenti()}$('pn').textContent=r.collegato?('Browser per Opifex sul tuo computer: '+(r.ponte||'')):''}
setInterval(()=>{if(!$('dl').hidden&&!$('v-dialogo').hidden)opStato()},6000);
async function opAgenti(){const r=await j('/api/opifex/agenti');if(r.errore){$('om').textContent=r.errore;return}
 $('oa').innerHTML=(r.agenti||[]).map(a=>`<option value="${a.id}">${E(a.nome)} - ${E(a.ruolo||'')}</option>`).join('')}
$('ol').onclick=async()=>{$('om').textContent='Accedo…';let r;
 if(!passo2)r=await j('/api/opifex/login',{method:'POST',body:JSON.stringify({url:$('ou').value.trim(),email:$('oe').value.trim(),password:$('op').value})});
 else r=await j('/api/opifex/2fa',{method:'POST',body:JSON.stringify({codice:$('oc').value.trim()})});
 if(r.errore){$('om').textContent=r.errore;return}
 if(r.passo==='codice'){passo2=true;$('oc').hidden=false;$('op').hidden=true;$('om').textContent='Inserisci il codice del tuo secondo fattore.';return}
 passo2=false;$('oc').hidden=true;$('op').hidden=false;$('op').value='';$('oc').value='';$('om').textContent='';opStato()};
$('oq').onclick=async()=>{await j('/api/opifex/esci',{method:'POST'});$('oz').innerHTML='';$('oa').innerHTML='';opStato()};
function bolla(t,c){const d=document.createElement('div');d.className='mb '+c;d.textContent=t;$('oz').appendChild(d);$('oz').scrollTop=1e9;return d}
async function invia(){const m=$('ot').value.trim();if(!m||!$('oa').value)return;$('ot').value='';bolla(m,'u');const att=bolla('…','a');
 const r=await j('/api/opifex/chat',{method:'POST',body:JSON.stringify({agente_id:Number($('oa').value),messaggio:m,fascia:$('of').value,archivio:$('oar').checked})});
 if(r.errore){att.textContent='⚠ '+r.errore;return}
 for(let i=0;i<150;i++){await new Promise(z=>setTimeout(z,2000));const s=await j('/api/opifex/coda?id='+r.coda_id);
  if(s.errore){att.textContent='⚠ '+s.errore;return}
  if(s.stato==='finito'){const x=s.risultato||{};att.textContent=x.risposta||x.testo||JSON.stringify(x);$('oz').scrollTop=1e9;return}
  if(s.stato==='errore'){att.textContent='⚠ '+(s.errore||'Errore');return}}
 att.textContent='⚠ L\'agente sta ancora lavorando: la risposta comparirà in Opifex, nella Chat.'}
$('oi').onclick=invia;$('ot').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();invia()}};
const batti=()=>fetch('/api/vivo').catch(()=>{});batti();setInterval(batti,5000);addEventListener('pagehide',()=>{try{navigator.sendBeacon('/api/chiudi')}catch(e){}});
/* ---------- avvio: se l'indice è vuoto si parte dalle cartelle, altrimenti dall'archivio ---------- */
(async()=>{await agg();if(!PR.totale&&!PR.in_corso)vai('indice');else cercaOra()})();
</script></body></html>
"""


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

        def _bin(self, cod, dati, tipo, extra=None):
            self.send_response(cod); self.send_header("Content-Type", tipo); self.send_header("Content-Length", str(len(dati)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers(); self.wfile.write(dati)

        def _file(self, p, tipo):
            """Invia un file del computer a pezzi (serve a far scorrere i video nel lettore della finestra)."""
            tot = p.stat().st_size
            ini, fin, cod = 0, max(0, tot - 1), 200
            m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if m and (m[1] or m[2]):
                if m[1]:
                    ini = int(m[1]); fin = min(int(m[2]) if m[2] else tot - 1, tot - 1)
                else:
                    ini = max(0, tot - int(m[2]))
                if ini > fin:
                    return self._r(416, {"errore": "intervallo non valido"})
                cod = 206
            self.send_response(cod); self.send_header("Content-Type", tipo); self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fin - ini + 1))
            if cod == 206:
                self.send_header("Content-Range", f"bytes {ini}-{fin}/{tot}")
            self.end_headers()
            try:
                with open(p, "rb") as f:
                    f.seek(ini)
                    resto = fin - ini + 1
                    while resto > 0:
                        b = f.read(min(1 << 20, resto))
                        if not b:
                            break
                        self.wfile.write(b); resto -= len(b)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def _locale(self):
            """La finestra parla solo con questo computer: richieste da altri indirizzi o da altri siti web vengono rifiutate."""
            if not interfaccia:
                return True
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            origine = self.headers.get("Origin")
            return host in ("127.0.0.1", "localhost") and (not origine or urlparse(origine).hostname in ("127.0.0.1", "localhost"))

        def _ok(self, q):
            return not chiave or self.headers.get("Authorization", "") == "Bearer " + chiave or (q.get("chiave") or [""])[0] == chiave

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if not self._locale():
                return self._r(403, {"errore": "non consentito"})
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
                    st = stato(db)
                    return self._r(200, {**PROG, "totale": sum(st["file"].values()), "per_tipo": st["per_tipo"], "dimensione": st["dimensione"]})
                if interfaccia and u.path == "/api/cerca":
                    g = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
                    tipo = g("tipo") if g("tipo") in ("immagine", "video", "audio", "testo") else None
                    return self._r(200, {"risultati": cerca(db, g("q"), min(int(g("n", "24")), 100), finto, tipo, g("ordine", "rilevanza"),
                                                            int(g("da", "0")), int(g("larghezza_min", "0")))})
                if interfaccia and u.path == "/api/dettaglio":
                    try:
                        return self._r(200, dettaglio(db, int((q.get("id") or ["0"])[0])))
                    except ValueError as e:
                        return self._r(200, {"errore": str(e)})
                if interfaccia and u.path == "/api/miniatura":
                    t = (q.get("t") or [None])[0]
                    jpg = miniatura(db, int((q.get("id") or ["0"])[0]), float(t) if t not in (None, "") else None, int((q.get("w") or ["360"])[0]))
                    if jpg is None:
                        return self._bin(204, b"", "image/jpeg")
                    return self._bin(200, jpg, "image/jpeg", {"Cache-Control": "max-age=86400"})
                if interfaccia and u.path == "/api/media":
                    try:
                        p = _percorso_di(db, int((q.get("id") or ["0"])[0]))
                    except ValueError as e:
                        return self._r(404, {"errore": str(e)})
                    if not p.is_file():
                        return self._r(404, {"errore": "file non raggiungibile"})
                    import mimetypes
                    return self._file(p, mimetypes.guess_type(p.name)[0] or "application/octet-stream")
                if interfaccia and u.path == "/api/impostazioni":
                    return self._r(200, {"riprendi_da_solo": imp_leggi(db, "riprendi_da_solo", "1") == "1"})
                self._r(404, {"errore": "usa /cerca?q=... oppure /stato"})
            except Exception as e:  # noqa: BLE001
                self._r(500, {"errore": f"{type(e).__name__}: {e}"[:200]})

        def do_POST(self):
            if not interfaccia or not self._ok({}) or not self._locale():
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
                err = avvia_scansione(db, [str(x) for x in (corpo.get("cartelle") or [])], int(corpo.get("passo") or 30), finto)
                return self._r(200, {"errore": err} if err else {"ok": True})
            if self.path == "/api/impostazioni":
                if "riprendi_da_solo" in corpo:
                    imp_scrivi(db, "riprendi_da_solo", "1" if corpo["riprendi_da_solo"] else "0")
                return self._r(200, {"ok": True})
            if self.path == "/api/apri":
                try:
                    apri_file(db, int(corpo.get("id") or 0), bool(corpo.get("mostra")))
                    return self._r(200, {"ok": True})
                except ValueError as e:
                    return self._r(200, {"errore": str(e)})
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
    if interfaccia and finestra:
        def riprendi():   # all'apertura riparte da solo dalle cartelle ricordate (si puo' spegnere dalla finestra)
            time.sleep(4)
            if imp_leggi(db, "riprendi_da_solo", "1") == "1":
                avvia_scansione(db, None, 30, finto)
        threading.Thread(target=riprendi, daemon=True).start()
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
