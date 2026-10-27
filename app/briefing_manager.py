"""Brief breve di ogni manager di dipartimento (massimo circa 5 minuti di lettura/ascolto): cosa e' successo, opportunita', cosa serve da Lorenzo."""
from .esecuzione import esegui_agente

SOTTO = """WITH RECURSIVE sotto AS (SELECT id FROM agenti WHERE superiore_id = %(m)s UNION SELECT x.id FROM agenti x JOIN sotto s ON x.superiore_id = s.id)"""


def manager_di_dipartimento(conn) -> list[dict]:
    return conn.execute(
        """SELECT a.id, a.nome, d.nome AS divisione FROM agenti a JOIN divisioni d ON d.id = a.divisione_id
           WHERE a.attivo AND a.tipo = 'divisione' AND a.livello IN ('manager', 'referente') AND NOT a.sentinella ORDER BY a.id""").fetchall()


def dati(conn, m: dict, ore: int) -> str:
    p = {"m": m["id"], "o": f"{ore} hours"}
    parti = [f"Dipartimento: {m['divisione']}"]
    fatte = conn.execute(
        SOTTO + """ SELECT t.titolo, a.nome FROM task t JOIN agenti a ON a.id = t.assegnato_agente_id
                    WHERE (t.assegnato_agente_id IN (SELECT id FROM sotto) OR t.assegnato_agente_id = %(m)s)
                      AND t.stato = 'completata' AND t.completata_il > NOW() - %(o)s::interval ORDER BY t.completata_il DESC LIMIT 8""", p).fetchall()
    aperte = conn.execute(
        SOTTO + """ SELECT t.titolo, t.stato, t.scadenza, a.nome FROM task t JOIN agenti a ON a.id = t.assegnato_agente_id
                    WHERE (t.assegnato_agente_id IN (SELECT id FROM sotto) OR t.assegnato_agente_id = %(m)s) AND t.stato <> 'completata'
                    ORDER BY t.scadenza NULLS LAST, t.id LIMIT 10""", p).fetchall()
    ric = conn.execute(
        SOTTO + """ SELECT a.nome, r.domanda FROM richieste_informazioni r JOIN agenti a ON a.id = r.agente_id
                    WHERE r.stato = 'aperta' AND (r.agente_id IN (SELECT id FROM sotto) OR r.agente_id = %(m)s) LIMIT 6""", p).fetchall()
    ini = conn.execute("""SELECT titolo, stato, sintesi FROM iniziative WHERE aperta_da_agente_id = %(m)s
                          AND (stato IN ('da_approvare', 'in_corso') OR (stato = 'conclusa' AND conclusa_il > NOW() - %(o)s::interval)) LIMIT 5""", p).fetchall()
    parti.append("Task completate: " + ("; ".join(f"{r['titolo']} ({r['nome']})" for r in fatte) or "nessuna"))
    parti.append("Task aperte: " + ("; ".join(f"{r['titolo']} [{r['stato']}{', entro ' + str(r['scadenza']) if r['scadenza'] else ''}] ({r['nome']})" for r in aperte) or "nessuna"))
    if ric:
        parti.append("Richieste di informazioni aperte: " + "; ".join(f"{r['nome']}: {r['domanda'][:120]}" for r in ric))
    if ini:
        parti.append("Iniziative: " + "; ".join(f"{r['titolo']} [{r['stato']}]" + (f" — sintesi: {r['sintesi'][:200]}" if r["sintesi"] else "") for r in ini))
    from . import squadre
    for pr in conn.execute("SELECT id, nome FROM progetti WHERE pm_agente_id = %s AND NOT archiviato AND eliminato_il IS NULL", (m["id"],)).fetchall():
        ks = squadre.kpi_elenco(conn, pr["id"])
        parti.append(f"Progetto «{pr['nome']}» — KPI della squadra: " + ("; ".join(f"{k['agente']}: {squadre._riga_kpi(k)}" for k in ks[:10]) or "nessuno assegnato"))
    return "\n".join(parti)


def genera(conn, m: dict, tipo: str) -> str | None:
    ore = 24 if tipo == "mattina" else 14
    testo_dati = dati(conn, m, ore)
    conn.commit()
    msg = ("Scrivi il tuo brief per Lorenzo, che ha 5 minuti per ogni manager: massimo 250 parole, in italiano, parlato (si potra' anche ascoltare a voce), con tre parti brevi: "
           "1) Cosa e' successo nel tuo dipartimento; 2) Opportunita' (anche quelle emerse da altri dipartimenti); 3) Cosa mi serve da te / decisioni. "
           "Usa solo i dati sotto, non inventare nulla; se un punto non ha contenuto, saltalo.\n\n=== Dati ===\n" + testo_dati)
    try:
        return esegui_agente(m["id"], msg, "interno", memorizza=False, max_token=700)["risposta"]
    except Exception:  # noqa: BLE001 - un manager che non risponde non ferma il briefing
        return None
