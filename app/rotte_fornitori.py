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
        prezzi.segna_manuale(conn, nome)
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


# ---------- Catalogo modelli (1.24.3) ----------
from . import catalogo_modelli, modello_economico, prezzi  # noqa: E402


@router.post("/modelli/importa")
def importa_modelli(u: dict = Depends(solo_titolare)):
    """Importa l'elenco completo dei modelli dai fornitori con chiave attiva (senza prezzi: vanno inseriti)."""
    with connessione() as conn:
        esito = catalogo_modelli.importa(conn)
        registro.registra(conn, u, "modelli", "importati", "Catalogo modelli", dettagli={k: v.get("nuovi", 0) for k, v in esito.items()})
        return esito


@router.get("/modelli/elenco")
def elenco_modelli(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        modelli = conn.execute(
            """SELECT m.nome, f.nome AS fornitore, m.fascia, m.costo_input_per_milione, m.costo_output_per_milione, m.usa_per_dialoghi, m.importato, m.prezzo_origine
               FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id ORDER BY f.nome, m.nome""").fetchall()
        return {"modelli": [{**m, "costo_input_per_milione": float(m["costo_input_per_milione"]) if m["costo_input_per_milione"] is not None else None,
                             "costo_output_per_milione": float(m["costo_output_per_milione"]) if m["costo_output_per_milione"] is not None else None} for m in modelli],
                "automatico": catalogo_modelli.automatico(conn), "piano": catalogo_modelli.piano(conn)}


class ImpostazioniModello(BaseModel):
    usa_per_dialoghi: bool | None = None
    fascia: str | None = Field(default=None, pattern="^(economico|standard|avanzato)$")
    costo_input_per_milione: float | None = Field(default=None, ge=0)
    costo_output_per_milione: float | None = Field(default=None, ge=0)


@router.put("/modelli/{nome:path}/impostazioni")
def impostazioni_modello(nome: str, d: ImpostazioniModello, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (nome,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modello inesistente")
        if d.usa_per_dialoghi is not None:
            conn.execute("UPDATE modelli_ai SET usa_per_dialoghi = %s WHERE nome = %s", (d.usa_per_dialoghi, nome))
        if d.fascia:
            conn.execute("UPDATE modelli_ai SET fascia = %s WHERE nome = %s", (d.fascia, nome))
        if d.costo_input_per_milione is not None and d.costo_output_per_milione is not None:
            conn.execute("UPDATE modelli_ai SET costo_input_per_milione=%s, costo_output_per_milione=%s WHERE nome=%s", (d.costo_input_per_milione, d.costo_output_per_milione, nome))
            prezzi.segna_manuale(conn, nome)
    return {"stato": "ok"}


@router.post("/modelli/prezzi/listino")
def applica_listino(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return {**prezzi.applica_listino(conn), "data_listino": prezzi.DATA_LISTINO}


@router.post("/modelli/prezzi/calibra")
def calibra_prezzi(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return prezzi.calibra(conn)


class Automatico(BaseModel):
    attivo: bool


@router.put("/dialoghi-modello-automatico")
def imposta_automatico(d: Automatico, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('dialoghi_modello_automatico', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore",
                     ("true" if d.attivo else "false",))
    return {"automatico": d.attivo}


@router.get("/modelli-economici")
def anteprima_economici(_: dict = Depends(solo_titolare)):
    """Che cosa cambierebbe: per ogni agente il modello attuale e quello proposto."""
    with connessione() as conn:
        return {"piano": modello_economico.piano(conn)}


@router.post("/modelli-economici")
def tutti_economici(u: dict = Depends(solo_titolare)):
    """Ogni agente passa al modello piu' economico adatto ai suoi dati (e alla ricerca web o ai siti, se li usa). Si puo' annullare."""
    with connessione() as conn:
        return modello_economico.applica(conn, u)


@router.post("/modelli-economici/ripristina")
def ripristina_modelli(u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return modello_economico.ripristina(conn, u)


@router.post("/dialoghi-modello-economico")
def assegna_economico(u: dict = Depends(solo_titolare)):
    """Toglie le scelte manuali: ogni agente usa il modello piu' economico adatto (automatico acceso)."""
    with connessione() as conn:
        n = conn.execute("UPDATE agenti SET modello_dialogo = NULL WHERE modello_dialogo IS NOT NULL").rowcount
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('dialoghi_modello_automatico', 'true') ON CONFLICT (chiave) DO UPDATE SET valore = 'true'")
        registro.registra(conn, u, "modelli", "dialoghi al modello piu' economico", "Tutti gli agenti", dettagli={"agenti": n})
        return {"agenti_aggiornati": n, "piano": catalogo_modelli.piano(conn)}
