"""Sintesi vocale con ElevenLabs: legge briefing e risposte ad alta voce. Il testo esce verso ElevenLabs solo se Lorenzo ha dichiarato le garanzie
(come per gli altri fornitori); i testi pubblici non le richiedono. Limiti di lunghezza e di richieste all'ora per non consumare crediti."""
import httpx

from . import cassaforte
from .db import connessione

MAX_CARATTERI = 4500
MAX_ORA = 150
MODELLO = "eleven_multilingual_v2"


class ErroreVoce(Exception):
    def __init__(self, messaggio: str, codice: int = 409):
        super().__init__(messaggio)
        self.codice = codice


def _imp(conn, chiave: str, default: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return (r["valore"] if r else default) or default


def _set(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, valore))


def configurazione(conn) -> dict:
    return {"chiave": bool(_imp(conn, "chiave_elevenlabs_cifrata")), "voce_id": _imp(conn, "elevenlabs_voce_id"),
            "garanzie": _imp(conn, "elevenlabs_garanzie", "0") == "1", "telegram_voce": _imp(conn, "elevenlabs_telegram_voce", "0") == "1"}


def salva(conn, chiave: str | None, voce_id: str | None, garanzie: bool, telegram_voce: bool):
    if chiave:
        _set(conn, "chiave_elevenlabs_cifrata", cassaforte.cifra(chiave.strip()))
    _set(conn, "elevenlabs_voce_id", (voce_id or "").strip()[:60])
    _set(conn, "elevenlabs_garanzie", "1" if garanzie else "0")
    _set(conn, "elevenlabs_telegram_voce", "1" if telegram_voce else "0")


def rimuovi_chiave(conn):
    conn.execute("DELETE FROM impostazioni_sistema WHERE chiave = 'chiave_elevenlabs_cifrata'")


def _chiave(conn) -> str:
    c = _imp(conn, "chiave_elevenlabs_cifrata")
    if not c:
        raise ErroreVoce("ElevenLabs non e' collegato: inserisci la chiave in Impostazioni → Voce")
    return cassaforte.decifra(c)


def voci(conn) -> list[dict]:
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": _chiave(conn)}, timeout=20)
    except httpx.HTTPError as e:
        raise ErroreVoce(f"ElevenLabs non raggiungibile ({type(e).__name__})", 502) from None
    if r.status_code != 200:
        raise ErroreVoce("ElevenLabs ha rifiutato la chiave" if r.status_code in (401, 403) else f"ElevenLabs ha risposto {r.status_code}", 502 if r.status_code >= 500 else 409)
    return [{"id": v["voice_id"], "nome": v.get("name", "?")} for v in r.json().get("voices", [])][:60]


def sintetizza(testo: str, fascia: str = "interno", utente_id: int | None = None, voce_id: str | None = None) -> bytes:
    testo = (testo or "").strip()
    if not testo:
        raise ErroreVoce("Niente da leggere", 422)
    if len(testo) > MAX_CARATTERI:
        raise ErroreVoce(f"Testo troppo lungo per la lettura ({len(testo)} caratteri, massimo {MAX_CARATTERI})", 413)
    with connessione() as conn:
        c = configurazione(conn)
        if fascia != "pubblico" and not c["garanzie"]:
            raise ErroreVoce("Per far leggere testi interni ad ElevenLabs devi prima dichiarare le garanzie (non conservazione e DPA) in Impostazioni → Voce")
        voce_id = (voce_id or "").strip() or c["voce_id"]
        if not voce_id:
            raise ErroreVoce("Scegli una voce in Impostazioni → Voce")
        recenti = conn.execute("SELECT count(*) AS n FROM registro_azioni WHERE azione = 'voce_sintetizzata' AND creata_il >= NOW() - interval '1 hour'").fetchone()["n"]
        if recenti >= MAX_ORA:
            raise ErroreVoce("Troppe letture in un'ora: riprova piu' tardi", 429)
        chiave = _chiave(conn)
    try:
        r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voce_id}", params={"output_format": "mp3_44100_64"},
                       headers={"xi-api-key": chiave, "content-type": "application/json"}, json={"text": testo, "model_id": MODELLO}, timeout=90)
    except httpx.HTTPError as e:
        raise ErroreVoce(f"ElevenLabs non raggiungibile ({type(e).__name__})", 502) from None
    if r.status_code != 200:
        raise ErroreVoce("ElevenLabs ha rifiutato la richiesta (chiave, voce o crediti)" if r.status_code in (400, 401, 402, 403, 404, 422) else f"ElevenLabs ha risposto {r.status_code}", 502)
    with connessione() as conn:
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('voce_sintetizzata', %s::jsonb, %s)", ('{"caratteri": %d}' % len(testo), utente_id))
    return r.content
