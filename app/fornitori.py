"""Connettore unico verso i fornitori AI (Anthropic/Claude, OpenAI/GPT, xAI/Grok).

Gli agenti non parlano mai direttamente con un fornitore: passano da qui.
Le chiavi API stanno nel file .env del server oppure, se inserite dall'app, cifrate nella cassaforte: mai in chiaro e mai su Drive.
Si usa HTTP diretto (httpx), senza librerie specifiche dei fornitori, cosi' le dipendenze restano poche.
"""
from dataclasses import dataclass, field

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
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": k,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=corpo,
        timeout=180,
    )
    if r.status_code != 200:
        raise ErroreFornitore(f"Anthropic: {r.status_code} {r.text[:200]}")
    d = r.json()
    testo = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    return Risposta(testo, d["usage"]["input_tokens"], d["usage"]["output_tokens"], {"stop": d.get("stop_reason") or ""})


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
    r = httpx.post(url, headers=intest, json=corpo, timeout=120)
    if r.status_code == 400 and "max_completion_tokens" in r.text:
        # i modelli piu' recenti di OpenAI vogliono questo nome per il limite di risposta
        corpo["max_completion_tokens"] = corpo.pop("max_tokens")
        r = httpx.post(url, headers=intest, json=corpo, timeout=120)
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
