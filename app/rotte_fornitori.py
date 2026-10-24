"""Fornitori AI: chiavi inseribili dall'app (cifrate), registrazione modelli e verifica dello stato (solo titolare)."""
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import cassaforte, fornitori, registro
from .config import impostazioni
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione")
NOMI = ("anthropic", "openai", "xai")


def _origine(conn, nome: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (f"chiave_{nome}_cifrata",)).fetchone()
    if r and r["valore"]:
        return "app"
    return "server" if getattr(impostazioni, f"chiave_{nome}", "") else "mancante"


@router.get("/fornitori/chiavi")
def stato_chiavi(_: dict = Depends(solo_titolare)):
    """Da dove viene la chiave di ogni fornitore (mai la chiave stessa)."""
    with connessione() as conn:
        return {n: _origine(conn, n) for n in NOMI}


class Chiave(BaseModel):
    chiave: str | None = Field(default=None, max_length=400)   # None o vuota = rimuove quella dell'app


@router.put("/fornitori/{nome}/chiave")
def imposta_chiave(nome: str, d: Chiave, u: dict = Depends(solo_titolare)):
    if nome not in NOMI:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fornitore sconosciuto")
    k = (d.chiave or "").strip()
    if k and (len(k) < 20 or " " in k):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La chiave non sembra valida")
    with connessione() as conn:
        if not k:
            conn.execute("DELETE FROM impostazioni_sistema WHERE chiave = %s", (f"chiave_{nome}_cifrata",))
        else:
            try:
                cifrata = cassaforte.cifra(k)
            except cassaforte.CassaforteNonConfigurata as e:
                raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
            conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore",
                         (f"chiave_{nome}_cifrata", cifrata))
        registro.registra(conn, u, "chiave_fornitore", "impostata" if k else "rimossa", nome, "fornitore", nome)
        conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES (%s, '{}'::jsonb, %s)",
                     (f"chiave_{nome}_{'impostata' if k else 'rimossa'}", u["id"]))
        return {"origine": _origine(conn, nome)}


class NuovoModello(BaseModel):
    fornitore: str
    nome: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._:\-/]+$")
    fascia: str = Field(default="standard", pattern="^(economico|standard|avanzato)$")
    costo_input_per_milione: float | None = Field(default=None, ge=0, le=100000)
    costo_output_per_milione: float | None = Field(default=None, ge=0, le=100000)


@router.post("/modelli", status_code=201)
def registra_modello(d: NuovoModello, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        f = conn.execute("SELECT id FROM fornitori_ai WHERE nome = %s", (d.fornitore,)).fetchone()
        if f is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fornitore sconosciuto")
        if conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (d.nome,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Modello gia' registrato")
        conn.execute("INSERT INTO modelli_ai (fornitore_id, nome, costo_input_per_milione, costo_output_per_milione, fascia) VALUES (%s,%s,%s,%s,%s)",
                     (f["id"], d.nome, d.costo_input_per_milione, d.costo_output_per_milione, d.fascia))
    return {"stato": "ok"}


class Costi(BaseModel):
    costo_input_per_milione: float | None = Field(default=None, ge=0, le=100000)
    costo_output_per_milione: float | None = Field(default=None, ge=0, le=100000)


@router.put("/modelli/{nome:path}/costi")
def costi_modello(nome: str, d: Costi, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE modelli_ai SET costo_input_per_milione=%s, costo_output_per_milione=%s WHERE nome=%s RETURNING id",
                         (d.costo_input_per_milione, d.costo_output_per_milione, nome)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modello inesistente")
    return {"stato": "ok"}


def _esito_errore(msg: str) -> str:
    m = msg.lower()
    if "non configurata" in m:
        return "chiave mancante"
    if "401" in m or "invalid" in m and "key" in m or "authentication" in m:
        return "chiave non valida"
    if "429" in m or "quota" in m or "rate" in m:
        return "credito esaurito o troppe richieste"
    if "402" in m or "billing" in m or "insufficient" in m:
        return "credito esaurito"
    if "404" in m and "model" in m:
        return "modello non disponibile per questa chiave"
    if "timeout" in m or "connect" in m:
        return "servizio non raggiungibile"
    return "errore: " + msg[:160]


@router.post("/fornitori/verifica")
def verifica(_: dict = Depends(solo_titolare)):
    """Richiesta minima a ogni fornitore con il suo modello piu' economico registrato."""
    risultati = []
    with connessione() as conn:
        for n in NOMI:
            m = conn.execute("""SELECT m.nome FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE f.nome = %s
                                ORDER BY (m.fascia = 'economico') DESC, m.id LIMIT 1""", (n,)).fetchone()
            risultati.append({"fornitore": n, "modello": m["nome"] if m else None, "origine_chiave": _origine(conn, n)})
    for r in risultati:
        if r["modello"] is None:
            r.update(ok=False, ms=None, dettaglio="nessun modello registrato")
            continue
        t0 = time.time()
        try:
            fornitori.chiama_modello(r["fornitore"], r["modello"], "Rispondi con una sola parola.", "Dì ok.", 16)
            r.update(ok=True, ms=int((time.time() - t0) * 1000), dettaglio="attivo")
        except Exception as e:  # noqa: BLE001
            r.update(ok=False, ms=int((time.time() - t0) * 1000), dettaglio=_esito_errore(str(e)))
    return risultati
