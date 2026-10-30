"""Sfondo con un'opera d'arte da Wikimedia Commons, diversa ogni 10 minuti.

Il server sceglie l'opera (la stessa per tutti nello stesso intervallo di 10 minuti), la scarica, la tiene nel database e la serve all'app. Se Commons non risponde resta l'ultima opera gia' scaricata;
se non ce n'e' nessuna l'app usa le scene disegnate. Autore e licenza si vedono sempre accanto all'opera."""
import html
import random
import re
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from .db import connessione
from .permessi import utente_corrente

router = APIRouter(prefix="/sfondo-arte", tags=["sfondo"])

DURATA = 600   # secondi: un'opera ogni 10 minuti
API = "https://commons.wikimedia.org/w/api.php"
UA = "Opifex/1 (https://github.com/Loxeze/Opifex; sfondo con opere d'arte di pubblico dominio) httpx"
# categorie di dipinti di autori noti, dove Commons ha molte riproduzioni di pubblico dominio
ARTISTI = ["Claude Monet", "Vincent van Gogh", "Johannes Vermeer", "Sandro Botticelli", "Caspar David Friedrich", "Camille Pissarro", "Paul Cézanne",
             "Pierre-Auguste Renoir", "Edgar Degas", "Gustav Klimt", "Rembrandt", "Titian", "Ivan Aivazovsky", "Albert Bierstadt", "John Constable",
             "Claude Lorrain", "Giovanni Segantini", "Édouard Manet", "Alfred Sisley", "Gustave Courbet", "Francesco Guardi", "Katsushika Hokusai",
             "Giorgione", "Paul Gauguin", "Thomas Cole", "Georges Seurat"]
CATEGORIE = ["Paintings by " + a for a in ARTISTI]
LICENZE_OK = re.compile(r"public domain|\bpd\b|cc0|cc[- ]by|no restrictions", re.I)
MAX_BYTE = 6_000_000
_elenchi: dict[str, tuple[float, list[str]]] = {}
_blocco = threading.Lock()
_ultimo_errore = [0.0]


class ErroreArte(Exception):
    pass


def slot_di(ora: float | None = None) -> int:
    return int((time.time() if ora is None else ora) // DURATA)


def _api(parametri: dict) -> dict:
    """Una richiesta all'API di Commons (sostituibile nei collaudi)."""
    try:
        r = httpx.get(API, params={**parametri, "format": "json"}, headers={"User-Agent": UA}, timeout=20)
    except httpx.HTTPError as e:
        raise ErroreArte(f"Commons non raggiungibile ({type(e).__name__})") from None
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/json"):
        raise ErroreArte(f"Commons ha risposto {r.status_code}")
    return r.json()


def _scarica(url: str) -> tuple[bytes, str]:
    if not url.startswith("https://upload.wikimedia.org/") and not url.startswith("https://thumb.wikimedia.org/"):
        raise ErroreArte("Indirizzo non ammesso")
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=40, follow_redirects=False)
    except httpx.HTTPError as e:
        raise ErroreArte(f"Download non riuscito ({type(e).__name__})") from None
    mime = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if r.status_code != 200 or mime not in ("image/jpeg", "image/png") or len(r.content) > MAX_BYTE:
        raise ErroreArte("Immagine non utilizzabile")
    return r.content, mime


def _file_di(categoria: str, profondita: int = 2) -> list[str]:
    """Titoli dei file di una categoria e, a due livelli, delle sue sottocategorie (elenco tenuto in memoria per un giorno)."""
    ora = time.time()
    if categoria in _elenchi and ora - _elenchi[categoria][0] < 86400:
        return _elenchi[categoria][1]
    titoli: list[str] = []
    sotto: list[str] = []
    cont: dict = {}
    for _ in range(3):
        d = _api({"action": "query", "list": "categorymembers", "cmtitle": "Category:" + categoria if not categoria.startswith("Category:") else categoria,
                  "cmtype": "file|subcat", "cmlimit": "500", **cont})
        for m in d.get("query", {}).get("categorymembers", []):
            if m.get("ns") == 6 and re.search(r"\.(jpe?g|png)$", m["title"], re.I):
                titoli.append(m["title"])
            elif m.get("ns") == 14:
                sotto.append(m["title"])
        if "continue" not in d:
            break
        cont = d["continue"]
    if profondita > 1 and sotto:
        random.Random(len(sotto)).shuffle(sotto)
        for s in sotto[:8]:
            try:
                titoli += _file_di(s, profondita - 1)
            except ErroreArte:
                continue
    _elenchi[categoria] = (ora, titoli)
    return titoli


def _pulisci(testo: str, massimo: int = 140) -> str:
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", testo or ""))).strip()
    return t[:massimo]


def _scheda(titolo_file: str) -> dict | None:
    d = _api({"action": "query", "titles": titolo_file, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1920",
              "iiextmetadatafilter": "LicenseShortName|Artist|ObjectName"})
    for p in (d.get("query", {}).get("pages") or {}).values():
        ii = (p.get("imageinfo") or [None])[0]
        if not ii:
            continue
        w, hh = ii.get("width") or 0, ii.get("height") or 0
        if w < 1400 or hh <= 0 or w / hh < 1.25 or ii.get("mime") not in ("image/jpeg", "image/png"):
            return None
        meta = ii.get("extmetadata") or {}
        lic = _pulisci((meta.get("LicenseShortName") or {}).get("value", ""), 60)
        if not LICENZE_OK.search(lic):
            return None
        nome = _pulisci((meta.get("ObjectName") or {}).get("value", "")) or re.sub(r"^File:|\.\w+$", "", titolo_file)
        return {"url": ii.get("thumburl") or ii.get("url"), "titolo": nome, "autore": _pulisci((meta.get("Artist") or {}).get("value", ""), 80),
                "licenza": lic, "pagina": ii.get("descriptionurl") or ""}
    return None


def prepara(slot: int) -> bool:
    """Sceglie l'opera dell'intervallo e la salva. Vero se c'e' (gia' o ora); falso se non si e' riusciti."""
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM sfondi_arte WHERE slot=%s", (slot,)).fetchone():
            return True
    rng = random.Random(slot * 7919)
    for _ in range(8):
        try:
            titoli = _file_di(rng.choice(CATEGORIE))
            if not titoli:
                continue
            s = _scheda(rng.choice(titoli))
            if not s or not s["url"]:
                continue
            dati, mime = _scarica(s["url"])
        except ErroreArte:
            continue
        with connessione() as conn:
            conn.execute("""INSERT INTO sfondi_arte (slot, titolo, autore, licenza, pagina, mime, immagine) VALUES (%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (slot) DO NOTHING""", (slot, s["titolo"], s["autore"], s["licenza"], s["pagina"], mime, dati))
            conn.execute("DELETE FROM sfondi_arte WHERE slot NOT IN (SELECT slot FROM sfondi_arte ORDER BY slot DESC LIMIT 8)")
        return True
    return False


SINCRONO = False   # nei collaudi si prepara nello stesso thread


def _in_secondo_piano(slot: int):
    """Una sola preparazione alla volta; dopo un insuccesso si aspettano due minuti prima di riprovare."""
    def lavoro():
        if not _blocco.acquire(blocking=False):
            return
        try:
            if time.time() - _ultimo_errore[0] < 120:
                return
            try:
                if not prepara(slot):
                    _ultimo_errore[0] = time.time()
            except Exception:  # noqa: BLE001 - lo sfondo non deve mai disturbare il resto
                _ultimo_errore[0] = time.time()
        finally:
            _blocco.release()
    if SINCRONO:
        lavoro()
    else:
        threading.Thread(target=lavoro, daemon=True).start()


@router.get("/corrente")
def corrente(_: dict = Depends(utente_corrente)):
    slot = slot_di()
    with connessione() as conn:
        r = conn.execute("SELECT slot, titolo, autore, licenza, pagina FROM sfondi_arte WHERE slot=%s", (slot,)).fetchone()
        if r is None:
            _in_secondo_piano(slot)
            if SINCRONO:
                r = conn.execute("SELECT slot, titolo, autore, licenza, pagina FROM sfondi_arte WHERE slot=%s", (slot,)).fetchone()
            if r is None:
                r = conn.execute("SELECT slot, titolo, autore, licenza, pagina FROM sfondi_arte ORDER BY slot DESC LIMIT 1").fetchone()
    resto = DURATA - int(time.time() % DURATA)
    if r is None:
        return {"disponibile": False, "riprova_tra": 30}
    return {"disponibile": True, "slot": r["slot"], "titolo": r["titolo"], "autore": r["autore"], "licenza": r["licenza"], "pagina": r["pagina"],
            "aggiornata": r["slot"] == slot, "cambia_tra": resto if r["slot"] == slot else 20}


@router.get("/immagine/{slot}")
def immagine(slot: int, _: dict = Depends(utente_corrente)):
    with connessione() as conn:
        r = conn.execute("SELECT mime, immagine FROM sfondi_arte WHERE slot=%s", (slot,)).fetchone()
    if r is None:
        raise HTTPException(404, "Opera non disponibile")
    return Response(content=bytes(r["immagine"]), media_type=r["mime"], headers={"Cache-Control": "private, max-age=86400"})
