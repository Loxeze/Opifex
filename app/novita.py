"""Fase 3: stato in tempo reale degli agenti (cosa fanno, ultima attivita', formazione in corso) e contatori delle novita' non viste.
Sola lettura del registro eventi e delle tabelle: nessuna chiamata ai modelli, nessun costo."""
from fastapi import APIRouter, Depends, HTTPException, status

from .db import connessione
from .permessi import solo_titolare, utente_corrente
from . import plancia

router = APIRouter(tags=["novita"])
AREE = ("progetti", "ginnasio", "documenti")


def stato_agenti(conn) -> dict:
    out: dict[int, dict] = {}
    for x in plancia.lavoro_adesso(conn)["al_lavoro"]:
        passi = conn.execute(
            """SELECT tipo, left(dettaglio, 120) AS dettaglio, EXTRACT(EPOCH FROM (NOW() - creato_il))::int AS fa_s FROM eventi_lavoro
               WHERE agente_id = %s AND tipo IN ('strumento','fase','errore_strumento') AND creato_il > NOW() - make_interval(secs => %s) ORDER BY id DESC LIMIT 8""",
            (x["agente_id"], x["da_secondi"] + 5)).fetchall()
        out[x["agente_id"]] = {"lavoro": {"sta_facendo": x["sta_facendo"][:160], "da_secondi": x["da_secondi"], "progetto": x["progetto"], "compito": x["compito"],
                                          "passi": [{"tipo": p["tipo"], "dettaglio": p["dettaglio"], "fa_s": p["fa_s"]} for p in reversed(passi)]}}
    for r in conn.execute("""SELECT agente_id, max(creato_il) AS u, EXTRACT(EPOCH FROM (NOW() - max(creato_il)))::int AS fa_s,
                                    (array_agg(tipo ORDER BY id DESC))[1] AS tipo
                             FROM eventi_lavoro WHERE tipo IN ('fine','errore') AND agente_id IS NOT NULL GROUP BY agente_id""").fetchall():
        out.setdefault(r["agente_id"], {})["ultimo"] = {"fa_s": r["fa_s"], "esito": "errore" if r["tipo"] == "errore" else "concluso"}
    for r in conn.execute("""SELECT f.agente_id, f.id, f.competenza_nome, f.livello, f.fase, f.token_usati, f.stato,
                                    (SELECT count(*) FROM formazione_materiale m WHERE m.richiesta_id = f.id) AS documenti
                             FROM richieste_formazione f WHERE f.agente_id IS NOT NULL AND f.stato IN ('in_corso','appunti_pronti','da_approvare')""").fetchall():
        out.setdefault(r["agente_id"], {})["formazione"] = {"richiesta_id": r["id"], "competenza": r["competenza_nome"], "livello": r["livello"], "fase": r["fase"] or r["stato"],
                                                            "stato": r["stato"], "documenti": r["documenti"], "token": r["token_usati"]}
    return out


def _visto(conn, utente_id: int, area: str):
    r = conn.execute("SELECT visto_il FROM novita_viste WHERE utente_id = %s AND area = %s", (utente_id, area)).fetchone()
    if r:
        return r["visto_il"]
    conn.execute("INSERT INTO novita_viste (utente_id, area) VALUES (%s,%s) ON CONFLICT DO NOTHING", (utente_id, area))   # prima volta: si parte da zero, nessun arretrato
    return conn.execute("SELECT visto_il FROM novita_viste WHERE utente_id = %s AND area = %s", (utente_id, area)).fetchone()["visto_il"]


def conteggi(conn, utente_id: int) -> dict:
    v = {a: _visto(conn, utente_id, a) for a in AREE}
    n = lambda q, *p: conn.execute(q, p).fetchone()["n"]
    return {
        "progetti": n("""SELECT (SELECT count(*) FROM task WHERE completata_il > %s) + (SELECT count(*) FROM task WHERE creato_da_agente_id IS NOT NULL AND creata_il > %s) AS n""", v["progetti"], v["progetti"]),
        "ginnasio": n("""SELECT (SELECT count(*) FROM richieste_formazione WHERE stato IN ('appunti_pronti','da_approvare'))
                              + (SELECT count(*) FROM competenze_livelli WHERE approvata_il > %s) AS n""", v["ginnasio"]),
        "documenti": n("SELECT count(*) AS n FROM documenti WHERE creato_il > %s", v["documenti"]),
    }


@router.get("/gestione/agenti-stato")
def agenti_stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return stato_agenti(conn)


@router.get("/novita")
def novita(utente: dict = Depends(utente_corrente)):
    if utente["ruolo_globale"] != "titolare":
        return {a: 0 for a in AREE}
    with connessione() as conn:
        return conteggi(conn, utente["id"])


@router.post("/novita/{area}/visto")
def visto(area: str, utente: dict = Depends(utente_corrente)):
    if area not in AREE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Area sconosciuta")
    with connessione() as conn:
        conn.execute("""INSERT INTO novita_viste (utente_id, area, visto_il) VALUES (%s,%s,NOW()) ON CONFLICT (utente_id, area) DO UPDATE SET visto_il = NOW()""", (utente["id"], area))
    return {"ok": True}
