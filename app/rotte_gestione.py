"""Gestione di agenti e connessioni dall'interfaccia (solo titolare)."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import etichetta
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione")

FASCE = ("pubblico", "interno", "riservato")


def _pulisci_siti(siti: list[str]) -> list[str]:
    """Tiene solo i domini (senza http://, percorsi o spazi), senza doppioni."""
    out = []
    for s in siti:
        d = re.sub(r"^https?://", "", s.strip().lower()).split("/")[0]
        if d and re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d) and d not in out:
            out.append(d)
    return out


class Fase(BaseModel):
    titolo: str = Field(min_length=1, max_length=120)
    istruzioni: str = Field(default="", max_length=4000)
    approvazione: bool = True
    parere_superiore: bool = False


def _scrivi_fasi(conn, agente_id: int, fasi: list[dict]):
    if len(fasi) > 12:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Al massimo 12 fasi")
    conn.execute("DELETE FROM fasi_agente WHERE agente_id = %s", (agente_id,))
    for i, f in enumerate(fasi, 1):
        conn.execute("INSERT INTO fasi_agente (agente_id, posizione, titolo, istruzioni, approvazione, parere_superiore) VALUES (%s,%s,%s,%s,%s,%s)",
                     (agente_id, i, f["titolo"].strip(), (f.get("istruzioni") or "").strip(), f.get("approvazione", True), f.get("parere_superiore", False)))


class DatiAgente(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    ruolo: str = Field(min_length=1, max_length=120)
    divisione_id: int | None = None
    superiore_id: int | None = None
    livello: str = "operativo"
    sentinella: bool = False
    modello: str
    istruzioni: str = Field(min_length=1, max_length=16000)
    fascia_dati_max: str = "pubblico"
    max_token_risposta: int = Field(default=8000, ge=100, le=16000)
    budget_token_mensile: int | None = Field(default=None, gt=0)
    accesso_web: bool = True
    siti_consentiti: list[str] = []
    max_ricerche: int = Field(default=3, ge=1, le=10)
    attivo: bool = True
    modello_dialogo: str | None = None
    dialoghi_attivi: bool = False
    vede_tutto: bool = False
    drive_attivo: bool = False
    gmail_account_id: int | None = None
    social_attivo: bool = False
    email_attivo: bool = False
    rimanda_a: str | None = Field(default=None, max_length=300)
    crm_attivo: bool = False
    canva_attivo: bool = False
    fasi: list[Fase] = []
    connessioni: list[int] = []


class ModificaAgente(BaseModel):
    """Tutti i campi opzionali: si modifica solo cio' che viene inviato."""
    nome: str | None = Field(default=None, min_length=1, max_length=60)
    ruolo: str | None = Field(default=None, min_length=1, max_length=120)
    divisione_id: int | None = None
    superiore_id: int | None = None
    livello: str | None = None
    sentinella: bool | None = None
    modello: str | None = None
    istruzioni: str | None = Field(default=None, min_length=1, max_length=16000)
    fascia_dati_max: str | None = None
    max_token_risposta: int | None = Field(default=None, ge=100, le=16000)
    budget_token_mensile: int | None = Field(default=None, gt=0)
    accesso_web: bool | None = None
    siti_consentiti: list[str] | None = None
    max_ricerche: int | None = Field(default=None, ge=1, le=10)
    attivo: bool | None = None
    modello_dialogo: str | None = None
    dialoghi_attivi: bool | None = None
    vede_tutto: bool | None = None
    drive_attivo: bool | None = None
    gmail_account_id: int | None = None
    social_attivo: bool | None = None
    email_attivo: bool | None = None
    rimanda_a: str | None = Field(default=None, max_length=300)
    crm_attivo: bool | None = None
    canva_attivo: bool | None = None
    fasi: list[Fase] | None = None
    connessioni: list[int] | None = None


def _valida(conn, d: dict):
    if d.get("gmail_account_id") and not conn.execute(
            "SELECT 1 FROM account_google WHERE id = %s AND 'gmail' = ANY(servizi)", (d["gmail_account_id"],)).fetchone():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "L'account scelto non ha il permesso Gmail")
    if d.get("fascia_dati_max") is not None and d["fascia_dati_max"] not in FASCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello di riservatezza non valido")
    if d.get("livello") is not None and d["livello"] not in ("referente", "manager", "operativo"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello non valido")
    if d.get("modello") is not None:
        if conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (d["modello"],)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Modello AI non registrato")
    if d.get("modello_dialogo"):
        if conn.execute("SELECT 1 FROM modelli_ai WHERE nome = %s", (d["modello_dialogo"],)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Modello per i dialoghi non registrato")
    if d.get("divisione_id") is not None:
        if conn.execute("SELECT 1 FROM divisioni WHERE id = %s", (d["divisione_id"],)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Divisione inesistente")
    if d.get("superiore_id") is not None:
        if conn.execute("SELECT 1 FROM agenti WHERE id = %s", (d["superiore_id"],)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Superiore inesistente")
    for cid in d.get("connessioni") or []:
        if conn.execute("SELECT 1 FROM connessioni WHERE id = %s", (cid,)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Connessione inesistente")


def _regola_posizione(dati: dict):
    """Una sentinella sta fuori da dipartimenti e gerarchia. Tutti gli altri (tranne il referente) devono avere un dipartimento o un superiore."""
    if dati.get("sentinella"):
        dati["divisione_id"], dati["superiore_id"], dati["livello"] = None, None, "manager"
        return
    if dati.get("livello") != "referente" and not dati.get("divisione_id") and not dati.get("superiore_id"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Per un agente che non e' una sentinella scegli un dipartimento o un superiore a cui risponde")


def _scrivi_connessioni(conn, agente_id: int, ids: list[int]):
    conn.execute("DELETE FROM agenti_connessioni WHERE agente_id = %s", (agente_id,))
    for cid in dict.fromkeys(ids):
        conn.execute("INSERT INTO agenti_connessioni (agente_id, connessione_id) VALUES (%s, %s)", (agente_id, cid))


def _registra(conn, agente_id: int, azione: str, utente_id: int, dettagli: dict):
    conn.execute(
        "INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) VALUES (%s, %s, %s::jsonb, %s)",
        (agente_id, azione, json.dumps(dettagli), utente_id),
    )


QUERY_AGENTI = """
SELECT a.id, a.nome, a.ruolo, a.livello, a.tipo, a.divisione_id, d.nome AS divisione, a.superiore_id,
       a.sentinella,
       CASE WHEN a.sentinella THEN 'sentinella' WHEN a.tipo = 'sistema' AND a.livello = 'referente' THEN 'referente' ELSE a.livello END AS categoria,
       a.modello, a.istruzioni, a.fascia_dati_max, a.max_token_risposta, a.budget_token_mensile,
       a.accesso_web, a.siti_consentiti, a.max_ricerche, a.attivo, a.modello_dialogo, a.dialoghi_attivi, a.vede_tutto, a.drive_attivo, a.gmail_account_id, a.social_attivo, a.email_attivo, a.rimanda_a, a.crm_attivo, a.canva_attivo, ETICHETTA_SQL AS etichetta,
       COALESCE((SELECT json_agg(json_build_object('titolo', f.titolo, 'istruzioni', f.istruzioni, 'approvazione', f.approvazione,
                                                    'parere_superiore', f.parere_superiore) ORDER BY f.posizione)
                 FROM fasi_agente f WHERE f.agente_id = a.id), '[]'::json) AS fasi,
       COALESCE((SELECT array_agg(x.azienda_id ORDER BY x.azienda_id) FROM agenti_aziende x WHERE x.agente_id = a.id), '{}') AS aziende,
       COALESCE((SELECT array_agg(ac.connessione_id ORDER BY ac.connessione_id)
                 FROM agenti_connessioni ac WHERE ac.agente_id = a.id), '{}') AS connessioni,
       COALESCE((SELECT SUM(COALESCE(c.token_input,0) + COALESCE(c.token_output,0))
                 FROM costi_api c WHERE c.agente_id = a.id
                 AND c.creato_il >= date_trunc('month', NOW())), 0)::bigint AS token_mese,
       COALESCE((SELECT SUM(c.costo_stimato) FROM costi_api c WHERE c.agente_id = a.id
                 AND c.creato_il >= date_trunc('month', NOW())), 0)::float AS costo_mese
FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
""".replace("ETICHETTA_SQL", etichetta.sql())


@router.get("/agenti")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(QUERY_AGENTI + " ORDER BY a.id").fetchall()


def _cambio(conn) -> float:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'cambio_eur_per_usd'").fetchone()
    try:
        return float(r["valore"]) if r else 0.92
    except ValueError:
        return 0.92


@router.get("/opzioni")
def opzioni(_: dict = Depends(solo_titolare)):
    """Voci per i menu a tendina dei moduli."""
    with connessione() as conn:
        return {
            "modelli": conn.execute(
                """SELECT m.nome, f.nome AS fornitore, m.fascia FROM modelli_ai m
                   JOIN fornitori_ai f ON f.id = m.fornitore_id ORDER BY f.nome, m.nome""").fetchall(),
            "divisioni": conn.execute("SELECT id, nome FROM divisioni WHERE attiva ORDER BY id").fetchall(),
            "aziende": conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY id").fetchall(),
            "account_gmail": conn.execute("SELECT id, etichetta, email FROM account_google WHERE 'gmail'=ANY(servizi) ORDER BY etichetta").fetchall(),
            "fornitori": conn.execute(
                """SELECT nome, non_conservazione_attiva, dpa_firmato, fascia_dati_max
                   FROM fornitori_ai ORDER BY nome""").fetchall(),
            "cambio_eur": _cambio(conn),
        }


@router.post("/agenti", status_code=201)
def crea(d: DatiAgente, utente: dict = Depends(solo_titolare)):
    dati = d.model_dump()
    dati["siti_consentiti"] = _pulisci_siti(d.siti_consentiti)
    _regola_posizione(dati)
    with connessione() as conn:
        _valida(conn, dati)
        if conn.execute("SELECT 1 FROM agenti WHERE lower(nome) = lower(%s)", (d.nome,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un agente con questo nome")
        riga = conn.execute(
            """INSERT INTO agenti (divisione_id, superiore_id, nome, ruolo, livello, tipo, modello, fascia_dati_max,
                   istruzioni, max_token_risposta, budget_token_mensile, accesso_web, siti_consentiti,
                   max_ricerche, attivo, modello_dialogo, dialoghi_attivi, sentinella, vede_tutto, drive_attivo, gmail_account_id, social_attivo)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (dati["divisione_id"], dati["superiore_id"], d.nome, d.ruolo, dati["livello"],
             "divisione" if dati["divisione_id"] else "sistema", d.modello, d.fascia_dati_max, d.istruzioni,
             d.max_token_risposta, d.budget_token_mensile, d.accesso_web, dati["siti_consentiti"],
             d.max_ricerche, d.attivo, d.modello_dialogo or None, d.dialoghi_attivi, bool(dati.get("sentinella")), d.vede_tutto, d.drive_attivo, d.gmail_account_id, d.social_attivo),
        ).fetchone()
        if d.email_attivo:
            conn.execute("UPDATE agenti SET email_attivo = TRUE WHERE id = %s", (riga["id"],))
        if d.crm_attivo:
            conn.execute("UPDATE agenti SET crm_attivo = TRUE WHERE id = %s", (riga["id"],))
        if d.canva_attivo:
            conn.execute("UPDATE agenti SET canva_attivo = TRUE WHERE id = %s", (riga["id"],))
        if d.rimanda_a:
            conn.execute("UPDATE agenti SET rimanda_a = %s WHERE id = %s", (d.rimanda_a.strip() or None, riga["id"]))
        _scrivi_connessioni(conn, riga["id"], d.connessioni)
        if d.fasi:
            _scrivi_fasi(conn, riga["id"], [f.model_dump() for f in d.fasi])
        _registra(conn, riga["id"], "agente_creato", utente["id"], {"nome": d.nome})
    return {"id": riga["id"]}


@router.put("/agenti/{agente_id}")
def modifica(agente_id: int, d: ModificaAgente, utente: dict = Depends(solo_titolare)):
    campi = d.model_dump(exclude_unset=True)
    if not campi:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nessuna modifica")
    if campi.get("siti_consentiti") is not None:
        campi["siti_consentiti"] = _pulisci_siti(campi["siti_consentiti"])
    with connessione() as conn:
        attuale = conn.execute("SELECT divisione_id, superiore_id, livello, sentinella FROM agenti WHERE id = %s", (agente_id,)).fetchone()
        if attuale is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        if any(k in campi for k in ("sentinella", "livello", "divisione_id", "superiore_id")):
            risultato = {**attuale, **{k: campi[k] for k in ("sentinella", "livello", "divisione_id", "superiore_id") if k in campi}}
            if campi.get("sentinella") is None:
                risultato["sentinella"] = bool(attuale["sentinella"]) if "sentinella" not in campi else False
            _regola_posizione(risultato)
            for k in ("sentinella", "livello", "divisione_id", "superiore_id"):
                campi[k] = risultato[k]
        _valida(conn, campi)
        if campi.get("superiore_id") == agente_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Un agente non puo' rispondere a se stesso")
        if campi.get("superiore_id") is not None and conn.execute(
                """WITH RECURSIVE sotto AS (SELECT id FROM agenti WHERE superiore_id = %s
                      UNION SELECT x.id FROM agenti x JOIN sotto s ON x.superiore_id = s.id)
                   SELECT 1 FROM sotto WHERE id = %s""", (agente_id, campi["superiore_id"])).fetchone():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Il superiore scelto dipende gia' da questo agente: si creerebbe un giro chiuso")
        if "nome" in campi and conn.execute(
                "SELECT 1 FROM agenti WHERE lower(nome) = lower(%s) AND id <> %s", (campi["nome"], agente_id)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un agente con questo nome")
        ids = campi.pop("connessioni", None)
        fasi = campi.pop("fasi", None)
        if "istruzioni" in campi:
            from . import competenze_base
            competenze_base.salva_storico(conn, agente_id, "modifica", campi["istruzioni"])      # il testo precedente non si perde
        if "divisione_id" in campi:
            campi["tipo"] = "divisione" if campi["divisione_id"] else "sistema"
        if campi:
            nomi = list(campi)  # nomi di colonna fissi dal modello, mai dall'input diretto
            conn.execute(
                "UPDATE agenti SET " + ", ".join(f"{n} = %s" for n in nomi) + " WHERE id = %s",
                [campi[n] for n in nomi] + [agente_id],
            )
        if ids is not None:
            _scrivi_connessioni(conn, agente_id, ids)
        if fasi is not None:
            _scrivi_fasi(conn, agente_id, fasi)
        _registra(conn, agente_id, "agente_modificato", utente["id"],
                  {"campi": sorted(list(campi) + (["connessioni"] if ids is not None else []) + (["fasi"] if fasi is not None else []))})
    return {"stato": "ok"}


class DatiConnessione(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    tipo: str = "sito"
    indirizzo: str | None = Field(default=None, max_length=300)
    descrizione: str | None = Field(default=None, max_length=500)
    stato: str = "da_configurare"


def _valida_connessione(d: DatiConnessione):
    if d.tipo not in ("sito", "app", "altro"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo non valido")
    if d.stato not in ("da_configurare", "attiva", "spenta"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Stato non valido")


@router.get("/connessioni")
def elenco_connessioni(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT c.id, c.nome, c.tipo, c.indirizzo, c.descrizione, c.stato,
                      COALESCE((SELECT array_agg(ac.agente_id ORDER BY ac.agente_id)
                                FROM agenti_connessioni ac WHERE ac.connessione_id = c.id), '{}') AS agenti,
                      (s.connessione_id IS NOT NULL) AS accesso_configurato, s.dominio, s.url_login, s.fascia_contenuto, s.max_pagine
               FROM connessioni c LEFT JOIN accessi_siti s ON s.connessione_id = c.id ORDER BY c.id""").fetchall()


@router.post("/connessioni", status_code=201)
def crea_connessione(d: DatiConnessione, _: dict = Depends(solo_titolare)):
    _valida_connessione(d)
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM connessioni WHERE lower(nome) = lower(%s)", (d.nome,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' una connessione con questo nome")
        riga = conn.execute(
            "INSERT INTO connessioni (nome, tipo, indirizzo, descrizione, stato) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (d.nome, d.tipo, d.indirizzo, d.descrizione, d.stato)).fetchone()
    return {"id": riga["id"]}


@router.put("/connessioni/{cid}")
def modifica_connessione(cid: int, d: DatiConnessione, _: dict = Depends(solo_titolare)):
    _valida_connessione(d)
    with connessione() as conn:
        r = conn.execute(
            "UPDATE connessioni SET nome=%s, tipo=%s, indirizzo=%s, descrizione=%s, stato=%s WHERE id=%s RETURNING id",
            (d.nome, d.tipo, d.indirizzo, d.descrizione, d.stato, cid)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connessione inesistente")
    return {"stato": "ok"}


@router.delete("/connessioni/{cid}")
def elimina_connessione(cid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM connessioni WHERE id = %s RETURNING id", (cid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connessione inesistente")
    return {"stato": "ok"}


class RichiestaAssistente(BaseModel):
    richiesta: str = Field(min_length=1, max_length=4000)
    scheda: dict = {}
    conversazione: list[dict] = []


@router.post("/assistente-prompt")
def assistente_prompt(d: RichiestaAssistente, _: dict = Depends(solo_titolare)):
    from . import assistente_prompt as ap
    from .fornitori import ErroreFornitore
    try:
        return ap.chiedi(d.richiesta, d.scheda, d.conversazione)
    except ap.AssistenteNonDisponibile as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ErroreFornitore as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


def _prova_una(agente_id: int) -> dict:
    import time

    from .cassaforte import CassaforteNonConfigurata
    from .esecuzione import EsecuzioneBloccata, esegui_agente
    from .fornitori import ErroreFornitore
    from .navigatore import ErroreNavigazione
    t0 = time.time()
    try:
        r = esegui_agente(agente_id, "Prova di funzionamento: presentati in due frasi dicendo che cosa fai e per quali imprese lavori.", "pubblico", None)
    except (EsecuzioneBloccata, ErroreFornitore, CassaforteNonConfigurata, ErroreNavigazione) as e:
        return {"riuscita": False, "errore": str(e)[:300], "secondi": round(time.time() - t0, 1)}
    except Exception as e:  # noqa: BLE001 - la prova deve sempre dare un esito, mai un errore generico
        return {"riuscita": False, "errore": f"Errore imprevisto ({type(e).__name__})", "secondi": round(time.time() - t0, 1)}
    with connessione() as conn:
        ultimo = conn.execute("SELECT dettagli FROM registro_azioni WHERE agente_id=%s AND azione='risposta_vuota' ORDER BY id DESC LIMIT 1", (agente_id,)).fetchone()
    vuota = r["risposta"].startswith("(L'agente non ha scritto nessuna risposta")
    return {"riuscita": not vuota, "risposta": r["risposta"], "token_input": r["token_input"], "token_output": r["token_output"],
            "secondi": round(time.time() - t0, 1), "dettagli": (ultimo["dettagli"] if (vuota and ultimo) else None)}


@router.post("/agenti/{agente_id}/prova")
def prova_agente(agente_id: int, _=Depends(solo_titolare)):
    """Manda all'agente una domanda semplice e mostra la risposta cosi' com'e': serve a capire se risponde e con quali limiti."""
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM agenti WHERE id = %s", (agente_id,)).fetchone():
            raise HTTPException(404, "Agente non trovato")
    return _prova_una(agente_id)


@router.post("/salute-agenti")
def salute_agenti(_=Depends(solo_titolare)):
    """Prova tutti gli agenti accesi, quattro alla volta, con una domanda breve. Costa qualche migliaio di token in tutto."""
    from concurrent.futures import ThreadPoolExecutor
    with connessione() as conn:
        ag = conn.execute("""SELECT a.id, a.nome, a.ruolo, a.attivo, a.modello, d.nome AS divisione FROM agenti a
                             LEFT JOIN divisioni d ON d.id = a.divisione_id ORDER BY d.nome NULLS FIRST, a.nome""").fetchall()
    accesi = [a for a in ag if a["attivo"]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        esiti = dict(zip([a["id"] for a in accesi], pool.map(lambda a: _prova_una(a["id"]), accesi)))
    righe = []
    for a in ag:
        e = esiti.get(a["id"])
        if e is None:
            stato = "spento"
        elif e["riuscita"]:
            stato = "ok"
        elif e.get("dettagli") is not None or not e.get("errore"):
            stato = "vuota"
        elif "sospeso" in e["errore"].lower() or "budget" in e["errore"].lower() or "tetto" in e["errore"].lower() or "riservatezza" in e["errore"].lower() or "garanzie" in e["errore"].lower():
            stato = "bloccato"
        else:
            stato = "errore"
        righe.append({"id": a["id"], "nome": a["nome"], "ruolo": a["ruolo"], "divisione": a["divisione"], "modello": a["modello"], "stato": stato,
                      "secondi": e["secondi"] if e else None, "token": (e.get("token_input", 0) + e.get("token_output", 0)) if e else 0,
                      "anteprima": (e.get("risposta") or "")[:140] if e else "", "errore": (e.get("errore") if e else None),
                      "dettagli": (e.get("dettagli") if e else None)})
    conteggio = {k: sum(1 for r in righe if r["stato"] == k) for k in ("ok", "vuota", "errore", "bloccato", "spento")}
    return {"agenti": righe, "conteggio": conteggio}


# ---- competenze di base: storico delle istruzioni ed elenco scaricabile
@router.get("/agenti/{agente_id}/istruzioni-storico")
def istruzioni_storico(agente_id: int, _: dict = Depends(solo_titolare)):
    from . import competenze_base
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM agenti WHERE id = %s", (agente_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        return {"versioni": competenze_base.storico(conn, agente_id)}


@router.get("/competenze/esporta")
def esporta_competenze(_: dict = Depends(solo_titolare)):
    from fastapi.responses import Response
    from . import competenze_base
    with connessione() as conn:
        testo = competenze_base.esporta_markdown(conn)
    return Response(content=testo, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="agenti-competenze.md"'})
