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


class ErroreLocale(ErroreFornitore):
    """Il modello sul portatile non e' raggiungibile (spento, offline, tunnel giu') o non risponde in tempo: si puo' ripiegare su un altro fornitore."""


PAUSE_RIPROVA = (2, 6, 15)          # secondi tra un tentativo e l'altro
CODICI_TRANSITORI = {408, 409, 425, 429, 500, 502, 503, 504, 529}   # sovraccarico o guasto momentaneo del fornitore


import contextvars
MODELLO_FORZATO = contextvars.ContextVar("modello_forzato", default=None)   # nome del modello da usare al posto di quello dell'agente (riunioni: massima qualita')
SFORZO_FORZATO = contextvars.ContextVar("sforzo_forzato", default=None)
SFORZO = contextvars.ContextVar("sforzo_agente", default=None)   # 'low' | 'medium' | 'high': sforzo di ragionamento dell'agente in esecuzione (solo modelli Anthropic)


CACHE_LETTA = contextvars.ContextVar("cache_letta", default=None)   # token riletti dalla cache nella risposta in corso (per le misure)


def _con_cache(corpo: dict) -> dict:
    """Cache dei prompt di Anthropic: istruzioni+strumenti e la coda della conversazione vengono riletti al 10% del prezzo
    a ogni giro di strumenti. Due punti di taglio: fine di 'system' (copre anche gli strumenti) e ultimo blocco dei messaggi."""
    c = dict(corpo)
    sistema = c.get("system")
    if isinstance(sistema, str) and sistema.strip():
        c["system"] = [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}]
    elif isinstance(sistema, list) and sistema and isinstance(sistema[-1], dict) and "cache_control" not in sistema[-1]:
        c["system"] = sistema[:-1] + [{**sistema[-1], "cache_control": {"type": "ephemeral"}}]
    mess = c.get("messages")
    if isinstance(mess, list) and mess and isinstance(mess[-1], dict):
        ultimo = mess[-1]
        cont = ultimo.get("content")
        if isinstance(cont, str) and cont.strip():
            cont = [{"type": "text", "text": cont}]
        if isinstance(cont, list) and cont and isinstance(cont[-1], dict) and cont[-1].get("type") in ("text", "tool_result", "tool_use", "image") \
                and "cache_control" not in cont[-1]:
            c["messages"] = mess[:-1] + [{**ultimo, "content": cont[:-1] + [{**cont[-1], "cache_control": {"type": "ephemeral"}}]}]
    return c


def token_ingresso(uso: dict) -> int:
    """Token di ingresso equivalenti al prezzo pieno: i nuovi in cache costano 1,25, quelli riletti 0,1 (cosi' il costo stimato resta giusto)."""
    letti = int(uso.get("cache_read_input_tokens") or 0)
    scritti = int(uso.get("cache_creation_input_tokens") or 0)
    return int(uso.get("input_tokens") or 0) + round(scritti * 1.25) + round(letti * 0.1)


def invia(url: str, intestazioni: dict, corpo: dict, timeout: int = 180):
    """POST al fornitore con nuovi tentativi per gli errori momentanei (sovraccarico, limite di richieste, rete lenta).
    Senza questo un singolo 529 o un timeout fermava l'agente. Gli errori definitivi (chiave, richiesta sbagliata) passano subito."""
    ultimo = ""
    sforzo = SFORZO.get()
    anthropic = "api.anthropic.com/v1/messages" in url
    if anthropic:
        corpo = _con_cache(corpo)
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
            if anthropic and r.status_code == 200:
                try:
                    letti = int((r.json().get("usage") or {}).get("cache_read_input_tokens") or 0)
                    CACHE_LETTA.set((CACHE_LETTA.get() or 0) + letti)
                except (ValueError, TypeError):
                    pass
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
    t_in, t_out, giri = token_ingresso(d["usage"]), d["usage"]["output_tokens"], 0
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
        t_in += token_ingresso(d["usage"]); t_out += d["usage"]["output_tokens"]
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


def url_locale() -> str:
    """Indirizzo di Ollama (impostazione 'locale_url'); di norma l'IP privato Tailscale del portatile, porta 11434."""
    try:
        from .db import connessione
        with connessione() as conn:
            r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'locale_url'").fetchone()
        v = (r["valore"] if r else "") or ""
    except Exception:  # noqa: BLE001
        v = ""
    v = v.strip().rstrip("/")
    return v if v.startswith(("http://", "https://")) else "http://127.0.0.1:11434"


# ---------- piu' computer locali (portatile, fisso...): ognuno con il suo Ollama; Opifex sceglie quello acceso e adatto ----------
AUTO = "locale-auto"     # modello «automatico»: il modello principale del primo computer acceso, nell'ordine di preferenza
_TAGS: dict = {}         # url -> (insieme dei modelli scaricati oppure None se non risponde, istante)
_ULTIMA: dict = {}       # modello chiesto -> (url, modello usato davvero): chi ha servito l'ultima richiesta
_LAVORO: dict = {}       # url -> {"in_corso", "modello", "da", "misure"}
_BLOCCO_LOCALE = __import__("threading").Lock()


def macchine_locali() -> list[dict]:
    """Computer con Ollama, in ordine di preferenza (impostazione 'locale_macchine'). Senza elenco vale il solo indirizzo 'locale_url' (il portatile)."""
    import json as _j
    grezzo, vram = "", "8"
    try:
        from .db import connessione
        with connessione() as conn:
            r = {x["chiave"]: x["valore"] for x in conn.execute("SELECT chiave, valore FROM impostazioni_sistema WHERE chiave IN ('locale_macchine', 'locale_vram_gb')").fetchall()}
        grezzo, vram = r.get("locale_macchine") or "", r.get("locale_vram_gb") or "8"
    except Exception:  # noqa: BLE001
        pass
    out = []
    try:
        for m in (_j.loads(grezzo) if grezzo else []):
            u = str(m.get("url") or "").strip().rstrip("/")
            if u.startswith(("http://", "https://")):
                out.append({"nome": str(m.get("nome") or "Computer")[:40], "url": u, "modello": str(m.get("modello") or "")[:120],
                            "vram_gb": float(m.get("vram_gb") or 8), "ram_gb": float(m.get("ram_gb") or 32)})
    except (ValueError, TypeError, AttributeError):
        out = []
    return out or [{"nome": "Portatile", "url": url_locale(), "modello": "", "vram_gb": float(vram or 8), "ram_gb": 32.0}]


def modelli_macchina(url: str, forza: bool = False):
    """Modelli scaricati su quel computer, oppure None se non risponde. In memoria per 45 secondi (15 se non risponde): non si interroga a ogni richiesta."""
    import time as _t
    v = _TAGS.get(url)
    if v and not forza and _t.monotonic() - v[1] < (45 if v[0] is not None else 15):
        return v[0]
    try:
        r = httpx.get(url + "/api/tags", timeout=httpx.Timeout(4, connect=2))
        nomi = {m["name"] for m in r.json().get("models", []) if isinstance(m, dict) and m.get("name")} if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError, TypeError):
        nomi = None
    _TAGS[url] = (nomi, _t.monotonic())
    return nomi


def _in_corso(url: str) -> int:
    return int((_LAVORO.get(url) or {}).get("in_corso") or 0)


def scegli_macchina(modello: str, escludi: tuple = ()) -> tuple[dict, str]:
    """Quale computer serve questa richiesta, e con quale modello. Un modello preciso va al computer acceso che lo ha (il meno occupato, se sono piu' d'uno);
    «locale-auto», o un modello che nessun computer acceso ha, va al modello principale del primo computer acceso nell'ordine di preferenza."""
    accese = [(m, t) for m in macchine_locali() if m["url"] not in escludi and (t := modelli_macchina(m["url"])) is not None]
    if not accese:
        raise ErroreLocale("Nessun computer con il modello locale risponde (portatile o fisso): sono accesi e collegati, con Ollama e Tailscale attivi e la VPN spenta?")
    if modello != AUTO:
        con = [m for m, t in accese if modello in t]
        if con:
            return min(con, key=lambda x: _in_corso(x["url"])), modello
    for m, t in accese:
        if m["modello"] and m["modello"] in t:
            return m, m["modello"]
    if modello != AUTO and len(macchine_locali()) == 1:
        return accese[0][0], modello          # un solo computer: si prova comunque, Ollama dira' se il modello manca
    raise ErroreLocale(f"Il modello locale «{modello}» non e' disponibile su nessun computer acceso, e per quelli accesi non e' indicato un modello principale")


_FINESTRE: dict = {}   # (url, modello) -> (token, istante)


def _contesto_caricato(url: str, modello: str) -> int:
    try:
        r = httpx.get(url + "/api/ps", timeout=httpx.Timeout(3, connect=2))
        return next((int(m.get("context_length") or 0) for m in (r.json().get("models") or []) if m.get("name") == modello), 0)
    except (httpx.HTTPError, ValueError):
        return 0


def finestra_locale(modello: str) -> int:
    """Finestra di contesto del modello locale sul computer che lo servirebbe adesso: quella vera se Ollama lo ha in memoria, altrimenti l'ultima vista
    o l'impostazione 'locale_contesto' (8192)."""
    import time as _t
    try:
        m, eff = scegli_macchina(modello)
        chiave = (m["url"], eff)
    except ErroreFornitore:
        m, eff, chiave = None, modello, ("", modello)
    v = _FINESTRE.get(chiave)
    if v and _t.monotonic() - v[1] < 120:
        return v[0]
    ctx = _contesto_caricato(m["url"], eff) if m else 0
    if not ctx:
        if v:
            ctx = v[0]
        else:
            try:
                from .db import connessione
                with connessione() as conn:
                    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'locale_contesto'").fetchone()
                ctx = int((r["valore"] if r else "") or 8192)
            except Exception:  # noqa: BLE001
                ctx = 8192
    _FINESTRE[chiave] = (ctx, _t.monotonic())
    return ctx


def controlla_troncamento(modello: str, token_prompt: int) -> bool:
    """Ollama taglia in silenzio l'inizio del prompt se supera la finestra di contesto: memoria, istruzioni e dossier spariscono e l'agente «perde i riferimenti».
    Se il prompt riempie tutta la finestra lo segnalo (una notifica l'ora, e nel registro azioni)."""
    if token_prompt < 3000:
        return False
    url, eff = _ULTIMA.get(modello) or (url_locale(), modello)
    contesto = _contesto_caricato(url, eff)
    if not contesto or token_prompt < contesto - 48:
        return False
    try:
        from .db import connessione
        with connessione() as conn:
            gia = conn.execute("SELECT 1 FROM registro_azioni WHERE azione = 'locale_prompt_troncato' AND creata_il > NOW() - INTERVAL '1 hour' LIMIT 1").fetchone()
            conn.execute("INSERT INTO registro_azioni (azione, dettagli) VALUES ('locale_prompt_troncato', %s::jsonb)", (__import__("json").dumps({"modello": eff, "contesto": contesto, "token_prompt": token_prompt}),))
            if not gia:
                conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, TRUE, FALSE)",
                             (f"Il modello locale {eff} ha ricevuto piu' testo di quanto la sua finestra di contesto ({contesto} token) contenga: l'inizio (istruzioni, memoria, dossier) viene tagliato e gli agenti perdono i riferimenti. "
                              "Aumenta OLLAMA_CONTEXT_LENGTH su quel computer (per esempio 16384) e riavvia Ollama, oppure assegna agli agenti con molta memoria un modello online.",))
    except Exception:  # noqa: BLE001 - un avviso mancato non deve fermare l'agente
        pass
    return True


def posta_locale(corpo: dict):
    """Chiamata a Ollama sul computer scelto, con il conteggio delle richieste in corso e la misura della velocita' (token generati al secondo, lettura del prompt compresa).
    Se quel computer cade proprio adesso, la richiesta passa una volta a un altro computer acceso."""
    import time as _t
    chiesto, esclusi, ultimo = corpo.get("model") or "", (), None
    for _ in range(2):
        try:
            m, eff = scegli_macchina(chiesto, esclusi)
        except ErroreLocale:
            if ultimo is not None:
                raise ultimo from None
            raise
        url = m["url"]
        with _BLOCCO_LOCALE:
            st = _LAVORO.setdefault(url, {"in_corso": 0, "modello": "", "da": 0.0, "misure": []})
            st["in_corso"] += 1
            st["modello"] = eff
            if st["in_corso"] == 1:
                st["da"] = _t.time()
        t0 = _t.monotonic()
        try:
            r = httpx.post(url + "/v1/chat/completions", json={**corpo, "model": eff}, timeout=httpx.Timeout(900, connect=5))
        except httpx.ConnectError as e:      # non raggiungibile: lo si segna spento e si prova l'altro
            _TAGS[url] = (None, _t.monotonic())
            esclusi, ultimo = esclusi + (url,), e
            continue
        finally:
            with _BLOCCO_LOCALE:
                st["in_corso"] = max(0, st["in_corso"] - 1)
        _ULTIMA[chiesto] = (url, eff)
        try:
            if r.status_code == 200:
                tok, dt = int((r.json().get("usage") or {}).get("completion_tokens") or 0), _t.monotonic() - t0
                if tok >= 5 and dt > 0.2:
                    with _BLOCCO_LOCALE:
                        st["misure"] = (st["misure"] + [{"token_s": round(tok / dt, 1), "token": tok, "secondi": round(dt, 1), "modello": eff, "quando": _t.time()}])[-20:]
        except (ValueError, AttributeError, TypeError):
            pass
        return r
    raise ultimo


def lavoro_locale(url: str | None = None) -> dict:
    """Che cosa sta facendo un computer (o, senza indirizzo, tutti insieme): richieste in corso, ultima velocita', media recente."""
    import time as _t
    with _BLOCCO_LOCALE:
        stati = [_LAVORO[url]] if url and url in _LAVORO else ([] if url else list(_LAVORO.values()))
        m = sorted((x for st in stati for x in st["misure"]), key=lambda x: x["quando"])
        attivi = [st for st in stati if st["in_corso"]]
        recenti = [x for x in m if _t.time() - x["quando"] < 1800]
        return {"in_corso": sum(st["in_corso"] for st in stati), "modello_in_corso": attivi[0]["modello"] if attivi else "",
                "da_secondi": int(_t.time() - min(st["da"] for st in attivi)) if attivi else 0,
                "ultima": ({**m[-1], "secondi_fa": int(_t.time() - m[-1]["quando"])} if m else None),
                "media_token_s": round(sum(x["token_s"] for x in recenti) / len(recenti), 1) if recenti else None}


def _chiama_locale(modello: str, istruzioni: str, messaggio: str, max_token: int) -> Risposta:
    """Ollama espone lo stesso formato di OpenAI. Niente nuovi tentativi: se il portatile non risponde si ripiega subito."""
    corpo = {"model": modello, "max_tokens": max_token, "stream": False,
             "messages": [{"role": "system", "content": istruzioni}, {"role": "user", "content": messaggio}]}
    try:
        r = posta_locale(corpo)
    except httpx.HTTPError as e:
        raise ErroreLocale(f"Il modello locale non risponde ({type(e).__name__}): il portatile e' acceso e collegato?") from None
    if r.status_code == 404:
        raise ErroreFornitore(f"Il modello locale «{modello}» non e' scaricato sul portatile (in Ollama: ollama pull {modello})")
    if r.status_code in CODICI_TRANSITORI:
        raise ErroreLocale(f"Il modello locale e' occupato o in errore ({r.status_code})")
    if r.status_code != 200:
        raise ErroreFornitore(f"Modello locale: {r.status_code} {r.text[:200]}")
    try:
        d = r.json()
        uso = d.get("usage") or {}
        controlla_troncamento(modello, int(uso.get("prompt_tokens") or 0))
        return Risposta(d["choices"][0]["message"].get("content") or "", int(uso.get("prompt_tokens") or 0), int(uso.get("completion_tokens") or 0),
                        {"stop": d["choices"][0].get("finish_reason") or ""})
    except (ValueError, KeyError, IndexError, TypeError):
        raise ErroreFornitore("Modello locale: risposta non valida") from None


def chiama_modello(fornitore: str, modello: str, istruzioni: str, messaggio: str, max_token: int = 1500,
                   web: dict | None = None) -> Risposta:
    """fornitore: 'anthropic' | 'openai' | 'xai' | 'locale'. web: {'siti': [...], 'max_ricerche': n} (solo Anthropic per ora)."""
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
    if fornitore == "locale":
        return _chiama_locale(modello, istruzioni, messaggio, max_token)
    raise ErroreFornitore(f"Fornitore sconosciuto: {fornitore}")
