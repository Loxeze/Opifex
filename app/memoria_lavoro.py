"""Memoria di lavoro degli agenti: voci brevi (decisioni, fatti, preferenze, lezioni, sintesi) approvate da una persona.
Le voci hanno un ambito (azienda, progetto, dipartimento): un agente riceve solo quelle del proprio ambito e solo se la
riservatezza consente di inviarle al suo fornitore. Mai chiavi o password nelle voci."""
import re
from datetime import date

from .documenti import query_ricerca
from .riservatezza import puo_uscire

TIPI = ("decisione", "fatto", "preferenza", "lezione", "sintesi", "regola", "procedura", "esempio", "errore", "studio")
TIPI_AGENTE = ("decisione", "fatto", "preferenza", "lezione", "regola", "procedura", "esempio", "errore", "studio")
# dossier di competenza: queste voci invecchiano (le regole cambiano) e vanno riverificate
TIPI_CON_VERIFICA = ("regola", "procedura", "studio", "lezione")
GIORNI_VERIFICA = 180
MAX_VOCI = 6
MAX_CARATTERI = 4500
MAX_PERSONA = 5
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
            fonte: str | None = None, agente_id=None, utente_id=None, stato: str = "proposta", decisa_da=None, sostituisce_id=None,
            ambito_agente_id=None, tema: str | None = None, origine: str | None = None, casi: int = 0, persona: bool = False, task_id=None) -> int:
    if tipo not in TIPI:
        raise MemoriaNonValida("Tipo non valido")
    if fascia_dati not in ("pubblico", "interno", "riservato"):
        raise MemoriaNonValida("Riservatezza non valida")
    t = pulisci(testo)
    if persona and any(x is not None for x in (azienda_id, progetto_id, divisione_id, task_id, ambito_agente_id)):
        raise MemoriaNonValida("Una voce sulla persona non ha altro ambito")
    if task_id is not None and conn.execute("SELECT 1 FROM task WHERE id = %s", (task_id,)).fetchone() is None:
        raise MemoriaNonValida("Task inesistente")
    if conn.execute("SELECT 1 FROM memorie_lavoro WHERE stato IN ('proposta','approvata') AND lower(testo) = lower(%s) "
                    "AND divisione_id IS NOT DISTINCT FROM %s AND azienda_id IS NOT DISTINCT FROM %s AND agente_id IS NOT DISTINCT FROM %s "
                    "AND persona = %s AND task_id IS NOT DISTINCT FROM %s",
                    (t, divisione_id, azienda_id, ambito_agente_id, persona, task_id)).fetchone():
        raise MemoriaNonValida("Voce gia' presente")
    r = conn.execute(
        """INSERT INTO memorie_lavoro (testo, tipo, stato, fascia_dati, azienda_id, progetto_id, divisione_id, fonte, proposta_da_agente_id,
               proposta_da_utente_id, sostituisce_id, decisa_da_utente_id, decisa_il, agente_id, tema, origine, casi, persona, task_id, verifica_il)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s = 'approvata' THEN NOW() END, %s,%s,%s,%s,%s,%s,
                   CASE WHEN %s = 'approvata' AND %s = ANY(%s) THEN CURRENT_DATE + %s END) RETURNING id""",
        (t, tipo, stato, fascia_dati, azienda_id, progetto_id, divisione_id, (fonte or "")[:200] or None, agente_id, utente_id,
         sostituisce_id, decisa_da, stato, ambito_agente_id, (tema or "").strip()[:80] or None, (origine or "")[:60] or None, max(0, int(casi or 0)), persona, task_id,
         stato, tipo, list(TIPI_CON_VERIFICA), GIORNI_VERIFICA)).fetchone()
    if sostituisce_id and stato == "approvata":
        conn.execute("UPDATE memorie_lavoro SET stato = 'superata' WHERE id = %s AND stato = 'approvata'", (sostituisce_id,))
    return r["id"]


def proponi_da_agente(conn, agente_id: int, testo: str, tipo: str = "decisione", ambito: str = "reparto", tema: str | None = None) -> int:
    """Lo strumento dell'agente: l'ambito e' quello dell'agente (il suo dipartimento e, se ne ha una sola, la sua azienda).
    ambito «personale»: la voce vale solo per questo agente (resta nel suo fascicolo)."""
    if tipo not in TIPI_AGENTE:
        raise MemoriaNonValida("Tipo non valido")
    a = conn.execute("SELECT divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    az = conn.execute("SELECT azienda_id FROM agenti_aziende WHERE agente_id = %s", (agente_id,)).fetchall()
    return proponi(conn, testo, tipo, divisione_id=a["divisione_id"] if a else None, azienda_id=az[0]["azienda_id"] if len(az) == 1 else None,
                   fonte="proposta dell'agente", agente_id=agente_id, tema=tema, origine="agente",
                   ambito_agente_id=agente_id if ambito == "personale" else None)


LIVELLI = {1: "CHI E' LORENZO (valido sempre)", 2: "AZIENDA E REPARTO", 3: "PROGETTO", 4: "TASK IN CORSO"}


def voci_per_agente(conn, a: dict, messaggio: str) -> list[dict]:
    """Voci approvate dei quattro livelli (persona, azienda/reparto, progetto, task) pertinenti al messaggio e all'ambito dell'agente.
    Il livello 1 (Lorenzo) arriva a tutti gli agenti, ma solo se la riservatezza consente di inviarlo al fornitore; gli altri solo nell'ambito dell'agente.
    Se nessuna parola coincide, le piu' recenti. Ogni voce porta il suo livello."""
    vede_tutto = bool(a.get("vede_tutto"))
    filtro = """v.stato = 'approvata' AND (v.agente_id IS NULL OR v.agente_id = %(a)s) AND (v.persona OR %(vt)s OR (
                  (v.divisione_id IS NULL OR v.divisione_id = %(div)s)
                  AND (v.azienda_id IS NULL OR v.azienda_id IN (SELECT azienda_id FROM agenti_aziende WHERE agente_id = %(a)s))
                  AND (v.progetto_id IS NULL OR v.progetto_id IN (SELECT progetto_id FROM progetti_agenti WHERE agente_id = %(a)s))
                  AND (v.task_id IS NULL OR v.task_id IN (SELECT t.id FROM task t WHERE t.assegnato_agente_id = %(a)s
                         OR t.id IN (SELECT padre_id FROM task WHERE assegnato_agente_id = %(a)s AND padre_id IS NOT NULL)
                         OR t.progetto_id IN (SELECT progetto_id FROM progetti_agenti WHERE agente_id = %(a)s)))))"""
    liv = "CASE WHEN v.persona THEN 1 WHEN v.task_id IS NOT NULL THEN 4 WHEN v.progetto_id IS NOT NULL THEN 3 ELSE 2 END"
    campi = f"v.id, v.testo, v.tipo, v.fascia_dati, v.creata_il, v.tema, v.casi, v.verifica_il, v.agente_id, {liv} AS livello"
    par = {"vt": vede_tutto, "div": a.get("divisione_id"), "a": a["id"], "l": MAX_VOCI * 3}
    q = query_ricerca(messaggio or "")
    righe = []
    if q:
        par["q"] = q
        righe = conn.execute(f"""SELECT {campi}, ts_rank_cd(v.ricerca, to_tsquery('italian', %(q)s)) AS p
                                 FROM memorie_lavoro v WHERE {filtro} AND v.ricerca @@ to_tsquery('italian', %(q)s)
                                 ORDER BY p DESC, v.casi DESC, v.id DESC LIMIT %(l)s""", par).fetchall()
    recenti = conn.execute(f"""SELECT {campi} FROM memorie_lavoro v WHERE {filtro}
                               AND v.tipo IN ('sintesi','decisione') AND NOT v.persona ORDER BY v.id DESC LIMIT 3""", par).fetchall()
    # task e progetto sono il lavoro in corso: le loro voci recenti si vedono anche se la domanda non le nomina
    attive = conn.execute(f"""SELECT {campi} FROM memorie_lavoro v WHERE {filtro} AND (v.task_id IS NOT NULL) ORDER BY v.id DESC LIMIT 3""", par).fetchall()
    persona = conn.execute(f"""SELECT {campi} FROM memorie_lavoro v WHERE {filtro} AND v.persona ORDER BY v.id DESC LIMIT 40""", par).fetchall()
    # del livello 1 tutti gli agenti ricevono il nucleo (le voci piu' pertinenti al messaggio, poi le altre) fino a MAX_PERSONA
    pert = {r["id"] for r in righe if r["livello"] == 1}
    persona = sorted(persona, key=lambda r: (r["id"] not in pert, -r["id"]))
    visti, out = set(), []
    for r in persona[:MAX_PERSONA] + list(attive) + list(righe) + list(recenti):
        if r["id"] in visti:
            continue
        visti.add(r["id"])
        if puo_uscire(r["fascia_dati"], a["fascia_dati_max"], a["fascia_fornitore"], a["non_conservazione_attiva"], a["dpa_firmato"])[0]:
            out.append(r)
    nonp = [r for r in out if r["livello"] != 1]
    return [r for r in out if r["livello"] == 1] + nonp[:MAX_VOCI + 2]


def contesto(conn, a: dict, messaggio: str) -> str:
    voci = voci_per_agente(conn, a, messaggio)
    if not voci:
        return ""
    righe, tot, ultimo = [], 0, None
    for v in sorted(voci, key=lambda r: r["livello"]):
        scaduta = v.get("verifica_il") is not None and v["verifica_il"] < date.today()
        etichetta = v["tipo"] + (" personale" if v.get("agente_id") else "") + (f", tema {v['tema']}" if v.get("tema") else "") + f", {v['creata_il']:%d/%m/%Y}"
        riga = f"- [{etichetta}]" + (" (DA RIVERIFICARE: potrebbe essere superata)" if scaduta else "") + f" {v['testo']}"
        if tot + len(riga) > MAX_CARATTERI:
            continue
        if v["livello"] != ultimo:
            ultimo = v["livello"]
            righe.append(f"## {LIVELLI[ultimo]}")
        tot += len(riga)
        righe.append(riga)
    return ("MEMORIA DI LAVORO, a quattro livelli (decisioni e fatti gia' approvati: tienine conto e non rimetterli in discussione senza motivo; in caso di "
            "contrasto vale il livello piu' specifico: task, poi progetto, poi azienda, poi le indicazioni generali su Lorenzo; se una voce e' superata o "
            "sbagliata dillo a Lorenzo; la data indica quando e' stata registrata):\n" + "\n".join(righe))


STRUMENTO = {"name": "memoria_proponi",
             "description": "Proponi di aggiungere al dossier di competenza una decisione, un fatto, una preferenza di Lorenzo, una lezione, una regola, una procedura, "
                            "un esempio, un errore da evitare o un risultato di studio (una sola informazione, breve, senza password o chiavi). Non entra finche' "
                            "non la approva una persona. ambito: «reparto» (vale per il tuo dipartimento, predefinito) o «personale» (vale solo per te).",
             "input_schema": {"type": "object", "properties": {"testo": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPI_AGENTE)},
                                                               "tema": {"type": "string"}, "ambito": {"type": "string", "enum": ["reparto", "personale"]}},
                              "required": ["testo"]}}
