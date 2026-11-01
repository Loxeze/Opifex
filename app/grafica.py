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
