"""Catalogo dei modelli AI: importa l'elenco completo dai fornitori (Anthropic, OpenAI, xAI), classifica il livello e sceglie
il modello piu' economico per i dialoghi di ogni agente, nel rispetto di riservatezza e ricerca web."""
import re

import httpx

from . import fornitori
from .riservatezza import puo_uscire

NOMI = ("anthropic", "openai", "xai")
_URL = {"anthropic": "https://api.anthropic.com/v1/models?limit=1000", "openai": "https://api.openai.com/v1/models", "xai": "https://api.x.ai/v1/models"}
_ESCLUDI = re.compile(r"embed|whisper|tts|dall-e|moderation|audio|realtime|transcribe|image|imagine|video|sora|search|instruct|davinci|babbage|computer-use|vision|speech|live", re.I)
_DATATO = re.compile(r"(-\d{4}-\d{2}-\d{2}|-\d{8}|-\d{4}|-latest)$")
_ECONOMICO = re.compile(r"haiku|mini|nano|flash|lite|small|fast", re.I)
_AVANZATO = re.compile(r"opus|mythos|fable|-pro\b|^o1$|^o3$|^o1-|^o3-|heavy|ultra|^grok-4$", re.I)


class ErroreCatalogo(Exception):
    pass


def fascia_di(nome: str) -> str:
    if _ECONOMICO.search(nome):
        return "economico"
    if _AVANZATO.search(nome):
        return "avanzato"
    return "standard"


def _ammesso(fornitore: str, nome: str) -> bool:
    if _ESCLUDI.search(nome) or _DATATO.search(nome):
        return False
    if fornitore == "anthropic":
        return nome.startswith("claude")
    if fornitore == "openai":
        return bool(re.match(r"^(gpt-|chatgpt-|o\d)", nome))
    if fornitore == "xai":
        return nome.startswith("grok")
    return False


def elenca(fornitore: str) -> list[str]:
    k = fornitori.chiave(fornitore)
    if not k:
        raise ErroreCatalogo("chiave mancante")
    h = {"x-api-key": k, "anthropic-version": "2023-06-01"} if fornitore == "anthropic" else {"Authorization": "Bearer " + k}
    try:
        r = httpx.get(_URL[fornitore], headers=h, timeout=30)
    except httpx.HTTPError as e:
        raise ErroreCatalogo(f"non raggiungibile ({type(e).__name__})") from None
    if r.status_code >= 400:
        raise ErroreCatalogo(f"risposta {r.status_code}")
    try:
        ids = [x["id"] for x in r.json().get("data", []) if isinstance(x, dict) and x.get("id")]
    except ValueError:
        raise ErroreCatalogo("risposta non valida") from None
    return sorted({i for i in ids if _ammesso(fornitore, i)})


def importa(conn) -> dict:
    """Aggiunge i modelli mancanti (senza prezzo, livello stimato dal nome). Non tocca quelli gia' registrati."""
    esito: dict = {}
    for n in NOMI:
        try:
            nomi = elenca(n)
        except ErroreCatalogo as e:
            esito[n] = {"errore": str(e), "nuovi": 0, "totale": 0}
            continue
        f = conn.execute("SELECT id FROM fornitori_ai WHERE nome = %s", (n,)).fetchone()
        if f is None:
            esito[n] = {"errore": "fornitore sconosciuto", "nuovi": 0, "totale": 0}
            continue
        nuovi = 0
        for nome in nomi:
            if conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (nome,)).fetchone():
                continue
            conn.execute("INSERT INTO modelli_ai (fornitore_id, nome, fascia, importato) VALUES (%s,%s,%s,TRUE)", (f["id"], nome, fascia_di(nome)))
            nuovi += 1
        esito[n] = {"nuovi": nuovi, "totale": len(nomi)}
    return esito


def _impostazione(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return r["valore"] if r and r["valore"] != "" else d


def automatico(conn) -> bool:
    return _impostazione(conn, "dialoghi_modello_automatico", "true") == "true"


def scegli_per_dialogo(conn, agente: dict) -> str | None:
    """Nome del modello piu' economico utilizzabile da questo agente per parlare, o None se non c'e' nulla di adatto.
    agente: fascia_dati_max, accesso_web. Un fornitore e' adatto se ha la chiave e puo' ricevere i dati che l'agente puo' trattare;
    con la ricerca web restano i soli modelli Anthropic (gli altri non la fanno)."""
    righe = conn.execute(
        """SELECT m.nome, m.fascia, m.costo_input_per_milione AS ci, m.costo_output_per_milione AS co, f.nome AS fornitore,
                  f.fascia_dati_max AS ff, f.non_conservazione_attiva AS nc, f.dpa_firmato AS dpa
           FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE m.usa_per_dialoghi""").fetchall()
    chiavi: dict = {}
    cand = []
    for r in righe:
        if agente.get("accesso_web") and r["fornitore"] != "anthropic":
            continue
        if r["fornitore"] not in chiavi:
            chiavi[r["fornitore"]] = bool(fornitori.chiave(r["fornitore"]))
        if not chiavi[r["fornitore"]]:
            continue
        if not puo_uscire(agente["fascia_dati_max"], agente["fascia_dati_max"], r["ff"], r["nc"], r["dpa"])[0]:
            continue
        cand.append(r)
    if not cand:
        return None
    eco = [r for r in cand if r["fascia"] == "economico"] or cand

    def chiave(r):
        noto = r["ci"] is not None and r["co"] is not None
        return (0 if noto else 1, float(r["ci"] or 0) + float(r["co"] or 0), 0 if r["fornitore"] == "anthropic" else 1, r["nome"])
    return sorted(eco, key=chiave)[0]["nome"]


def piano(conn) -> list[dict]:
    """Quale modello userebbe ogni agente per i dialoghi, ora."""
    out = []
    for a in conn.execute("SELECT id, nome, fascia_dati_max, accesso_web, modello_dialogo FROM agenti WHERE attivo ORDER BY nome").fetchall():
        scelto = a["modello_dialogo"] or (scegli_per_dialogo(conn, a) if automatico(conn) else None)
        out.append({"id": a["id"], "nome": a["nome"], "modello": scelto, "esplicito": bool(a["modello_dialogo"])})
    return out
