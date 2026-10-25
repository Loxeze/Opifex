"""Regola «non inventare mai» e richieste di informazioni mancanti.

Un agente che non ha un dato lo chiede prima al superiore (se puo' dialogare), poi a Lorenzo scrivendo una riga
[MANCA] ... oppure [MANCA-BLOCCANTE] ... Le righe diventano richieste nella casella «Richieste» e nel briefing.
Se bloccanti, accodano anche una notifica urgente (inviata dal canale configurato).
"""
import re
from difflib import SequenceMatcher

REGOLA = """

REGOLA FERREA - NON INVENTARE MAI: non inventare dati, numeri, date, fonti, nomi o fatti. Usa solo cio' che ti e' stato dato
(istruzioni, documenti, risposte dei colleghi, pagine lette).

AUTONOMIA - LORENZO E' L'ULTIMA RISORSA, NON LA PRIMA. Se ti manca un'informazione, risolvila nell'ordine:
1) cercala tu: documenti, memoria di lavoro, decisioni gia' prese da Lorenzo (se elencate sotto), ricerca web se la hai;
2) chiedila ai colleghi: prima il tuo superiore, poi chi nell'organizzazione se ne occupa (altri manager, specialisti, Aurora che coordina). Se un collega ti risponde, usa la risposta e vai avanti;
3) se resta un dubbio che non cambia la sostanza, scegli l'ipotesi piu' ragionevole, dichiarala in una riga («Ipotesi: ...») e prosegui: Lorenzo la correggera' se serve;
4) solo se nessuno puo' decidere scrivi su una riga a parte «[MANCA] la domanda precisa che solo Lorenzo puo' risolvere»; se senza quel dato non puoi proseguire «[MANCA-BLOCCANTE] ...».
Lorenzo va interpellato SOLO per: spese o impegni economici, invii all'esterno a suo nome, azioni irreversibili, credenziali o accessi che solo lui puo' dare, scelte di strategia e priorita' che nessun collega puo' prendere.
NON chiedergli: conferme su cio' che ti ha gia' detto di fare o che rientra nel tuo compito (fallo e riferisci), cose gia' scritte nei documenti o nelle sue risposte precedenti, domande gia' poste da un altro agente, scelte operative che puoi fare tu.
Intanto completa la parte di lavoro che puoi fare e indica chiaramente cosa resta in sospeso."""

_RIGA = re.compile(r"^\s*[\[«]\s*MANCA(-BLOCCANTE)?\s*[\]»]\s*:?\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (t or "").lower())).strip()


def _gia_chiesta(conn, domanda: str) -> bool:
    """Una domanda uguale o quasi (anche posta da un altro agente) gia' aperta o con risposta recente non va richiesta a Lorenzo."""
    n = _norm(domanda)
    for r in conn.execute("""SELECT domanda FROM richieste_informazioni
                             WHERE stato = 'aperta' OR (stato = 'risposta' AND risposta_il > NOW() - INTERVAL '60 days')
                             ORDER BY id DESC LIMIT 300""").fetchall():
        m = _norm(r["domanda"])
        if m == n or SequenceMatcher(None, m, n).ratio() >= 0.8:
            return True
    return False


def decisioni_note(conn, max_voci: int = 20) -> str:
    """Cio' che Lorenzo ha gia' risposto agli agenti (ultimi 60 giorni): serve a tutti, cosi' nessuno richiede la stessa cosa."""
    righe = conn.execute("""SELECT domanda, risposta FROM richieste_informazioni
                            WHERE stato = 'risposta' AND risposta IS NOT NULL AND risposta_il > NOW() - INTERVAL '60 days'
                            ORDER BY risposta_il DESC LIMIT %s""", (max_voci,)).fetchall()
    if not righe:
        return ""
    return ("COSA LORENZO HA GIA' DECISO O RISPOSTO (vale per tutti: non richiederlo, usalo):\n"
            + "\n".join(f"- {r['domanda'][:250]} -> {r['risposta'][:400]}" for r in righe))


def estrai_e_salva(conn, agente_id: int, testo: str) -> int:
    """Registra le richieste contenute nel testo. Ritorna quante nuove ne ha create."""
    nuove = 0
    for m in _RIGA.finditer(testo or ""):
        domanda = m.group(2).strip().strip("]»").strip()[:600]
        if len(domanda) < 5:
            continue
        bloccante = bool(m.group(1))
        if _gia_chiesta(conn, domanda):
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
