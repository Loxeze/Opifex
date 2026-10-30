#!/usr/bin/env python3
"""Connettore Opifex per NAS (v1.0).

Gira sul NAS dentro un contenitore Docker. Si collega SOLO in uscita a Opifex (nessuna porta da aprire), con la chiave del connettore.
Legge in sola lettura le cartelle montate sotto /dati: per ogni foto/video manda a Opifex la scheda (misure, data, fotocamera, luogo)
e qualche miniatura. Gli originali non si muovono, tranne su richiesta esplicita: una foto ridimensionata oppure l'audio di un video da trascrivere.
"""
import io
import json
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

VERSIONE = "1.1"
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
    return "foto" if n.endswith(EST_FOTO) else "video" if n.endswith(EST_VIDEO) else "audio" if n.endswith(EST_AUDIO) else None


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


# ---------------- scansione ----------------
def elenca(radice: Path):
    for cartella, sotto, files in os.walk(radice):
        sotto[:] = [d for d in sorted(sotto) if d.lower() not in SALTA and not d.startswith(".")]
        for f in sorted(files):
            if f.startswith(".") or not tipo_di(f):
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
    try:
        meta, mini = scheda_foto(p) if t == "foto" else scheda_video(p) if t == "video" else scheda_audio(p)
    except Exception as e:  # noqa: BLE001 - file illeggibile: lo si annuncia comunque, senza miniatura
        log.warning("Scheda non letta per %s: %s", rel, type(e).__name__)
        meta, mini = {}, []
    files = [("miniature", (f"m{i}.jpg", b, "image/jpeg")) for i, b in enumerate(mini)]
    chiama("POST", "/file", data={"cartella_id": cid, "rel": rel, "meta": json.dumps(meta)}, files=files or None, timeout=180)
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
    for rel, size, mtime in elenca(radice):
        lotto.append((rel, size, mtime))
        totale += 1
        if len(lotto) >= LOTTO:
            svuota()
    svuota()
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
