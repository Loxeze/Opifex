"""Dashboard di un singolo progetto: task, persone e agenti al lavoro, impegno, milestone, manager di riferimento."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import pm, registro
from .db import connessione
from .permessi import solo_titolare, utente_corrente

router = APIRouter(tags=["progetto"])


def _aziende_utente(conn, u: dict) -> list[int]:
    return [r["azienda_id"] for r in conn.execute("SELECT azienda_id FROM accessi_azienda WHERE utente_id = %s", (u["id"],)).fetchall()]


def _puo_vedere(conn, u: dict, p: dict) -> bool:
    if u["ruolo_globale"] == "titolare":
        return True
    if p["azienda_id"] in _aziende_utente(conn, u):
        return True
    return bool(conn.execute("SELECT 1 FROM task WHERE progetto_id = %s AND (assegnato_utente_id = %s OR creato_da_utente_id = %s) LIMIT 1", (p["id"], u["id"], u["id"])).fetchone())


@router.get("/progetti-miei")
def miei(u: dict = Depends(utente_corrente)):
    """I progetti che l'utente puo' aprire: tutti per il titolare, quelli delle sue imprese (o con sue task) per i collaboratori."""
    with connessione() as conn:
        az = _aziende_utente(conn, u)
        righe = conn.execute("""SELECT p.id, p.nome, p.descrizione, COALESCE(p.colore, z.colore) AS colore, z.nome AS azienda, p.archiviato,
                                       (SELECT count(*) FROM task t WHERE t.progetto_id = p.id AND t.stato <> 'completata') AS aperte,
                                       (SELECT count(*) FROM task t WHERE t.progetto_id = p.id) AS totali
                                FROM progetti p LEFT JOIN aziende z ON z.id = p.azienda_id
                                WHERE p.eliminato_il IS NULL AND (%(tit)s OR p.azienda_id = ANY(%(az)s)
                                      OR EXISTS (SELECT 1 FROM task t WHERE t.progetto_id = p.id AND (t.assegnato_utente_id = %(u)s OR t.creato_da_utente_id = %(u)s)))
                                ORDER BY p.archiviato, z.nome, p.nome""", {"tit": u["ruolo_globale"] == "titolare", "az": az or [0], "u": u["id"]}).fetchall()
    return {"progetti": righe}


@router.get("/progetti/{pid}/dashboard")
def dashboard(pid: int, u: dict = Depends(utente_corrente)):
    tit = u["ruolo_globale"] == "titolare"
    with connessione() as conn:
        p = conn.execute("""SELECT p.id, p.nome, p.descrizione, p.allineamento, p.allineamento_il, p.archiviato, p.azienda_id, z.nome AS azienda, COALESCE(p.colore, z.colore) AS colore,
                                   p.pm_agente_id, p.drive_cartella_id
                            FROM progetti p LEFT JOIN aziende z ON z.id = p.azienda_id WHERE p.id = %s AND p.eliminato_il IS NULL""", (pid,)).fetchone()
        if p is None or not _puo_vedere(conn, u, p):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progetto non trovato")
        task = conn.execute("""SELECT t.id, t.titolo, t.stato, t.priorita, t.scadenza, t.completata_il, t.aggiornata_il, t.padre_id,
                                      t.assegnato_agente_id, a.nome AS agente, t.assegnato_utente_id, us.nome AS persona,
                                      (t.scadenza < CURRENT_DATE AND t.stato <> 'completata') AS in_ritardo
                               FROM task t LEFT JOIN agenti a ON a.id = t.assegnato_agente_id LEFT JOIN utenti us ON us.id = t.assegnato_utente_id
                               WHERE t.progetto_id = %s ORDER BY (t.stato = 'completata'), t.scadenza NULLS LAST, t.id LIMIT 300""", (pid,)).fetchall()
        conteggi = {s: sum(1 for t in task if t["stato"] == s) for s in ("da_fare", "in_corso", "in_attesa", "completata")}
        agenti = conn.execute("""SELECT a.id, a.nome, a.ruolo, a.livello, dv.nome AS ambito,
                                        count(t.id) FILTER (WHERE t.stato <> 'completata') AS aperte, count(t.id) FILTER (WHERE t.stato = 'completata') AS chiuse,
                                        (SELECT count(*) FROM task_commenti c JOIN task tt ON tt.id = c.task_id
                                          WHERE tt.progetto_id = %(p)s AND c.agente_id = a.id AND c.creato_il > NOW() - interval '7 days') AS attivita_7g
                                 FROM agenti a LEFT JOIN divisioni dv ON dv.id = a.divisione_id
                                 JOIN task t ON t.assegnato_agente_id = a.id AND t.progetto_id = %(p)s
                                 GROUP BY a.id, dv.nome ORDER BY aperte DESC, a.nome""", {"p": pid}).fetchall()
        persone = conn.execute("""SELECT us.id, us.nome, count(t.id) FILTER (WHERE t.stato <> 'completata') AS aperte, count(t.id) FILTER (WHERE t.stato = 'completata') AS chiuse
                                  FROM utenti us JOIN task t ON t.assegnato_utente_id = us.id AND t.progetto_id = %s GROUP BY us.id ORDER BY aperte DESC""", (pid,)).fetchall()
        milestone = conn.execute("SELECT id, titolo, scadenza, raggiunta_il FROM milestone WHERE progetto_id = %s ORDER BY (raggiunta_il IS NOT NULL), scadenza NULLS LAST, id", (pid,)).fetchall()
        pm_ag = conn.execute("SELECT id, nome FROM agenti WHERE id = %s", (p["pm_agente_id"],)).fetchone() if p["pm_agente_id"] else None
        manager = conn.execute("""SELECT DISTINCT ON (dv.id) dv.nome AS ambito, m.id, m.nome FROM progetti_agenti pa JOIN agenti a ON a.id = pa.agente_id
                                  JOIN divisioni dv ON dv.id = a.divisione_id JOIN agenti m ON m.divisione_id = dv.id AND m.livello = 'manager' AND m.attivo
                                  WHERE pa.progetto_id = %s AND dv.nome <> %s ORDER BY dv.id, m.id""", (pid, pm.NOME_DIVISIONE)).fetchall() if tit else []
        p.pop("drive_cartella_id", None)
        return {"progetto": p, "task": task, "conteggi": conteggi, "in_ritardo": sum(1 for t in task if t["in_ritardo"]), "agenti": agenti, "persone": persone,
                "milestone": milestone, "pm": pm_ag, "manager": manager, "puo_modificare": tit}


class Milestone(BaseModel):
    titolo: str = Field(min_length=3, max_length=200)
    scadenza: date | None = None


@router.post("/gestione/progetti/{pid}/milestone", status_code=201)
def nuova(pid: int, d: Milestone, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("SELECT 1 FROM progetti WHERE id = %s", (pid,)).fetchone():
            raise HTTPException(404, "Progetto non trovato")
        i = conn.execute("INSERT INTO milestone (progetto_id, titolo, scadenza) VALUES (%s,%s,%s) RETURNING id", (pid, " ".join(d.titolo.split()), d.scadenza)).fetchone()["id"]
        registro.registra(conn, u, "organizzazione", "milestone creata", d.titolo[:100], "milestone", i)
    return {"id": i}


class Raggiunta(BaseModel):
    raggiunta: bool


@router.post("/gestione/milestone/{mid}/raggiunta")
def raggiungi(mid: int, d: Raggiunta, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE milestone SET raggiunta_il = CASE WHEN %s THEN NOW() END WHERE id = %s RETURNING titolo", (d.raggiunta, mid)).fetchone()
        if r is None:
            raise HTTPException(404, "Milestone non trovata")
        registro.registra(conn, u, "organizzazione", "milestone raggiunta" if d.raggiunta else "milestone riaperta", r["titolo"][:100], "milestone", mid)
    return {"ok": True}


@router.delete("/gestione/milestone/{mid}")
def elimina(mid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("DELETE FROM milestone WHERE id = %s RETURNING titolo", (mid,)).fetchone()
        if r is None:
            raise HTTPException(404, "Milestone non trovata")
        registro.registra(conn, u, "organizzazione", "milestone eliminata", r["titolo"][:100], "milestone", mid)
    return {"ok": True}


@router.post("/gestione/progetti/{pid}/project-manager")
def crea_pm(pid: int, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        aid = pm.crea_per(conn, pid)
        if aid is None:
            raise HTTPException(404, "Progetto non trovato")
        registro.registra(conn, u, "organizzazione", "project manager assicurato", f"progetto {pid}", "progetto", pid)
    return {"pm_agente_id": aid}
