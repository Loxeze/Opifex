#!/usr/bin/env python3
"""Banco di lavoro Opifex (v1.0) - gira sul PC di montaggio.

Si collega SOLO in uscita a Opifex. Prende un lavoro alla volta (inventario dei file, fotogrammi, silenzi, ffmpeg) e lavora esclusivamente
dentro la CARTELLA DI LAVORO indicata: non legge ne' scrive altrove. Le uscite di ffmpeg vanno nella sottocartella "uscite".
Variabili: OPIFEX_URL, OPIFEX_TOKEN, OPIFEX_CARTELLA (la cartella dei file di lavoro, es. la cartella sincronizzata di Google Drive).
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"], check=False)
    import requests

VERSIONE = "1.0"
URL = os.environ.get("OPIFEX_URL", "").rstrip("/")
TOKEN = os.environ.get("OPIFEX_TOKEN", "")
DATI = Path(os.environ.get("OPIFEX_CARTELLA", ".")).resolve()
EST_MEDIA = (".mp4", ".mov", ".mxf", ".mkv", ".avi", ".mts", ".m2ts", ".mpg", ".mpeg", ".webm", ".m4v", ".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac", ".aac", ".ogg")
EST_USCITA = (".mp4", ".mov", ".mp3", ".wav", ".m4a", ".jpg", ".png", ".srt", ".txt", ".xml")
BLOCCATI = ("movie=", "concat:", "pipe:", "http:", "https:", "ftp:", "tcp:", "udp:", "rtmp", "file:", "-filter_script", "-filter_complex_script",
            "-protocol_whitelist", "..", "~", "-dump", "-report", "-passlogfile")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("opifex-banco")


def trova_ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"], check=False)
        import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


FF = None


class Rifiutato(Exception):
    pass


def sicuro(rel: str, deve_esistere: bool = True) -> Path:
    """Percorso dentro la cartella di lavoro, mai fuori."""
    s = str(rel or "").replace("\\", "/")
    if not s or s.startswith("/") or re.match(r"^[A-Za-z]:", s) or ".." in s.split("/"):
        raise Rifiutato(f"percorso non consentito: {rel!r}")
    p = (DATI / s).resolve()
    try:
        p.relative_to(DATI)
    except ValueError:
        raise Rifiutato(f"percorso fuori dalla cartella di lavoro: {rel!r}") from None
    if deve_esistere and not p.exists():
        raise Rifiutato(f"file non trovato nella cartella di lavoro: {rel}")
    return p


def esegui(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run([FF, "-hide_banner", "-nostdin", *args], capture_output=True, text=True, timeout=timeout, errors="replace")


def sonda(p: Path) -> dict:
    """Misure di un file leggendo l'intestazione di ffmpeg (non serve ffprobe)."""
    t = esegui(["-i", str(p)], 60).stderr
    d = {}
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", t)
    if m:
        d["durata"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    v = re.search(r"Stream #[^\n]*Video:[^\n]*?,\s*(\d{2,5})x(\d{2,5})", t)
    if v:
        d["larghezza"], d["altezza"] = int(v[1]), int(v[2])
        f = re.search(r"([\d.]+)\s*fps", t)
        d["fps"] = float(f[1]) if f else None
    d["audio"] = "Audio:" in t
    return d


def impronta(p: Path) -> str:
    import hashlib
    h = hashlib.sha1(str(p.stat().st_size).encode())
    with open(p, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()[:10]


def lavoro_inventario(par: dict) -> tuple[str, list]:
    base = DATI if par.get("cartella") in (None, "", ".") else sicuro(par["cartella"])
    righe, viste = [], {}
    n = 0
    for radice, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() != "uscite" and not d.startswith(".")]
        for nome in sorted(files):
            if not nome.lower().endswith(EST_MEDIA):
                continue
            n += 1
            if n > 150:
                righe.append("[... altri file non elencati: restringi la cartella]")
                return "\n".join(righe), []
            p = Path(radice) / nome
            rel = p.relative_to(DATI).as_posix()
            try:
                d = sonda(p)
                imp = impronta(p)
            except Exception as e:  # noqa: BLE001
                righe.append(f"{rel} | non leggibile ({type(e).__name__})")
                continue
            dup = viste.get(imp)
            viste.setdefault(imp, rel)
            righe.append(f"{rel} | {p.stat().st_size / 1e6:.1f} MB | {d.get('durata', 0):.1f} s | "
                         + (f"{d['larghezza']}x{d['altezza']} {d.get('fps') or '?'} fps" if "larghezza" in d else "solo audio")
                         + f" | audio {'si' if d.get('audio') else 'NO'} | impronta {imp}" + (f" | DUPLICATO di {dup}" if dup else ""))
    return "\n".join(righe) or "Nessun file audio/video in questa cartella", []


def lavoro_fotogrammi(par: dict) -> tuple[str, list]:
    p = sicuro(par["file"])
    tempi = [float(t) for t in par["tempi"]][:24]
    imgs = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(tempi):
            r = esegui(["-y", "-ss", f"{t:.2f}", "-i", str(p), "-frames:v", "1", "-vf", "scale='min(480,iw)':-2", os.path.join(tmp, f"f{i:02d}.jpg")], 120)
            if not os.path.exists(os.path.join(tmp, f"f{i:02d}.jpg")):
                raise RuntimeError(f"nessun fotogramma al secondo {t} ({r.stderr.strip()[-120:]})")
        for g in range(0, len(tempi), 6):
            gruppo = tempi[g:g + 6]
            seq = os.path.join(tmp, f"m{g // 6}_%02d.jpg")
            for k in range(len(gruppo)):
                shutil.copy(os.path.join(tmp, f"f{g + k:02d}.jpg"), seq % k)
            out = os.path.join(tmp, f"mosaico{g // 6}.jpg")
            colonne = 3 if len(gruppo) > 2 else len(gruppo)
            righe = -(-len(gruppo) // colonne)
            esegui(["-y", "-i", seq.replace("%02d", "%02d"), "-vf", f"tile={colonne}x{righe}", "-frames:v", "1", out], 120)
            imgs.append((f"tempi_{'-'.join(str(t) for t in gruppo)}.jpg", open(out, "rb").read()))
    return f"{len(tempi)} fotogrammi di {par['file']} ai secondi {tempi}, in mosaici da 6 (3 per riga, in ordine).", imgs


def lavoro_silenzi(par: dict) -> tuple[str, list]:
    p = sicuro(par["file"])
    r = esegui(["-i", str(p), "-vn", "-af", f"silencedetect=noise={par['soglia_db']}dB:d={par['durata_min']}", "-f", "null", "-"], 3600)
    inizi = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", r.stderr)]
    fini = re.findall(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", r.stderr)
    righe = [f"{i:.2f} -> {float(f[0]):.2f} ({float(f[1]):.2f} s)" for i, f in zip(inizi, fini)]
    return f"Pause di silenzio (soglia {par['soglia_db']} dB, minimo {par['durata_min']} s) in {par['file']}: {len(righe)}\n" + "\n".join(righe[:300]), []


def valida_ffmpeg(args: list[str]) -> tuple[list[str], Path]:
    if len(args) < 2:
        raise Rifiutato("servono almeno un ingresso e un'uscita")
    for a in args:
        b = a.lower().replace("\\", "/")
        if any(x in b for x in BLOCCATI):
            raise Rifiutato(f"opzione non consentita: {a[:60]}")
        if (a.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", a)) and not a.startswith("/dev/null"):
            raise Rifiutato(f"percorso assoluto non consentito: {a[:60]}")
    fuori = []
    lavfi = False
    for i, a in enumerate(args[:-1]):
        if a == "-f" and args[i + 1] == "lavfi":
            lavfi = True
        elif a == "-i":
            if lavfi:
                lavfi = False
                fuori.append(args[i + 1])
            else:
                fuori.append(str(sicuro(args[i + 1])))
    uscita_rel = args[-1].replace("\\", "/")
    if not uscita_rel.startswith("uscite/") or not uscita_rel.lower().endswith(EST_USCITA):
        raise Rifiutato(f"l'uscita deve stare in uscite/ e finire con {', '.join(EST_USCITA)}")
    uscita = sicuro(uscita_rel, deve_esistere=False)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    # sostituisce i percorsi relativi di ingresso con quelli reali, senza toccare il resto
    out, saltare = [], False
    for i, a in enumerate(args[:-1]):
        if saltare:
            saltare = False
            continue
        if a == "-i" and i + 1 < len(args) - 1:
            prec_lavfi = i >= 2 and args[i - 2] == "-f" and args[i - 1] == "lavfi"
            out += ["-i", args[i + 1] if prec_lavfi else str(sicuro(args[i + 1]))]
            saltare = True
        else:
            out.append(a)
    return out + [str(uscita)], uscita


def lavoro_ffmpeg(par: dict) -> tuple[str, list]:
    args, uscita = valida_ffmpeg([str(a) for a in par["argomenti"]])
    r = esegui(["-y", *args], 7200)
    if r.returncode != 0 or not uscita.exists():
        raise RuntimeError("ffmpeg non e' riuscito: " + r.stderr.strip()[-500:])
    d = sonda(uscita)
    return (f"Prodotto uscite/{uscita.name}: {uscita.stat().st_size / 1e6:.1f} MB, {d.get('durata', 0):.1f} s"
            + (f", {d['larghezza']}x{d['altezza']} {d.get('fps') or '?'} fps" if "larghezza" in d else ", solo audio") + f", audio {'si' if d.get('audio') else 'NO'}. "
            "Il file resta sul PC nella cartella uscite."), []


def _xml_clip(i: int, n: int, ref: str, nome: str, pathurl: str, durata_f: int, fps: int, inizio: int, fine: int, da: int, a: int, larg: int, alt: int, scala: float, primo: bool, audio: bool) -> str:
    from xml.sax.saxutils import escape
    ritmo = f"<rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>"
    filtro = ""
    if not audio and scala and abs(scala - 100) > 0.5:
        filtro = ("<filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype>"
                  f"<parameter><parameterid>scale</parameterid><name>Scale</name><valuemin>0</valuemin><valuemax>1000</valuemax><value>{scala:.1f}</value></parameter></effect></filter>")
    if primo:
        file_ = (f'<file id="{ref}"><name>{escape(nome)}</name><pathurl>{escape(pathurl)}</pathurl>{ritmo}<duration>{durata_f}</duration>'
                 f"<media><video><samplecharacteristics>{ritmo}<width>{larg}</width><height>{alt}</height></samplecharacteristics></video><audio><channelcount>2</channelcount></audio></media></file>")
    else:
        file_ = f'<file id="{ref}"/>'
    return (f'<clipitem id="{"a" if audio else "v"}clip-{i}"><name>{escape(nome)}</name><enabled>TRUE</enabled><duration>{durata_f}</duration>{ritmo}'
            f"<start>{inizio}</start><end>{fine}</end><in>{da}</in><out>{a}</out>{file_}{filtro}</clipitem>")


def lavoro_xml(par: dict) -> tuple[str, list]:
    """Progetto di montaggio (Final Cut Pro 7 XML, che Premiere Pro e DaVinci Resolve importano): le clip in fila con i punti di ingresso/uscita."""
    from urllib.parse import quote
    from xml.sax.saxutils import escape
    fps = int(par.get("fps") or 25)
    larg, alt = int(par.get("larghezza") or 2160), int(par.get("altezza") or 3840)
    nome_seq = re.sub(r"[^\w .\-]", "_", str(par.get("nome") or "Montaggio"))[:60]
    clip, vid, aud, file_ref, pos, avvisi = par.get("clip") or [], [], [], {}, 0, []
    for i, c in enumerate(clip, 1):
        p = sicuro(c["file"])
        d = sonda(p)
        da, a = float(c["da"]), float(c["a"])
        if not (0 <= da < a):
            raise Rifiutato(f"clip {i}: tempi non validi ({da}-{a})")
        if d.get("durata") and a > d["durata"] + 0.5:
            raise Rifiutato(f"clip {i}: {c['file']} dura {d['durata']:.1f} s, l'uscita {a} e' oltre")
        f_in, f_out = round(da * fps), round(a * fps)
        lung = f_out - f_in
        ref = file_ref.get(c["file"]) or f"file-{len(file_ref) + 1}"
        primo = c["file"] not in file_ref
        file_ref[c["file"]] = ref
        url = "file://localhost" + quote("/" + p.as_posix().lstrip("/"), safe="/")
        scala = 100.0 * larg / d["larghezza"] if d.get("larghezza") and par.get("ingrandisci", True) else 100.0
        if d.get("larghezza") and scala > 101:
            avvisi.append(f"{c['file']} ({d['larghezza']}x{d['altezza']}) e' ingrandito al {scala:.0f}%")
        args = (i, len(clip), ref, p.name, url, round((d.get("durata") or a) * fps), fps, pos, pos + lung, f_in, f_out, d.get("larghezza") or larg, d.get("altezza") or alt, scala)
        vid.append(_xml_clip(*args, primo, False))
        aud.append(_xml_clip(*args, primo, True))
        pos += lung
    if not vid:
        raise Rifiutato("nessuna clip")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4"><sequence id="sequenza-1"><name>' + escape(nome_seq) + f"</name><duration>{pos}</duration>"
           f"<rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate><media><video><format><samplecharacteristics><rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>"
           f"<width>{larg}</width><height>{alt}</height><anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></format>"
           "<track>" + "".join(vid) + "</track></video><audio><track>" + "".join(aud) + "</track></audio></media></sequence></xmeml>")
    uscita = sicuro(f"uscite/{nome_seq.replace(' ', '_')}.xml", deve_esistere=False)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    uscita.write_text(xml, encoding="utf-8")
    return (f"Progetto di montaggio uscite/{uscita.name}: {len(vid)} clip, {pos / fps:.1f} s, sequenza {larg}x{alt} a {fps} fps (Final Cut Pro 7 XML: in Premiere Pro File > Importa, in DaVinci Resolve File > Importa > Timeline). "
            + ("Attenzione: " + "; ".join(avvisi) + " (l'ingrandimento e' dichiarato, non e' 4K nativo). " if avvisi else "") + "I file restano nei percorsi del PC."), []


LAVORI = {"xml": lavoro_xml, "inventario": lavoro_inventario, "fotogrammi": lavoro_fotogrammi, "silenzi": lavoro_silenzi, "ffmpeg": lavoro_ffmpeg}
S = requests.Session()
S.headers.update({"Authorization": "Bearer " + TOKEN, "X-Versione": VERSIONE})


def chiama(metodo: str, percorso: str, **kw):
    kw.setdefault("timeout", 120)
    r = S.request(metodo, URL + "/banco" + percorso, **kw)
    if r.status_code == 401:
        raise SystemExit("Chiave della postazione non valida: scarica un pacchetto nuovo da Opifex.")
    r.raise_for_status()
    return r.json()


def esegui_lavoro(l: dict) -> None:
    try:
        testo, immagini = LAVORI[l["tipo"]](l["parametri"])
        ok = True
    except Rifiutato as e:
        testo, immagini, ok = f"Rifiutato dalla postazione: {e}", [], False
    except subprocess.TimeoutExpired:
        testo, immagini, ok = "Il lavoro ha superato il tempo massimo", [], False
    except Exception as e:  # noqa: BLE001
        testo, immagini, ok = f"{type(e).__name__}: {e}"[:600], [], False
    files = [("file", (n, d, "image/jpeg")) for n, d in immagini]
    S.post(URL + f"/banco/lavoro/{l['id']}/esito", data={"ok": "true" if ok else "false", "testo": testo}, files=files, timeout=300).raise_for_status()
    log.info("Lavoro %s (%s): %s", l["id"], l["tipo"], "ok" if ok else "errore")


def battito() -> None:
    while True:
        try:
            chiama("GET", "/ping", timeout=20)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(60)


def main() -> None:
    global FF
    if not URL or not TOKEN:
        raise SystemExit("Mancano OPIFEX_URL e OPIFEX_TOKEN.")
    if not DATI.is_dir():
        raise SystemExit(f"La cartella di lavoro non esiste: {DATI}")
    FF = trova_ffmpeg()
    (DATI / "uscite").mkdir(exist_ok=True)
    threading.Thread(target=battito, daemon=True).start()
    log.info("Banco di lavoro %s: cartella %s, ffmpeg %s", VERSIONE, DATI, FF)
    while True:
        try:
            l = chiama("GET", "/lavoro").get("lavoro")
            if l:
                esegui_lavoro(l)
                continue
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Opifex non raggiungibile o errore (%s): riprovo", type(e).__name__)
        time.sleep(5)


if __name__ == "__main__":
    main()
