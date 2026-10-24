"""Regola «non inventare mai» e richieste di informazioni mancanti.

Un agente che non ha un dato lo chiede prima al superiore (se puo' dialogare), poi a Lorenzo scrivendo una riga
[MANCA] ... oppure [MANCA-BLOCCANTE] ... Le righe diventano richieste nella casella «Richieste» e nel briefing.
Se bloccanti, accodano anche una notifica urgente (inviata dal canale configurato).
"""
import re

REGOLA = """

REGOLA FERREA - NON INVENTARE MAI: non inventare dati, numeri, date, fonti, nomi o fatti. Usa solo cio' che ti e' stato dato
(istruzioni, documenti, risposte dei colleghi, pagine lette). Se ti manca un'informazione necessaria:
1) se puoi dialogare con il tuo superiore, chiedila a lui; 2) altrimenti, o se lui non la ha, scrivi su una riga a parte
«[MANCA] la domanda precisa che Lorenzo deve risolvere». Se senza quel dato non puoi proseguire scrivi invece «[MANCA-BLOCCANTE] ...».
Intanto completa la parte di lavoro che puoi fare e indica chiaramente cosa resta in sospeso."""

_RIGA = re.compile(r"^\s*[\[«]\s*MANCA(-BLOCCANTE)?\s*[\]»]\s*:?\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def estrai_e_salva(conn, agente_id: int, testo: str) -> int:
    """Registra le richieste contenute nel testo. Ritorna quante nuove ne ha create."""
    nuove = 0
    for m in _RIGA.finditer(testo or ""):
        domanda = m.group(2).strip().strip("]»").strip()[:600]
        if len(domanda) < 5:
            continue
        bloccante = bool(m.group(1))
        if conn.execute("SELECT 1 FROM richieste_informazioni WHERE agente_id = %s AND domanda = %s AND stato = 'aperta'",
                        (agente_id, domanda)).fetchone():
            continue
        conn.execute("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante) VALUES (%s,%s,%s)",
                     (agente_id, domanda, bloccante))
        if bloccante:
            nome = conn.execute("SELECT nome FROM agenti WHERE id = %s", (agente_id,)).fetchone()["nome"]
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)",
                         (f"{nome} e' bloccato e ha bisogno di te: {domanda}",))
        nuove += 1
    return nuove


def risposte_da_consegnare(conn, agente_id: int) -> str:
    """Testo con le risposte di Lorenzo non ancora viste dall'agente (le segna come consegnate)."""
    righe = conn.execute(
        "SELECT id, domanda, risposta FROM richieste_informazioni WHERE agente_id = %s AND stato = 'risposta' AND NOT consegnata ORDER BY id",
        (agente_id,)).fetchall()
    if not righe:
        return ""
    conn.execute("UPDATE richieste_informazioni SET consegnata = TRUE WHERE id = ANY(%s)", ([r["id"] for r in righe],))
    return ("Informazioni fornite da Lorenzo alle tue richieste:\n"
            + "\n".join(f"- Domanda: {r['domanda']}\n  Risposta di Lorenzo: {r['risposta']}" for r in righe) + "\n\n")
