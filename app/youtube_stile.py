"""Riferimenti da YouTube: trascrizione con i tempi e ritmo del parlato di un video, per capire come e' costruito (gancio, struttura, pause, ritmo).
Dal solo testo non si vedono le immagini: tagli, inquadrature e colore non sono ricavabili; per quelli servono gli XML di montaggio. Nessun video viene scaricato."""
import re
from urllib.parse import parse_qs, urlparse

import httpx


class ErroreYoutube(Exception):
    pass


def id_video(url: str) -> str:
    u = urlparse((url or "").strip())
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        v = u.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com"):
        v = parse_qs(u.query).get("v", [""])[0] or (u.path.split("/")[2] if re.match(r"^/(shorts|embed|live)/", u.path) and len(u.path.split("/")) > 2 else "")
    else:
        raise ErroreYoutube("Non e' un indirizzo YouTube")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", v or ""):
        raise ErroreYoutube("Indirizzo YouTube non riconosciuto")
    return v


def _trascrizione(video_id: str) -> list[dict]:
    """[{text, start, duration}] (sostituibile nei collaudi)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        t = YouTubeTranscriptApi().fetch(video_id, languages=["it", "en", "es", "fr", "de", "pt"])
        return [{"text": s["text"], "start": s["start"], "duration": s["duration"]} if isinstance(s, dict) else
                {"text": s.text, "start": s.start, "duration": s.duration} for s in t]
    except ImportError:
        raise ErroreYoutube("Manca il componente per leggere le trascrizioni di YouTube") from None
    except Exception as e:  # noqa: BLE001 - YouTube puo' bloccare o non avere sottotitoli
        raise ErroreYoutube("Trascrizione non disponibile (" + type(e).__name__ + "): il video potrebbe non avere sottotitoli o YouTube blocca la richiesta") from None


def _titolo(url: str) -> dict:
    try:
        r = httpx.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, headers={"User-Agent": "Opifex/1"}, timeout=15)
        return r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {}


def _tc(s):
    return f"{int(s // 60)}:{int(s % 60):02d}"


def analizza(url: str) -> str:
    vid = id_video(url)
    seg = [s for s in _trascrizione(vid) if str(s.get("text", "")).strip()]
    if len(seg) < 5:
        raise ErroreYoutube("La trascrizione e' troppo breve per essere analizzata")
    meta = _titolo(url)
    fine = seg[-1]["start"] + seg[-1]["duration"]
    parole = sum(len(s["text"].split()) for s in seg)
    pause = [seg[i + 1]["start"] - (seg[i]["start"] + seg[i]["duration"]) for i in range(len(seg) - 1)]
    lunghe = [p for p in pause if p >= 1.0]
    wpm = parole / (fine / 60) if fine else 0
    gancio = " ".join(s["text"] for s in seg if s["start"] < 30).replace("\n", " ")
    chiusa = " ".join(s["text"] for s in seg if s["start"] > fine - 30).replace("\n", " ")
    n = 10
    blocchi = []
    for k in range(n):
        a, b = fine * k / n, fine * (k + 1) / n
        t = " ".join(s["text"] for s in seg if a <= s["start"] < b).replace("\n", " ")
        blocchi.append(f"[{_tc(a)}] " + " ".join(t.split()[:28]) + ("…" if len(t.split()) > 28 else ""))
    r = [f"ANALISI DEL PARLATO — video YouTube «{meta.get('title') or vid}»" + (f" di {meta['author_name']}" if meta.get("author_name") else "") + f" ({url.strip()})",
         f"- Durata {_tc(fine)}; {parole} parole, circa {wpm:.0f} parole al minuto" + (" (parlato veloce)" if wpm > 170 else " (parlato lento e disteso)" if wpm < 110 else " (ritmo medio)") + ".",
         f"- Pause lunghe (oltre 1 s): {len(lunghe)}" + (f", una ogni {fine / len(lunghe):.0f} s in media" if lunghe else "") + ".",
         "- Nota: sono visibili solo parole e tempi del parlato; tagli, inquadrature, grafiche, colore e musica non si ricavano da qui.",
         "", "GANCIO (primi 30 secondi): " + gancio[:600], "", "CHIUSURA (ultimi 30 secondi): " + chiusa[:600], "", "STRUTTURA (un estratto ogni decimo di video):"] + blocchi
    return "\n".join(r)
