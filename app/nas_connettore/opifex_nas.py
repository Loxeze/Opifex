#!/usr/bin/env python3
"""Connettore Opifex per NAS (v1.0).

Gira sul NAS dentro un contenitore Docker. Si collega SOLO in uscita a Opifex (nessuna porta da aprire), con la chiave del connettore.
Legge in sola lettura le cartelle montate sotto /dati: per ogni foto/video manda a Opifex la scheda (misure, data, fotocamera, luogo)
e qualche miniatura. Gli originali non si muovono, tranne su richiesta esplicita: una foto ridimensionata oppure l'audio di un video da trascrivere.
"""
import io
import json
import re
import zipfile
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from PIL import ExifTags, Image, ImageOps

try:
    import pillow_heif  # facoltativo: foto HEIC dell'iPhone
    pillow_heif.register_heif_opener()
except Exception:  # noqa: BLE001
    pass

try:
    import pypdf  # noqa: F401 - per leggere i PDF; se manca (compose vecchio) lo installo da solo
except ImportError:
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "pypdf==5.1.0"], timeout=300, capture_output=True)
    except Exception:  # noqa: BLE001
        pass

VERSIONE = "1.3"
URL = os.environ.get("OPIFEX_URL", "").rstrip("/")
TOKEN = os.environ.get("OPIFEX_TOKEN", "")
DATI = Path(os.environ.get("OPIFEX_DATI", "/dati"))
LATO_MINIATURA = 512
MAX_MINIATURA = 240_000
LOTTO = 500
SEGMENTO_S = 480  # audio a pezzi da 8 minuti (mp3 mono 32 kbps: ~2 MB)
EST_FOTO = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif", ".bmp", ".gif", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".raf", ".rw2")
EST_VIDEO = (".mp4", ".mov", ".mxf", ".mkv", ".avi", ".mts", ".m2ts", ".mpg", ".mpeg", ".webm", ".m4v", ".mp4v", ".braw")
EST_AUDIO = (".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac", ".aac", ".ogg")
EST_DOC = (".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".txt", ".md", ".csv", ".rtf", ".html", ".htm", ".xml", ".json", ".srt", ".vtt")
MAX_TESTO = 150_000
SALTA = {"@eadir", "#recycle", ".thumbnails", "$recycle.bin", "system volume information", "@recently-snapshot", ".@__thumb"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("opifex-nas")
S = requests.Session()
S.headers.update({"Authorization": "Bearer " + TOKEN, "X-Versione": VERSIONE})


def chiama(metodo: str, percorso: str, **kw):
    kw.setdefault("timeout", 120)
    r = S.request(metodo, URL + "/archivio-nas/connettore" + percorso, **kw)
    if r.status_code == 401:
        raise SystemExit("Chiave del connettore non valida: scarica un pacchetto nuovo da Opifex (Archivio NAS).")
    r.raise_for_status()
    return r.json()


def tipo_di(nome: str):
    n = nome.lower()
    return "foto" if n.endswith(EST_FOTO) else "video" if n.endswith(EST_VIDEO) else "audio" if n.endswith(EST_AUDIO) else "documento" if n.endswith(EST_DOC) else None


# ---------------- miniature e schede ----------------
def jpeg_sotto_limite(im: Image.Image, lato: int, limite: int) -> bytes:
    im = im.convert("RGB")
    for q in (78, 68, 58, 48):
        c = im.copy()
        c.thumbnail((lato, lato))
        b = io.BytesIO()
        c.save(b, "JPEG", quality=q, optimize=True)
        if len(b.getvalue()) <= limite:
            return b.getvalue()
    c = im.copy()
    c.thumbnail((320, 320))
    b = io.BytesIO()
    c.save(b, "JPEG", quality=50)
    return b.getvalue()


def _gps(exif) -> dict | None:
    try:
        g = exif.get_ifd(ExifTags.IFD.GPSInfo)
        if not g:
            return None

        def gradi(v, rif):
            d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -d if rif in ("S", "W") else d
        return {"lat": gradi(g[2], g[1]), "lon": gradi(g[4], g[3])}
    except Exception:  # noqa: BLE001
        return None


def scheda_foto(p: Path):
    meta, mini = {}, []
    with Image.open(p) as im:
        try:
            exif = im.getexif()
        except Exception:  # noqa: BLE001
            exif = None
        if exif:
            data = None
            try:
                data = exif.get_ifd(ExifTags.IFD.Exif).get(36867) or exif.get(306)
            except Exception:  # noqa: BLE001
                data = exif.get(306)
            if isinstance(data, str) and len(data) >= 19:
                meta["scattato_il"] = data[:10].replace(":", "-") + "T" + data[11:19]
            cam = " ".join(str(x).strip() for x in (exif.get(271), exif.get(272)) if x)
            if cam:
                meta["fotocamera"] = cam[:120]
            g = _gps(exif)
            if g:
                meta["luogo"] = g
        im = ImageOps.exif_transpose(im)
        meta["larghezza"], meta["altezza"] = im.size
        mini.append(jpeg_sotto_limite(im, LATO_MINIATURA, MAX_MINIATURA))
    return meta, mini


def esegui(args: list[str], timeout=180) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout)


def scheda_video(p: Path):
    meta, mini = {}, []
    r = esegui(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)], 60)
    info = json.loads(r.stdout or b"{}")
    durata = 0.0
    try:
        durata = float(info.get("format", {}).get("duration") or 0)
    except ValueError:
        pass
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            meta["larghezza"], meta["altezza"] = s.get("width"), s.get("height")
            meta["codec"] = s.get("codec_name")
            try:
                a, b = (s.get("avg_frame_rate") or "0/1").split("/")
                meta["fps"] = round(float(a) / float(b), 3) if float(b) else None
            except (ValueError, ZeroDivisionError):
                pass
            break
    if durata:
        meta["durata_s"] = round(durata, 2)
    tag = (info.get("format", {}).get("tags") or {})
    ct = tag.get("creation_time") or tag.get("com.apple.quicktime.creationdate")
    if isinstance(ct, str) and len(ct) >= 19:
        meta["scattato_il"] = ct[:19].replace(" ", "T")
    for fr in (0.15, 0.5, 0.85):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "f.jpg"
            esegui(["ffmpeg", "-v", "error", "-ss", f"{durata * fr:.2f}", "-i", str(p), "-frames:v", "1", "-vf", f"scale='min({LATO_MINIATURA},iw)':-2", "-q:v", "5", str(out)], 120)
            if out.exists() and out.stat().st_size > 0:
                with Image.open(out) as im:
                    mini.append(jpeg_sotto_limite(im, LATO_MINIATURA, MAX_MINIATURA))
    meta = {k: v for k, v in meta.items() if v is not None}
    return meta, mini


def scheda_audio(p: Path):
    r = esegui(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(p)], 60)
    info = json.loads(r.stdout or b"{}")
    try:
        return {"durata_s": round(float(info.get("format", {}).get("duration") or 0), 2)}, []
    except ValueError:
        return {}, []


# ---------------- documenti scritti ----------------
def _da_xml(b: bytes) -> str:
    t = b.decode("utf-8", "replace")
    t = re.sub(r"</(w:p|a:p|text:p|text:h|row|si)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
    return re.sub(r"[ \t]+", " ", t)


def testo_documento(p: Path) -> str:
    n = p.name.lower()
    if p.stat().st_size > 80 * 1024 * 1024:
        return ""
    if n.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        out, tot = [], 0
        for pg in PdfReader(str(p)).pages:
            t = pg.extract_text() or ""
            out.append(t); tot += len(t)
            if tot > MAX_TESTO:
                break
        return "\n".join(out)
    if n.endswith((".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp")):
        with zipfile.ZipFile(p) as z:
            nomi = z.namelist()
            if n.endswith(".docx"):
                parti = ["word/document.xml"]
            elif n.endswith(".xlsx"):
                parti = ["xl/sharedStrings.xml"]
            elif n.endswith(".pptx"):
                parti = sorted((x for x in nomi if re.match(r"ppt/slides/slide\d+\.xml$", x)), key=lambda x: int(re.findall(r"\d+", x)[-1]))
            else:
                parti = ["content.xml"]
            out, tot = [], 0
            for x in parti:
                if x in nomi:
                    t = _da_xml(z.read(x)); out.append(t); tot += len(t)
                    if tot > MAX_TESTO:
                        break
            return "\n".join(out)
    raw = p.read_bytes()[: MAX_TESTO * 2]
    t = raw.decode("utf-8", "replace") if b"\x00" not in raw[:2000] else raw.decode("utf-16", "replace")
    if n.endswith((".html", ".htm", ".xml")):
        t = _da_xml(t.encode())
    elif n.endswith(".rtf"):
        t = re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", t)
    return t


# ---------------- scansione ----------------
def elenca(radice: Path, stat: dict | None = None):
    st_ = stat if stat is not None else {}
    st_.update({"cartelle": 0, "illeggibili": 0, "altri": 0, "estensioni": {}})

    def errore(e):
        st_["illeggibili"] += 1
    for cartella, sotto, files in os.walk(radice, onerror=errore):
        st_["cartelle"] += 1
        sotto[:] = [d for d in sorted(sotto) if d.lower() not in SALTA and not d.startswith(".")]
        for f in sorted(files):
            if f.startswith(".") or f.startswith("~$") or not tipo_di(f):
                if not f.startswith("."):
                    st_["altri"] += 1
                    e = f.rsplit(".", 1)[-1].lower()[:6] if "." in f else "(senza)"
                    st_["estensioni"][e] = st_["estensioni"].get(e, 0) + 1
                continue
            p = Path(cartella) / f
            try:
                st = p.stat()
            except OSError:
                continue
            yield p.relative_to(radice).as_posix(), int(st.st_size), int(st.st_mtime)


def invia_file(cid: int, radice: Path, rel: str) -> bool:
    p = radice / rel
    t = tipo_di(rel)
    contenuto = ""
    try:
        if t == "documento":
            meta, mini = {}, []
            contenuto = re.sub(r"\n\s*\n+", "\n", testo_documento(p))[:MAX_TESTO]
        else:
            meta, mini = scheda_foto(p) if t == "foto" else scheda_video(p) if t == "video" else scheda_audio(p)
    except Exception as e:  # noqa: BLE001 - file illeggibile: lo si annuncia comunque, senza miniatura
        log.warning("Scheda non letta per %s: %s", rel, type(e).__name__)
        meta, mini = {}, []
    files = [("miniature", (f"m{i}.jpg", b, "image/jpeg")) for i, b in enumerate(mini)]
    chiama("POST", "/file", data={"cartella_id": cid, "rel": rel, "meta": json.dumps(meta), "contenuto": contenuto}, files=files or None, timeout=180)
    return True


def scansiona(cartella: dict) -> None:
    cid = cartella["id"]
    radice = (DATI / cartella["percorso"]).resolve() if cartella["percorso"] else DATI
    if not str(radice).startswith(str(DATI.resolve())) or not radice.is_dir():
        chiama("POST", "/fine-scansione", json={"cartella_id": cid, "scan": 0, "errore": f"Cartella non trovata sul NAS: /dati/{cartella['percorso']} (controlla i volumi nel docker-compose)"})
        return
    scan = int(time.time())
    totale = nuovi = 0
    lotto: list = []

    def svuota():
        nonlocal nuovi
        if not lotto:
            return
        r = chiama("POST", "/sincronizza", json={"cartella_id": cid, "scan": scan, "file": [{"rel": a, "size": b, "mtime": c} for a, b, c in lotto]})
        for rel in r.get("servono", []):
            try:
                invia_file(cid, radice, rel)
                nuovi += 1
            except requests.RequestException as e:
                log.warning("Invio non riuscito per %s: %s", rel, type(e).__name__)
            if nuovi % 25 == 0:
                evadi_richieste()
        lotto.clear()
    stat: dict = {}
    for rel, size, mtime in elenca(radice, stat):
        lotto.append((rel, size, mtime))
        totale += 1
        if len(lotto) >= LOTTO:
            svuota()
    svuota()
    if totale == 0:   # nessun file riconosciuto: dico perche', senza cancellare nulla dal catalogo
        try:
            radice_elenco = ", ".join(sorted(x.name for x in radice.iterdir())[:6])
        except OSError:
            radice_elenco = ""
        if stat.get("illeggibili"):
            msg = f"Il contenitore non riesce a leggere {stat['illeggibili']} cartelle (permessi): dai al contenitore il permesso di lettura sulla cartella condivisa."
        elif not stat.get("altri") and stat.get("cartelle", 0) <= 1 and not radice_elenco:
            msg = f"La cartella /dati/{cartella['percorso']} e' VUOTA per il contenitore: il percorso a sinistra dei due punti in 'volumes' del docker-compose non esiste sul NAS o e' sbagliato (Docker ne crea una vuota)."
        elif stat.get("altri"):
            top = ", ".join(f".{k} x{v}" for k, v in sorted(stat["estensioni"].items(), key=lambda x: -x[1])[:5])
            msg = f"Visti {stat['altri']} file ma nessuno di tipo foto, video, audio o documento riconosciuto ({top})."
        else:
            msg = f"Trovate {stat.get('cartelle', 0)} cartelle ma nessun file dentro. Contenuto: {radice_elenco or 'vuoto'}."
        chiama("POST", "/fine-scansione", json={"cartella_id": cid, "scan": 0, "errore": msg[:290]})
        log.warning("Cartella %s: %s", cartella["percorso"] or "/", msg)
        return
    chiama("POST", "/fine-scansione", json={"cartella_id": cid, "scan": scan})
    log.info("Cartella %s: %d file visti, %d nuovi o cambiati", cartella["percorso"] or "/", totale, nuovi)


# ---------------- richieste ----------------
def consegna_foto(r: dict) -> None:
    p = trova(r)
    with Image.open(p) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    lato = int(r.get("lato_max") or 2400)
    for q in (90, 82, 74, 66, 58):
        c = im.copy()
        c.thumbnail((lato, lato))
        b = io.BytesIO()
        c.save(b, "JPEG", quality=q, optimize=True)
        if len(b.getvalue()) <= 13 * 1024 * 1024:
            break
        lato = int(lato * 0.8)
    chiama("POST", f"/consegna/{r['id']}", data=b.getvalue(), headers={"Content-Type": "image/jpeg"}, timeout=300)


def consegna_trascrizione(r: dict) -> None:
    p = trova(r)
    parte = 0
    with tempfile.TemporaryDirectory() as d:
        res = esegui(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "-f", "segment", "-segment_time", str(SEGMENTO_S), "-reset_timestamps", "1", str(Path(d) / "p%04d.mp3")], 3600)
        pezzi = sorted(Path(d).glob("p*.mp3"))
        if res.returncode != 0 or not pezzi:
            raise RuntimeError("audio non estraibile dal file")
        for i, z in enumerate(pezzi):
            chiama("POST", f"/trascrizione/{r['id']}", params={"parte": i, "ultima": 1 if i == len(pezzi) - 1 else 0}, data=z.read_bytes(), headers={"Content-Type": "audio/mpeg"}, timeout=600)
            parte += 1


def trova(r: dict) -> Path:
    base = (DATI / r["percorso_cartella"]).resolve() if r["percorso_cartella"] else DATI.resolve()
    p = (base / r["rel"]).resolve()
    if not str(p).startswith(str(DATI.resolve())) or not p.is_file():
        raise FileNotFoundError("il file non c'e' piu' sul NAS")
    return p


def evadi_richieste() -> None:
    try:
        cfg = chiama("GET", "/config")
    except requests.RequestException:
        return
    for r in cfg.get("richieste", []):
        try:
            consegna_foto(r) if r["tipo"] == "foto" else consegna_trascrizione(r)
            log.info("Richiesta %s (%s) evasa", r["id"], r["tipo"])
        except Exception as e:  # noqa: BLE001
            log.warning("Richiesta %s fallita: %s", r["id"], e)
            try:
                chiama("POST", f"/errore-richiesta/{r['id']}", json={"errore": f"{type(e).__name__}: {e}"[:290]})
            except requests.RequestException:
                pass


def main() -> None:
    if not URL or not TOKEN:
        raise SystemExit("Mancano OPIFEX_URL e OPIFEX_TOKEN: usa il docker-compose.yml scaricato da Opifex.")
    log.info("Connettore Opifex %s avviato verso %s", VERSIONE, URL)
    ultima: dict[int, float] = {}   # ultima scansione di ogni cartella: una cartella nuova parte subito, le altre ogni "intervallo"
    while True:
        try:
            cfg = chiama("GET", "/config")
            evadi_richieste()
            intervallo = max(60, int(cfg.get("intervallo") or 900))
            if not cfg.get("cartelle"):
                log.info("Nessuna cartella da catalogare: aggiungila in Opifex (Archivio NAS)")
            for c in cfg.get("cartelle", []):
                if time.time() - ultima.get(c["id"], 0.0) >= intervallo or c["id"] not in ultima:
                    log.info("Scansione della cartella %s", c["percorso"] or "/")
                    try:
                        scansiona(c)
                    except requests.RequestException:
                        raise
                    except Exception as e:  # noqa: BLE001 - il problema si vede in Opifex, accanto alla cartella
                        log.exception("Scansione non riuscita")
                        chiama("POST", "/fine-scansione", json={"cartella_id": c["id"], "scan": 0, "errore": f"{type(e).__name__}: {e}"[:290]})
                    ultima[c["id"]] = time.time()
        except requests.RequestException as e:
            log.warning("Opifex non raggiungibile (%s): riprovo tra poco", type(e).__name__)
        except Exception:  # noqa: BLE001
            log.exception("Errore imprevisto, riprovo")
        time.sleep(30)


if __name__ == "__main__":
    main()
