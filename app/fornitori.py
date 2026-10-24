"""Connettore unico verso i fornitori AI (Anthropic/Claude, OpenAI/GPT, xAI/Grok).

Gli agenti non parlano mai direttamente con un fornitore: passano da qui.
Le chiavi API stanno solo nel file .env del server, mai nel database ne' su Drive.
Si usa HTTP diretto (httpx), senza librerie specifiche dei fornitori, cosi' le dipendenze restano poche.
"""
from dataclasses import dataclass

import httpx

from .config import impostazioni


@dataclass
class Risposta:
    testo: str
    token_input: int
    token_output: int


class ErroreFornitore(Exception):
    pass


def _chiama_anthropic(modello: str, istruzioni: str, messaggio: str, max_token: int,
                      web: dict | None = None) -> Risposta:
    if not impostazioni.chiave_anthropic:
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
            "x-api-key": impostazioni.chiave_anthropic,
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
    return Risposta(testo, d["usage"]["input_tokens"], d["usage"]["output_tokens"])


def _chiama_compatibile_openai(url: str, chiave: str, nome: str, modello: str, istruzioni: str,
                               messaggio: str, max_token: int) -> Risposta:
    """OpenAI e xAI usano lo stesso formato di richiesta."""
    if not chiave:
        raise ErroreFornitore(f"Chiave {nome} non configurata")
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {chiave}", "content-type": "application/json"},
        json={
            "model": modello,
            "max_tokens": max_token,
            "messages": [
                {"role": "system", "content": istruzioni},
                {"role": "user", "content": messaggio},
            ],
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise ErroreFornitore(f"{nome}: {r.status_code} {r.text[:200]}")
    d = r.json()
    return Risposta(
        d["choices"][0]["message"]["content"] or "",
        d["usage"]["prompt_tokens"],
        d["usage"]["completion_tokens"],
    )


def chiama_modello(fornitore: str, modello: str, istruzioni: str, messaggio: str, max_token: int = 1500,
                   web: dict | None = None) -> Risposta:
    """fornitore: 'anthropic' | 'openai' | 'xai'. web: {'siti': [...], 'max_ricerche': n} (solo Anthropic per ora)."""
    if fornitore == "anthropic":
        return _chiama_anthropic(modello, istruzioni, messaggio, max_token, web)
    if fornitore == "openai":
        return _chiama_compatibile_openai(
            "https://api.openai.com/v1/chat/completions", impostazioni.chiave_openai,
            "OpenAI", modello, istruzioni, messaggio, max_token)
    if fornitore == "xai":
        return _chiama_compatibile_openai(
            "https://api.x.ai/v1/chat/completions", impostazioni.chiave_xai,
            "xAI", modello, istruzioni, messaggio, max_token)
    raise ErroreFornitore(f"Fornitore sconosciuto: {fornitore}")
