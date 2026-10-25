"""App installabile (QR code) e notifiche push sui dispositivi."""
import segno
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import registro, webpush
from .db import connessione
from .permessi import solo_titolare, utente_corrente

router = APIRouter(tags=["pwa"])


def _url_app(conn, richiesta: Request) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'app_url'").fetchone()
    if r and r["valore"]:
        return r["valore"].rstrip("/") + "/app/"
    proto = richiesta.headers.get("x-forwarded-proto") or richiesta.url.scheme
    host = richiesta.headers.get("x-forwarded-host") or richiesta.headers.get("host") or richiesta.url.netloc
    return f"{proto}://{host}/app/"


@router.get("/gestione/app/invito")
def invito(richiesta: Request, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        url = _url_app(conn, richiesta)
        personalizzato = bool(conn.execute("SELECT 1 FROM impostazioni_sistema WHERE chiave = 'app_url' AND valore <> ''").fetchone())
    qr = segno.make(url, error="m")
    return {"url": url, "personalizzato": personalizzato, "svg": qr.svg_inline(scale=7, border=2, dark="#1a1318", light="#ffffff", omitsize=True)}


class UrlApp(BaseModel):
    url: str = Field(default="", max_length=200)


@router.put("/gestione/app/url")
def imposta_url(d: UrlApp, u: dict = Depends(solo_titolare)):
    url = d.url.strip().rstrip("/")
    if url and not (url.startswith("https://") and " " not in url and "." in url):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indirizzo non valido: deve iniziare con https://")
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('app_url', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (url,))
        registro.registra(conn, u, "organizzazione", "indirizzo dell'app impostato", url or "(automatico)")
    return {"ok": True}


@router.get("/pwa/chiave")
def chiave(_: dict = Depends(utente_corrente)):
    with connessione() as conn:
        return {"chiave": webpush.chiavi(conn)[1]}


class Iscrizione(BaseModel):
    endpoint: str = Field(max_length=1000)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)
    dispositivo: str | None = Field(default=None, max_length=120)


@router.post("/pwa/iscrivi", status_code=201)
def iscrivi(d: Iscrizione, u: dict = Depends(utente_corrente)):
    if not webpush.endpoint_valido(d.endpoint):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Servizio di notifiche non riconosciuto")
    try:
        if len(webpush.b64u_dec(d.p256dh)) != 65 or len(webpush.b64u_dec(d.auth)) < 8:
            raise ValueError
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chiavi del dispositivo non valide") from None
    with connessione() as conn:
        conn.execute("""INSERT INTO push_iscrizioni (utente_id, endpoint, p256dh, auth, dispositivo) VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (endpoint) DO UPDATE SET utente_id = EXCLUDED.utente_id, p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth, dispositivo = EXCLUDED.dispositivo""",
                     (u["id"], d.endpoint, d.p256dh, d.auth, (d.dispositivo or "").strip() or None))
    return {"ok": True}


class Fine(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.post("/pwa/disiscrivi")
def disiscrivi(d: Fine, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        conn.execute("DELETE FROM push_iscrizioni WHERE endpoint = %s AND utente_id = %s", (d.endpoint, u["id"]))
    return {"ok": True}


@router.get("/pwa/dispositivi")
def dispositivi(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        return {"dispositivi": conn.execute("SELECT id, dispositivo, endpoint, creata_il FROM push_iscrizioni WHERE utente_id = %s ORDER BY id", (u["id"],)).fetchall()}


@router.post("/pwa/prova")
def prova(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        n = webpush.a_tutti(conn, "Opifex", "Le notifiche funzionano su questo dispositivo.", u["id"])
    return {"raggiunti": n}
