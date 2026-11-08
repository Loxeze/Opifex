"""Cruscotto del singolo progetto: materiale prodotto dagli agenti, calendario, Gantt, attivita' recente e riunione con i soggetti coinvolti."""
from fastapi import APIRouter, Depends, HTTPException, status

from . import call_riunioni
from .db import connessione
from .permessi import solo_titolare, utente_corrente
from .rotte_progetto import _puo_vedere

router = APIRouter(tags=["progetto"])
MIN_CARATTERI_PRODOTTO = 150      # un commento di agente conta come "materiale prodotto" solo se e' un testo vero, non un "fatto"


def _progetto(conn, pid, u):
    p = conn.execute("SELECT id, nome, descrizione, allineamento, azienda_id, pm_agente_id FROM progetti WHERE id = %s AND eliminato_il IS NULL", (pid,)).fetchone()
    if p is None or not _puo_vedere(conn, u, p):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
    return p


def soggetti(conn, pid: int, p: dict) -> list[dict]:
    """I manager coinvolti: il project manager, i manager di riferimento degli agenti assegnati e chi li guida; solo quelli che possono sedere a una riunione."""
    ammessi = {m["id"]: m for m in call_riunioni.manager_disponibili(conn)}
    ids: list[int] = []
    def aggiungi(i):
        if i in ammessi and i not in ids:
            ids.append(i)
    if p.get("pm_agente_id"):
        aggiungi(p["pm_agente_id"])
    for r in conn.execute("""SELECT DISTINCT a.id, a.livello, a.superiore_id FROM agenti a
                             WHERE a.id IN (SELECT agente_id FROM progetti_agenti WHERE progetto_id = %(p)s
                                            UNION SELECT assegnato_agente_id FROM task WHERE progetto_id = %(p)s AND assegnato_agente_id IS NOT NULL)""", {"p": pid}).fetchall():
        aggiungi(r["id"] if r["id"] in ammessi else r["superiore_id"])
    return [{"id": i, "nome": ammessi[i]["nome"], "ruolo": ammessi[i]["ruolo"], "reparto": ammessi[i]["reparto"]} for i in ids]


@router.get("/progetti/{pid}/cruscotto")
def cruscotto(pid: int, u: dict = Depends(utente_corrente)):
    tit = u["ruolo_globale"] == "titolare"
    with connessione() as conn:
        p = _progetto(conn, pid, u)
        commenti = conn.execute("""SELECT c.id, c.task_id, t.titolo AS task, a.id AS agente_id, a.nome AS agente, c.testo, c.creato_il
                                   FROM task_commenti c JOIN task t ON t.id = c.task_id JOIN agenti a ON a.id = c.agente_id
                                   WHERE t.progetto_id = %s AND length(c.testo) >= %s ORDER BY c.creato_il DESC LIMIT 40""", (pid, MIN_CARATTERI_PRODOTTO)).fetchall()
        documenti = conn.execute("""SELECT d.id, d.nome, d.nome_file, d.caratteri, d.fascia_dati, d.creato_il, ag.nome AS agente,
                                           (d.id IN (SELECT documento_id FROM progetti_documenti WHERE progetto_id = %(p)s)) AS di_base
                                    FROM documenti d LEFT JOIN agenti ag ON ag.id = d.creato_da_agente_id
                                    WHERE d.id IN (SELECT documento_id FROM progetti_documenti WHERE progetto_id = %(p)s
                                                   UNION SELECT td.documento_id FROM task_documenti td JOIN task t ON t.id = td.task_id WHERE t.progetto_id = %(p)s)
                                    ORDER BY d.creato_il DESC LIMIT 40""", {"p": pid}).fetchall() if tit else []
        materiale = sorted([{"tipo": "testo", **c} for c in commenti] + [{"tipo": "documento", **d} for d in documenti], key=lambda x: x["creato_il"], reverse=True)[:40]
        for m in materiale:
            if m["tipo"] == "testo":
                m["anteprima"] = " ".join(m["testo"].split())[:260]
        task = conn.execute("""SELECT t.id, t.titolo, t.stato, t.priorita, t.creata_il, t.scadenza, t.completata_il, t.padre_id,
                                      COALESCE(a.nome, us.nome) AS responsabile, (t.scadenza < CURRENT_DATE AND t.stato <> 'completata') AS in_ritardo
                               FROM task t LEFT JOIN agenti a ON a.id = t.assegnato_agente_id LEFT JOIN utenti us ON us.id = t.assegnato_utente_id
                               WHERE t.progetto_id = %s ORDER BY t.creata_il LIMIT 300""", (pid,)).fetchall()
        milestone = conn.execute("SELECT id, titolo, scadenza, raggiunta_il FROM milestone WHERE progetto_id = %s ORDER BY scadenza NULLS LAST, id", (pid,)).fetchall()
        riunioni = conn.execute("""SELECT id, titolo, stato, COALESCE(programmata_il, creato_il) AS quando FROM tavoli WHERE progetto_id = %s AND tipo = 'call'
                                   ORDER BY COALESCE(programmata_il, creato_il) DESC LIMIT 30""", (pid,)).fetchall() if tit else []
        attivita = conn.execute("""(SELECT 'commento' AS tipo, c.creato_il AS quando, t.titolo AS oggetto, a.nome AS chi FROM task_commenti c JOIN task t ON t.id = c.task_id
                                        JOIN agenti a ON a.id = c.agente_id WHERE t.progetto_id = %(p)s)
                                    UNION ALL (SELECT 'completata', t.completata_il, t.titolo, COALESCE(a.nome, us.nome) FROM task t LEFT JOIN agenti a ON a.id = t.assegnato_agente_id
                                        LEFT JOIN utenti us ON us.id = t.assegnato_utente_id WHERE t.progetto_id = %(p)s AND t.completata_il IS NOT NULL)
                                    UNION ALL (SELECT 'milestone', m.raggiunta_il, m.titolo, NULL FROM milestone m WHERE m.progetto_id = %(p)s AND m.raggiunta_il IS NOT NULL)
                                    ORDER BY quando DESC LIMIT 15""", {"p": pid}).fetchall()
        sogg = soggetti(conn, pid, p) if tit else []
        aperte = [t for t in task if t["stato"] != "completata"]
        return {"materiale": materiale, "task": task, "milestone": milestone, "riunioni": riunioni, "attivita": attivita, "soggetti": sogg,
                "numeri": {"prodotti": len(materiale), "aperte": len(aperte), "in_ritardo": sum(1 for t in aperte if t["in_ritardo"]),
                           "scadenze_7g": sum(1 for t in aperte if t["scadenza"] and 0 <= (t["scadenza"] - __import__("datetime").date.today()).days <= 7)}}


@router.get("/progetti/{pid}/materiale/{commento_id}")
def leggi_testo(pid: int, commento_id: int, u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        _progetto(conn, pid, u)
        c = conn.execute("""SELECT c.id, t.titolo AS task, a.nome AS agente, c.testo, c.creato_il FROM task_commenti c JOIN task t ON t.id = c.task_id
                            JOIN agenti a ON a.id = c.agente_id WHERE c.id = %s AND t.progetto_id = %s""", (commento_id, pid)).fetchone()
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Contenuto non trovato")
        return c


def _odg(conn, p: dict) -> str:
    righe = [f"Progetto «{p['nome']}». " + " ".join(str(p.get("descrizione") or "").split())[:500]]
    rit = conn.execute("SELECT titolo FROM task WHERE progetto_id = %s AND stato <> 'completata' AND scadenza < CURRENT_DATE ORDER BY scadenza LIMIT 6", (p["id"],)).fetchall()
    if rit:
        righe.append("Task in ritardo: " + "; ".join(t["titolo"] for t in rit))
    pross = conn.execute("""SELECT titolo, scadenza FROM milestone WHERE progetto_id = %s AND raggiunta_il IS NULL ORDER BY scadenza NULLS LAST LIMIT 4""", (p["id"],)).fetchall()
    if pross:
        righe.append("Milestone aperte: " + "; ".join(m["titolo"] + (f" (entro {m['scadenza']:%d/%m/%Y})" if m["scadenza"] else "") for m in pross))
    righe.append("Si parla dello stato di avanzamento del progetto e di cosa serve per andare avanti.")
    return "\n".join(righe)[:2500]


@router.post("/gestione/progetti/{pid}/riunione", status_code=201)
def avvia_riunione(pid: int, u: dict = Depends(solo_titolare)):
    """Crea e apre una call con i manager coinvolti nel progetto, con l'ordine del giorno preso dai dati del progetto."""
    with connessione() as conn:
        p = _progetto(conn, pid, u)
        sogg = soggetti(conn, pid, p)[:call_riunioni.MAX_PARTECIPANTI]
        if not sogg:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nessun manager coinvolto in questo progetto: assegna un project manager o delle task agli agenti")
        try:
            tid = call_riunioni.crea(conn, u["id"], f"Riunione su {p['nome']}"[:200], _odg(conn, p), [s["nome"] for s in sogg])
        except call_riunioni.ErroreCall as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
        conn.execute("UPDATE tavoli SET progetto_id = %s WHERE id = %s", (pid, tid))
    call_riunioni.avvia(tid, u)      # dopo il commit: usa una sua connessione
    return {"id": tid, "partecipanti": [s["nome"] for s in sogg]}
