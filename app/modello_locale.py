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
    """Interroga Ollama: raggiungibile? quali modelli ha scaricati?"""
    base = fornitori.url_locale()
    try:
        r = httpx.get(base + "/api/tags", timeout=httpx.Timeout(8, connect=4))
    except httpx.HTTPError as e:
        return {"raggiungibile": False, "errore": f"non risponde ({type(e).__name__})", "modelli": [], "url": base}
    if r.status_code != 200:
        return {"raggiungibile": False, "errore": f"risposta {r.status_code}", "modelli": [], "url": base}
    try:
        nomi = sorted(m["name"] for m in r.json().get("models", []) if isinstance(m, dict) and m.get("name"))
    except (ValueError, TypeError):
        return {"raggiungibile": False, "errore": "risposta non valida: e' Ollama?", "modelli": [], "url": base}
    return {"raggiungibile": True, "errore": "", "modelli": nomi, "url": base}


@router.get("/locale")
def stato_locale(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        registrati = [r["nome"] for r in conn.execute("SELECT m.nome FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE f.nome = 'locale' ORDER BY m.nome").fetchall()]
        candidati = [r["nome"] for r in conn.execute("SELECT m.nome FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE f.nome <> 'locale' AND f.nome IN ('anthropic','openai','xai') ORDER BY f.nome, m.nome").fetchall()]
        return {"url": _imp(conn, "locale_url", ""), "ripiego": _imp(conn, "locale_ripiego", ""), "registrati": registrati, "candidati_ripiego": candidati}


class ImpostazioniLocale(BaseModel):
    url: str = Field(default="", max_length=200)
    ripiego: str = Field(default="", max_length=120)


@router.put("/locale")
def salva_locale(d: ImpostazioniLocale, _: dict = Depends(solo_titolare)):
    url = d.url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'indirizzo deve iniziare con http:// (per esempio http://100.101.102.103:11434)")
    with connessione() as conn:
        if d.ripiego and not conn.execute("""SELECT 1 FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE m.nome = %s AND f.nome <> 'locale'""", (d.ripiego,)).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il modello di ripiego deve essere un modello Claude o GPT gia' registrato")
        _salva(conn, "locale_url", url)
        _salva(conn, "locale_ripiego", d.ripiego)
    return {"stato": "ok"}


@router.post("/locale/prova")
def prova_locale(_: dict = Depends(solo_titolare)):
    return prova()


@router.post("/locale/modelli/importa")
def importa_modelli_locali(_: dict = Depends(solo_titolare)):
    """Registra come modelli di Opifex quelli scaricati su Ollama (a costo zero), cosi' si possono assegnare agli agenti."""
    p = prova()
    if not p["raggiungibile"]:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Il portatile non risponde: " + p["errore"])
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
