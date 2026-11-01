"""Grafica disegnata dagli agenti: impaginano in HTML e CSS, Opifex la trasforma in PNG, JPG o PDF con un browser vero.
Niente rete (salvo i caratteri di Google Fonts), niente script: le foto arrivano da Drive e si inseriscono come @nome."""
import re

from . import creativi

MAX_HTML = 200_000
MAX_IMMAGINI = 8
PDF = {"a4_pdf": (794, 1123, "A4 verticale"), "a4_orizzontale_pdf": (1123, 794, "A4 orizzontale"), "a3_pdf": (1123, 1587, "A3 verticale")}
STAMPA = {"a4_300dpi": (794, 1123), "a3_300dpi": (1123, 1587)}   # misura CSS: il file esce a 300 dpi
HOST_FONT = ("fonts.googleapis.com", "fonts.gstatic.com")


class ErroreGrafica(Exception):
    pass


def formati() -> str:
    return ", ".join(list(creativi.FORMATI) + list(PDF) + ["personalizzato (larghezza e altezza in pixel)"])


def misure(formato: str, larghezza=None, altezza=None) -> tuple[int, int, float, str]:
    """Ritorna (larghezza css, altezza css, scala, descrizione)."""
    if formato in STAMPA:
        w, h = STAMPA[formato]
        fw, fh, desc = creativi.FORMATI[formato]
        return w, h, fw / w, desc
    if formato in creativi.FORMATI:
        w, h, desc = creativi.FORMATI[formato]
        return w, h, 1.0, desc
    if formato in PDF:
        w, h, desc = PDF[formato]
        return w, h, 1.0, desc
    if formato in ("", "personalizzato", None):
        try:
            w, h = int(larghezza), int(altezza)
        except (TypeError, ValueError):
            raise ErroreGrafica("formato mancante: scegli tra " + formati())
        if not (200 <= w <= 8000 and 200 <= h <= 8000):
            raise ErroreGrafica("larghezza e altezza devono essere tra 200 e 8000 pixel")
        return w, h, 1.0, f"{w}x{h}"
    raise ErroreGrafica("formato sconosciuto: " + formati())


def alleggerisci(dati: bytes, mime: str, lato: int = 3000) -> tuple[bytes, str]:
    """Le foto grandi vengono ridotte (lato massimo) perche' la pagina resti leggera; la rotazione EXIF viene applicata."""
    import io
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(dati))
        im.load()
        im = ImageOps.exif_transpose(im)
    except Exception:
        return dati, mime
    if max(im.size) <= lato and mime in ("image/png", "image/jpeg", "image/webp"):
        return dati, mime
    im.thumbnail((lato, lato))
    b = io.BytesIO()
    if im.mode in ("RGBA", "LA", "P"):
        im.convert("RGBA").save(b, "PNG")
        return b.getvalue(), "image/png"
    im.convert("RGB").save(b, "JPEG", quality=92)
    return b.getvalue(), "image/jpeg"


def componi(html: str, immagini: dict[str, str]) -> str:
    """Sostituisce @nome con la foto (data URI) e aggiunge la base del documento se manca."""
    t = str(html or "")
    if len(t) < 30:
        raise ErroreGrafica("manca l'HTML della grafica")
    if len(t) > MAX_HTML:
        raise ErroreGrafica("HTML troppo lungo")
    for nome, uri in immagini.items():
        t = re.sub(r"@" + re.escape(nome) + r"(?![\w-])", lambda _m, u=uri: u, t)
    base = "<meta charset='utf-8'><style>html,body{margin:0;padding:0}*{box-sizing:border-box}</style>"
    if "<html" not in t.lower():
        t = "<!doctype html>" + base + (t if "<body" in t.lower() else "<body>" + t + "</body>")
    else:
        t = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + base, t, count=1, flags=re.I) if re.search(r"<head", t, re.I) else t
    return t


def renderizza(html: str, larghezza: int, altezza: int, scala: float = 1.0, uscita: str = "png", pdf: bool = False) -> bytes:
    from playwright.sync_api import sync_playwright

    def filtro(route):
        u = route.request.url
        host = re.sub(r"^https?://([^/:]+).*$", r"\1", u) if u.startswith("http") else ""
        if u.startswith(("data:", "about:")) or host in HOST_FONT:
            route.continue_()
        else:
            route.abort()

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        try:
            ctx = br.new_context(viewport={"width": larghezza, "height": altezza}, device_scale_factor=scala, java_script_enabled=False, locale="it-IT")
            ctx.set_default_timeout(30000)
            ctx.route("**/*", filtro)
            pg = ctx.new_page()
            pg.set_content(html, wait_until="load")
            try:
                pg.evaluate("document.fonts.ready")
            except Exception:
                pass
            if pdf:
                return pg.pdf(width=f"{larghezza}px", height=f"{altezza}px", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            if uscita == "jpg":
                return pg.screenshot(type="jpeg", quality=92, clip={"x": 0, "y": 0, "width": larghezza, "height": altezza})
            return pg.screenshot(type="png", clip={"x": 0, "y": 0, "width": larghezza, "height": altezza})
        finally:
            br.close()


# ---------- controlli prima di consegnare ----------
_JS_CONTROLLI = """() => {
 const W = innerWidth, H = innerHeight, out = {fuori: [], piccoli: [], contrasto: [], sovrapposti: [], vuoti: []};
 const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(',').map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
 const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
 const sfondo = el => { for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e); if (s.backgroundImage !== 'none') return null; const c = parse(s.backgroundColor); if (c && c.a > 0.95) return c; } return {r: 255, g: 255, b: 255, a: 1}; };
 const els = [...document.querySelectorAll('body *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
 const rr = [];
 for (const e of els) {
  const r = e.getBoundingClientRect(), s = getComputedStyle(e), t = e.textContent.trim().replace(/\\s+/g, ' ').slice(0, 40), fs = parseFloat(s.fontSize);
  if (r.width === 0 || r.height === 0 || s.visibility === 'hidden' || s.display === 'none') continue;
  if (r.left < -1 || r.top < -1 || r.right > W + 1 || r.bottom > H + 1) out.fuori.push('«' + t + '» esce dalla pagina');
  if ((e.scrollWidth > e.clientWidth + 2 || e.scrollHeight > e.clientHeight + 2) && s.overflow !== 'visible') out.fuori.push('«' + t + '» risulta tagliato');
  if (fs < W * 0.016) out.piccoli.push('«' + t + '» ' + Math.round(fs) + 'px');
  const b = sfondo(e), f = parse(s.color);
  if (b && f) { const l1 = lum(f), l2 = lum(b), cr = (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05); if (cr < (fs >= W * 0.03 ? 3 : 4.5)) out.contrasto.push('«' + t + '» ' + cr.toFixed(1) + ':1'); }
  rr.push({t, r, e});
 }
 for (let i = 0; i < rr.length; i++) for (let j = i + 1; j < rr.length; j++) {
  const a = rr[i], b = rr[j]; if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
  const x = Math.max(0, Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left)), y = Math.max(0, Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top));
  const min = Math.min(a.r.width * a.r.height, b.r.width * b.r.height); if (min > 0 && x * y > 0.2 * min) out.sovrapposti.push('«' + a.t + '» si sovrappone a «' + b.t + '»');
 }
 const iv = [...document.querySelectorAll('body *')].map(e => e.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0 && r.height < H * 0.9).map(r => [r.top, r.bottom]).sort((a, b) => a[0] - b[0]);
 let ini = H, fine = 0; for (const [a, b] of iv) { if (a < ini) ini = a; if (b > fine) fine = b; }
 if (iv.length && fine - ini < H * 0.55) out.vuoti.push('il contenuto occupa solo il ' + Math.round(100 * (fine - ini) / H) + '% dell altezza: pagina sbilanciata o vuota');
 return out;
}"""

_MODELLO_CONTROLLI = ("fuori", "piccoli", "contrasto", "sovrapposti", "vuoti")


def controlli(html: str, larghezza: int, altezza: int) -> list[str]:
    """Controlli oggettivi sull'impaginazione: testi fuori pagina o tagliati, troppo piccoli, poco contrasto, sovrapposti, grandi vuoti."""
    from playwright.sync_api import sync_playwright
    senza_script = re.sub(r"<script\b.*?</script>", "", html, flags=re.I | re.S)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        try:
            ctx = br.new_context(viewport={"width": larghezza, "height": altezza})
            ctx.route("**/*", lambda route: route.continue_() if route.request.url.startswith(("data:", "about:")) or re.sub(r"^https?://([^/:]+).*$", r"\1", route.request.url) in HOST_FONT else route.abort())
            pg = ctx.new_page()
            pg.set_content(senza_script, wait_until="load")
            r = pg.evaluate(_JS_CONTROLLI)
        finally:
            br.close()
    etichette = {"fuori": "TESTO FUORI PAGINA O TAGLIATO", "piccoli": "TESTO TROPPO PICCOLO (illeggibile in stampa/su telefono)", "contrasto": "CONTRASTO INSUFFICIENTE",
                 "sovrapposti": "ELEMENTI SOVRAPPOSTI", "vuoti": "SPAZIO MAL DISTRIBUITO"}
    out = []
    for k in _MODELLO_CONTROLLI:
        v = list(dict.fromkeys(r.get(k) or []))[:5]
        if v:
            out.append(etichette[k] + ": " + "; ".join(v))
    return out


ISTRUZIONE_CRITICA = ("Sei un art director severo (editoria, cultura, comunicazione visiva). Guardi una grafica realizzata da un agente e dici la verita', senza compiacere. "
                      "Valuta: gerarchia (un solo punto focale evidente), impaginazione e margini, ritmo e spazio bianco, uso di colore e carattere (massimo 2 caratteri e 3 colori coerenti), "
                      "leggibilita', rispetto del brief e dello stile di riferimento, aspetto professionale (non da modulo ne' da presentazione scolastica). "
                      "Rispondi in italiano: riga 1 'VOTO n/10 - OK' oppure 'VOTO n/10 - DA RIFARE' (OK solo da 8 in su); poi massimo 6 difetti concreti, ciascuno con la correzione precisa "
                      "(es. 'titolo troppo piccolo: portalo a 9% della larghezza', 'rimuovi le card con bordo, usa una colonna unica'). Se e' bella dillo e indica solo le rifiniture.")


def critica(png: bytes, brief: str, riservata: bool = False) -> str:
    """Giudizio visivo dell'art director. La grafica e' materiale destinato alla pubblicazione: fascia 'pubblico' salvo diversa indicazione."""
    from . import visione
    try:
        return visione.chiedi([("image/png", png)], ISTRUZIONE_CRITICA, "Brief: " + (brief or "(non indicato)")[:1200] + "\nGiudica la grafica.",
                              "interno" if riservata else "pubblico", "", 800)
    except visione.VisioneNonDisponibile as e:
        return "NON HO POTUTO GUARDARLA: " + str(e)
    except Exception as e:  # noqa: BLE001
        return f"NON HO POTUTO GUARDARLA: errore del lettore di immagini ({type(e).__name__})"
