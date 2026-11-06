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


SCHEMA_ANALISI = """
CREATE TABLE IF NOT EXISTS persone (id INTEGER PRIMARY KEY, nome TEXT, centro BLOB, n INTEGER DEFAULT 0, nascosta INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS volti (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL, pos REAL, x REAL, y REAL, w REAL, h REAL, punteggio REAL, emb BLOB, persona_id INTEGER);
CREATE INDEX IF NOT EXISTS volti_file ON volti(file_id);
CREATE INDEX IF NOT EXISTS volti_persona ON volti(persona_id);
CREATE TABLE IF NOT EXISTS etichette (file_id INTEGER NOT NULL, gruppo TEXT, tag TEXT, p REAL);
CREATE INDEX IF NOT EXISTS etichette_file ON etichette(file_id);
CREATE INDEX IF NOT EXISTS etichette_tag ON etichette(tag);
CREATE TABLE IF NOT EXISTS scene (file_id INTEGER NOT NULL, t0 REAL, t1 REAL);
CREATE INDEX IF NOT EXISTS scene_file ON scene(file_id);
CREATE TABLE IF NOT EXISTS raccolte (id INTEGER PRIMARY KEY, nome TEXT UNIQUE, creata REAL);
CREATE TABLE IF NOT EXISTS raccolta_file (raccolta_id INTEGER NOT NULL, file_id INTEGER NOT NULL, aggiunto REAL, PRIMARY KEY (raccolta_id, file_id));
"""


def apri(db: str) -> sqlite3.Connection:
    c = sqlite3.connect(db, check_same_thread=False, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    if "meta" not in {r[1] for r in c.execute("PRAGMA table_info(file)")}:
        c.execute("ALTER TABLE file ADD COLUMN meta TEXT")   # metadati letti dai file (archivi creati con versioni precedenti)
    c.execute("CREATE TABLE IF NOT EXISTS impostazioni (chiave TEXT PRIMARY KEY, valore TEXT)")
    cols = {r[1] for r in c.execute("PRAGMA table_info(file)")}
    for nome, tipo in (("analisi", "INTEGER DEFAULT 0"), ("nitidezza", "REAL"), ("esposizione", "TEXT"), ("dhash", "TEXT"), ("colori", "TEXT"), ("stelle", "INTEGER DEFAULT 0"),
                       ("colore", "TEXT"), ("parole", "TEXT"), ("n_volti", "INTEGER DEFAULT 0"), ("gruppo_dup", "INTEGER"), ("migliore", "INTEGER DEFAULT 1")):
        if nome not in cols:
            c.execute(f"ALTER TABLE file ADD COLUMN {nome} {tipo}")
    c.executescript(SCHEMA_ANALISI)
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
        subprocess.run([ffmpeg(), "-v", "error", "-ss", str(t), "-i", str(p), "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "4", "-y", str(f)], capture_output=True, timeout=300)
        if f.exists() and f.stat().st_size > 0:
            out.append((float(t), str(f)))
        if avanza:
            avanza((i + 1) / n)
    return out


def salva_vettori(c, fid, pos_v):
    for pos, v in pos_v:
        a = np.asarray(v, dtype="float16")
        c.execute("INSERT INTO vettore (file_id, pos, dim, v) VALUES (?,?,?,?)", (fid, pos, int(a.shape[0]), a.tobytes()))


# ---------- analisi aggiuntive: etichette, volti, qualita', scene ----------
B_ETICHETTE, B_QUALITA, B_VOLTI, B_SCENE = 1, 2, 4, 8
SOGLIA_VOLTO = float(os.environ.get("INDICE_SOGLIA_VOLTO", "0.45"))     # somiglianza (coseno) per dire «e' la stessa persona»
SOGLIA_DUP = int(os.environ.get("INDICE_SOGLIA_DUP", "6"))               # differenza massima (su 64) tra due foto quasi uguali
SOGLIA_SFOCATA = float(os.environ.get("INDICE_SOGLIA_SFOCATA", "25"))
SOGLIA_SCENA = os.environ.get("INDICE_SOGLIA_SCENA", "0.30")
MODELLI_VOLTI = {
    "yunet.onnx": ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
                   "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "sface.onnx": ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
                   "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79")}
# Ogni gruppo: (nome mostrato, frase per CLIP). Le frasi sono in inglese: il modello le capisce meglio e cerca comunque anche in italiano.
VOCABOLARIO = {
    "scena": [("paesaggio", "a landscape"), ("città", "a city street"), ("architettura", "the exterior of a building"), ("interno", "an indoor interior"),
              ("natura", "nature, trees and plants"), ("mare", "the sea and the coast"), ("montagna", "mountains"), ("ritratto", "a portrait of a person"),
              ("folla", "a crowd of people"), ("evento", "a public event"), ("oggetto", "a close-up of an object"), ("veduta aerea", "an aerial view from a drone"),
              ("opera d'arte", "a painting or a work of art"), ("documento", "a page of text or a document"), ("cibo", "food"), ("schermata", "a computer screenshot")],
    "inquadratura": [("campo lunghissimo", "an extreme wide shot of a vast scene"), ("campo largo", "a wide shot showing the whole place"),
                     ("campo medio", "a medium shot"), ("primo piano", "a close-up shot"), ("particolare", "an extreme close-up of a small detail")],
    "luce": [("alba o tramonto", "golden light of sunrise or sunset"), ("giorno", "a bright sunny day"), ("notte", "a dark night scene"),
             ("nuvoloso", "an overcast gray day"), ("controluce", "a backlit silhouette")],
    "soggetto": [("castello", "a castle"), ("torre", "a tower"), ("chiesa", "a church"), ("borgo", "a medieval village"), ("affresco", "a fresco on a wall"),
                 ("museo", "a museum gallery"), ("persone", "people"), ("bambini", "children"), ("intervista", "a person being interviewed"),
                 ("palco", "a stage performance"), ("strada", "a street"), ("ponte", "a bridge"), ("giardino", "a garden"), ("fiume", "a river"),
                 ("bosco", "a forest"), ("animali", "animals"), ("fiori", "flowers"), ("porto", "a harbour with boats"), ("rovine", "ancient ruins"),
                 ("libro o manoscritto", "a book or a manuscript"), ("statua", "a statue or a monument"), ("mercato", "a market"), ("auto", "a car"),
                 ("cielo", "the sky and clouds"), ("scultura", "a sculpture"), ("artigianato", "handmade craft work"), ("cucina", "people cooking")]}
SOGLIE_ETICHETTE = {"scena": (0.30, 1), "inquadratura": (0.35, 1), "luce": (0.40, 1), "soggetto": (0.12, 3)}


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def cartella_modelli(db) -> Path:
    return Path(os.environ.get("INDICE_MODELLI") or (Path(db).resolve().parent / "modelli"))


class Volti:
    """Riconoscimento dei volti in locale (OpenCV: YuNet per trovarli, SFace per distinguerli). I modelli, piccoli, si scaricano una volta sola e se ne controlla l'impronta."""

    def __init__(self, cartella):
        self.cartella = Path(cartella)
        self.ok = None
        self.motivo = ""

    def _modello(self, nome):
        url, sha = MODELLI_VOLTI[nome]
        dest = self.cartella / nome
        if dest.exists() and _sha256(dest) == sha:
            return dest
        self.cartella.mkdir(parents=True, exist_ok=True)
        import urllib.request
        tmp = dest.with_suffix(".tmp")
        with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        if _sha256(tmp) != sha:
            tmp.unlink()
            raise ValueError("il modello scaricato non ha l'impronta attesa")
        tmp.replace(dest)
        return dest

    def pronto(self) -> bool:
        if self.ok is None:
            try:
                import cv2
                self._cv2 = cv2
                self._det = cv2.FaceDetectorYN.create(str(self._modello("yunet.onnx")), "", (320, 320), 0.85, 0.3, 5000)
                self._rec = cv2.FaceRecognizerSF.create(str(self._modello("sface.onnx")), "")
                self.ok = True
            except Exception as e:  # noqa: BLE001
                self.ok = False
                self.motivo = f"{type(e).__name__}: {e}"[:160]
                log.warning("Riconoscimento volti non disponibile (%s)", self.motivo)
        return self.ok

    def rileva(self, percorso):
        cv2 = self._cv2
        img = cv2.imdecode(np.fromfile(str(percorso), dtype=np.uint8), cv2.IMREAD_COLOR)   # legge anche percorsi con accenti e applica l'orientamento EXIF
        if img is None:
            return []
        h, w = img.shape[:2]
        if max(h, w) > 2400:
            s = 2400 / max(h, w)
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]
        self._det.setInputSize((w, h))
        _, f = self._det.detect(img)
        out = []
        for r in (f if f is not None else []):
            x, y, fw, fh = (float(v) for v in r[:4])
            if fw < 36 or fh < 36:
                continue
            e = self._rec.feature(self._rec.alignCrop(img, r)).flatten().astype("float32")
            e /= (np.linalg.norm(e) or 1.0)
            out.append({"x": max(0.0, x) / w, "y": max(0.0, y) / h, "w": fw / w, "h": fh / h, "punteggio": float(r[14]), "emb": e, "px": min(fw, fh)})
        return out


class Persone:
    """Raggruppa i volti: ogni nuovo volto va alla persona piu' somigliante, oppure ne nasce una nuova. Il nome lo dai tu, una volta sola."""

    def __init__(self, c):
        self.c = c
        self.carica()

    def carica(self):
        r = self.c.execute("SELECT id, centro, n FROM persone WHERE centro IS NOT NULL").fetchall()
        self.ids = [x["id"] for x in r]
        self.ns = [x["n"] for x in r]
        self.M = np.stack([np.frombuffer(x["centro"], dtype="float32") for x in r]) if r else None

    def assegna(self, emb, buono: bool):
        if self.M is not None:
            s = self.M @ emb
            i = int(np.argmax(s))
            if s[i] >= SOGLIA_VOLTO:
                n = self.ns[i]
                nuovo = (self.M[i] * n + emb) / (n + 1)
                nuovo /= (np.linalg.norm(nuovo) or 1.0)
                self.M[i], self.ns[i] = nuovo, n + 1
                self.c.execute("UPDATE persone SET centro=?, n=? WHERE id=?", (nuovo.astype("float32").tobytes(), n + 1, self.ids[i]))
                return self.ids[i]
        if not buono:
            return None
        pid = self.c.execute("INSERT INTO persone (centro, n) VALUES (?,1)", (emb.astype("float32").tobytes(),)).lastrowid
        self.ids.append(pid)
        self.ns.append(1)
        self.M = emb[None, :].copy() if self.M is None else np.vstack([self.M, emb[None, :]])
        return pid


def salva_volti(c, fid, immagini, volti: Volti, persone: Persone):
    """Cerca i volti in foto o fotogrammi e li assegna alle persone. Ritorna quanti ne ha trovati."""
    c.execute("DELETE FROM volti WHERE file_id=?", (fid,))
    persone.carica()
    tot = 0
    for pos, f in immagini:
        try:
            trovati = volti.rileva(f)
        except Exception as e:  # noqa: BLE001
            log.debug("volti %s: %s", f, e)
            continue
        for v in trovati:
            pid = persone.assegna(v["emb"], v["punteggio"] >= 0.9 and v["px"] >= 60)
            c.execute("INSERT INTO volti (file_id, pos, x, y, w, h, punteggio, emb, persona_id) VALUES (?,?,?,?,?,?,?,?,?)",
                      (fid, pos, v["x"], v["y"], v["w"], v["h"], v["punteggio"], v["emb"].astype("float32").tobytes(), pid))
            tot += 1
    c.execute("UPDATE file SET n_volti=? WHERE id=?", (tot, fid))
    return tot


def qualita_immagine(percorso) -> dict:
    """Nitidezza, esposizione, colori dominanti e impronta visiva (per trovare le foto quasi uguali)."""
    from PIL import Image, ImageOps
    with Image.open(percorso) as im:
        im.draft("RGB", (1024, 1024))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((512, 512))
        g = np.asarray(im.convert("L"), dtype="float32")
        lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
        media, scuri, chiari = float(g.mean()), float((g < 20).mean()), float((g > 240).mean())
        esp = "sottoesposta" if media < 45 or scuri > 0.55 else "sovraesposta" if media > 215 or chiari > 0.30 else "ok"
        q = im.resize((96, 96)).quantize(5)
        pal = q.getpalette() or []
        freq = sorted(q.getcolors() or [], reverse=True)
        colori = ["#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]) for _, i in freq[:5]]
        px = np.asarray(im.convert("L").resize((9, 8)), dtype="int16")
        bit = (px[:, 1:] > px[:, :-1]).flatten()
        dh = f"{int(''.join('1' if b else '0' for b in bit), 2):016x}"
    return {"nitidezza": float(lap.var()), "esposizione": esp, "colori": colori, "dhash": dh, "luminosita": media}


def vocabolario(mod):
    """Le frasi del vocabolario, convertite una volta in vettori CLIP. None se CLIP non e' disponibile."""
    if getattr(mod, "_voc", None) is not None:
        return mod._voc or None
    voc = {}
    for g, voci in VOCABOLARIO.items():
        vs = [mod.testo("a photo of " + en) for _, en in voci]
        if any(v is None for v in vs):
            mod._voc = False
            return None
        voc[g] = ([n for n, _ in voci], np.stack([np.asarray(v, dtype="float32") for v in vs]))
    mod._voc = voc
    return voc


def calcola_etichette(c, mod, fid) -> bool:
    """Etichette dedotte dai vettori gia' calcolati (nessuna rilettura del file): scena, inquadratura, luce, soggetti."""
    voc = vocabolario(mod)
    righe = c.execute("SELECT dim, v FROM vettore WHERE file_id=?", (fid,)).fetchall()
    if not voc or not righe:
        return False
    d = next(iter(voc.values()))[1].shape[1]
    V = [np.frombuffer(r["v"], dtype="float16").astype("float32") for r in righe if r["dim"] == d]
    if not V:
        return False
    V = np.stack(V)
    c.execute("DELETE FROM etichette WHERE file_id=?", (fid,))
    tags = []
    for g, (nomi, T) in voc.items():
        z = 100.0 * (V @ T.T)
        z -= z.max(axis=1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(axis=1, keepdims=True)
        p = p.mean(axis=0)
        soglia, massimo = SOGLIE_ETICHETTE[g]
        for i in np.argsort(-p)[:massimo]:
            if p[i] >= soglia:
                tags.append((g, nomi[int(i)], float(p[i])))
    f = c.execute("SELECT max(w*h) a, count(*) n FROM volti WHERE file_id=?", (fid,)).fetchone()
    if f and f["n"]:
        tags.append(("soggetto", "persone", 1.0))
        if f["n"] >= 4:
            tags.append(("soggetto", "gruppo di persone", 1.0))
        if (f["a"] or 0) >= 0.06 and not any(t[1] == "primo piano" for t in tags):
            tags.append(("inquadratura", "primo piano", 0.9))
    for g, t, p in tags:
        c.execute("INSERT INTO etichette (file_id, gruppo, tag, p) VALUES (?,?,?,?)", (fid, g, t, p))
    c.execute("DELETE FROM testi WHERE file_id=? AND tipo='etichette'", (fid,))
    if tags:
        c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (" . ".join(sorted({t for _, t, _ in tags})), fid, "etichette", 0))
    return True


def scene_video(p: Path, durata: float):
    """Tagli di montaggio del video (cambi di inquadratura) letti da ffmpeg. Ritorna [(inizio, fine)]."""
    cmd = [ffmpeg(), "-hide_banner", "-nostats", "-i", str(p), "-vf", f"scale=320:-2,select='gt(scene,{SOGLIA_SCENA})',showinfo", "-an", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=6 * 3600)
    tagli = sorted({float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)})
    punti = [0.0] + [t for t in tagli if t > 0.5] + ([durata] if durata else [])
    out = []
    for a, b in zip(punti, punti[1:]):
        if b - a >= 0.5:
            out.append((a, b))
    return out or ([(0.0, durata)] if durata else [])


def analisi_extra(c, mod, ctx, fid, p: Path, tipo, immagini, durata, bits):
    """Le analisi oltre al testo e ai vettori. `immagini` = [(secondo, file)] di foto o fotogrammi gia' pronti. Segna come fatto cio' che e' riuscito."""
    fatto = 0
    if bits & B_QUALITA and immagini:
        fase("Misuro nitidezza e colori", 90)
        camp = [immagini[int(i * (len(immagini) - 1) / max(1, min(len(immagini), 12) - 1))] for i in range(min(len(immagini), 12))]
        rs = []
        for _, f in camp:
            try:
                rs.append(qualita_immagine(f))
            except Exception:  # noqa: BLE001
                pass
        if rs:
            r0 = rs[len(rs) // 2]
            nit = float(np.median([r["nitidezza"] for r in rs]))
            c.execute("UPDATE file SET nitidezza=?, esposizione=?, colori=?, dhash=? WHERE id=?",
                      (nit, r0["esposizione"], json.dumps(r0["colori"]), r0["dhash"] if tipo == "immagine" else None, fid))
            fatto |= B_QUALITA
    if bits & B_VOLTI and immagini and ctx.get("volti") is not None:
        fase("Cerco i volti", 92)
        salva_volti(c, fid, immagini, ctx["volti"], ctx["persone"])
        fatto |= B_VOLTI
    if bits & B_ETICHETTE:
        fase("Assegno le etichette", 95)
        if calcola_etichette(c, mod, fid):
            fatto |= B_ETICHETTE
    if bits & B_SCENE and tipo == "video":
        fase("Cerco i tagli di montaggio", 96)
        try:
            sc = scene_video(p, durata)
            c.execute("DELETE FROM scene WHERE file_id=?", (fid,))
            c.executemany("INSERT INTO scene (file_id, t0, t1) VALUES (?,?,?)", [(fid, a, b) for a, b in sc])
            fatto |= B_SCENE
        except Exception as e:  # noqa: BLE001
            log.debug("scene %s: %s", p, e)
    elif bits & B_SCENE:
        fatto |= B_SCENE
    c.execute("UPDATE file SET analisi = COALESCE(analisi, 0) | ? WHERE id=?", (fatto, fid))


def bits_attesi(db, mod, ctx) -> int:
    """Quali analisi aggiuntive sono attive e possibili su questo computer."""
    b = B_QUALITA
    if imp_leggi(db, "analisi_etichette", "1") == "1" and vocabolario(mod):
        b |= B_ETICHETTE
    if imp_leggi(db, "analisi_volti", "1") == "1":
        v = ctx.get("volti")
        if v is not None and v.pronto():
            b |= B_VOLTI
        elif v is not None:
            PROG["avvisi"].append("Riconoscimento volti non disponibile su questo computer: " + (v.motivo or "?"))
    if imp_leggi(db, "analisi_scene", "1") == "1":
        b |= B_SCENE
    return b


def completa_analisi(c, mod, ctx, bits, passo):
    """Applica le analisi aggiuntive ai file gia' indicizzati che non le hanno (archivi fatti prima, o funzioni accese dopo)."""
    righe = c.execute("SELECT * FROM file WHERE stato='ok' AND tipo IN ('immagine','video') AND (COALESCE(analisi,0) & ?) != ? "
                      "ORDER BY CASE tipo WHEN 'immagine' THEN 0 ELSE 1 END, id", (bits, bits)).fetchall()
    if not righe:
        return
    PROG.update(stadio="Analisi aggiuntive (volti, etichette, qualità, scene)", da_fare=len(righe), fatti=0, prossimi=[], recenti=[])
    tempi: dict = {}
    for i, riga in enumerate(righe):
        if PROG["ferma"]:
            break
        p = Path(riga["radice"]) / riga["rel"]
        PROG["corrente"] = riga["rel"]
        PROG["file"] = {"rel": riga["rel"], "tipo": riga["tipo"], "dimensione": riga["dimensione"], "fase": "Comincio", "pct": 1}
        PROG["prossimi"] = [{"rel": r["rel"], "tipo": r["tipo"], "dimensione": r["dimensione"]} for r in righe[i + 1:i + 11]]
        t0 = time.time()
        esito = True
        mancano = bits & ~(riga["analisi"] or 0)
        try:
            if not p.exists():
                esito = False
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    imgs = []
                    if mancano & (B_QUALITA | B_VOLTI):
                        if riga["tipo"] == "immagine":
                            imgs = [(0.0, str(p))]
                        else:
                            fase("Estraggo i fotogrammi", 20)
                            imgs = fotogrammi(p, passo, Path(tmp), riga["durata"] or 0)
                    analisi_extra(c, mod, ctx, riga["id"], p, riga["tipo"], imgs, riga["durata"] or 0, mancano)
        except Exception as e:  # noqa: BLE001
            esito = False
            log.warning("analisi %s: %s", riga["rel"], e)
        c.commit()
        sec = time.time() - t0
        PROG["fatti"] = i + 1
        PROG["recenti"] = ([{"rel": riga["rel"], "tipo": riga["tipo"], "sec": round(sec, 1), "ok": esito}] + PROG["recenti"])[:8]
        t = tempi.setdefault(riga["tipo"], [0, 0.0])
        t[0] += 1
        t[1] += sec
        PROG["eta_s"] = int(sum(x[1] for x in tempi.values()) / max(1, sum(x[0] for x in tempi.values())) * (len(righe) - i - 1))
    PROG["file"] = {}


def raggruppa_duplicati(c):
    """Foto quasi identiche (raffiche, copie): le mette in gruppo e segna la migliore. Non cancella e non sposta nulla."""
    c.execute("UPDATE file SET gruppo_dup=NULL, migliore=1 WHERE tipo='immagine'")
    r = c.execute("SELECT id, radice, rel, dhash, nitidezza, dimensione, larghezza, altezza FROM file WHERE tipo='immagine' AND dhash IS NOT NULL ORDER BY radice, rel").fetchall()
    padre: dict = {}

    def trova(x):
        while padre.setdefault(x, x) != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unisci(a, b):
        ra, rb = trova(a), trova(b)
        if ra != rb:
            padre[rb] = ra
    ints = [int(x["dhash"], 16) for x in r]
    uguali: dict = {}
    for i, x in enumerate(r):
        uguali.setdefault((ints[i], x["larghezza"], x["altezza"], x["dimensione"]), []).append(x["id"])
    for ids in uguali.values():
        for k in ids[1:]:
            unisci(ids[0], k)
    cartella = [x["radice"] + "|" + x["rel"].rsplit("/", 1)[0] if "/" in x["rel"] else x["radice"] + "|" for x in r]
    for i in range(len(r)):
        for j in range(i + 1, min(i + 31, len(r))):
            if cartella[i] == cartella[j] and bin(ints[i] ^ ints[j]).count("1") <= SOGLIA_DUP:
                unisci(r[i]["id"], r[j]["id"])
    gruppi: dict = {}
    for x in r:
        gruppi.setdefault(trova(x["id"]), []).append(x)
    for membri in gruppi.values():
        if len(membri) < 2:
            continue
        migliore = max(membri, key=lambda m: ((m["nitidezza"] or 0), m["dimensione"] or 0))
        gid = min(m["id"] for m in membri)
        for m in membri:
            c.execute("UPDATE file SET gruppo_dup=?, migliore=? WHERE id=?", (gid, 1 if m["id"] == migliore["id"] else 0, m["id"]))
    c.commit()


def pulisci_analisi(c, fid):
    for t in ("volti", "etichette", "scene"):
        c.execute(f"DELETE FROM {t} WHERE file_id = ?", (fid,))  # nosec B608 - nomi fissi
    c.execute("UPDATE file SET analisi=0, n_volti=0 WHERE id = ?", (fid,))


def indicizza_file(c, mod: Modelli, riga, radice: Path, passo: int, ctx=None):
    p = radice / riga["rel"]
    est = p.suffix.lower()
    fid = riga["id"]
    tipo = riga["tipo"]
    bits = (ctx or {}).get("bits", 0)
    c.execute("DELETE FROM testi WHERE file_id = ?", (fid,))
    c.execute("DELETE FROM vettore WHERE file_id = ?", (fid,))
    pulisci_analisi(c, fid)
    c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (riga["rel"].replace("/", " ").replace("_", " ").replace("-", " "), fid, "nome", 0))
    fase("Leggo i metadati", 3)
    meta, info = leggi_metadati(p, tipo)
    salva_meta(c, fid, meta, info, tipo)   # i metadati sono subito ricercabili, anche se il resto fallisce
    if est in EST_TESTO or est in (".docx", ".pdf"):
        fase("Leggo il testo", 20)
        for i, b in enumerate(blocchi(testo_di(p, est))):
            c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (b, fid, "testo", i))
    elif est in EST_IMG:
        if np is not None:
            fase("Analizzo l'immagine", 40)
            salva_vettori(c, fid, [(0.0, v) for v in mod.immagini([str(p)])])
        if bits:
            analisi_extra(c, mod, ctx, fid, p, tipo, [(0.0, str(p))], 0, bits)
    elif est in EST_VID or est in EST_AUD:
        durata = info.get("durata") or 0
        with tempfile.TemporaryDirectory() as tmp:
            fase("Estraggo l'audio", 8)
            wav = os.path.join(tmp, "a.wav")
            r = subprocess.run([ffmpeg(), "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000", wav], capture_output=True, timeout=7200)
            video = est in EST_VID and (np is not None or bool(bits & (B_QUALITA | B_VOLTI)))
            if r.returncode == 0 and os.path.exists(wav):
                fine_tr = 70 if video else 97
                fase("Trascrivo il parlato", 10)
                for t0, tx in mod.trascrivi(wav, lambda f: fase("Trascrivo il parlato", 10 + f * (fine_tr - 10)), durata):
                    c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (tx, fid, "parlato", t0))
            if video:
                fase("Estraggo i fotogrammi", 72)
                fr = fotogrammi(p, passo, Path(tmp), durata, lambda f: fase("Estraggo i fotogrammi", 72 + f * 13))
                if fr and np is not None:
                    fase("Analizzo le immagini", 86)
                    salva_vettori(c, fid, list(zip([t for t, _ in fr], mod.immagini([f for _, f in fr]))))
                if bits:
                    analisi_extra(c, mod, ctx, fid, p, tipo, fr, durata, bits)
    fase("Salvo", 99)
    c.execute("UPDATE file SET stato='ok', errore=NULL, indicizzato=? WHERE id=?", (time.time(), fid))


PROG = {"in_corso": False, "fatti": 0, "da_fare": 0, "corrente": "", "ferma": False, "esito": "", "fase_scan": "", "visti": 0,
        "file": {}, "prossimi": [], "recenti": [], "eta_s": None, "inizio": None, "avvisi": [], "stadio": ""}


def fase(nome, pct):
    """Dove sta lavorando ora l'indice, per il file in corso (si vede nella finestra)."""
    f = PROG.setdefault("file", {})
    f["fase"], f["pct"] = nome, int(max(0, min(99, pct)))


def avvia_scansione(db, cartelle=None, passo=15, finto=False):
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
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)   # il PC non va in sospensione finche' lavora
        except Exception:  # noqa: BLE001
            pass
        try:
            r = scansiona(db, cart, 0, passo, finto)
            PROG["esito"] = "Fermato." if PROG["ferma"] else f"Finito: {r['fatti']} file indicizzati."
        except Exception as e:  # noqa: BLE001
            PROG["esito"] = f"Errore: {type(e).__name__}: {e}"[:200]
        PROG.update(in_corso=False, corrente="", file={}, prossimi=[], fase_scan="", stadio="")
        try:
            if sys.platform == "win32":
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:  # noqa: BLE001
            pass
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
    PROG.update(fase_scan="Preparo i modelli di analisi", stadio="Indicizzo i nuovi file")
    usa_volti = imp_leggi(db, "analisi_volti", "1") == "1" and (not finto or bool(os.environ.get("INDICE_MODELLI")))
    ctx = {"volti": Volti(cartella_modelli(db)) if usa_volti else None, "persone": Persone(c)}
    ctx["bits"] = 0 if PROG["ferma"] else bits_attesi(db, mod, ctx)
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
            indicizza_file(c, mod, riga, Path(riga["radice"]), passo, ctx)
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
    if not PROG["ferma"] and not limite:
        completa_analisi(c, mod, ctx, ctx["bits"], passo)
        if not PROG["ferma"]:
            raggruppa_duplicati(c)
    return {"da_fare": len(coda), "fatti": fatti}


# ---------- ricerca ----------
def _fts_query(q: str) -> str:
    parole = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]
    return " OR ".join(f'"{w}"*' for w in parole[:12])


SOGLIA_SIM = float(os.environ.get("INDICE_SOGLIA", "0.20"))   # sotto questa somiglianza CLIP un fotogramma non e' una risposta
COLONNE = ("id, radice, rel, tipo, dimensione, mtime, durata, larghezza, altezza, data_ripresa, meta, stelle, colore, parole, n_volti, colori, nitidezza, esposizione, "
           "gruppo_dup, migliore, (SELECT group_concat(tag, '|') FROM etichette WHERE file_id = file.id) AS tags")
COLORI_VALIDI = ("rosso", "arancio", "giallo", "verde", "blu", "viola")


def _scheda(f, dove=None, pos=None, estratto=None, punteggio=None):
    """Una riga del catalogo, con tutto quello che serve a mostrarla (percorso, misure, metadati, etichette)."""
    try:
        meta = json.loads(f["meta"]) if f["meta"] else {}
    except ValueError:
        meta = {}
    try:
        colori = json.loads(f["colori"]) if f["colori"] else []
    except ValueError:
        colori = []
    rel = f["rel"]
    video_audio = f["tipo"] in ("video", "audio")
    return {"id": f["id"], "file": rel, "nome": rel.rsplit("/", 1)[-1], "cartella": str(Path(f["radice"]) / rel.rsplit("/", 1)[0]) if "/" in rel else f["radice"],
            "radice": f["radice"], "percorso": str(Path(f["radice"]) / rel), "tipo": f["tipo"], "dove": dove,
            "secondo": round(pos, 1) if dove in ("parlato", "immagine", "persona", "simili") and video_audio and pos is not None else None,
            "estratto": estratto, "data": f["data_ripresa"], "punteggio": punteggio, "dimensione": f["dimensione"], "mtime": f["mtime"],
            "durata": f["durata"], "larghezza": f["larghezza"], "altezza": f["altezza"], "meta": meta,
            "risoluzione": etichetta_risoluzione(f["larghezza"], f["altezza"]) if f["tipo"] == "video" else "",
            "stelle": f["stelle"] or 0, "colore": f["colore"] or "", "parole": f["parole"] or "", "n_volti": f["n_volti"] or 0,
            "tags": [t for t in (f["tags"] or "").split("|") if t], "colori": colori, "sfocata": f["tipo"] == "immagine" and f["nitidezza"] is not None and f["nitidezza"] < SOGLIA_SFOCATA,
            "esposizione": f["esposizione"] or "", "doppioni": bool(f["gruppo_dup"]) and not f["migliore"], "in_gruppo": bool(f["gruppo_dup"])}


ORDINI_SQL = {"recenti": "indicizzato DESC", "data": "COALESCE(data_ripresa, datetime(mtime, 'unixepoch')) DESC", "nome": "rel COLLATE NOCASE ASC",
              "dimensione": "dimensione DESC", "nitidezza": "nitidezza DESC"}


def _clausole(tipo=None, min_larghezza=0, filtri=None):
    """Condizioni SQL comuni a ricerca e catalogo (tipo, risoluzione, stelle, colore, raccolta, persona, etichetta, solo migliori, sfocate)."""
    f = filtri or {}
    dove, par = [], []
    if tipo:
        dove.append("tipo=?"); par.append(tipo)
    if min_larghezza:
        dove.append("larghezza>=?"); par.append(int(min_larghezza))
    if f.get("stelle"):
        dove.append("stelle>=?"); par.append(int(f["stelle"]))
    if f.get("colore") in COLORI_VALIDI:
        dove.append("colore=?"); par.append(f["colore"])
    if f.get("raccolta"):
        dove.append("id IN (SELECT file_id FROM raccolta_file WHERE raccolta_id=?)"); par.append(int(f["raccolta"]))
    if f.get("persona"):
        dove.append("id IN (SELECT file_id FROM volti WHERE persona_id=?)"); par.append(int(f["persona"]))
    if f.get("tag"):
        dove.append("id IN (SELECT file_id FROM etichette WHERE tag=?)"); par.append(str(f["tag"]))
    if f.get("migliori"):
        dove.append("COALESCE(migliore, 1)=1")
    if f.get("sfocate"):
        dove.append("tipo='immagine' AND nitidezza IS NOT NULL AND nitidezza < ?"); par.append(SOGLIA_SFOCATA)
    if f.get("con_volti"):
        dove.append("n_volti > 0")
    return dove, par


def _dopo_persona(c, schede, filtri):
    pid = (filtri or {}).get("persona")
    if pid:
        for s in schede:
            r = c.execute("SELECT min(pos) p FROM volti WHERE file_id=? AND persona_id=?", (s["id"], int(pid))).fetchone()
            if r and r["p"] is not None and s["tipo"] == "video":
                s["dove"], s["secondo"] = "persona", round(r["p"], 1)
    return schede


def sfoglia(db, n=30, offset=0, tipo=None, ordine="recenti", min_larghezza=0, filtri=None):
    """Il catalogo senza una frase di ricerca: i file piu' recenti (o ordinati come si preferisce) con i loro metadati."""
    c = apri(db)
    dove, par = _clausole(tipo, min_larghezza, filtri)
    dove.insert(0, "stato='ok'")
    o = ORDINI_SQL.get(ordine, ORDINI_SQL["recenti"])
    righe = c.execute(f"SELECT {COLONNE} FROM file WHERE {' AND '.join(dove)} ORDER BY {o} LIMIT ? OFFSET ?", (*par, n, offset)).fetchall()  # nosec B608 - parti fisse
    return _dopo_persona(c, [_scheda(f) for f in righe], filtri)


_VETT = {"k": None, "ids": [], "pos": [], "M": None}


def _matrice(c):
    """Tutti i vettori in memoria, riletti solo quando l'indice cambia: rende rapide ricerca e «trova simili»."""
    k = tuple(c.execute("SELECT count(*), COALESCE(max(id),0) FROM vettore").fetchone())
    if _VETT["k"] == k and _VETT["M"] is not None:
        return _VETT
    righe = c.execute("SELECT file_id, pos, dim, v FROM vettore").fetchall()
    if not righe:
        _VETT.update(k=k, ids=[], pos=[], M=None)
        return _VETT
    dim = max({r["dim"] for r in righe}, key=lambda d: sum(1 for r in righe if r["dim"] == d))
    ok = [r for r in righe if r["dim"] == dim]
    _VETT.update(k=k, ids=[r["file_id"] for r in ok], pos=[r["pos"] for r in ok],
                 M=np.stack([np.frombuffer(r["v"], dtype="float16").astype("float32") for r in ok]))
    return _VETT


def cerca(db, q, n=10, finto=False, tipo=None, ordine="rilevanza", offset=0, min_larghezza=0, filtri=None):
    if not (q or "").strip():
        return sfoglia(db, n, offset, tipo, "recenti" if ordine == "rilevanza" else ordine, min_larghezza, filtri)
    c = apri(db)
    punti: dict = {}
    pool = (n + offset) * (8 if (tipo or min_larghezza or filtri) else 4)

    def aggiungi(fid, pos, tipo_, testo, rango, peso):
        k = (fid, tipo_)
        p = punti.setdefault(k, {"file_id": fid, "tipo": tipo_, "pos": pos, "testo": testo, "score": 0.0})
        p["score"] += peso / (60 + rango)
    fq = _fts_query(q)
    if fq:
        for i, r in enumerate(c.execute("SELECT file_id, tipo, pos, snippet(testi, 0, '[', ']', ' … ', 18) AS s FROM testi WHERE testi MATCH ? ORDER BY bm25(testi) LIMIT ?", (fq, pool))):
            aggiungi(r["file_id"], r["pos"], r["tipo"], r["s"], i, 1.0)
    ql = q.strip().lower()   # il nome di una persona trova tutti i file in cui compare
    for pr in c.execute("SELECT id, nome FROM persone WHERE nome IS NOT NULL AND lower(nome) LIKE ?", (f"%{ql}%",)).fetchall():
        for i, r in enumerate(c.execute("SELECT file_id, min(pos) p FROM volti WHERE persona_id=? GROUP BY file_id LIMIT ?", (pr["id"], pool))):
            aggiungi(r["file_id"], r["p"], "persona", pr["nome"], i, 1.5)
    V = _matrice(c) if np is not None else {"M": None}
    if V["M"] is not None:
        v = Modelli(finto).testo(q)
        if v is not None and len(v) == V["M"].shape[1]:
            s = V["M"] @ np.asarray(v, dtype="float32")
            soglia = 0.6 if finto else SOGLIA_SIM
            for rango, i in enumerate([k for k in np.argsort(-s)[:pool] if s[k] >= soglia]):
                aggiungi(V["ids"][i], V["pos"][i], "immagine", f"somiglianza visiva {float(s[i]):.2f}", rango, 0.8)
    ris = sorted(punti.values(), key=lambda x: -x["score"])
    dove, par = _clausole(tipo, min_larghezza, filtri)
    extra = (" AND " + " AND ".join(dove)) if dove else ""
    visti, out = set(), []
    for r in ris:
        if r["file_id"] in visti:
            continue
        f = c.execute(f"SELECT {COLONNE} FROM file WHERE id=?{extra}", (r["file_id"], *par)).fetchone()  # nosec B608 - parti fisse
        if f is None:
            continue
        visti.add(r["file_id"])
        out.append(_scheda(f, r["tipo"], r["pos"], r["testo"], round(r["score"] * 100, 2)))
    if ordine in ("data", "nome", "dimensione"):
        out.sort(key=(lambda x: x["data"] or "") if ordine == "data" else (lambda x: x["nome"].lower()) if ordine == "nome" else (lambda x: -(x["dimensione"] or 0)),
                 reverse=(ordine == "data"))
    return _dopo_persona(c, out[offset:offset + n], filtri)


def simili(db, fid: int, n=24, offset=0):
    """Le immagini piu' vicine a una data (anche in altre cartelle e nei fotogrammi dei video), per somiglianza visiva."""
    c = apri(db)
    V = _matrice(c)
    if V["M"] is None:
        return []
    sel = [i for i, x in enumerate(V["ids"]) if x == fid]
    if not sel:
        return []
    q = V["M"][sel].mean(axis=0)
    q /= (np.linalg.norm(q) or 1.0)
    s = V["M"] @ q
    out, visti = [], {fid}
    for i in np.argsort(-s):
        f_id = V["ids"][int(i)]
        if f_id in visti:
            continue
        visti.add(f_id)
        f = c.execute(f"SELECT {COLONNE} FROM file WHERE id=?", (f_id,)).fetchone()
        if f is not None:
            out.append(_scheda(f, "simili", V["pos"][int(i)], f"somiglianza {float(s[i]):.2f}", round(float(s[i]) * 100, 1)))
        if len(out) >= n + offset:
            break
    return out[offset:]


def dettaglio(db, fid: int):
    c = apri(db)
    f = c.execute(f"SELECT {COLONNE}, stato, errore, indicizzato, analisi FROM file WHERE id=?", (fid,)).fetchone()
    if f is None:
        raise ValueError("File non trovato nell'indice")
    d = _scheda(f)
    d.update(stato=f["stato"], errore=f["errore"], indicizzato=f["indicizzato"], raggiungibile=os.path.exists(d["percorso"]))
    d["testi"] = [{"pos": r["pos"], "tipo": r["tipo"], "testo": r["testo"]} for r in
                  c.execute("SELECT pos, tipo, testo FROM testi WHERE file_id=? AND tipo IN ('parlato','testo') ORDER BY CAST(pos AS REAL) LIMIT 400", (fid,))]
    d["volti"] = [{"id": r["id"], "pos": r["pos"], "persona_id": r["persona_id"], "nome": r["nome"], "x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]} for r in
                  c.execute("SELECT v.id, v.pos, v.persona_id, p.nome, v.x, v.y, v.w, v.h FROM volti v LEFT JOIN persone p ON p.id=v.persona_id WHERE v.file_id=? ORDER BY v.pos, v.x LIMIT 300", (fid,))]
    d["scene"] = [{"t0": r["t0"], "t1": r["t1"]} for r in c.execute("SELECT t0, t1 FROM scene WHERE file_id=? ORDER BY t0 LIMIT 2000", (fid,))]
    d["etichette"] = [{"gruppo": r["gruppo"], "tag": r["tag"]} for r in c.execute("SELECT gruppo, tag FROM etichette WHERE file_id=? ORDER BY gruppo", (fid,))]
    d["raccolte"] = [r["nome"] for r in c.execute("SELECT r.nome FROM raccolte r JOIN raccolta_file x ON x.raccolta_id=r.id WHERE x.file_id=?", (fid,))]
    d["gruppo"] = ([{"id": r["id"], "nome": r["rel"].rsplit("/", 1)[-1], "migliore": bool(r["migliore"])} for r in
                    c.execute("SELECT id, rel, migliore FROM file WHERE gruppo_dup=(SELECT gruppo_dup FROM file WHERE id=?) AND id!=?", (fid, fid))]
                   if f["gruppo_dup"] else [])
    return d


# ---------- valutazioni, raccolte, etichette ----------
def valuta(db, ids, stelle=None, colore=None, parole=None):
    c = apri(db)
    ids = [int(i) for i in ids][:5000]
    for fid in ids:
        if stelle is not None:
            c.execute("UPDATE file SET stelle=? WHERE id=?", (max(0, min(5, int(stelle))), fid))
        if colore is not None:
            c.execute("UPDATE file SET colore=? WHERE id=?", (colore if colore in COLORI_VALIDI else None, fid))
        if parole is not None:
            testo = ", ".join(p.strip() for p in str(parole).split(",") if p.strip())[:500]
            c.execute("UPDATE file SET parole=? WHERE id=?", (testo or None, fid))
            c.execute("DELETE FROM testi WHERE file_id=? AND tipo='parole'", (fid,))
            if testo:
                c.execute("INSERT INTO testi (testo, file_id, tipo, pos) VALUES (?,?,?,?)", (testo, fid, "parole", 0))
    c.commit()


def raccolte_elenco(db):
    return [dict(r) for r in apri(db).execute("SELECT r.id, r.nome, (SELECT count(*) FROM raccolta_file x WHERE x.raccolta_id=r.id) AS n FROM raccolte r ORDER BY r.nome COLLATE NOCASE")]


def raccolta_azione(db, corpo: dict):
    c = apri(db)
    if corpo.get("crea"):
        nome = str(corpo["crea"]).strip()[:80]
        if not nome:
            raise ValueError("Scrivi un nome per la raccolta")
        c.execute("INSERT OR IGNORE INTO raccolte (nome, creata) VALUES (?,?)", (nome, time.time()))
        rid = c.execute("SELECT id FROM raccolte WHERE nome=?", (nome,)).fetchone()["id"]
    else:
        rid = int(corpo.get("id") or 0)
        if not c.execute("SELECT 1 FROM raccolte WHERE id=?", (rid,)).fetchone():
            raise ValueError("Raccolta non trovata")
    for fid in corpo.get("aggiungi") or []:
        c.execute("INSERT OR IGNORE INTO raccolta_file (raccolta_id, file_id, aggiunto) VALUES (?,?,?)", (rid, int(fid), time.time()))
    for fid in corpo.get("togli") or []:
        c.execute("DELETE FROM raccolta_file WHERE raccolta_id=? AND file_id=?", (rid, int(fid)))
    if corpo.get("elimina"):
        c.execute("DELETE FROM raccolta_file WHERE raccolta_id=?", (rid,))
        c.execute("DELETE FROM raccolte WHERE id=?", (rid,))
    c.commit()
    return rid


def etichette_elenco(db, n=80):
    return [dict(r) for r in apri(db).execute("SELECT tag, gruppo, count(DISTINCT file_id) AS n FROM etichette GROUP BY tag, gruppo ORDER BY n DESC LIMIT ?", (n,))]


# ---------- persone ----------
def persone_elenco(db, nascoste=False):
    c = apri(db)
    righe = c.execute("""SELECT p.id, p.nome, p.nascosta,
        (SELECT count(*) FROM volti v WHERE v.persona_id=p.id) AS n_volti,
        (SELECT count(DISTINCT file_id) FROM volti v WHERE v.persona_id=p.id) AS n_file,
        (SELECT id FROM volti v WHERE v.persona_id=p.id ORDER BY v.punteggio * v.w * v.h DESC LIMIT 1) AS esempio
        FROM persone p WHERE p.nascosta=? ORDER BY n_file DESC, p.id""", (1 if nascoste else 0,)).fetchall()
    return [dict(r) for r in righe if r["n_volti"] > 0]


def persona_rinomina(db, pid, nome):
    c = apri(db)
    c.execute("UPDATE persone SET nome=? WHERE id=?", ((nome or "").strip()[:80] or None, int(pid)))
    c.commit()


def persona_nascondi(db, pid, nascondi=True):
    c = apri(db)
    c.execute("UPDATE persone SET nascosta=? WHERE id=?", (1 if nascondi else 0, int(pid)))
    c.commit()


def persone_unisci(db, da, a):
    """Due gruppi che erano la stessa persona: i volti di `da` passano ad `a` (il nome di `a` resta, altrimenti prende quello di `da`)."""
    da, a = int(da), int(a)
    if da == a:
        raise ValueError("Scegli due persone diverse")
    c = apri(db)
    pa, pd = (c.execute("SELECT nome, centro, n FROM persone WHERE id=?", (x,)).fetchone() for x in (a, da))
    if pa is None or pd is None:
        raise ValueError("Persona non trovata")
    c.execute("UPDATE volti SET persona_id=? WHERE persona_id=?", (a, da))
    if pa["centro"] and pd["centro"]:
        m = (np.frombuffer(pa["centro"], dtype="float32") * pa["n"] + np.frombuffer(pd["centro"], dtype="float32") * pd["n"])
        m /= (np.linalg.norm(m) or 1.0)
        c.execute("UPDATE persone SET centro=?, n=? WHERE id=?", (m.astype("float32").tobytes(), pa["n"] + pd["n"], a))
    if not pa["nome"] and pd["nome"]:
        c.execute("UPDATE persone SET nome=? WHERE id=?", (pd["nome"], a))
    c.execute("DELETE FROM persone WHERE id=?", (da,))
    c.commit()


def volto_sposta(db, vid, persona_id=None):
    """Corregge un errore: questo volto non e' di quella persona. Senza destinazione ne nasce una nuova."""
    c = apri(db)
    v = c.execute("SELECT emb FROM volti WHERE id=?", (int(vid),)).fetchone()
    if v is None:
        raise ValueError("Volto non trovato")
    if not persona_id:
        persona_id = c.execute("INSERT INTO persone (centro, n) VALUES (?,1)", (v["emb"],)).lastrowid
    c.execute("UPDATE volti SET persona_id=? WHERE id=?", (int(persona_id), int(vid)))
    c.commit()
    return persona_id


def volto_miniatura(db, vid: int, w=160):
    """Il ritaglio del volto (con un po' di margine), preso dalla foto o dal fotogramma del video."""
    c = apri(db)
    v = c.execute("SELECT v.file_id, v.pos, v.x, v.y, v.w, v.h, f.radice, f.rel, f.tipo FROM volti v JOIN file f ON f.id=v.file_id WHERE v.id=?", (int(vid),)).fetchone()
    if v is None:
        return None
    w = max(48, min(int(w), 600))
    cache = Path(db).resolve().parent / "miniature"
    cache.mkdir(exist_ok=True)
    dest = cache / f"volto_{int(vid)}_{w}.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    p = Path(v["radice"]) / v["rel"]
    if not p.exists():
        return None
    from PIL import Image, ImageOps
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = str(p)
            if v["tipo"] == "video":
                src = os.path.join(tmp, "f.jpg")
                subprocess.run([ffmpeg(), "-v", "error", "-ss", str(v["pos"] or 0), "-i", str(p), "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "3", "-y", src], capture_output=True, timeout=120)
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                W, H = im.size
                mx, my = v["w"] * 0.35, v["h"] * 0.35
                box = (max(0, int((v["x"] - mx) * W)), max(0, int((v["y"] - my) * H)), min(W, int((v["x"] + v["w"] + mx) * W)), min(H, int((v["y"] + v["h"] + my) * H)))
                im = im.crop(box)
                im.thumbnail((w, w))
                im.save(dest, "JPEG", quality=85)
    except Exception:  # noqa: BLE001
        return None
    return dest.read_bytes() if dest.exists() else None


# ---------- avvio con Windows ----------
def _collegamento_avvio() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Opifex Archivio.lnk"


def avvio_windows(attivo=None):
    """Fa partire l'archivio da solo all'accensione del computer (senza aprire finestre): serve a un PC dedicato che lavora da solo."""
    exe = os.environ.get("OPIFEX_EXE", "")
    if sys.platform != "win32" or not exe:
        return {"disponibile": False, "attivo": False}
    lnk = _collegamento_avvio()
    if attivo is None:
        return {"disponibile": True, "attivo": lnk.exists()}
    if attivo:
        q = lambda t: str(t).replace("'", "''")  # noqa: E731
        cmd = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(lnk)}');$s.TargetPath='{q(exe)}';$s.Arguments='--nascosto';"
               f"$s.WorkingDirectory='{q(Path(exe).parent)}';$s.Description='Opifex - Archivio (avvio automatico)';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, timeout=60, creationflags=0x08000000)
    elif lnk.exists():
        lnk.unlink()
    return {"disponibile": True, "attivo": lnk.exists()}


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
            "volti": c.execute("SELECT count(*) n FROM volti").fetchone()["n"],
            "persone": c.execute("SELECT count(*) n FROM persone WHERE nascosta=0 AND id IN (SELECT persona_id FROM volti)").fetchone()["n"],
            "etichettati": c.execute("SELECT count(DISTINCT file_id) n FROM etichette").fetchone()["n"],
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
        for t in ("volti", "etichette", "scene", "raccolta_file"):
            c.execute(f"DELETE FROM {t} WHERE file_id IN ({q})", blocco)  # nosec B608 - nomi fissi
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

/* 2.26: valutazioni, persone, filtri, scene */
.filtri2{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:-6px 0 16px}
.filtri2 select{padding:5px 10px;border-radius:999px;font-size:13px;font-weight:600;background:rgba(255,255,255,.10);border:1px solid transparent;color:#D9CFC4}
.filtri2 select.on{background:rgba(232,146,74,.22);border-color:var(--pri);color:#F7B97A}
.pal{display:inline-flex;gap:5px;align-items:center}.pal button{width:20px;height:20px;border-radius:50%;border:2px solid transparent;padding:0}.pal button.on{border-color:#fff}
.stelle{display:inline-flex;gap:2px}.stelle button{background:transparent;border:0;color:rgba(255,255,255,.28);font-size:22px;line-height:1;padding:0 2px}.stelle button.on{color:#F2A862}.stelle button:hover{color:#F7B97A}
.badge.st{right:8px;top:8px;color:#F2A862;letter-spacing:1px}.badge.av{left:8px;top:32px;background:rgba(243,196,106,.9);color:#1A110A}
.badge.pt{width:12px;height:12px;border-radius:50%;padding:0;right:8px;top:30px}
.tagrow{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}.tagrow .et{font-size:11px;padding:1px 8px}
.mese{grid-column:1/-1;margin:14px 0 2px;font-family:var(--serif);font-size:19px;text-transform:capitalize;letter-spacing:0;color:var(--testo);font-weight:500}
.avviso.az{display:flex;align-items:center;gap:10px;justify-content:space-between;background:rgba(232,146,74,.16);color:#F7B97A}
.pers-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}
.pers{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:22px;padding:14px;display:flex;flex-direction:column;gap:8px;align-items:center;text-align:center}
.pers img,.vis-v img{width:112px;height:112px;border-radius:50%;object-fit:cover;background:rgba(0,0,0,.3);border:2px solid rgba(232,146,74,.5)}
.pers input{text-align:center;font-family:var(--serif);font-size:17px}
.pers select{width:100%;font-size:13px}
.volti-r{display:flex;gap:12px;flex-wrap:wrap}.vis-v{width:104px;display:flex;flex-direction:column;gap:5px;align-items:center;text-align:center}.vis-v img{width:72px;height:72px;cursor:pointer}.vis-v input{padding:4px 6px;font-size:12px;text-align:center;border-radius:8px}
.scene{display:grid;grid-template-columns:repeat(auto-fill,minmax(116px,1fr));gap:8px}
.scene div{cursor:pointer;font-size:12px;color:var(--tenue)}.scene img{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:10px;display:block;background:rgba(0,0,0,.3)}.scene div:hover img{outline:2px solid var(--pri)}
.sw{display:inline-block;width:26px;height:26px;border-radius:8px;border:1px solid rgba(255,255,255,.25)}
.sel-r{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.sel-r select,.sel-r input{width:auto;flex:1;min-width:140px}
</style>
</head>
<body>
<header class="top"><div class="marchio"><i></i>Opifex · Archivio</div>
<nav class="sc"><button id="t-esplora" class="on">Esplora</button><button id="t-persone">Persone</button><button id="t-indice">Indicizzazione</button><button id="t-dialogo">Dialogo con Opifex</button></nav>
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
 <div class="filtri2" id="filtri2">
  <select id="ftag" title="Che cosa si vede"><option value="">Qualsiasi soggetto</option></select>
  <select id="fst" title="Valutazione"><option value="0">Qualsiasi valutazione</option><option value="1">★ o più</option><option value="2">★★ o più</option><option value="3">★★★ o più</option><option value="4">★★★★ o più</option><option value="5">★★★★★</option></select>
  <span class="pal" id="fcol" title="Etichetta colore"></span>
  <select id="frac" title="Raccolta"><option value="0">Tutte le raccolte</option></select>
  <button class="chip" id="fmig" title="Nasconde i doppioni e le foto quasi uguali, tenendo la migliore">Solo i migliori</button>
  <button class="chip" id="fsf" title="Foto fuori fuoco o mosse">Sfocate</button>
  <button class="chip" id="fvo">Con volti</button>
  <button class="chip on" id="fpe" hidden></button></div>
 <div class="avviso az" id="fsim" hidden><span id="fsim-t"></span><button class="s piccolo" id="fsim-x">Esci dai simili ✕</button></div>
 <div class="m" id="intest" style="margin-bottom:10px"></div>
 <div class="griglia" id="gr"></div><div style="text-align:center;margin-top:18px"><button class="s" id="altri" hidden>Mostra altri</button></div>
</div>
<div id="v-persone" hidden>
 <div class="carta"><div class="riga" style="justify-content:space-between"><div><h2>Persone</h2><div class="m">I volti trovati nelle foto e nei video, raggruppati da soli. Dai un nome a una persona una volta sola: da quel momento la cerchi per nome e vedi in quali file e in quale minuto compare. Tutto avviene su questo computer: i volti non escono mai.</div></div>
 <label class="interr m"><input type="checkbox" id="pnasc"> Mostra anche le nascoste</label></div></div>
 <div class="pers-g" id="pg"></div><div class="vuoto" id="pvuoto" hidden>Ancora nessun volto: avvia l'indicizzazione, le analisi delle persone partono da sole.</div>
</div>
<div id="v-indice" hidden>
 <div class="carta"><h2>Cartelle</h2><div class="m">Sfoglia il computer: vedi cosa è già nell'indice, cosa è in coda e cosa è ancora fuori. Le cartelle che aggiungi restano ricordate anche dopo aver chiuso l'app.</div>
 <div id="cr" class="m" style="margin:12px 0 4px"></div><div id="cl"></div>
 <div class="riga" style="margin-top:12px"><input id="np" style="flex:1;min-width:220px" placeholder="Oppure scrivi un percorso, per esempio D:\Montarrenti o Z:\Archivio\Video"><button id="na" class="s">Aggiungi</button></div></div>
 <div class="carta"><h2>Analisi automatiche</h2><div class="m">Dopo l'indicizzazione il programma guarda ogni foto e ogni video: che cosa si vede, quanto è nitida, quali volti ci sono, dove cambia l'inquadratura. Può lavorare da solo, di notte, su un PC dedicato.</div>
 <div class="riga" style="margin-top:12px;gap:18px"><label class="interr"><input type="checkbox" id="an-v"> Riconosci i volti</label><label class="interr"><input type="checkbox" id="an-e"> Descrivi ciò che si vede</label><label class="interr"><input type="checkbox" id="an-s"> Trova i tagli di montaggio nei video</label></div>
 <div class="riga" style="margin-top:10px"><label class="interr"><input type="checkbox" id="av-w"> Avvia da solo quando accendo il computer (senza aprire finestre)</label></div><div class="m" id="av-w-m" style="margin-top:4px"></div></div>
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
function vai(n){for(const k of['esplora','persone','indice','dialogo']){$('v-'+k).hidden=k!==n;$('t-'+k).className=k===n?'on':''}
 if(n==='indice'){carica(qui);agg()}if(n==='persone')caricaPersone();if(n==='dialogo')opStato();if(n!=='esplora')chiudiDett()}
['esplora','persone','indice','dialogo'].forEach(k=>$('t-'+k).onclick=()=>vai(k));
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
const imp=(k,v)=>j('/api/impostazioni',{method:'POST',body:JSON.stringify({[k]:v})});
[['an-v','analisi_volti'],['an-e','analisi_etichette'],['an-s','analisi_scene']].forEach(([i,k])=>{$(i).onchange=()=>imp(k,$(i).checked)});
j('/api/impostazioni').then(r=>{$('auto').checked=!!r.riprendi_da_solo;$('an-v').checked=!!r.analisi_volti;$('an-e').checked=!!r.analisi_etichette;$('an-s').checked=!!r.analisi_scene;
 const a=r.avvio_windows||{};$('av-w').checked=!!a.attivo;$('av-w').disabled=!a.disponibile;$('av-w-m').textContent=a.disponibile?'':'Disponibile solo con il programma installato su Windows (IndiceArchivio.exe).'}).catch(()=>{});
$('av-w').onchange=async()=>{const r=await j('/api/avvio_windows',{method:'POST',body:JSON.stringify({attivo:$('av-w').checked})});$('av-w').checked=!!r.attivo;$('av-w-m').textContent=r.attivo?'Fatto: all\'accesso a Windows l\'archivio parte nascosto e riprende il lavoro.':''};
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
 if(r.in_corso&&r.stadio)testo=r.stadio+' · '+testo;
 $('b').style.width=Math.min(100,pc)+'%';$('bt').classList.toggle('indef',ind);$('p').textContent=testo;
 $('av').disabled=!!r.in_corso;$('fe').disabled=!r.in_corso;
 $('avvisi').innerHTML=(r.avvisi||[]).map(a=>`<div class="avviso">${E(a)}</div>`).join('');
 const pt=r.per_tipo||{};
 $('numeri').innerHTML=[['Nell\'indice',(r.totale||0).toLocaleString('it-IT')],['Foto',(pt.immagine||0).toLocaleString('it-IT')],['Video',(pt.video||0).toLocaleString('it-IT')],['Audio',(pt.audio||0).toLocaleString('it-IT')],['Documenti',(pt.testo||0).toLocaleString('it-IT')],['Persone',(r.persone||0).toLocaleString('it-IT')],['Volti trovati',(r.volti||0).toLocaleString('it-IT')],['Descritti',(r.etichettati||0).toLocaleString('it-IT')],['Dimensione',mb(r.dimensione)||'0 B']].map(a=>`<div class="num"><b>${a[1]}</b><span class="m">${a[0]}</span></div>`).join('');
 $('lavoro').innerHTML=r.in_corso&&f.rel?`<h3 style="margin-top:6px">In lavorazione ora</h3><div class="lav"><div class="ic">${icona(f.tipo,22)}</div><div class="tx"><div class="nomefile" title="${E(f.rel)}">${E(nomeDi(f.rel))}</div><div class="m">${E(f.fase||'')} · ${f.pct||0}%${f.dimensione?' · '+mb(f.dimensione):''}</div><div class="barra sottile" style="margin-top:6px"><i style="width:${f.pct||0}%"></i></div></div></div>`:'';
 $('prossimi').innerHTML=(r.prossimi||[]).length?'<h3 style="margin-top:16px">Prossimi in coda</h3>'+r.prossimi.map(x=>voceCoda(x,'attesa')).join(''):'';
 $('recenti').innerHTML=(r.recenti||[]).length?'<h3 style="margin-top:16px">Completati di recente</h3>'+r.recenti.map(x=>voceCoda(x,'fatto')).join(''):'';
 $('stato-alto').textContent=r.in_corso?'Indicizzazione in corso…':(r.totale?`${r.totale.toLocaleString('it-IT')} file nell'indice`:'');
 const mostra=r.in_corso&&$('v-indice').hidden;$('sb').classList.toggle('on',!!mostra);
 if(mostra){$('sb-t').textContent=f.rel?`${nomeDi(f.rel)} · ${f.fase||''}`:testo;$('sb-p').textContent=r.da_fare?`${r.fatti}/${r.da_fare}`:'';$('sb-b').style.width=Math.min(100,pc)+'%'}}
setInterval(agg,1500);
/* ---------- esplora ---------- */
const COL={rosso:'#E5604D',arancio:'#E8924A',giallo:'#E8CB4A',verde:'#5FBF7F',blu:'#5B9BE0',viola:'#A57BD6'};
const S={tipo:'',k4:false,vista:'g',da:0,n:24,ris:[],q:'',corr:-1,stelle:0,colore:'',raccolta:0,persona:0,personaNome:'',tag:'',migliori:false,sfocate:false,volti:false,simili:0,similiNome:''};
let RACC=[];
const star=n=>'★'.repeat(n);
document.querySelectorAll('#filtri [data-tipo]').forEach(b=>b.onclick=()=>{S.tipo=b.dataset.tipo;document.querySelectorAll('#filtri [data-tipo]').forEach(x=>x.classList.toggle('on',x===b));cercaOra()});
$('f4k').onclick=()=>{S.k4=!S.k4;$('f4k').classList.toggle('on',S.k4);cercaOra()};
$('ord').onchange=()=>cercaOra();
$('vg').onclick=()=>{S.vista='g';$('vg').classList.add('on');$('ve').classList.remove('on');$('gr').classList.remove('elenco')};
$('ve').onclick=()=>{S.vista='e';$('ve').classList.add('on');$('vg').classList.remove('on');$('gr').classList.add('elenco')};
$('ce').onclick=()=>{S.simili=0;cercaOra()};$('q').onkeydown=e=>{if(e.key==='Enter'){S.simili=0;cercaOra()}};
$('fcol').innerHTML=Object.keys(COL).map(k=>`<button data-c="${k}" title="${k}" style="background:${COL[k]}"></button>`).join('');
$('fcol').querySelectorAll('button').forEach(b=>b.onclick=()=>{S.colore=S.colore===b.dataset.c?'':b.dataset.c;aggFiltri();cercaOra()});
$('ftag').onchange=()=>{S.tag=$('ftag').value;aggFiltri();cercaOra()};
$('fst').onchange=()=>{S.stelle=Number($('fst').value);aggFiltri();cercaOra()};
$('frac').onchange=()=>{S.raccolta=Number($('frac').value);aggFiltri();cercaOra()};
[['fmig','migliori'],['fsf','sfocate'],['fvo','volti']].forEach(([i,k])=>$(i).onclick=()=>{S[k]=!S[k];aggFiltri();cercaOra()});
$('fpe').onclick=()=>{S.persona=0;aggFiltri();cercaOra()};
$('fsim-x').onclick=()=>{S.simili=0;cercaOra()};
function aggFiltri(){$('fcol').querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.c===S.colore));
 $('ftag').classList.toggle('on',!!S.tag);$('fst').classList.toggle('on',S.stelle>0);$('frac').classList.toggle('on',S.raccolta>0);
 $('fmig').classList.toggle('on',S.migliori);$('fsf').classList.toggle('on',S.sfocate);$('fvo').classList.toggle('on',S.volti);
 $('fpe').hidden=!S.persona||!!S.simili;$('fpe').textContent='Persona: '+(S.personaNome||'senza nome')+' ✕'}
async function caricaFiltri(){
 try{const t=(await j('/api/etichette')).etichette||[];const v=$('ftag').value;
  $('ftag').innerHTML='<option value="">Qualsiasi soggetto</option>'+t.map(x=>`<option value="${E(x.tag)}">${E(x.tag)} (${x.n})</option>`).join('');$('ftag').value=v||S.tag||''}catch(e){}
 try{RACC=(await j('/api/raccolte')).raccolte||[];$('frac').innerHTML='<option value="0">Tutte le raccolte</option>'+RACC.map(x=>`<option value="${x.id}">${E(x.nome)} (${x.n})</option>`).join('');$('frac').value=String(S.raccolta||0)}catch(e){}}
function datiRiga(x){const m=x.meta||{},o=[];
 if(x.larghezza&&x.tipo!=='audio')o.push(x.larghezza+'×'+x.altezza+(m.Megapixel?' ('+m.Megapixel+' MP)':''));
 if(x.tipo==='video'&&m['Fotogrammi al secondo'])o.push(m['Fotogrammi al secondo']+' fps');
 if(m.Pagine)o.push(m.Pagine+' pag.');
 if(m.Modello)o.push(m.Modello);
 if(x.dimensione)o.push(mb(x.dimensione));
 const d=dataIt(x.data||x.mtime);if(d)o.push(d);return o.join(' · ')}
function etichettaTrovato(x){
 if(x.dove==='parlato')return`<b style="color:var(--pri)">${dur(x.secondo)}</b> ${evid(x.estratto||'')}`;
 if(x.dove==='persona')return x.secondo!=null?`La persona compare dal minuto <b style="color:var(--pri)">${dur(x.secondo)}</b>`:'Compare in questo file';
 if(x.dove==='simili')return x.secondo!=null?`Simile, al minuto <b style="color:var(--pri)">${dur(x.secondo)}</b>`:'';
 if(x.dove==='immagine')return x.secondo!=null?`Immagine simile al minuto <b style="color:var(--pri)">${dur(x.secondo)}</b>`:'Immagine simile alla tua descrizione';
 if(x.dove==='meta')return'Trovato nei metadati: '+evid(x.estratto||'');
 if(x.dove==='nome')return'';
 return evid(x.estratto||'')}
function scheda(x,i){
 const t=x.secondo!=null?x.secondo:'';const vis=x.tipo==='immagine'||x.tipo==='video';
 const th=vis?`<img loading="lazy" alt="" src="/api/miniatura?id=${x.id}${t!==''?'&t='+t:''}&w=420" onerror="this.remove()">`:'';
 const tr=etichettaTrovato(x);const tg=(x.tags||[]).slice(0,4);
 return`<div class="sch" data-i="${i}"><div class="anteprima"><span class="grande">${icona(x.tipo,46)}</span>${th}<span class="badge sx">${NT[x.tipo]||x.tipo}</span>`+
 (x.stelle?`<span class="badge st">${star(x.stelle)}</span>`:'')+(x.colore&&COL[x.colore]?`<span class="badge pt" style="background:${COL[x.colore]}" title="${x.colore}"></span>`:'')+
 (x.sfocata?'<span class="badge av">Sfocata</span>':x.doppioni?'<span class="badge av">Doppione</span>':'')+
 (x.risoluzione?`<span class="badge ris">${x.risoluzione}</span>`:'')+((x.tipo==='video'||x.tipo==='audio')&&x.durata?`<span class="badge dx">${dur(x.durata)}</span>`:'')+
 `</div><div class="corpo"><div class="nomefile" title="${E(x.percorso)}">${E(x.nome)}</div><div class="dove" title="${E(x.cartella)}"><bdi>${E(x.cartella)}</bdi></div><div class="dati">${E(datiRiga(x))}${x.n_volti?' · '+x.n_volti+(x.n_volti===1?' volto':' volti'):''}</div>${tr?`<div class="estratto">${tr}</div>`:''}`+
 (tg.length?`<div class="tagrow">${tg.map(g=>`<span class="et">${E(g)}</span>`).join('')}</div>`:'')+`</div></div>`}
const meseDi=x=>{const d=x.data?new Date(String(x.data).replace(' ','T')):new Date((x.mtime||0)*1000);return isNaN(d)?'Senza data':d.toLocaleDateString('it-IT',{month:'long',year:'numeric'})};
function disegna(){let h='',ult='';const per=$('ord').value==='data'&&!S.simili;
 S.ris.forEach((x,i)=>{if(per){const m=meseDi(x);if(m!==ult){h+=`<h3 class="mese">${E(m)}</h3>`;ult=m}}h+=scheda(x,i)});
 $('gr').innerHTML=h||`<div class="vuoto" style="grid-column:1/-1">${S.q||S.persona||S.tag||S.stelle||S.colore||S.raccolta||S.sfocate||S.volti?'Nessun risultato. Prova con altre parole, o togli qualche filtro.':'L\'indice è vuoto: vai su «Indicizzazione», aggiungi una cartella e avvia.'}</div>`;
 $('gr').querySelectorAll('.sch').forEach(el=>el.onclick=()=>apriDett(Number(el.dataset.i)))}
async function cercaOra(altri){
 if(!altri){S.da=0;S.ris=[]}
 const q=$('q').value.trim();S.q=q;$('intest').textContent='Cerco…';aggFiltri();$('fsim').hidden=!S.simili;
 let r,u;
 if(S.simili){u='/api/simili?id='+S.simili+'&da='+S.da+'&n='+S.n;$('fsim-t').textContent='Foto e video che somigliano a «'+S.similiNome+'»'}
 else u='/api/cerca?q='+encodeURIComponent(q)+'&tipo='+S.tipo+'&ordine='+$('ord').value+'&da='+S.da+'&n='+S.n+'&larghezza_min='+(S.k4?3800:0)+'&stelle='+S.stelle+'&colore='+S.colore+'&raccolta='+S.raccolta+'&persona='+S.persona+'&tag='+encodeURIComponent(S.tag)+'&migliori='+(S.migliori?1:0)+'&sfocate='+(S.sfocate?1:0)+'&con_volti='+(S.volti?1:0);
 try{r=await j(u)}catch(e){$('intest').textContent='Non riesco a leggere l\'indice.';return}
 const nuovi=r.risultati||[];S.ris=S.ris.concat(nuovi);disegna();
 $('altri').hidden=nuovi.length<S.n;
 const filt=S.persona||S.tag||S.stelle||S.colore||S.raccolta||S.sfocate||S.volti||S.migliori;
 $('intest').textContent=S.ris.length?(S.simili?`${S.ris.length}${nuovi.length===S.n?'+':''} file simili`:q||filt?`${S.ris.length}${nuovi.length===S.n?'+':''} risultati${q?` per «${q}»`:''}`:'File indicizzati di recente (cerca per vedere i risultati più pertinenti)'):''}
$('altri').onclick=()=>{S.da+=S.n;cercaOra(true)};
/* ---------- dettaglio ---------- */
function chiudiDett(){$('dr').classList.remove('on');$('vela').classList.remove('on');$('dr').innerHTML=''}
$('vela').onclick=chiudiDett;
document.addEventListener('keydown',e=>{if(!$('dr').classList.contains('on')||/INPUT|TEXTAREA|SELECT/.test((e.target||{}).tagName))return;
 if(e.key==='Escape')chiudiDett();else if(e.key==='ArrowRight'&&S.corr<S.ris.length-1)apriDett(S.corr+1);else if(e.key==='ArrowLeft'&&S.corr>0)apriDett(S.corr-1);
 else if(/^[0-5]$/.test(e.key)&&S.ris[S.corr]){valutaRapida(S.ris[S.corr].id,Number(e.key))}});
async function valutaRapida(id,n){await j('/api/valuta',{method:'POST',body:JSON.stringify({ids:[id],stelle:n})});const x=S.ris.find(y=>y.id===id);if(x)x.stelle=n;disegna();if($('dr').classList.contains('on'))apriDett(S.corr,true)}
async function apriDett(i,noscroll){S.corr=i;const x=S.ris[i];if(!x)return;$('vela').classList.add('on');$('dr').classList.add('on');if(!noscroll)$('dr').innerHTML='<div class="m">Carico…</div>';
 const d=await j('/api/dettaglio?id='+x.id);if(d.errore){$('dr').innerHTML='<div class="avviso">'+E(d.errore)+'</div>';return}
 const sec=x.secondo!=null?x.secondo:0,id=d.id;let pv='';const keep=noscroll?$('dr').scrollTop:0;
 if(d.tipo==='immagine')pv=`<img src="/api/media?id=${id}" alt="" onerror="this.onerror=function(){this.replaceWith(document.createTextNode('Anteprima non disponibile per questo formato: usa Apri.'))};this.src='/api/miniatura?id=${id}&w=1200'">`;
 else if(d.tipo==='video')pv=`<video id="pv" controls preload="metadata" poster="/api/miniatura?id=${id}&w=900${sec?'&t='+sec:''}" src="/api/media?id=${id}"></video>`;
 else if(d.tipo==='audio')pv=`<audio id="pv" controls preload="metadata" src="/api/media?id=${id}"></audio>`;
 else pv=`<div style="padding:30px;color:var(--pri)">${icona('testo',56)}</div>`;
 const righe=[['Percorso',d.percorso],['Dimensione',mb(d.dimensione)],['Modificato',dataIt(d.mtime)]];
 if(d.durata)righe.push(['Durata',dur(d.durata)]);
 if(d.larghezza&&d.tipo!=='audio'&&!(d.meta||{}).Risoluzione)righe.push(['Dimensioni',d.larghezza+'×'+d.altezza+(d.risoluzione?' ('+d.risoluzione+')':'')]);
 if(d.data)righe.push(['Data di ripresa',dataIt(d.data)+' '+String(d.data).slice(11,16)]);
 if(d.tipo==='immagine'){righe.push(['Nitidezza',d.sfocata?'Sfocata o mossa':'Buona']);if(d.esposizione)righe.push(['Esposizione',d.esposizione==='ok'?'Corretta':d.esposizione]);}
 for(const[k,v]of Object.entries(d.meta||{}))righe.push([k,v]);
 const av=d.tipo==='video'||d.tipo==='audio';
 const testi=(d.testi||[]).map(t=>av&&t.tipo==='parlato'?`<div class="tr clic" data-s="${t.pos}"><b>${dur(t.pos)}</b><span>${E(t.testo)}</span></div>`:`<div class="tr"><span>${E(t.testo)}</span></div>`).join('');
 const stl=[1,2,3,4,5].map(n=>`<button data-st="${n}" class="${d.stelle>=n?'on':''}" title="${n} stelle (tasto ${n})">★</button>`).join('');
 const col=Object.keys(COL).map(k=>`<button data-c="${k}" title="${k}" class="${d.colore===k?'on':''}" style="background:${COL[k]}"></button>`).join('');
 const vol=(d.volti||[]).slice(0,24).map(v=>`<div class="vis-v"><img src="/api/volto?id=${v.id}&w=120" alt="" data-p="${v.persona_id||''}" data-n="${E(v.nome||'')}" title="${v.persona_id?'Mostra tutti i file con questa persona':'Volto troppo piccolo per essere raggruppato'}">`+
   (d.tipo==='video'&&v.pos!=null?`<span class="m">${dur(Number(v.pos))}</span>`:'')+(v.persona_id?`<input data-vp="${v.persona_id}" value="${E(v.nome||'')}" placeholder="Chi è?"><button class="s piccolo" data-sp="${v.id}" title="Il programma ha sbagliato: questa non è la stessa persona">Non è lei/lui</button>`:'')+`</div>`).join('');
 const sc=(d.scene||[]).length>1?(d.scene||[]).slice(0,80).map((s,k)=>`<div data-s="${s.t0}"><img loading="lazy" src="/api/miniatura?id=${id}&t=${s.t0}&w=240" alt="">${k+1} · ${dur(s.t0)}</div>`).join(''):'';
 const gr=(d.gruppo||[]).length?`<div class="m" style="margin-top:8px">${d.doppioni?'Questo è un doppione: ':'Ha dei doppioni o foto quasi uguali: '}${(d.gruppo||[]).map(g=>E(g.nome)+(g.migliore?' (la migliore)':'')).join(', ')}.</div>`:'';
 $('dr').innerHTML=`<div class="riga" style="justify-content:space-between"><div class="riga"><button class="s piccolo" id="dp" ${i<1?'disabled':''}>&larr;</button><button class="s piccolo" id="ds" ${i>=S.ris.length-1?'disabled':''}>&rarr;</button></div><button class="s piccolo" id="dx">Chiudi ✕</button></div>`+
 `<h2 style="margin-top:14px;word-break:break-word">${E(d.nome)}</h2><div class="m" style="word-break:break-all">${E(d.cartella)}</div><div class="prev">${pv}</div>`+
 (d.raggiungibile?'':'<div class="avviso">Il file non è raggiungibile ora: disco o NAS scollegato. Restano i dati dell\'indice.</div>')+(d.errore?`<div class="avviso">Errore in indicizzazione: ${E(d.errore)}</div>`:'')+
 `<div class="riga" style="margin:6px 0 10px"><button class="p piccolo" id="da">Apri col programma predefinito</button><button class="s piccolo" id="dm">Mostra nella cartella</button><button class="s piccolo" id="dc">Copia percorso</button>${d.tipo==='immagine'||d.tipo==='video'?'<button class="s piccolo" id="dsim">Trova simili</button>':''}</div><div class="m" id="dmsg"></div>`+
 `<div class="riga" style="margin:10px 0"><span class="stelle" id="dst">${stl}</span><span class="pal" id="dcol">${col}</span></div>`+
 `<div class="sel-r"><input id="dpar" value="${E(d.parole||'')}" placeholder="Parole chiave, separate da virgola"><button class="s piccolo" id="dpars">Salva</button></div>`+
 `<div class="sel-r" style="margin-top:8px"><select id="drac"><option value="">Aggiungi a una raccolta…</option>${RACC.map(r=>`<option value="${r.id}">${E(r.nome)}</option>`).join('')}<option value="nuova">+ Nuova raccolta…</option></select></div>`+
 ((d.raccolte||[]).length?`<div class="tagrow" style="margin-top:6px">${d.raccolte.map(r=>`<span class="et ok">${E(r)}</span>`).join('')}</div>`:'')+gr+
 ((d.etichette||[]).length?`<h3 style="margin-top:18px">Che cosa si vede</h3><div class="tagrow">${d.etichette.map(g=>`<button class="chip" data-tag="${E(g.tag)}">${E(g.tag)}</button>`).join('')}</div>`:'')+
 ((d.colori||[]).length?`<h3 style="margin-top:18px">Colori dominanti</h3><div class="riga" style="gap:6px">${d.colori.map(c=>`<span class="sw" style="background:${E(c)}" title="${E(c)}"></span>`).join('')}</div>`:'')+
 (vol?`<h3 style="margin-top:18px">Persone ${d.tipo==='video'?'(e dove compaiono)':''}</h3><div class="volti-r">${vol}</div>`:'')+
 (sc?`<h3 style="margin-top:18px">Inquadrature (${d.scene.length}) · tocca per andarci</h3><div class="scene">${sc}</div>`:'')+
 `<h3 style="margin-top:18px">Informazioni</h3><table class="mt">${righe.map(r=>`<tr><td>${E(r[0])}</td><td>${E(r[1])}</td></tr>`).join('')}</table>`+
 (testi?`<h3 style="margin-top:18px">${av?'Trascrizione (tocca un passaggio per andarci)':'Testo'}</h3>${testi}`:'');
 $('dr').scrollTop=keep;
 $('dx').onclick=chiudiDett;$('dp').onclick=()=>apriDett(i-1);$('ds').onclick=()=>apriDett(i+1);
 const msg=t=>{$('dmsg').textContent=t};
 $('da').onclick=async()=>{const r=await j('/api/apri',{method:'POST',body:JSON.stringify({id})});msg(r.errore||'Aperto.')};
 $('dm').onclick=async()=>{const r=await j('/api/apri',{method:'POST',body:JSON.stringify({id,mostra:true})});msg(r.errore||'Cartella aperta.')};
 $('dc').onclick=()=>{const t=d.percorso;const fb=()=>{const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();try{document.execCommand('copy')}catch(e){}a.remove();msg('Percorso copiato.')};
  (navigator.clipboard?navigator.clipboard.writeText(t).then(()=>msg('Percorso copiato.')).catch(fb):Promise.resolve(fb()))};
 if($('dsim'))$('dsim').onclick=()=>{S.simili=id;S.similiNome=d.nome;chiudiDett();cercaOra()};
 $('dst').querySelectorAll('button').forEach(b=>b.onclick=()=>valutaRapida(id,d.stelle===Number(b.dataset.st)?0:Number(b.dataset.st)));
 $('dcol').querySelectorAll('button').forEach(b=>b.onclick=async()=>{const nuovo=d.colore===b.dataset.c?'':b.dataset.c;await j('/api/valuta',{method:'POST',body:JSON.stringify({ids:[id],colore:nuovo})});const y=S.ris.find(z=>z.id===id);if(y)y.colore=nuovo;disegna();apriDett(S.corr,true)});
 $('dpars').onclick=async()=>{await j('/api/valuta',{method:'POST',body:JSON.stringify({ids:[id],parole:$('dpar').value})});const y=S.ris.find(z=>z.id===id);if(y)y.parole=$('dpar').value;msg('Parole chiave salvate.')};
 $('dpar').onkeydown=e=>{if(e.key==='Enter')$('dpars').click()};
 $('drac').onchange=async()=>{let rid=$('drac').value;if(!rid)return;
  if(rid==='nuova'){const nome=prompt('Nome della nuova raccolta (per esempio «Selezione podcast»)');if(!nome){$('drac').value='';return}const r=await j('/api/raccolta',{method:'POST',body:JSON.stringify({crea:nome,aggiungi:[id]})});if(r.errore)return msg(r.errore)}
  else{const r=await j('/api/raccolta',{method:'POST',body:JSON.stringify({id:Number(rid),aggiungi:[id]})});if(r.errore)return msg(r.errore)}
  await caricaFiltri();apriDett(S.corr,true)};
 $('dr').querySelectorAll('[data-tag]').forEach(b=>b.onclick=()=>{S.tag=b.dataset.tag;S.simili=0;$('ftag').value=S.tag;chiudiDett();cercaOra()});
 $('dr').querySelectorAll('.vis-v img').forEach(im=>im.onclick=()=>{if(!im.dataset.p)return;S.persona=Number(im.dataset.p);S.personaNome=im.dataset.n;S.simili=0;chiudiDett();cercaOra()});
 $('dr').querySelectorAll('[data-vp]').forEach(inp=>inp.onchange=async()=>{await j('/api/persona',{method:'POST',body:JSON.stringify({id:Number(inp.dataset.vp),nome:inp.value})});msg('Nome salvato: da ora la persona si cerca per nome.');if(S.persona===Number(inp.dataset.vp))S.personaNome=inp.value});
 $('dr').querySelectorAll('[data-sp]').forEach(b=>b.onclick=async()=>{await j('/api/volto_sposta',{method:'POST',body:JSON.stringify({id:Number(b.dataset.sp)})});apriDett(S.corr,true)});
 const el=$('pv');if(el){el.onerror=()=>{msg('Il lettore non riesce a riprodurre questo formato: usa «Apri col programma predefinito».')};if(sec)el.addEventListener('loadedmetadata',()=>{el.currentTime=sec},{once:true})}
 $('dr').querySelectorAll('[data-s]').forEach(t=>t.onclick=()=>{if(el){el.currentTime=Number(t.dataset.s);el.play().catch(()=>{})}})}
/* ---------- persone ---------- */
async function caricaPersone(){const r=await j('/api/persone?nascoste='+($('pnasc').checked?1:0));const ps=r.persone||[];
 $('pvuoto').hidden=ps.length>0;
 $('pg').innerHTML=ps.map(p=>`<div class="pers" data-id="${p.id}"><img src="/api/volto?id=${p.esempio}&w=240" alt="" data-m="${p.id}" style="cursor:pointer" title="Mostra i file con questa persona"><input data-nome="${p.id}" value="${E(p.nome||'')}" placeholder="Chi è? Scrivi il nome"><div class="m">${p.n_file.toLocaleString('it-IT')} ${p.n_file===1?'file':'file'} · ${p.n_volti.toLocaleString('it-IT')} volti</div>`+
  `<div class="riga" style="justify-content:center"><button class="p piccolo" data-m="${p.id}">Mostra</button><button class="s piccolo" data-h="${p.id}">${$('pnasc').checked&&p.nascosta?'Ripristina':'Nascondi'}</button></div>`+
  `<select data-u="${p.id}"><option value="">Unisci con un'altra persona…</option>${ps.filter(o=>o.id!==p.id).map(o=>`<option value="${o.id}">${E(o.nome||'Senza nome #'+o.id)} (${o.n_file})</option>`).join('')}</select></div>`).join('');
 const nomeDiP=id=>(ps.find(p=>p.id===id)||{}).nome||'';
 $('pg').querySelectorAll('[data-m]').forEach(b=>b.onclick=()=>{const id=Number(b.dataset.m);S.persona=id;S.personaNome=nomeDiP(id);S.simili=0;vai('esplora');cercaOra()});
 $('pg').querySelectorAll('[data-nome]').forEach(i=>i.onchange=async()=>{await j('/api/persona',{method:'POST',body:JSON.stringify({id:Number(i.dataset.nome),nome:i.value})})});
 $('pg').querySelectorAll('[data-h]').forEach(b=>b.onclick=async()=>{const id=Number(b.dataset.h),p=ps.find(x=>x.id===id);await j('/api/persona',{method:'POST',body:JSON.stringify({id,nascondi:!(p&&p.nascosta)})});caricaPersone()});
 $('pg').querySelectorAll('[data-u]').forEach(s=>s.onchange=async()=>{if(!s.value)return;const da=Number(s.dataset.u),a=Number(s.value);
  if(!confirm('Sono la stessa persona? I loro volti verranno uniti in un unico gruppo.'))return void(s.value='');
  await j('/api/persona',{method:'POST',body:JSON.stringify({id:da,unisci_in:a})});caricaPersone()})}
$('pnasc').onchange=caricaPersone;
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
(async()=>{await agg();caricaFiltri();if(!PR.totale&&!PR.in_corso)vai('indice');else cercaOra()})();
setInterval(()=>{if(!$('v-esplora').hidden&&PR.in_corso)caricaFiltri()},60000);
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
                    return self._r(200, {**PROG, "totale": sum(st["file"].values()), "per_tipo": st["per_tipo"], "dimensione": st["dimensione"],
                                         "volti": st["volti"], "persone": st["persone"], "etichettati": st["etichettati"]})
                if interfaccia and u.path == "/api/cerca":
                    g = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
                    tipo = g("tipo") if g("tipo") in ("immagine", "video", "audio", "testo") else None
                    filtri = {"stelle": int(g("stelle", "0") or 0), "colore": g("colore"), "raccolta": int(g("raccolta", "0") or 0), "persona": int(g("persona", "0") or 0),
                              "tag": g("tag"), "migliori": g("migliori") == "1", "sfocate": g("sfocate") == "1", "con_volti": g("con_volti") == "1"}
                    return self._r(200, {"risultati": cerca(db, g("q"), min(int(g("n", "24")), 100), finto, tipo, g("ordine", "rilevanza"),
                                                            int(g("da", "0")), int(g("larghezza_min", "0")), filtri)})
                if interfaccia and u.path == "/api/simili":
                    return self._r(200, {"risultati": simili(db, int((q.get("id") or ["0"])[0]), min(int((q.get("n") or ["24"])[0]), 100), int((q.get("da") or ["0"])[0]))})
                if interfaccia and u.path == "/api/persone":
                    return self._r(200, {"persone": persone_elenco(db, (q.get("nascoste") or ["0"])[0] == "1")})
                if interfaccia and u.path == "/api/volto":
                    jpg = volto_miniatura(db, int((q.get("id") or ["0"])[0]), int((q.get("w") or ["160"])[0]))
                    return self._bin(204, b"", "image/jpeg") if jpg is None else self._bin(200, jpg, "image/jpeg", {"Cache-Control": "max-age=86400"})
                if interfaccia and u.path == "/api/etichette":
                    return self._r(200, {"etichette": etichette_elenco(db)})
                if interfaccia and u.path == "/api/raccolte":
                    return self._r(200, {"raccolte": raccolte_elenco(db)})
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
                    return self._r(200, {"riprendi_da_solo": imp_leggi(db, "riprendi_da_solo", "1") == "1", "analisi_volti": imp_leggi(db, "analisi_volti", "1") == "1",
                                         "analisi_etichette": imp_leggi(db, "analisi_etichette", "1") == "1", "analisi_scene": imp_leggi(db, "analisi_scene", "1") == "1",
                                         "avvio_windows": avvio_windows()})
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
                err = avvia_scansione(db, [str(x) for x in (corpo.get("cartelle") or [])], int(corpo.get("passo") or 15), finto)
                return self._r(200, {"errore": err} if err else {"ok": True})
            if self.path == "/api/impostazioni":
                for k in ("riprendi_da_solo", "analisi_volti", "analisi_etichette", "analisi_scene"):
                    if k in corpo:
                        imp_scrivi(db, k, "1" if corpo[k] else "0")
                return self._r(200, {"ok": True})
            if self.path == "/api/avvio_windows":
                return self._r(200, avvio_windows(bool(corpo.get("attivo"))))
            if self.path == "/api/valuta":
                valuta(db, corpo.get("ids") or [], corpo.get("stelle"), corpo.get("colore"), corpo.get("parole"))
                return self._r(200, {"ok": True})
            if self.path == "/api/raccolta":
                try:
                    return self._r(200, {"ok": True, "id": raccolta_azione(db, corpo)})
                except ValueError as e:
                    return self._r(200, {"errore": str(e)})
            if self.path == "/api/persona":
                try:
                    pid = int(corpo.get("id") or 0)
                    if "nome" in corpo:
                        persona_rinomina(db, pid, corpo["nome"])
                    if corpo.get("unisci_in"):
                        persone_unisci(db, pid, int(corpo["unisci_in"]))
                    if "nascondi" in corpo:
                        persona_nascondi(db, pid, bool(corpo["nascondi"]))
                    return self._r(200, {"ok": True})
                except ValueError as e:
                    return self._r(200, {"errore": str(e)})
            if self.path == "/api/volto_sposta":
                try:
                    return self._r(200, {"ok": True, "persona_id": volto_sposta(db, int(corpo.get("id") or 0), corpo.get("persona_id"))})
                except ValueError as e:
                    return self._r(200, {"errore": str(e)})
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
            while True:   # all'apertura e poi ogni 6 ore: cerca i file nuovi e porta avanti le analisi
                if imp_leggi(db, "riprendi_da_solo", "1") == "1" and not PROG["in_corso"]:
                    avvia_scansione(db, None, 15, finto)
                time.sleep(6 * 3600)
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
