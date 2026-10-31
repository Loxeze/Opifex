"""Strumenti dei lavori creativi (grafica, foto, social, copy): misurano e correggono invece di dichiarare.
- copy_controlla: controllo di un testo per piattaforma (lunghezze, hashtag, leggibilita' Gulpease, gancio, CTA, promesse da verificare, ripetizioni);
- immagine_analizza / immagine_adatta: misure e palette di un'immagine, controllo del formato, ritaglio ai formati dei social (la parte su Drive e' in strumenti_google)."""
import io
import re
from collections import Counter

FORMATI = {  # nome: (larghezza, altezza, descrizione)
    "ig_post": (1080, 1350, "Instagram post 4:5"), "ig_quadrato": (1080, 1080, "Instagram quadrato 1:1"), "verticale_9_16": (1080, 1920, "Story, Reel, TikTok, Shorts 9:16"),
    "linkedin": (1200, 627, "LinkedIn link/immagine 1,91:1"), "facebook": (1200, 630, "Facebook link 1,91:1"), "youtube_miniatura": (1280, 720, "Miniatura YouTube 16:9"),
    "x_post": (1600, 900, "Post su X 16:9"), "a4_300dpi": (2480, 3508, "A4 verticale a 300 dpi"), "a3_300dpi": (3508, 4961, "A3 verticale a 300 dpi"),
}
PIATTAFORME = {  # massimo caratteri, hashtag consigliati (min, max), righe del gancio visibili prima di «altro»
    "instagram": (2200, (3, 8), 125), "facebook": (63206, (0, 3), 120), "linkedin": (3000, (2, 5), 140), "x": (280, (0, 2), 280),
    "tiktok": (2200, (3, 6), 100), "youtube": (5000, (3, 5), 100), "sito": (100000, (0, 0), 160), "newsletter": (100000, (0, 0), 60),
}
PROMESSE = ("garantit", "100%", "il migliore", "la migliore", "unico", "unica", "senza rischi", "risultati certi", "gratis", "gratuito", "miracol", "rivoluzionari", "numero uno", "mai visto")
VERBI_CTA = ("scopri", "iscriviti", "prenota", "scrivici", "contattaci", "chiama", "visita", "partecipa", "compila", "scarica", "leggi", "guarda", "segui", "condividi", "commenta",
             "acquista", "richiedi", "registrati", "vieni", "unisciti", "prova", "ordina", "candidati", "clicca", "salva")
STOP = set("che di e il la le lo un una per con del della dei delle non sono come piu anche alla alle nel nella nei sul sulla ma se ci si da in a è o i gli al".split())


def _frasi(t: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])\s+|\n+", t.strip()) if s.strip()]


def copy_controlla(testo: str, piattaforma: str = "instagram", cta: str = "") -> str:
    t = str(testo or "").strip()
    if len(t) < 5:
        return "ERRORE: manca il testo da controllare"
    p = (piattaforma or "instagram").strip().lower()
    p = {"ig": "instagram", "fb": "facebook", "twitter": "x", "yt": "youtube"}.get(p, p)
    if p not in PIATTAFORME:
        return "ERRORE: piattaforma non riconosciuta (" + ", ".join(PIATTAFORME) + ")"
    limite, (hmin, hmax), gancio_max = PIATTAFORME[p]
    righe = []

    def voce(esito: str, testo_: str):
        righe.append(f"[{esito}] {testo_}")

    n = len(t)
    voce("OK" if n <= limite else "KO", f"Lunghezza {n} caratteri su {limite} consentiti su {p}" + ("" if n <= limite else f": togli {n - limite} caratteri"))
    tag = re.findall(r"#\w+", t)
    voce("OK" if hmin <= len(tag) <= hmax else "AVVISO", f"{len(tag)} hashtag (consigliati {hmin}-{hmax} su {p})" + (" — ripetuti: " + ", ".join(sorted({x for x in tag if tag.count(x) > 1})) if len(set(tag)) != len(tag) else ""))
    prima = _frasi(t)[0] if _frasi(t) else t
    voce("OK" if len(prima) <= gancio_max else "AVVISO", f"Gancio (prima frase) di {len(prima)} caratteri: su {p} se ne vedono circa {gancio_max} prima di «altro» — metti li' l'idea forte")
    corpo = re.sub(r"#\w+|https?://\S+|[\U0001F300-\U0001FAFF☀-➿]", " ", t)
    parole = re.findall(r"[A-Za-zÀ-ÿ']+", corpo)
    fr = _frasi(corpo)
    if parole and fr:
        lettere = sum(len(w) for w in parole)
        gulp = 89 + (300 * len(fr) - 10 * lettere) / len(parole)
        liv = "facile" if gulp >= 80 else "medio" if gulp >= 60 else "difficile" if gulp >= 40 else "molto difficile"
        voce("OK" if gulp >= 60 else "AVVISO", f"Leggibilita' Gulpease {gulp:.0f} ({liv}); frasi lunghe in media {len(parole) / len(fr):.1f} parole" + ("" if gulp >= 60 else ": accorcia le frasi, usa parole piu' semplici"))
        lunghe = [s for s in fr if len(re.findall(r"\w+", s)) > 30]
        if lunghe:
            voce("AVVISO", f"{len(lunghe)} frase/i oltre 30 parole: «{lunghe[0][:60]}…»")
        freq = Counter(w.lower() for w in parole if len(w) > 4 and w.lower() not in STOP)
        rip = [f"{w} x{c}" for w, c in freq.most_common(3) if c >= 4]
        if rip:
            voce("AVVISO", "Parole ripetute: " + ", ".join(rip))
    low = t.lower()
    prom = [x for x in PROMESSE if x in low]
    if prom:
        voce("AVVISO", "Promesse o superlativi da verificare o togliere: " + ", ".join(prom) + " (servono prova e fonte)")
    ha_cta = any(re.search(r"\b" + v, low) for v in VERBI_CTA) or bool(cta and cta.lower() in low)
    voce("OK" if ha_cta else "AVVISO", "Invito all'azione presente" if ha_cta else "Manca un invito all'azione chiaro (es. «scopri», «prenota», «scrivici»)")
    maius = sum(1 for c in corpo if c.isupper()) / max(1, sum(1 for c in corpo if c.isalpha()))
    if maius > 0.25:
        voce("AVVISO", f"Troppe maiuscole ({maius:.0%}): sembra un urlo")
    if re.search(r"  +", t):
        voce("AVVISO", "Spazi doppi")
    emoji = len(re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", t))
    if emoji > (8 if p in ("instagram", "tiktok") else 3):
        voce("AVVISO", f"{emoji} emoji: troppe per {p}")
    link = re.findall(r"https?://\S+", t)
    if p == "instagram" and link:
        voce("AVVISO", "Su Instagram i link nella didascalia non sono cliccabili: usa «link in bio»")
    ko = sum(1 for r in righe if r.startswith("[KO]"))
    av = sum(1 for r in righe if r.startswith("[AVVISO]"))
    return (f"CONTROLLO TESTO per {p}: {'DA CORREGGERE' if ko else 'ok' if not av else 'ok con avvisi'} ({ko} KO, {av} avvisi)\n" + "\n".join(righe)
            + "\nCorreggi i KO e valuta gli avvisi; registra poi il controllo con consegna_verifica.")


def _palette(im, n: int = 5) -> list[str]:
    p = im.convert("RGB").resize((96, 96)).quantize(colors=n, method=2)
    pal = p.getpalette() or []
    cont = sorted(p.getcolors() or [], reverse=True)
    return ["#%02X%02X%02X" % tuple(pal[i * 3:i * 3 + 3]) for _, i in cont][:n]


def analizza_bytes(dati: bytes) -> dict:
    from PIL import Image, ImageFilter, ImageStat
    im = Image.open(io.BytesIO(dati))
    im.load()
    w, h = im.size
    grigio = im.convert("L")
    luce = ImageStat.Stat(grigio).mean[0]
    contrasto = ImageStat.Stat(grigio).stddev[0]
    bordi = ImageStat.Stat(grigio.resize((min(w, 800), max(1, int(h * min(w, 800) / w)))).filter(ImageFilter.FIND_EDGES)).var[0]
    dpi = im.info.get("dpi")
    adatti = [f"{k} ({d})" for k, (fw, fh, d) in FORMATI.items() if abs(w / h - fw / fh) < 0.03 and w >= fw * 0.9]
    return {"larghezza": w, "altezza": h, "formato": im.format, "modo": im.mode, "megapixel": round(w * h / 1e6, 2), "proporzioni": round(w / h, 3), "byte": len(dati),
            "dpi": tuple(int(x) for x in dpi) if dpi else None, "luminosita": round(luce), "contrasto": round(contrasto), "nitidezza": round(bordi, 1),
            "palette": _palette(im), "adatto_a": adatti, "trasparenza": "A" in im.getbands()}


def testo_analisi(a: dict) -> str:
    righe = [f"{a['larghezza']}x{a['altezza']} px ({a['megapixel']} MP), proporzioni {a['proporzioni']}, {a['formato']} {a['modo']}, {a['byte'] / 1e6:.2f} MB" + (f", {a['dpi'][0]} dpi" if a["dpi"] else ""),
             f"Luminosita' {a['luminosita']}/255 ({'scura' if a['luminosita'] < 70 else 'molto chiara' if a['luminosita'] > 200 else 'ok'}), contrasto {a['contrasto']} ({'basso' if a['contrasto'] < 35 else 'ok'}), "
             f"nitidezza {a['nitidezza']} ({'possibile sfocatura' if a['nitidezza'] < 40 else 'ok'})",
             "Palette dominante: " + ", ".join(a["palette"]),
             "Adatta senza ritaglio a: " + (", ".join(a["adatto_a"]) or "nessun formato standard (usa immagine_adatta per ritagliare)")]
    if a["trasparenza"]:
        righe.append("Ha trasparenza (salvala PNG, non JPG).")
    if min(a["larghezza"], a["altezza"]) < 1000:
        righe.append("Risoluzione bassa: per social va bene fino a ~1080 px, per stampa servono almeno 300 dpi sul formato finale.")
    return "\n".join(righe)


def adatta_bytes(dati: bytes, formato: str, modo: str = "riempi", sfondo: str = "#FFFFFF") -> tuple[bytes, str, str]:
    """Ritorna (byte, estensione, note). modo: 'riempi' ritaglia al centro; 'contieni' lascia tutta l'immagine con bordi di colore."""
    from PIL import Image, ImageOps
    if formato not in FORMATI:
        raise ValueError("formato sconosciuto: " + ", ".join(FORMATI))
    fw, fh, desc = FORMATI[formato]
    im = Image.open(io.BytesIO(dati))
    im.load()
    im = ImageOps.exif_transpose(im)
    w, h = im.size
    note = []
    scala = max(fw / w, fh / h) if modo != "contieni" else min(fw / w, fh / h)
    if scala > 1.5:
        note.append(f"ingrandita {scala:.1f}x: la qualita' cala, usa un originale piu' grande se puoi")
    if modo == "contieni":
        r = im.convert("RGBA").resize((max(1, round(w * scala)), max(1, round(h * scala))), Image.LANCZOS)
        fondo = Image.new("RGB", (fw, fh), sfondo if re.fullmatch(r"#[0-9a-fA-F]{6}", sfondo or "") else "#FFFFFF")
        fondo.paste(r, ((fw - r.width) // 2, (fh - r.height) // 2), r)
        out = fondo
    else:
        out = ImageOps.fit(im.convert("RGB"), (fw, fh), Image.LANCZOS, centering=(0.5, 0.45))
        if (w / h > fw / fh and (w * fh / h) / fw > 1.6) or (h / w > fh / fw and (h * fw / w) / fh > 1.6):
            note.append("ritaglio forte: parte dell'immagine e' stata tagliata, controlla che il soggetto sia intero")
    buf = io.BytesIO()
    if "A" in im.getbands() and modo != "contieni" and formato not in ("a4_300dpi", "a3_300dpi"):
        im.convert("RGBA")
    out.save(buf, "JPEG", quality=92, optimize=True, dpi=(300, 300) if "300dpi" in formato else (72, 72))
    return buf.getvalue(), "jpg", f"{desc} {fw}x{fh}" + (" — " + "; ".join(note) if note else "")


STRUMENTO_COPY = {"name": "copy_controlla",
                  "description": "Controlla un testo social/copy PRIMA di consegnarlo: lunghezza e hashtag per piattaforma (instagram, facebook, linkedin, x, tiktok, youtube, sito, newsletter), "
                                 "gancio, leggibilita' (Gulpease), invito all'azione, promesse da verificare, ripetizioni. Restituisce KO e avvisi da correggere.",
                  "input_schema": {"type": "object", "properties": {"testo": {"type": "string"}, "piattaforma": {"type": "string"}, "cta": {"type": "string", "description": "Invito all'azione previsto (facoltativo)"}},
                                   "required": ["testo"]}}


def gestore_copy(nome, dati):
    if nome == "copy_controlla":
        return copy_controlla(str((dati or {}).get("testo") or ""), str((dati or {}).get("piattaforma") or "instagram"), str((dati or {}).get("cta") or ""))
    return "ERRORE: strumento sconosciuto"
