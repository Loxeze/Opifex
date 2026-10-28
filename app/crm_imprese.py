"""CRM: imprese del gruppo e reparti di Opifex associati a ogni contatto.
Un contatto si puo' contattare solo a nome delle imprese a cui e' associato. Per contattarlo a nome di un'altra serve prima una nuova
associazione, con motivo e data. Ogni cambiamento resta nella cronologia del contatto (crm_storico)."""
from datetime import date

from . import crm_modello as cm


class ErroreImprese(Exception):
    pass


def _azienda(conn, azienda_id: int) -> dict:
    a = conn.execute("SELECT id, nome FROM aziende WHERE id = %s", (azienda_id,)).fetchone()
    if a is None:
        raise ErroreImprese("Impresa inesistente")
    return a


def imprese_di(conn, cid: int) -> list[dict]:
    return conn.execute("""SELECT i.id, i.azienda_id, a.nome AS impresa, i.motivo, i.dal, COALESCE(u.nome, g.nome) AS da
                           FROM crm_contatto_imprese i JOIN aziende a ON a.id = i.azienda_id
                           LEFT JOIN utenti u ON u.id = i.utente_id LEFT JOIN agenti g ON g.id = i.agente_id
                           WHERE i.contatto_id = %s ORDER BY i.dal, i.id""", (cid,)).fetchall()


def reparti_di(conn, cid: int) -> list[dict]:
    return conn.execute("""SELECT r.id, r.divisione_id, d.nome AS reparto, r.nota
                           FROM crm_contatto_reparti r JOIN divisioni d ON d.id = r.divisione_id
                           WHERE r.contatto_id = %s ORDER BY d.nome""", (cid,)).fetchall()


def associa_impresa(conn, cid: int, azienda_id: int, motivo: str, dal: date | None = None, utente_id=None, agente_id=None) -> dict:
    cm._esiste(conn, cid)
    az = _azienda(conn, azienda_id)
    motivo = " ".join(str(motivo or "").split())
    if len(motivo) < 5:
        raise ErroreImprese("Scrivi il motivo dell'associazione (almeno 5 caratteri)")
    if conn.execute("SELECT 1 FROM crm_contatto_imprese WHERE contatto_id = %s AND azienda_id = %s", (cid, azienda_id)).fetchone():
        raise ErroreImprese(f"Il contatto e' gia' associato a {az['nome']}")
    dal = dal or date.today()
    r = conn.execute("""INSERT INTO crm_contatto_imprese (contatto_id, azienda_id, motivo, dal, utente_id, agente_id) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                     (cid, azienda_id, motivo[:500], dal, utente_id, agente_id)).fetchone()
    cm.storico(conn, cid, "impresa associata", None, f"{az['nome']} dal {dal.isoformat()}: {motivo[:200]}", utente_id, agente_id)
    return {"id": r["id"]}


def togli_impresa(conn, cid: int, azienda_id: int, utente_id=None, agente_id=None):
    az = _azienda(conn, azienda_id)
    if not conn.execute("DELETE FROM crm_contatto_imprese WHERE contatto_id = %s AND azienda_id = %s RETURNING 1", (cid, azienda_id)).fetchone():
        raise ErroreImprese("Associazione non trovata")
    cm.storico(conn, cid, "impresa rimossa", az["nome"], None, utente_id, agente_id)


def imposta_reparto(conn, cid: int, divisione_id: int, nota: str, utente_id=None, agente_id=None):
    cm._esiste(conn, cid)
    d = conn.execute("SELECT id, nome FROM divisioni WHERE id = %s", (divisione_id,)).fetchone()
    if d is None:
        raise ErroreImprese("Reparto inesistente")
    nota = " ".join(str(nota or "").split())
    if len(nota) < 3:
        raise ErroreImprese("Scrivi una nota: perche' il contatto puo' servire a questo reparto")
    prima = conn.execute("SELECT nota FROM crm_contatto_reparti WHERE contatto_id = %s AND divisione_id = %s", (cid, divisione_id)).fetchone()
    conn.execute("""INSERT INTO crm_contatto_reparti (contatto_id, divisione_id, nota, utente_id, agente_id) VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (contatto_id, divisione_id) DO UPDATE SET nota = EXCLUDED.nota, utente_id = EXCLUDED.utente_id, agente_id = EXCLUDED.agente_id""",
                 (cid, divisione_id, nota[:500], utente_id, agente_id))
    cm.storico(conn, cid, "reparto: " + d["nome"], prima["nota"] if prima else None, nota[:200], utente_id, agente_id)


def togli_reparto(conn, cid: int, divisione_id: int, utente_id=None, agente_id=None):
    d = conn.execute("SELECT nome FROM divisioni WHERE id = %s", (divisione_id,)).fetchone()
    if not conn.execute("DELETE FROM crm_contatto_reparti WHERE contatto_id = %s AND divisione_id = %s RETURNING 1", (cid, divisione_id)).fetchone():
        raise ErroreImprese("Reparto non associato")
    cm.storico(conn, cid, "reparto rimosso", d["nome"] if d else None, None, utente_id, agente_id)


def puo_contattare(conn, cid: int, azienda_id: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM crm_contatto_imprese WHERE contatto_id = %s AND azienda_id = %s", (cid, azienda_id)).fetchone())


def non_associati(conn, ids: list[int], azienda_id: int) -> list[int]:
    """Quali contatti dell'elenco NON si possono contattare a nome dell'impresa."""
    if not ids:
        return []
    ok = {r["contatto_id"] for r in conn.execute("SELECT contatto_id FROM crm_contatto_imprese WHERE azienda_id = %s AND contatto_id = ANY(%s)", (azienda_id, ids)).fetchall()}
    return [i for i in ids if i not in ok]


def scheda(conn, cid: int) -> dict:
    cm._esiste(conn, cid)
    return {"imprese": imprese_di(conn, cid), "reparti": reparti_di(conn, cid),
            "imprese_disponibili": conn.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome").fetchall(),
            "reparti_disponibili": conn.execute("SELECT id, nome FROM divisioni ORDER BY nome").fetchall(),
            "cronologia": cm.elenco_storico(conn, cid, 50)}
