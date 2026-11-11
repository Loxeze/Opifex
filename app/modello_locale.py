"""Modello locale: Ollama sul portatile di Lorenzo, raggiunto da un tunnel privato (Tailscale). Impostazioni, prova di collegamento, elenco dei modelli."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import fornitori, prova_modelli
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione", tags=["locale"])


def _imp(conn, k: str, d: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (k,)).fetchone()
    return r["valore"] if r and r["valore"] else d


def _salva(conn, k: str, v: str) -> None:
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (k, v))


def prova() -> dict:
    """Interroga Ollama su ogni computer: raggiungibile? quali modelli ha scaricati?"""
    macchine = []
    for m in fornitori.macchine_locali():
        v = {"nome": m["nome"], "url": m["url"], "modello": m["modello"], "raggiungibile": False, "errore": "", "modelli": []}
        try:
            r = httpx.get(m["url"] + "/api/tags", timeout=httpx.Timeout(8, connect=4))
            if r.status_code != 200:
                v["errore"] = f"risposta {r.status_code}"
            else:
                v["modelli"] = sorted(x["name"] for x in r.json().get("models", []) if isinstance(x, dict) and x.get("name"))
                v["raggiungibile"] = True
        except httpx.HTTPError as e:
            v["errore"] = f"non risponde ({type(e).__name__})"
        except (ValueError, TypeError):
            v["errore"] = "risposta non valida: e' Ollama?"
        fornitori._TAGS.pop(m["url"], None)   # dopo una prova esplicita si rilegge lo stato vero
        macchine.append(v)
    accese = [v for v in macchine if v["raggiungibile"]]
    return {"raggiungibile": bool(accese), "errore": "" if accese else "; ".join(v["nome"] + ": " + v["errore"] for v in macchine),
            "modelli": sorted({n for v in accese for n in v["modelli"]}), "url": macchine[0]["url"] if macchine else "", "macchine": macchine}


@router.get("/locale")
def stato_locale(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        registrati = [r["nome"] for r in conn.execute("SELECT m.nome FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE f.nome = 'locale' ORDER BY m.nome").fetchall()]
        candidati = [r["nome"] for r in conn.execute("SELECT m.nome FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE f.nome <> 'locale' AND f.nome IN ('anthropic','openai','xai') ORDER BY m.nome").fetchall()]
        ha_elenco = bool(_imp(conn, "locale_macchine", ""))
        return {"url": _imp(conn, "locale_url", ""), "ripiego": _imp(conn, "locale_ripiego", ""), "registrati": registrati, "candidati_ripiego": candidati,
                "macchine": fornitori.macchine_locali() if (ha_elenco or _imp(conn, "locale_url", "")) else []}


class Macchina(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=1, max_length=200)
    modello: str = Field(default="", max_length=120)      # modello principale di questo computer (usato da «locale-auto» e come sostituto)
    vram_gb: float = Field(default=8, ge=1, le=512)
    ram_gb: float = Field(default=32, ge=1, le=4096)


class ImpostazioniLocale(BaseModel):
    url: str = Field(default="", max_length=200)
    ripiego: str = Field(default="", max_length=120)
    macchine: list[Macchina] | None = Field(default=None, max_length=6)   # in ordine di preferenza: il primo acceso vince


@router.put("/locale")
def salva_locale(d: ImpostazioniLocale, _: dict = Depends(solo_titolare)):
    import json as _j
    url = d.url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'indirizzo deve iniziare con http:// (per esempio http://100.101.102.103:11434)")
    macchine = None
    if d.macchine is not None:
        macchine = []
        for m in d.macchine:
            u = m.url.strip().rstrip("/")
            if not u.startswith(("http://", "https://")):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{m.nome}: l'indirizzo deve iniziare con http:// (per esempio http://100.101.102.103:11434)")
            if u in [x["url"] for x in macchine]:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{m.nome}: questo indirizzo e' gia' in elenco")
            macchine.append({"nome": m.nome.strip(), "url": u, "modello": m.modello.strip(), "vram_gb": m.vram_gb, "ram_gb": m.ram_gb})
    with connessione() as conn:
        if d.ripiego and not conn.execute("""SELECT 1 FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE m.nome = %s AND f.nome <> 'locale'""", (d.ripiego,)).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il modello di ripiego deve essere un modello Claude o GPT gia' registrato")
        if macchine is not None:
            _salva(conn, "locale_macchine", _j.dumps(macchine) if macchine else "")
            _salva(conn, "locale_url", macchine[0]["url"] if macchine else "")
        else:
            _salva(conn, "locale_url", url)
        _salva(conn, "locale_ripiego", d.ripiego)
    fornitori._TAGS.clear(); fornitori._FINESTRE.clear()
    return {"stato": "ok"}


@router.post("/locale/prova")
def prova_locale(_: dict = Depends(solo_titolare)):
    return prova()


@router.post("/locale/modelli/importa")
def importa_modelli_locali(_: dict = Depends(solo_titolare)):
    """Registra come modelli di Opifex quelli scaricati su Ollama (a costo zero), cosi' si possono assegnare agli agenti."""
    p = prova()
    if not p["raggiungibile"]:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Nessun computer risponde: " + p["errore"])
    nuovi = 0
    with connessione() as conn:
        f = conn.execute("SELECT id FROM fornitori_ai WHERE nome = 'locale'").fetchone()
        if f is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fornitore locale non presente: aggiorna il database")
        for nome in p["modelli"]:
            if "embed" in nome.lower() or conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (nome,)).fetchone():
                continue
            conn.execute("INSERT INTO modelli_ai (fornitore_id, nome, costo_input_per_milione, costo_output_per_milione, fascia, importato, usa_per_dialoghi) VALUES (%s,%s,0,0,'economico',TRUE,FALSE)", (f["id"], nome))
            nuovi += 1
    return {"nuovi": nuovi, "totale": len(p["modelli"])}


class ProvaModello(BaseModel):
    modello: str = Field(min_length=1, max_length=120)
    dialogo: str | None = Field(default=None, max_length=120)   # modello per i dialoghi tra agenti (se omesso, lo stesso)


@router.post("/locale/affidabilita")
def avvia_prova(d: ProvaModello, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE f.nome = 'locale' AND m.nome = %s", (d.modello,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modello locale non registrato: premi prima «Registra i modelli del portatile»")
    if not prova_modelli.avvia(d.modello):
        raise HTTPException(status.HTTP_409_CONFLICT, "Una prova e' gia' in corso: aspetta che finisca")
    return {"stato": "avviata"}


@router.get("/locale/affidabilita")
def stato_prova(_: dict = Depends(solo_titolare)):
    s = prova_modelli.stato()
    s.pop("inizio", None)
    return {"corrente": s, "storico": prova_modelli.storico(), "soglia_velocita": prova_modelli.SOGLIA_VELOCITA}


def _motivi_esclusione(conn, a: dict) -> list[str]:
    """Agenti che restano online: possono scrivere fuori da Opifex o hanno bisogno di funzioni solo dei modelli Claude."""
    m = []
    if conn.execute("""SELECT 1 FROM agenti_connessioni ac JOIN connessioni c ON c.id = ac.connessione_id AND c.stato = 'attiva'
                       JOIN accessi_siti s ON s.connessione_id = c.id WHERE ac.agente_id = %s LIMIT 1""", (a["id"],)).fetchone():
        m.append("naviga siti con accesso (solo modelli Claude)")
    return m


def _piano(conn, modello: str) -> dict:
    if not conn.execute("SELECT 1 FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE f.nome = 'locale' AND m.nome = %s", (modello,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modello locale non registrato: premi prima «Registra i modelli del portatile»")
    cambia, restano = [], []
    for a in conn.execute("SELECT id, nome, modello, attivo FROM agenti WHERE attivo ORDER BY nome").fetchall():
        mot = _motivi_esclusione(conn, a)
        if mot:
            restano.append({"id": a["id"], "nome": a["nome"], "modello": a["modello"], "motivi": mot})
        elif a["modello"] != modello:
            cambia.append({"id": a["id"], "nome": a["nome"], "modello": a["modello"]})
    return {"cambia": cambia, "restano": restano}


@router.get("/locale/assegnazione")
def anteprima_assegnazione(modello: str, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return _piano(conn, modello)


@router.post("/locale/assegnazione")
def assegna_a_tutti(d: ProvaModello, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        p = _piano(conn, d.modello)
        dialogo = d.dialogo or d.modello
        if not conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (dialogo,)).fetchone():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modello per i dialoghi non registrato")
        for x in p["cambia"]:
            conn.execute("INSERT INTO modelli_prima_locale (agente_id, modello_precedente, dialogo_precedente) SELECT id, modello, modello_dialogo FROM agenti WHERE id = %s ON CONFLICT (agente_id) DO NOTHING", (x["id"],))
            conn.execute("UPDATE agenti SET modello = %s, modello_dialogo = %s WHERE id = %s", (d.modello, dialogo, x["id"]))
        if p["cambia"]:
            prima = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'modello_dialogo_predefinito'").fetchone()
            conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('dialogo_predefinito_prima_locale', %s) ON CONFLICT (chiave) DO NOTHING", ((prima["valore"] if prima else "") or "-",))
            _salva(conn, "modello_dialogo_predefinito", dialogo)
        conn.execute("INSERT INTO registro_azioni (azione, utente_id, dettagli) VALUES ('modello_locale_assegnato', %s, %s::jsonb)",
                     (u["id"], __import__("json").dumps({"modello": d.modello, "agenti": len(p["cambia"])})))
    return {"cambiati": len(p["cambia"]), "restano": len(p["restano"])}


@router.post("/locale/assegnazione/ripristina")
def ripristina_modelli(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        righe = conn.execute("SELECT agente_id, modello_precedente, dialogo_precedente FROM modelli_prima_locale").fetchall()
        n = 0
        for r in righe:
            if r["modello_precedente"]:
                conn.execute("UPDATE agenti SET modello = %s, modello_dialogo = %s WHERE id = %s", (r["modello_precedente"], r["dialogo_precedente"], r["agente_id"])); n += 1
        pr = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'dialogo_predefinito_prima_locale'").fetchone()
        if pr and pr["valore"]:
            _salva(conn, "modello_dialogo_predefinito", "claude-haiku-5-5" if pr["valore"] == "-" else pr["valore"])
        conn.execute("DELETE FROM impostazioni_sistema WHERE chiave = 'dialogo_predefinito_prima_locale'")
        conn.execute("DELETE FROM modelli_prima_locale")
        conn.execute("INSERT INTO registro_azioni (azione, utente_id, dettagli) VALUES ('modello_locale_ripristinato', %s, %s::jsonb)", (u["id"], __import__("json").dumps({"agenti": n})))
    return {"ripristinati": n}


@router.get("/locale/risorse")
def risorse_locale(_: dict = Depends(solo_titolare)):
    """Che cosa stanno facendo adesso i computer con Ollama (da /api/ps): modelli in memoria, scheda grafica e RAM occupate, richieste in corso, velocita'."""
    with connessione() as conn:
        og = conn.execute("""SELECT count(*) FILTER (WHERE azione = 'passaggio_online_finestra') AS online, count(*) FILTER (WHERE azione = 'prompt_a_budget') AS ridotti
                             FROM registro_azioni WHERE azione IN ('passaggio_online_finestra', 'prompt_a_budget') AND creata_il >= date_trunc('day', now())""").fetchone()
        oggi = {"passaggi_online": int(og["online"]), "prompt_ridotti": int(og["ridotti"])}
    macchine = []
    for m in fornitori.macchine_locali():
        v = {"nome": m["nome"], "modello_principale": m["modello"], "raggiungibile": False, "modelli": [], "vram_totale_gb": m["vram_gb"], "ram_totale_gb": m["ram_gb"],
             "gpu_usata_gb": 0, "ram_usata_gb": 0, "lavoro": fornitori.lavoro_locale(m["url"])}
        try:
            r = httpx.get(m["url"] + "/api/ps", timeout=httpx.Timeout(4, connect=2))
            r.raise_for_status()
            for x in (r.json().get("models") or []):
                tot, gpu = int(x.get("size") or 0), int(x.get("size_vram") or 0)
                v["modelli"].append({"nome": x.get("name"), "dimensione_gb": round(tot / 1e9, 1), "gpu_gb": round(gpu / 1e9, 1),
                                     "percentuale_gpu": round(100 * gpu / tot) if tot else 0, "contesto": x.get("context_length"), "scade": x.get("expires_at")})
            v["raggiungibile"] = True
            v["gpu_usata_gb"] = round(sum(x["gpu_gb"] for x in v["modelli"]), 1)
            v["ram_usata_gb"] = round(sum(x["dimensione_gb"] - x["gpu_gb"] for x in v["modelli"]), 1)
        except (httpx.HTTPError, ValueError):
            pass
        macchine.append(v)
    primo = macchine[0] if macchine else {"raggiungibile": False, "modelli": [], "vram_totale_gb": 8, "gpu_usata_gb": 0, "ram_usata_gb": 0}
    # i campi in cima restano quelli del primo computer, per chi leggeva la risposta di prima
    return {"macchine": macchine, "oggi": oggi, "raggiungibile": any(x["raggiungibile"] for x in macchine), "modelli": primo["modelli"], "vram_totale_gb": primo["vram_totale_gb"],
            "gpu_usata_gb": primo["gpu_usata_gb"], "ram_usata_gb": primo["ram_usata_gb"], "lavoro": fornitori.lavoro_locale()}


class ModoCantiere(BaseModel):
    modo: str = Field(pattern="^(auto|sempre|spento)$")


@router.get("/locale/cantieri")
def elenco_cantieri(_: dict = Depends(solo_titolare)):
    """Lavori a schede: come sono andati gli ultimi, e quanto e' costato il modello online che li ha diretti."""
    with connessione() as conn:
        righe = conn.execute("""SELECT c.id, c.creato_il, a.nome AS agente, c.origine, left(c.richiesta, 160) AS richiesta, jsonb_array_length(c.piano) AS schede, c.rifatte, c.stato,
                                       c.da_verificare, c.token_online, c.token_locali, c.costo_online::float AS costo_online, c.secondi
                                FROM cantieri c LEFT JOIN agenti a ON a.id = c.agente_id ORDER BY c.id DESC LIMIT 30""").fetchall()
        tot = conn.execute("""SELECT count(*) AS n, count(*) FILTER (WHERE stato = 'riuscito') AS riusciti, count(*) FILTER (WHERE stato = 'con_riserve') AS riserve,
                                     count(*) FILTER (WHERE stato = 'fallito') AS falliti, COALESCE(sum(costo_online),0)::float AS costo
                              FROM cantieri WHERE creato_il > now() - interval '30 days'""").fetchone()
        return {"modo": _imp(conn, "cantiere_modo", "auto"), "ultimi": [dict(r) for r in righe], "mese": dict(tot)}


@router.put("/locale/cantieri")
def salva_modo_cantiere(d: ModoCantiere, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _salva(conn, "cantiere_modo", d.modo)
    return {"modo": d.modo}


@router.get("/locale/cantieri/{cid}")
def dettaglio_cantiere(cid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("SELECT c.*, a.nome AS agente FROM cantieri c LEFT JOIN agenti a ON a.id = c.agente_id WHERE c.id = %s", (cid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavoro a schede inesistente")
        d = dict(r); d["costo_online"] = float(d["costo_online"] or 0)
        return d
