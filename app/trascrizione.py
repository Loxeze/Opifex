"""Trascrizione vocale con Whisper (OpenAI), condivisa da chat web e Telegram. L'audio esce dal server solo se la riservatezza lo consente."""
import httpx

from . import fornitori
from .db import connessione
from .riservatezza import puo_uscire

MAX_BYTE = 10 * 1024 * 1024
FORMATI = {"webm", "ogg", "oga", "opus", "mp4", "m4a", "wav", "mp3", "mpeg", "mpga"}
MAX_ORA = 60
MODELLI = ("gpt-4o-transcribe", "whisper-1")   # il primo e' piu' preciso; se non risponde si ripiega sul secondo
PAROLE_FISSE = ("Opifex", "Renovatio", "Logos", "Evidens", "Aquilia", "FARO", "Montarrenti", "Simposia", "Sovicille", "Masone", "Ginnasio", "Padre Casati", "Buffer", "Canva", "NAS", "CRM", "Drive", "Interreg", "PNRR", "europrogettazione")


def vocabolario(conn) -> str:
    """Nomi propri che i modelli di trascrizione storpiano (agenti, progetti, reparti): aiutano a scriverli giusti."""
    nomi = list(PAROLE_FISSE)
    try:
        for q in ("SELECT nome FROM agenti WHERE attivo ORDER BY id LIMIT 60", "SELECT nome FROM progetti WHERE NOT archiviato ORDER BY id DESC LIMIT 40", "SELECT nome FROM divisioni ORDER BY id LIMIT 20"):
            nomi += [r["nome"] for r in conn.execute(q).fetchall() if r["nome"]]
    except Exception:  # noqa: BLE001
        pass
    visti, out, n = set(), [], 0
    for x in nomi:
        k = x.strip().lower()
        if k and k not in visti and n + len(x) < 700:
            visti.add(k); out.append(x.strip()); n += len(x) + 2
    return "Dettatura in italiano. Nomi e termini che possono comparire: " + ", ".join(out) + "."


class ErroreTrascrizione(Exception):
    def __init__(self, messaggio: str, codice: int = 409):
        super().__init__(messaggio)
        self.codice = codice


def trascrivi(dati: bytes, estensione: str, fascia_dati: str, utente_id: int | None, tipo_contenuto: str = "application/octet-stream", limite_ora: int = MAX_ORA) -> str:
    estensione = estensione.lower()
    if estensione not in FORMATI:
        raise ErroreTrascrizione("Formato audio non supportato", 422)
    if len(dati) > MAX_BYTE:
        raise ErroreTrascrizione("Registrazione troppo lunga", 413)
    if len(dati) < 1000:
        raise ErroreTrascrizione("Registrazione vuota", 422)
    ext_whisper = "ogg" if estensione in ("oga", "opus") else estensione
    with connessione() as conn:
        f = conn.execute("SELECT fascia_dati_max, non_conservazione_attiva, dpa_firmato FROM fornitori_ai WHERE nome = 'openai'").fetchone()
        ok, motivo = puo_uscire(fascia_dati, "riservato", f["fascia_dati_max"], f["non_conservazione_attiva"], f["dpa_firmato"])
        if not ok:
            raise ErroreTrascrizione("Trascrizione sul server non consentita per questo tipo di dati: " + str(motivo) +
                                     ". Dichiara le garanzie di OpenAI in Sicurezza e garanzie" + (" (o usa la dettatura del browser)." if utente_id else "."), 409)
        recenti = conn.execute("SELECT count(*) AS n FROM registro_azioni WHERE azione='voce_trascritta' AND utente_id IS NOT DISTINCT FROM %s AND creata_il >= NOW() - interval '1 hour'",
                               (utente_id,)).fetchone()["n"]
        if recenti >= limite_ora:
            raise ErroreTrascrizione("Troppe trascrizioni in un'ora: riprova piu' tardi", 429)
    chiave = fornitori.chiave("openai")
    if not chiave:
        raise ErroreTrascrizione("Chiave OpenAI non configurata: inseriscila in Impostazioni → Sicurezza e garanzie", 409)
    with connessione() as conn:
        guida = vocabolario(conn)
    r = None
    for modello in MODELLI:
        dati_ = {"model": modello, "language": "it", "response_format": "json", "prompt": guida}
        if modello == "whisper-1":
            dati_["temperature"] = "0"
        try:
            r = httpx.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": "Bearer " + chiave}, data=dati_,
                           files={"file": ("voce." + ext_whisper, dati, tipo_contenuto)}, timeout=60)
        except httpx.HTTPError as e:
            if modello == MODELLI[-1]:
                raise ErroreTrascrizione(f"OpenAI non raggiungibile ({type(e).__name__})", 502) from None
            continue
        if r.status_code == 200 or r.status_code in (401, 429):
            break
    if r.status_code != 200:
        raise ErroreTrascrizione(f"OpenAI ha risposto {r.status_code}", 502)
    testo = (r.json().get("text") or "").strip()
    with connessione() as conn:
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('voce_trascritta', %s::jsonb, %s)", ('{"byte": %d}' % len(dati), utente_id))
    if not testo or "Nomi e termini che possono comparire" in testo:   # su audio vuoto alcuni modelli restituiscono la guida
        raise ErroreTrascrizione("Non ho capito nulla nella registrazione: riprova parlando piu' vicino al microfono", 422)
    return testo
