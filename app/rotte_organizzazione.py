"""Aziende, divisioni (dipartimenti), assegnazioni e vista d'insieme dell'organigramma (solo titolare)."""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione")

COLORE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _colore(c: str):
    if not COLORE.match(c):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Colore non valido (es. #22d3ee)")


class DatiAzienda(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    territorio: str | None = Field(default=None, max_length=200)
    profilo: str | None = Field(default=None, max_length=4000)
    criteri_interesse: str | None = Field(default=None, max_length=4000)
    colore: str = "#22d3ee"
    attiva: bool = True


class DatiDivisione(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    descrizione: str | None = Field(default=None, max_length=500)
    azienda_id: int | None = None          # compatibilita': se manca "aziende" vale come unica azienda
    aziende: list[int] | None = None       # tutte le aziende servite dal dipartimento
    colore: str = "#a78bfa"
    attiva: bool = True
    gestisce_posta: bool = False           # dipartimento Corrispondenza: i suoi agenti possono avere caselle di posta in esclusiva


@router.get("/aziende")
def elenco_aziende(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT a.id, a.nome, a.territorio, a.profilo, a.criteri_interesse, a.colore, a.attiva, a.allineamento, a.allineamento_il,
                      COALESCE((SELECT array_agg(x.agente_id ORDER BY x.agente_id) FROM agenti_aziende x WHERE x.azienda_id = a.id), '{}') AS agenti,
                      COALESCE((SELECT array_agg(x.divisione_id ORDER BY x.divisione_id) FROM divisioni_aziende x WHERE x.azienda_id = a.id), '{}') AS divisioni
               FROM aziende a ORDER BY a.id""").fetchall()


@router.post("/aziende", status_code=201)
def crea_azienda(d: DatiAzienda, _: dict = Depends(solo_titolare)):
    _colore(d.colore)
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM aziende WHERE lower(nome) = lower(%s)", (d.nome,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un'azienda con questo nome")
        r = conn.execute("INSERT INTO aziende (nome, territorio, profilo, criteri_interesse, colore, attiva) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                         (d.nome, d.territorio, d.profilo, d.criteri_interesse, d.colore, d.attiva)).fetchone()
    return {"id": r["id"]}


@router.put("/aziende/{aid}")
def modifica_azienda(aid: int, d: DatiAzienda, _: dict = Depends(solo_titolare)):
    _colore(d.colore)
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM aziende WHERE lower(nome) = lower(%s) AND id <> %s", (d.nome, aid)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un'azienda con questo nome")
        r = conn.execute("UPDATE aziende SET nome=%s, territorio=%s, profilo=%s, criteri_interesse=%s, colore=%s, attiva=%s WHERE id=%s RETURNING id",
                         (d.nome, d.territorio, d.profilo, d.criteri_interesse, d.colore, d.attiva, aid)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Azienda inesistente")
    return {"stato": "ok"}


class Allineamento(BaseModel):
    testo: str = Field(max_length=20000)


@router.put("/aziende/{aid}/allineamento")
def allineamento_azienda(aid: int, d: Allineamento, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE aziende SET allineamento=%s, allineamento_il=NOW() WHERE id=%s RETURNING id", (d.testo.strip(), aid)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Azienda inesistente")
    return {"stato": "ok"}


@router.delete("/aziende/{aid}")
def elimina_azienda(aid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        usata = conn.execute(
            """SELECT (SELECT count(*) FROM compiti WHERE azienda_id = %(a)s) + (SELECT count(*) FROM opportunita WHERE azienda_id = %(a)s)
                      + (SELECT count(*) FROM memoria WHERE azienda_id = %(a)s) AS n""", {"a": aid}).fetchone()["n"]
        if usata:
            raise HTTPException(status.HTTP_409_CONFLICT, "L'azienda ha compiti, opportunita' o memoria collegati: disattivala invece di eliminarla")
        r = conn.execute("DELETE FROM aziende WHERE id = %s RETURNING id", (aid,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Azienda inesistente")
    return {"stato": "ok"}


class AssegnaAziende(BaseModel):
    aziende: list[int]


@router.put("/agenti/{agente_id}/aziende")
def assegna_aziende(agente_id: int, d: AssegnaAziende, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM agenti WHERE id = %s", (agente_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente inesistente")
        for aid in d.aziende:
            if conn.execute("SELECT 1 FROM aziende WHERE id = %s", (aid,)).fetchone() is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Azienda inesistente")
        conn.execute("DELETE FROM agenti_aziende WHERE agente_id = %s", (agente_id,))
        for aid in dict.fromkeys(d.aziende):
            conn.execute("INSERT INTO agenti_aziende (agente_id, azienda_id) VALUES (%s,%s)", (agente_id, aid))
    return {"stato": "ok"}


def _aziende_scelte(d: DatiDivisione) -> list[int]:
    return list(dict.fromkeys(d.aziende if d.aziende is not None else ([d.azienda_id] if d.azienda_id is not None else [])))


def _controlla_azienda(conn, d: DatiDivisione):
    _colore(d.colore)
    for i in _aziende_scelte(d):
        if conn.execute("SELECT 1 FROM aziende WHERE id = %s", (i,)).fetchone() is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Azienda inesistente")


def _salva_aziende(conn, did: int, d: DatiDivisione):
    scelte = _aziende_scelte(d)
    conn.execute("DELETE FROM divisioni_aziende WHERE divisione_id = %s", (did,))
    for i in scelte:
        conn.execute("INSERT INTO divisioni_aziende (divisione_id, azienda_id) VALUES (%s,%s)", (did, i))
    conn.execute("UPDATE divisioni SET azienda_id = %s WHERE id = %s", (scelte[0] if scelte else None, did))


@router.get("/divisioni")
def elenco_divisioni(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            """SELECT d.id, d.nome, d.descrizione, d.azienda_id, d.colore, d.attiva, d.gestisce_posta,
                      COALESCE((SELECT array_agg(x.azienda_id ORDER BY x.azienda_id) FROM divisioni_aziende x WHERE x.divisione_id = d.id), '{}') AS aziende,
                      (SELECT count(*) FROM agenti a WHERE a.divisione_id = d.id) AS agenti
               FROM divisioni d ORDER BY d.id""").fetchall()


@router.post("/divisioni", status_code=201)
def crea_divisione(d: DatiDivisione, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _controlla_azienda(conn, d)
        if conn.execute("SELECT 1 FROM divisioni WHERE lower(nome) = lower(%s)", (d.nome,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un dipartimento con questo nome")
        r = conn.execute("INSERT INTO divisioni (nome, descrizione, azienda_id, colore, attiva, gestisce_posta) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                         (d.nome, d.descrizione, None, d.colore, d.attiva, d.gestisce_posta)).fetchone()
        _salva_aziende(conn, r["id"], d)
    return {"id": r["id"]}


@router.put("/divisioni/{did}")
def modifica_divisione(did: int, d: DatiDivisione, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        _controlla_azienda(conn, d)
        if conn.execute("SELECT 1 FROM divisioni WHERE lower(nome) = lower(%s) AND id <> %s", (d.nome, did)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, "Esiste gia' un dipartimento con questo nome")
        r = conn.execute("UPDATE divisioni SET nome=%s, descrizione=%s, azienda_id=%s, colore=%s, attiva=%s, gestisce_posta=%s WHERE id=%s RETURNING id",
                         (d.nome, d.descrizione, None, d.colore, d.attiva, d.gestisce_posta, did)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dipartimento inesistente")
        _salva_aziende(conn, did, d)
    return {"stato": "ok"}


@router.delete("/divisioni/{did}")
def elimina_divisione(did: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        n = conn.execute("SELECT count(*) AS n FROM agenti WHERE divisione_id = %s", (did,)).fetchone()["n"]
        if n:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Ci sono {n} agenti in questo dipartimento: spostali prima")
        legati = conn.execute("SELECT (SELECT count(*) FROM compiti WHERE divisione_id = %(d)s) AS n", {"d": did}).fetchone()["n"]
        if legati:
            raise HTTPException(status.HTTP_409_CONFLICT, "Il dipartimento ha compiti collegati: disattivalo invece di eliminarlo")
        r = conn.execute("DELETE FROM divisioni WHERE id = %s RETURNING id", (did,)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dipartimento inesistente")
    return {"stato": "ok"}


@router.get("/organigramma")
def organigramma(_: dict = Depends(solo_titolare)):
    """Dati per il grafico: aziende, dipartimenti e agenti con stato reale (carico = uso del tetto mensile)."""
    with connessione() as conn:
        agenti = conn.execute(
            """SELECT a.id, a.nome, a.ruolo, a.livello, a.tipo, a.sentinella, a.superiore_id, a.divisione_id, a.attivo, a.modello,
                      COALESCE((SELECT array_agg(x.azienda_id ORDER BY x.azienda_id) FROM agenti_aziende x WHERE x.agente_id = a.id), '{}') AS aziende,
                      COALESCE((SELECT array_agg(pa.progetto_id ORDER BY pa.progetto_id) FROM progetti_agenti pa WHERE pa.agente_id = a.id), '{}') AS progetti,
                      EXISTS (SELECT 1 FROM sospensioni_agenti s WHERE s.agente_id = a.id AND s.riattivato_il IS NULL) AS sospeso,
                      (SELECT count(*) FROM richieste_informazioni r WHERE r.agente_id = a.id AND r.stato = 'aperta') AS richieste,
                      (SELECT count(*) FROM richieste_informazioni r WHERE r.agente_id = a.id AND r.stato = 'aperta' AND r.bloccante) AS bloccanti,
                      COALESCE((SELECT SUM(COALESCE(c.token_input,0) + COALESCE(c.token_output,0)) FROM costi_api c
                                WHERE c.agente_id = a.id AND c.creato_il >= date_trunc('month', NOW())), 0)::bigint AS token_mese,
                      a.budget_token_mensile
               FROM agenti a ORDER BY a.id""").fetchall()
        for a in agenti:
            a["categoria"] = "sentinella" if a["sentinella"] else "referente" if a["tipo"] == "sistema" and a["livello"] == "referente" else a["livello"]
            if a["bloccanti"]:
                a["stato"] = "difficolta"
            elif a["sospeso"] or a["richieste"] or (a["budget_token_mensile"] and a["token_mese"] >= 0.85 * a["budget_token_mensile"]):
                a["stato"] = "pressione"
            else:
                a["stato"] = "sereno"
            a["carico"] = min(100, round(100 * a["token_mese"] / a["budget_token_mensile"])) if a["budget_token_mensile"] else None
        return {
            "aziende": conn.execute("SELECT id, nome, colore, attiva FROM aziende ORDER BY id").fetchall(),
            "divisioni": conn.execute("""SELECT d.id, d.nome, d.azienda_id, d.colore, d.attiva,
                                         COALESCE((SELECT array_agg(x.azienda_id ORDER BY x.azienda_id) FROM divisioni_aziende x WHERE x.divisione_id = d.id), '{}') AS aziende
                                  FROM divisioni d ORDER BY d.id""").fetchall(),
            "progetti": conn.execute("SELECT id, nome FROM progetti WHERE NOT archiviato ORDER BY nome").fetchall(),
            "agenti": agenti,
        }


@router.get("/organigramma/impulsi")
def impulsi(dopo: datetime | None = None, _: dict = Depends(solo_titolare)):
    """Interazioni avvenute dopo l'istante indicato (id 0 = Lorenzo al centro). Alimenta i raggi di luce del grafico."""
    with connessione() as conn:
        adesso = conn.execute("SELECT NOW() AS t").fetchone()["t"]
        if dopo is None:
            return {"adesso": adesso.isoformat(), "impulsi": []}
        righe = conn.execute(
            """SELECT tipo, da, a, t FROM (
                 SELECT 'messaggio' AS tipo, m.da_agente_id AS da, m.a_agente_id AS a, m.creato_il AS t
                   FROM messaggi_agenti m WHERE m.creato_il > %(d)s AND m.da_agente_id IS NOT NULL AND m.a_agente_id IS NOT NULL
                 UNION ALL
                 SELECT 'richiesta', r.agente_id, 0, r.creata_il FROM richieste_informazioni r WHERE r.creata_il > %(d)s
                 UNION ALL
                 SELECT 'chat', 0, x.agente_id, x.creata_il FROM registro_azioni x
                   WHERE x.azione = 'risposta_generata' AND x.agente_id IS NOT NULL AND x.creata_il > %(d)s
               ) u ORDER BY t LIMIT 100""", {"d": dopo}).fetchall()
        return {"adesso": adesso.isoformat(),
                "impulsi": [{"tipo": r["tipo"], "da": r["da"], "a": r["a"], "t": r["t"].isoformat()} for r in righe]}


@router.get("/dashboard/statistiche")
def statistiche(_: dict = Depends(solo_titolare)):
    """Numeri della barra in alto della Dashboard: consumi, attivita' e stato dell'organizzazione."""
    with connessione() as conn:
        r = conn.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN creato_il >= date_trunc('day', NOW()) THEN COALESCE(token_input,0)+COALESCE(token_output,0) END),0)::bigint AS token_oggi,
                 COALESCE(SUM(CASE WHEN creato_il >= date_trunc('day', NOW()) THEN COALESCE(costo_stimato,0) END),0)::float AS costo_oggi,
                 COALESCE(SUM(COALESCE(token_input,0)+COALESCE(token_output,0)),0)::bigint AS token_mese,
                 COALESCE(SUM(COALESCE(costo_stimato,0)),0)::float AS costo_mese,
                 COALESCE(SUM(COALESCE(token_input,0)),0)::bigint AS input_mese,
                 COALESCE(SUM(COALESCE(token_output,0)),0)::bigint AS output_mese
               FROM costi_api WHERE creato_il >= date_trunc('month', NOW())""").fetchone()
        r["messaggi_oggi"] = conn.execute("SELECT count(*) AS n FROM messaggi_agenti WHERE creato_il >= date_trunc('day', NOW())").fetchone()["n"]
        r["agenti_attivi"] = conn.execute("SELECT count(*) AS n FROM agenti WHERE attivo").fetchone()["n"]
        r["agenti_totali"] = conn.execute("SELECT count(*) AS n FROM agenti").fetchone()["n"]
        r["richieste_aperte"] = conn.execute("SELECT count(*) AS n FROM richieste_informazioni WHERE stato='aperta'").fetchone()["n"]
        r["richieste_bloccanti"] = conn.execute("SELECT count(*) AS n FROM richieste_informazioni WHERE stato='aperta' AND bloccante").fetchone()["n"]
        r["limite_dialoghi_giorno"] = int(conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave='dialoghi_budget_token_giornaliero'").fetchone()["valore"] or 0) \
            if conn.execute("SELECT 1 FROM impostazioni_sistema WHERE chiave='dialoghi_budget_token_giornaliero'").fetchone() else 0
        r["token_dialoghi_oggi"] = int(conn.execute(
            "SELECT COALESCE(SUM(COALESCE(token_input,0)+COALESCE(token_output,0)),0) AS t FROM costi_api WHERE tipo='dialogo' AND creato_il >= date_trunc('day', NOW())").fetchone()["t"])
        r["giorni"] = conn.execute(
            """SELECT to_char(g::date, 'DD/MM') AS giorno,
                      COALESCE((SELECT SUM(COALESCE(token_input,0)+COALESCE(token_output,0)) FROM costi_api c WHERE c.creato_il >= g AND c.creato_il < g + INTERVAL '1 day'),0)::bigint AS token
               FROM generate_series(date_trunc('day', NOW()) - INTERVAL '6 days', date_trunc('day', NOW()), INTERVAL '1 day') g ORDER BY g""").fetchall()
        r["top_agenti"] = conn.execute(
            """SELECT a.nome, SUM(COALESCE(c.token_input,0)+COALESCE(c.token_output,0))::bigint AS token
               FROM costi_api c JOIN agenti a ON a.id = c.agente_id WHERE c.creato_il >= date_trunc('month', NOW())
               GROUP BY a.nome ORDER BY token DESC LIMIT 3""").fetchall()
        return r
