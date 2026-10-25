"""Memoria di lavoro degli agenti: voci brevi (decisioni, fatti, preferenze, lezioni, sintesi) approvate da una persona.
Le voci hanno un ambito (azienda, progetto, dipartimento): un agente riceve solo quelle del proprio ambito e solo se la
riservatezza consente di inviarle al suo fornitore. Mai chiavi o password nelle voci."""
import re

from .documenti import query_ricerca
from .riservatezza import puo_uscire

TIPI = ("decisione", "fatto", "preferenza", "lezione", "sintesi")
MAX_VOCI = 6
MAX_CARATTERI = 3500
# una voce che sembra contenere un segreto non entra nella memoria
SEGRETO = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY|(password|passwd|pwd|token|api[_ -]?key)\s*[:=]\s*\S{6,})", re.I)


class MemoriaNonValida(Exception):
    pass


def pulisci(testo: str) -> str:
    t = re.sub(r"\s+", " ", (testo or "")).strip()
    if len(t) < 3:
        raise MemoriaNonValida("Testo troppo corto")
    if len(t) > 1200:
        raise MemoriaNonValida("Testo troppo lungo: massimo 1200 caratteri")
    if SEGRETO.search(t):
        raise MemoriaNonValida("Il testo sembra contenere una chiave o una password: la memoria non le conserva")
    return t


def proponi(conn, testo: str, tipo: str = "decisione", *, azienda_id=None, progetto_id=None, divisione_id=None, fascia_dati: str = "interno",
            fonte: str | None = None, agente_id=None, utente_id=None, stato: str = "proposta", decisa_da=None, sostituisce_id=None) -> int:
    if tipo not in TIPI:
        raise MemoriaNonValida("Tipo non valido")
    if fascia_dati not in ("pubblico", "interno", "riservato"):
        raise MemoriaNonValida("Riservatezza non valida")
    t = pulisci(testo)
    if conn.execute("SELECT 1 FROM memorie_lavoro WHERE stato IN ('proposta','approvata') AND lower(testo) = lower(%s) "
                    "AND divisione_id IS NOT DISTINCT FROM %s AND azienda_id IS NOT DISTINCT FROM %s", (t, divisione_id, azienda_id)).fetchone():
        raise MemoriaNonValida("Voce gia' presente")
    r = conn.execute(
        """INSERT INTO memorie_lavoro (testo, tipo, stato, fascia_dati, azienda_id, progetto_id, divisione_id, fonte, proposta_da_agente_id,
               proposta_da_utente_id, sostituisce_id, decisa_da_utente_id, decisa_il)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s = 'approvata' THEN NOW() END) RETURNING id""",
        (t, tipo, stato, fascia_dati, azienda_id, progetto_id, divisione_id, (fonte or "")[:200] or None, agente_id, utente_id,
         sostituisce_id, decisa_da, stato)).fetchone()
    if sostituisce_id and stato == "approvata":
        conn.execute("UPDATE memorie_lavoro SET stato = 'superata' WHERE id = %s AND stato = 'approvata'", (sostituisce_id,))
    return r["id"]


def proponi_da_agente(conn, agente_id: int, testo: str, tipo: str = "decisione") -> int:
    """Lo strumento dell'agente: l'ambito e' quello dell'agente (il suo dipartimento e, se ne ha una sola, la sua azienda)."""
    a = conn.execute("SELECT divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    az = conn.execute("SELECT azienda_id FROM agenti_aziende WHERE agente_id = %s", (agente_id,)).fetchall()
    return proponi(conn, testo, tipo, divisione_id=a["divisione_id"] if a else None, azienda_id=az[0]["azienda_id"] if len(az) == 1 else None,
                   fonte="proposta dell'agente", agente_id=agente_id)


def voci_per_agente(conn, a: dict, messaggio: str) -> list[dict]:
    """Voci approvate pertinenti al messaggio, nell'ambito dell'agente. Se nessuna parola coincide, le piu' recenti."""
    vede_tutto = bool(a.get("vede_tutto"))
    filtro = """v.stato = 'approvata' AND (%(vt)s OR (
                  (v.divisione_id IS NULL OR v.divisione_id = %(div)s)
                  AND (v.azienda_id IS NULL OR v.azienda_id IN (SELECT azienda_id FROM agenti_aziende WHERE agente_id = %(a)s))
                  AND (v.progetto_id IS NULL OR v.progetto_id IN (SELECT progetto_id FROM progetti_agenti WHERE agente_id = %(a)s))))"""
    par = {"vt": vede_tutto, "div": a.get("divisione_id"), "a": a["id"], "l": MAX_VOCI * 3}
    q = query_ricerca(messaggio or "")
    righe = []
    if q:
        par["q"] = q
        righe = conn.execute(f"""SELECT v.id, v.testo, v.tipo, v.fascia_dati, v.creata_il, ts_rank_cd(v.ricerca, to_tsquery('italian', %(q)s)) AS p
                                 FROM memorie_lavoro v WHERE {filtro} AND v.ricerca @@ to_tsquery('italian', %(q)s)
                                 ORDER BY p DESC, v.id DESC LIMIT %(l)s""", par).fetchall()
    recenti = conn.execute(f"""SELECT v.id, v.testo, v.tipo, v.fascia_dati, v.creata_il FROM memorie_lavoro v WHERE {filtro}
                               AND v.tipo IN ('sintesi','decisione') ORDER BY v.id DESC LIMIT 3""", par).fetchall()
    visti, out = set(), []
    for r in list(righe) + list(recenti):
        if r["id"] in visti:
            continue
        visti.add(r["id"])
        if puo_uscire(r["fascia_dati"], a["fascia_dati_max"], a["fascia_fornitore"], a["non_conservazione_attiva"], a["dpa_firmato"])[0]:
            out.append(r)
    return out[:MAX_VOCI + 2]


def contesto(conn, a: dict, messaggio: str) -> str:
    voci = voci_per_agente(conn, a, messaggio)
    if not voci:
        return ""
    righe, tot = [], 0
    for v in voci:
        riga = f"- [{v['tipo']}, {v['creata_il']:%d/%m/%Y}] {v['testo']}"
        if tot + len(riga) > MAX_CARATTERI:
            break
        tot += len(riga)
        righe.append(riga)
    return ("MEMORIA DI LAVORO (decisioni e fatti gia' approvati: tienine conto e non rimetterli in discussione senza motivo; se una voce e' superata o "
            "sbagliata dillo a Lorenzo; la data indica quando e' stata registrata):\n" + "\n".join(righe))


STRUMENTO = {"name": "memoria_proponi",
             "description": "Proponi di ricordare una decisione, un fatto, una preferenza di Lorenzo o una lezione utile in futuro (una sola informazione, breve, "
                            "senza password o chiavi). Non entra in memoria finche' non la approva una persona.",
             "input_schema": {"type": "object", "properties": {"testo": {"type": "string"}, "tipo": {"type": "string", "enum": ["decisione", "fatto", "preferenza", "lezione"]}},
                              "required": ["testo"]}}
