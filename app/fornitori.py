"""Connettore unico verso i fornitori AI (Anthropic/Claude, OpenAI/GPT, xAI/Grok).

Gli agenti non parlano mai direttamente con un fornitore: passano da qui.
Le chiavi API stanno nel file .env del server oppure, se inserite dall'app, cifrate nella cassaforte: mai in chiaro e mai su Drive.
Si usa HTTP diretto (httpx), senza librerie specifiche dei fornitori, cosi' le dipendenze restano poche.
"""
from dataclasses import dataclass, field

import time

import httpx

from .config import impostazioni


def chiave(fornitore: str) -> str:
    """Chiave del fornitore: prima quella salvata cifrata nell'app (Impostazioni), altrimenti quella del .env del server."""
    try:
        from . import cassaforte
        from .db import connessione
        with connessione() as conn:
            r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (f"chiave_{fornitore}_cifrata",)).fetchone()
        if r and r["valore"]:
            return cassaforte.decifra(r["valore"])
    except Exception:  # noqa: BLE001 - se la cassaforte o il database non rispondono si ricade sul .env
        pass
    return getattr(impostazioni, f"chiave_{fornitore}", "") or ""


@dataclass
class Risposta:
    testo: str
    token_input: int
    token_output: int
    diag: dict = field(default_factory=dict)   # passi, stop_reason, ritentativo: per capire perche' una risposta e' vuota


class ErroreFornitore(Exception):
    pass


PAUSE_RIPROVA = (2, 6, 15)          # secondi tra un tentativo e l'altro
CODICI_TRANSITORI = {408, 409, 425, 429, 500, 502, 503, 504, 529}   # sovraccarico o guasto momentaneo del fornitore


import contextvars
MODELLO_FORZATO = contextvars.ContextVar("modello_forzato", default=None)   # nome del modello da usare al posto di quello dell'agente (riunioni: massima qualita')
SFORZO_FORZATO = contextvars.ContextVar("sforzo_forzato", default=None)
SFORZO = contextvars.ContextVar("sforzo_agente", default=None)   # 'low' | 'medium' | 'high': sforzo di ragionamento dell'agente in esecuzione (solo modelli Anthropic)


def invia(url: str, intestazioni: dict, corpo: dict, timeout: int = 180):
    """POST al fornitore con nuovi tentativi per gli errori momentanei (sovraccarico, limite di richieste, rete lenta).
    Senza questo un singolo 529 o un timeout fermava l'agente. Gli errori definitivi (chiave, richiesta sbagliata) passano subito."""
    ultimo = ""
    sforzo = SFORZO.get()
    if sforzo and "api.anthropic.com/v1/messages" in url and "output_config" not in corpo:
        corpo = {**corpo, "output_config": {"effort": sforzo}}
    for n in range(len(PAUSE_RIPROVA) + 1):
        try:
            r = httpx.post(url, headers=intestazioni, json=corpo, timeout=timeout)
            if r.status_code == 400 and "output_config" in corpo and "output_config" in r.text:
                corpo = {k: v for k, v in corpo.items() if k != "output_config"}   # modello senza sforzo: si riprova senza
                r = httpx.post(url, headers=intestazioni, json=corpo, timeout=timeout)
        except httpx.HTTPError as e:   # timeout, rete interrotta, DNS
            ultimo = type(e).__name__
            r = None
        if r is not None and r.status_code not in CODICI_TRANSITORI:
            return r
        if r is not None:
            ultimo = f"{r.status_code} {r.text[:120]}"
            if n < len(PAUSE_RIPROVA):
                try:
                    attesa = min(float(r.headers.get("retry-after", 0)), 30)
                except ValueError:
                    attesa = 0
            else:
                attesa = 0
        else:
            attesa = 0
        if n < len(PAUSE_RIPROVA):
            time.sleep(max(attesa, PAUSE_RIPROVA[n]))
        elif r is not None:
            return r      # ultimo tentativo fallito: ci pensa il chiamante a segnalare l'errore col suo messaggio
    raise ErroreFornitore(f"Il fornitore non risponde ({ultimo}); riprovati {len(PAUSE_RIPROVA) + 1} tentativi")



def _chiama_anthropic(modello: str, istruzioni: str, messaggio: str, max_token: int,
                      web: dict | None = None) -> Risposta:
    k = chiave("anthropic")
    if not k:
        raise ErroreFornitore("Chiave Anthropic non configurata")
    corpo = {
        "model": modello,
        "max_tokens": max_token,
        "system": istruzioni,
        "messages": [{"role": "user", "content": messaggio}],
    }
    if web:
        # Ricerca web gestita da Anthropic; se ci sono siti consentiti, la ricerca resta dentro quelli
        strumento = {"type": "web_search_20250305", "name": "web_search", "max_uses": web.get("max_ricerche", 3)}
        if web.get("siti"):
            strumento["allowed_domains"] = web["siti"]
        corpo["tools"] = [strumento]
    r = invia("https://api.anthropic.com/v1/messages",
              {"x-api-key": k, "anthropic-version": "2023-06-01", "content-type": "application/json"}, corpo, 180)
    if r.status_code != 200:
        raise ErroreFornitore(f"Anthropic: {r.status_code} {r.text[:200]}")
    d = r.json()
    testo = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    t_in, t_out, giri = d["usage"]["input_tokens"], d["usage"]["output_tokens"], 0
    while d.get("stop_reason") == "max_tokens" and testo.strip() and not web and giri < 2:
        # risposta tagliata dal limite: si fa continuare dallo stesso punto e si ricuce il testo
        giri += 1
        r = invia("https://api.anthropic.com/v1/messages", {"x-api-key": k, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                  {**corpo, "messages": corpo["messages"] + [{"role": "assistant", "content": testo.rstrip()},
                                                             {"role": "user", "content": "La tua risposta e' stata interrotta dal limite di lunghezza. Continua esattamente dal punto in cui ti sei fermato, senza ripetere nulla e senza premesse."}]}, 180)
        if r.status_code != 200:
            break
        d = r.json()
        testo += "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        t_in += d["usage"]["input_tokens"]; t_out += d["usage"]["output_tokens"]
    return Risposta(testo, t_in, t_out, {"stop": d.get("stop_reason") or ""})


def _chiama_compatibile_openai(url: str, chiave: str, nome: str, modello: str, istruzioni: str,
                               messaggio: str, max_token: int) -> Risposta:
    """OpenAI e xAI usano lo stesso formato di richiesta."""
    if not chiave:
        raise ErroreFornitore(f"Chiave {nome} non configurata")
    corpo = {
        "model": modello,
        "max_tokens": max_token,
        "messages": [
            {"role": "system", "content": istruzioni},
            {"role": "user", "content": messaggio},
        ],
    }
    intest = {"Authorization": f"Bearer {chiave}", "content-type": "application/json"}
    r = invia(url, intest, corpo, 120)
    if r.status_code == 400 and "max_completion_tokens" in r.text:
        # i modelli piu' recenti di OpenAI vogliono questo nome per il limite di risposta
        corpo["max_completion_tokens"] = corpo.pop("max_tokens")
        r = invia(url, intest, corpo, 120)
    if r.status_code != 200:
        raise ErroreFornitore(f"{nome}: {r.status_code} {r.text[:200]}")
    d = r.json()
    return Risposta(
        d["choices"][0]["message"]["content"] or "",
        d["usage"]["prompt_tokens"],
        d["usage"]["completion_tokens"],
        {"stop": d["choices"][0].get("finish_reason") or ""},
    )


def chiama_modello(fornitore: str, modello: str, istruzioni: str, messaggio: str, max_token: int = 1500,
                   web: dict | None = None) -> Risposta:
    """fornitore: 'anthropic' | 'openai' | 'xai'. web: {'siti': [...], 'max_ricerche': n} (solo Anthropic per ora)."""
    if fornitore == "anthropic":
        return _chiama_anthropic(modello, istruzioni, messaggio, max_token, web)
    if fornitore == "openai":
        return _chiama_compatibile_openai(
            "https://api.openai.com/v1/chat/completions", chiave("openai"),
            "OpenAI", modello, istruzioni, messaggio, max_token)
    if fornitore == "xai":
        return _chiama_compatibile_openai(
            "https://api.x.ai/v1/chat/completions", chiave("xai"),
            "xAI", modello, istruzioni, messaggio, max_token)
    raise ErroreFornitore(f"Fornitore sconosciuto: {fornitore}")
