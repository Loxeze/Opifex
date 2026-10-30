"""Analisi tecnica dei montaggi: legge i file di sequenza (Premiere/Final Cut 7 «xmeml», DaVinci Resolve e Final Cut «fcpxml», EDL) e i sottotitoli (SRT, VTT)
e ne ricava un'impronta di stile: ritmo dei tagli, durata delle inquadrature, transizioni, livelli di montaggio, titoli, effetti, marcatori.
L'analisi e' calcolata dal programma (non inventata): serve a far capire agli agenti come monta Lorenzo."""
import re
import statistics
import xml.etree.ElementTree as ET
from fractions import Fraction

MAX_BYTE = 60 * 1024 * 1024


class MontaggioNonLeggibile(Exception):
    pass


def _tc(s: float) -> str:
    s = max(0, s)
    return f"{int(s // 60)}:{int(s % 60):02d}" if s < 3600 else f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"


def _conta(lista):
    d: dict[str, int] = {}
    for x in lista:
        x = (x or "").strip()
        if x:
            d[x] = d.get(x, 0) + 1
    return sorted(d.items(), key=lambda kv: -kv[1])


def _riga(nome, voci, massimo=8):
    return f"- {nome}: " + (", ".join(f"{k} ×{n}" for k, n in voci[:massimo]) if voci else "nessuno")


def _ritmo(durate: list[float], totale: float) -> list[str]:
    if not durate:
        return ["- Nessuna inquadratura trovata sul livello principale."]
    d = sorted(durate)
    med = statistics.median(d)
    fasce = [(0, 1, "sotto 1 s"), (1, 2, "1-2 s"), (2, 4, "2-4 s"), (4, 8, "4-8 s"), (8, 15, "8-15 s"), (15, 1e9, "oltre 15 s")]
    righe = [f"- Inquadrature sul livello principale: {len(d)}; durata media {sum(d) / len(d):.1f} s, mediana {med:.1f} s, minima {d[0]:.1f} s, massima {d[-1]:.1f} s.",
             f"- Tagli al minuto (media): {len(d) / (totale / 60):.1f}." if totale > 0 else "- Durata totale non disponibile."]
    righe.append("- Distribuzione: " + ", ".join(f"{nome} {sum(1 for x in d if a <= x < b) * 100 // len(d)}%" for a, b, nome in fasce if any(a <= x < b for x in d)))
    if len(durate) >= 8:
        q = len(durate) // 4
        a, b = sum(durate[:q]) / q, sum(durate[-q:]) / q
        righe.append(f"- Andamento: prime inquadrature {a:.1f} s in media, ultime {b:.1f} s ({'il ritmo accelera' if b < a * 0.8 else 'il ritmo rallenta' if b > a * 1.25 else 'ritmo costante'}).")
    return righe


# ---------------- xmeml (Premiere, Final Cut 7) ----------------
def _num(e, tag, default=None):
    x = e.find(tag) if e is not None else None
    try:
        return int(x.text) if x is not None and x.text not in (None, "") else default
    except ValueError:
        return default


def _xmeml(radice: ET.Element, nome_file: str) -> str:
    seq = radice.find(".//sequence")
    if seq is None:
        raise MontaggioNonLeggibile("Nessuna sequenza trovata nel file")
    tb = _num(seq.find("rate"), "timebase", 25) or 25
    fps = tb * (1000 / 1001 if (seq.findtext("rate/ntsc") or "").upper() == "TRUE" else 1)
    larg = seq.findtext(".//video/format/samplecharacteristics/width"); alt = seq.findtext(".//video/format/samplecharacteristics/height")
    video = seq.find("media/video"); audio = seq.find("media/audio")
    tracce = video.findall("track") if video is not None else []
    durate, per_traccia, effetti, trans, titoli, vel = [], [], [], [], [], 0
    for t, tr in enumerate(tracce):
        clip = []
        for c in tr.findall("clipitem"):
            s, e = _num(c, "start", -1), _num(c, "end", -1)
            if s is not None and e is not None and s >= 0 and e > s:
                clip.append((s, e, c))
            else:
                i, o = _num(c, "in", 0) or 0, _num(c, "out", 0) or 0
                if o > i:
                    clip.append((0, o - i, c))
            for ef in c.findall(".//filter/effect/name"):
                effetti.append(ef.text)
                if ef.text and re.search(r"time remap|velocit|speed", ef.text, re.I):
                    vel += 1
            nome = (c.findtext("name") or "")
            if re.search(r"\btitle|titol|text|testo|lower", nome, re.I):
                titoli.append(nome)
        per_traccia.append(len(clip))
        if t == 0 or len(tracce) == 1:
            durate = [(e - s) / fps for s, e, _ in clip]
        for ti in tr.findall("transitionitem"):
            trans.append(ti.findtext("effect/name") or "Transizione")
    tot = (_num(seq, "duration", 0) or 0) / fps or sum(durate)
    tracce_a = audio.findall("track") if audio is not None else []
    marc = [(m.findtext("name") or m.findtext("comment") or "", (_num(m, "in", 0) or 0) / fps) for m in seq.findall("marker")]
    r = [f"ANALISI TECNICA DEL MONTAGGIO — file «{nome_file}» (sequenza Premiere / Final Cut 7, formato xmeml)",
         f"- Sequenza «{seq.findtext('name') or 'senza nome'}», durata {_tc(tot)}, {fps:.2f} fotogrammi/s" + (f", {larg}x{alt}" if larg and alt else "") + ".",
         f"- Livelli video: {len(tracce)} (inquadrature per livello: {', '.join(map(str, per_traccia)) or '0'}). Livelli audio: {len(tracce_a)}."]
    r += _ritmo(durate, tot)
    r.append(f"- Transizioni: {len(trans)} su {len(durate)} inquadrature" + (f" ({len(trans) * 100 // max(1, len(durate))}% dei tagli ha una transizione)" if durate else "") + ". " + (", ".join(f"{k} ×{n}" for k, n in _conta(trans)[:6]) if trans else "Montaggio quasi tutto a taglio netto."))
    r.append(_riga("Effetti usati", _conta(effetti)))
    r.append(f"- Cambi di velocita' (time remap): {vel}.")
    r.append(_riga("Titoli e grafiche", _conta(titoli), 6))
    if marc:
        r.append("- Marcatori: " + "; ".join(f"{_tc(t)} {n}" for n, t in marc[:12]))
    return "\n".join(r)


# ---------------- fcpxml (DaVinci Resolve, Final Cut Pro) ----------------
def _t(s):
    if not s:
        return 0.0
    s = s.strip().rstrip("s")
    try:
        return float(Fraction(s))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _fcpxml(radice: ET.Element, nome_file: str) -> str:
    fm = radice.find(".//resources/format")
    fps = 25.0
    if fm is not None and fm.get("frameDuration"):
        fd = _t(fm.get("frameDuration"))
        fps = round(1 / fd, 2) if fd else 25.0
    seq = radice.find(".//sequence")
    if seq is None:
        raise MontaggioNonLeggibile("Nessuna sequenza trovata nel file")
    spine = seq.find("spine")
    durate, trans, titoli, effetti, marc, vel, connessi, tracce_ar = [], [], [], [], [], 0, 0, 0
    if spine is not None:
        for c in spine:
            tag = c.tag
            if tag in ("asset-clip", "clip", "video", "ref-clip", "mc-clip", "sync-clip", "audition"):
                durate.append(_t(c.get("duration")))
            elif tag == "title":
                titoli.append(c.get("name") or "Titolo"); durate.append(_t(c.get("duration")))
            elif tag == "transition":
                trans.append((c.get("name") or "Transizione", _t(c.get("duration"))))
            for sub in c.iter():
                if sub is c:
                    continue
                if sub.get("lane") and sub.tag in ("asset-clip", "clip", "video", "title", "audio", "ref-clip"):
                    connessi += 1
                    if sub.tag == "title":
                        titoli.append(sub.get("name") or "Titolo")
                if sub.tag in ("filter-video", "filter-audio"):
                    effetti.append(sub.get("name"))
                if sub.tag == "timeMap":
                    vel += 1
                if sub.tag in ("marker", "chapter-marker"):
                    marc.append((sub.get("value") or "", _t(sub.get("start"))))
            for m in c.findall("marker") + c.findall("chapter-marker"):
                pass
    durate = [d for d in durate if d > 0]
    tot = _t(seq.get("duration")) or sum(durate)
    larg, alt = (fm.get("width"), fm.get("height")) if fm is not None else (None, None)
    r = [f"ANALISI TECNICA DEL MONTAGGIO — file «{nome_file}» (sequenza DaVinci Resolve / Final Cut, formato fcpxml)",
         f"- Progetto «{(radice.find('.//project').get('name') if radice.find('.//project') is not None else None) or 'senza nome'}», durata {_tc(tot)}, {fps:.2f} fotogrammi/s" + (f", {larg}x{alt}" if larg and alt else "") + ".",
         f"- Clip collegate sopra o sotto la linea principale (B-roll, audio, titoli): {connessi}."]
    r += _ritmo(durate, tot)
    nt = [n for n, _ in trans]
    r.append(f"- Transizioni: {len(trans)} su {len(durate)} inquadrature. " + (", ".join(f"{k} ×{n}" for k, n in _conta(nt)[:6]) + f"; durata media {sum(d for _, d in trans) / len(trans):.2f} s." if trans else "Montaggio quasi tutto a taglio netto."))
    r.append(_riga("Effetti usati", _conta(effetti)))
    r.append(f"- Cambi di velocita' (time map): {vel}.")
    r.append(_riga("Titoli e grafiche", _conta(titoli), 6))
    if marc:
        r.append("- Marcatori: " + "; ".join(f"{_tc(t)} {n}" for n, t in marc[:12]))
    return "\n".join(r)


# ---------------- EDL ----------------
_EVENTO = re.compile(r"^\s*(\d{3,6})\s+(\S+)\s+(\S+)\s+(C|D|W\d*|K\w*)\s*(\d{1,4})?\s+(\d\d[:;]\d\d[:;]\d\d[:;]\d\d)\s+(\d\d[:;]\d\d[:;]\d\d[:;]\d\d)\s+(\d\d[:;]\d\d[:;]\d\d[:;]\d\d)\s+(\d\d[:;]\d\d[:;]\d\d[:;]\d\d)", re.M)


def _edl(testo: str, nome_file: str, fps: float = 25.0) -> str:
    def sec(tc):
        h, m, s, f = (int(x) for x in re.split(r"[:;]", tc))
        return h * 3600 + m * 60 + s + f / fps
    ev = _EVENTO.findall(testo)
    if not ev:
        raise MontaggioNonLeggibile("Nessun evento trovato nella EDL")
    titolo = (re.search(r"^TITLE:\s*(.+)$", testo, re.M) or [None, "senza nome"])[1]
    durate = [sec(e[8]) - sec(e[7]) for e in ev if e[2].upper().startswith("V") or e[2].upper() in ("B", "AA/V")]
    durate = [d for d in durate if d > 0]
    tipi = _conta([{"C": "Taglio netto", "D": "Dissolvenza"}.get(e[3][0], "Tendina/altro") for e in ev])
    tot = max((sec(e[8]) for e in ev), default=0) - min((sec(e[7]) for e in ev), default=0)
    r = [f"ANALISI TECNICA DEL MONTAGGIO — file «{nome_file}» (EDL, {fps:g} fotogrammi/s ipotizzati)", f"- Titolo «{titolo}», {len(ev)} eventi, durata circa {_tc(tot)}."]
    r += _ritmo(durate, tot)
    r.append(_riga("Tipo di passaggi", tipi))
    r.append(_riga("Bobine/sorgenti piu' usate", _conta([e[1] for e in ev]), 6))
    return "\n".join(r)


# ---------------- sottotitoli ----------------
_CUE = re.compile(r"(\d\d:\d\d:\d\d[,.]\d{3}|\d\d:\d\d[,.]\d{3})\s*-->\s*(\d\d:\d\d:\d\d[,.]\d{3}|\d\d:\d\d[,.]\d{3})[^\n]*\n((?:.+\n?)+)")


def _sec(x):
    p = x.replace(",", ".").split(":")
    p = [float(v) for v in p]
    return sum(v * 60 ** i for i, v in enumerate(reversed(p)))


def sottotitoli(testo: str, nome_file: str) -> str:
    cue = [(_sec(a), _sec(b), re.sub(r"<[^>]+>", "", t).strip().replace("\n", " ")) for a, b, t in _CUE.findall(testo.replace("\r", ""))]
    if not cue:
        raise MontaggioNonLeggibile("Nessun sottotitolo trovato")
    dur = [b - a for a, b, _ in cue]; car = [len(t) for _, _, t in cue]
    tot = cue[-1][1]
    r = [f"SOTTOTITOLI — file «{nome_file}»: {len(cue)} sottotitoli su {_tc(tot)}; durata media {sum(dur) / len(dur):.1f} s, {sum(car) / len(car):.0f} caratteri in media, "
         f"{len(cue) / (tot / 60):.1f} sottotitoli al minuto.", "", "TESTO CON TEMPI:"]
    r += [f"[{_tc(a)}] {t}" for a, _, t in cue]
    return "\n".join(r)


def analizza(nome_file: str, contenuto: bytes) -> str | None:
    """Testo di analisi se il file e' una sequenza di montaggio o dei sottotitoli, altrimenti None (il file resta trattato come XML o testo normale)."""
    n = nome_file.lower()
    if len(contenuto) > MAX_BYTE:
        raise MontaggioNonLeggibile("File troppo grande")
    try:
        testo = contenuto.decode("utf-8-sig")
    except UnicodeDecodeError:
        testo = contenuto.decode("latin-1")
    if n.endswith((".srt", ".vtt")):
        return sottotitoli(testo, nome_file)
    if n.endswith(".edl"):
        return _edl(testo, nome_file)
    if n.endswith((".xml", ".fcpxml")):
        testa = testo[:2000]
        if "<xmeml" not in testa and "<fcpxml" not in testa:
            if n.endswith(".fcpxml"):
                raise MontaggioNonLeggibile("Il file non e' un fcpxml valido")
            return None
        try:
            radice = ET.fromstring(testo)
        except ET.ParseError:
            raise MontaggioNonLeggibile("Il file XML non e' leggibile") from None
        return _xmeml(radice, nome_file) if radice.tag == "xmeml" else _fcpxml(radice, nome_file)
    return None
