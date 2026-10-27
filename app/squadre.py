"""Squadre di progetto, KPI e valutazioni di manager e PM.
Il project manager legge il brief, cerca chi ha le competenze (con livello, carico e affidabilita'), propone la squadra; Lorenzo approva.
Proprieta' dell'agente: resta al manager d'area (prompt, permessi, budget); il lavoro dentro il progetto lo comanda il PM. Il manager d'area viene avvisato
e puo' richiamare un suo agente. I KPI li assegna e li aggiorna il PM; i pollici su/giu' li danno i manager (ai loro sottoposti) e i PM (alla loro squadra)."""
import re
from datetime import date

from . import dossier, ginnasio
from .memoria_lavoro import SEGRETO
from .scheda_progetto import SchedaNonValida

MAX_MEMBRI = 8
MAX_KPI_PER_AGENTE = 5
ESITI = ("in_linea", "a_rischio", "fuori_rotta", "raggiunto")


class ErroreSquadra(Exception):
    pass


def _testo(v, massimo: int) -> str:
    t = re.sub(r"[ \t]+", " ", str(v or "")).strip()
    if len(t) > massimo:
        raise ErroreSquadra(f"Testo troppo lungo: massimo {massimo} caratteri")
    if SEGRETO.search(t):
        raise ErroreSquadra("Il testo sembra contenere una chiave o una password")
    return t


def progetto_del_pm(conn, agente_id: int, nome=None) -> dict:
    ps = conn.execute("SELECT id, nome FROM progetti WHERE pm_agente_id = %s AND NOT archiviato AND eliminato_il IS NULL", (agente_id,)).fetchall()
    if not ps:
        raise ErroreSquadra("Non sei il project manager di alcun progetto")
    n = str(nome or "").strip().lower()
    if n:
        ps = [p for p in ps if n in p["nome"].lower()]
    if len(ps) != 1:
        raise ErroreSquadra("Indica il nome del progetto")
    return ps[0]


def _ancestor(conn, superiore_id: int, agente_id: int) -> bool:
    return conn.execute("""WITH RECURSIVE su(id) AS (SELECT superiore_id FROM agenti WHERE id = %s UNION SELECT a.superiore_id FROM agenti a JOIN su ON a.id = su.id WHERE a.superiore_id IS NOT NULL)
                           SELECT 1 FROM su WHERE id = %s""", (agente_id, superiore_id)).fetchone() is not None


# ---------- ricerca e proposta della squadra ----------
def cerca(conn, richieste: list[dict]) -> str:
    """Per ogni competenza richiesta: gli agenti che la hanno (livello, carico, affidabilita') e le lacune."""
    if not isinstance(richieste, list) or not richieste:
        raise ErroreSquadra("Indica almeno una competenza: [{competenza, livello_minimo}]")
    out = []
    for r in richieste[:10]:
        nome = ginnasio._nome((r or {}).get("competenza"))
        try:
            minimo = int((r or {}).get("livello_minimo") or 1)
        except (TypeError, ValueError):
            minimo = 1
        comp = conn.execute("SELECT id, nome FROM competenze WHERE lower(nome) = lower(%s) OR lower(nome) LIKE %s ORDER BY (lower(nome) = lower(%s)) DESC LIMIT 1",
                            (nome, "%" + nome.lower() + "%", nome)).fetchone() if nome else None
        if comp is None:
            out.append(f"- «{nome}»: competenza non presente in libreria → LACUNA (chiedila al Ginnasio con formazione_richiedi)")
            continue
        righe = conn.execute(
            """SELECT a.id, a.nome, a.ruolo, x.livello, d.nome AS reparto,
                      (SELECT count(*) FROM task t WHERE t.assegnato_agente_id = a.id AND t.stato <> 'completata') AS aperte,
                      (SELECT count(*) FROM progetti_agenti pa JOIN progetti p ON p.id = pa.progetto_id WHERE pa.agente_id = a.id AND NOT p.archiviato AND p.eliminato_il IS NULL AND pa.squadra) AS progetti
               FROM agenti_competenze x JOIN agenti a ON a.id = x.agente_id LEFT JOIN divisioni d ON d.id = a.divisione_id
               WHERE x.competenza_id = %s AND a.attivo AND NOT a.sentinella AND a.ruolo_speciale IS NULL ORDER BY x.livello DESC, a.nome""", (comp["id"],)).fetchall()
        adatti = [a for a in righe if a["livello"] >= minimo]
        if not adatti:
            out.append(f"- «{comp['nome']}» livello ≥ {minimo}: nessun agente" + (f" (il migliore e' livello {righe[0]['livello']})" if righe else "") + " → LACUNA")
            continue
        out.append(f"- «{comp['nome']}» livello ≥ {minimo}:")
        for a in adatti[:6]:
            st = dossier.statistiche(conn, a["id"])
            aff = f"affidabilita' {round(st['tasso_approvazione'] * 100)}% su {st['casi']} casi" if st["tasso_approvazione"] is not None else "affidabilita' non ancora misurabile"
            out.append(f"    · {a['nome']} ({a['reparto'] or '—'}): livello {a['livello']}, {a['aperte']} task aperte, {a['progetti']} squadre, {aff}")
    return "\n".join(out)


def proponi(conn, pm_id: int, dati: dict) -> str:
    p = progetto_del_pm(conn, pm_id, dati.get("progetto"))
    membri = dati.get("membri")
    if not isinstance(membri, list) or not membri:
        raise ErroreSquadra("Indica i membri: [{agente, ruolo, motivo}]")
    if len(membri) > MAX_MEMBRI:
        raise ErroreSquadra(f"Una squadra ha al massimo {MAX_MEMBRI} membri")
    if conn.execute("SELECT 1 FROM squadre_proposte WHERE progetto_id = %s AND stato = 'proposta'", (p["id"],)).fetchone():
        raise ErroreSquadra("C'e' gia' una proposta di squadra in attesa di approvazione per questo progetto")
    righe = []
    for m in membri:
        n = ginnasio._nome((m or {}).get("agente"))
        a = conn.execute("SELECT id, nome FROM agenti WHERE attivo AND lower(nome) = lower(%s) AND NOT sentinella AND ruolo_speciale IS NULL", (n,)).fetchone()
        if a is None:
            raise ErroreSquadra(f"Agente «{n}» non trovato (usa il nome esatto)")
        righe.append((a["id"], _testo((m or {}).get("ruolo"), 120), _testo((m or {}).get("motivo"), 300)))
    sid = conn.execute("INSERT INTO squadre_proposte (progetto_id, proposta_da_agente_id, motivazione, lacune) VALUES (%s,%s,%s,%s) RETURNING id",
                       (p["id"], pm_id, _testo(dati.get("motivazione"), 1500), _testo(dati.get("lacune"), 800))).fetchone()["id"]
    for aid, ruolo, motivo in righe:
        conn.execute("INSERT INTO squadre_proposte_membri (proposta_id, agente_id, ruolo_progetto, motivo) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (sid, aid, ruolo, motivo))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                 (f"Il project manager propone una squadra per «{p['nome']}» ({len(righe)} agenti): da approvare nella dashboard del progetto.",))
    return f"Proposta di squadra #{sid} per «{p['nome']}» registrata: la approva Lorenzo."


def decidi(conn, proposta_id: int, approva: bool, utente_id: int, nota: str | None = None) -> dict:
    s = conn.execute("SELECT * FROM squadre_proposte WHERE id = %s FOR UPDATE", (proposta_id,)).fetchone()
    if s is None or s["stato"] != "proposta":
        raise ErroreSquadra("Proposta non trovata o gia' decisa")
    if not approva:
        conn.execute("UPDATE squadre_proposte SET stato = 'respinta', nota = %s, deciso_il = NOW(), deciso_da_utente_id = %s WHERE id = %s", (_testo(nota, 500) or None, utente_id, proposta_id))
        if s["proposta_da_agente_id"]:
            conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)",
                         (s["proposta_da_agente_id"], f"Lorenzo ha respinto la squadra proposta" + (f": {nota}" if nota else ".")))
        return {"stato": "respinta"}
    p = conn.execute("SELECT nome FROM progetti WHERE id = %s", (s["progetto_id"],)).fetchone()
    aggiunti = []
    for m in conn.execute("SELECT m.*, a.nome, a.superiore_id FROM squadre_proposte_membri m JOIN agenti a ON a.id = m.agente_id WHERE m.proposta_id = %s", (proposta_id,)).fetchall():
        aggiungi(conn, s["progetto_id"], m["agente_id"], m["ruolo_progetto"], p["nome"])
        aggiunti.append(m["nome"])
    conn.execute("UPDATE squadre_proposte SET stato = 'approvata', nota = %s, deciso_il = NOW(), deciso_da_utente_id = %s WHERE id = %s", (_testo(nota, 500) or None, utente_id, proposta_id))
    if s["proposta_da_agente_id"]:
        conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)",
                     (s["proposta_da_agente_id"], f"Lorenzo ha approvato la squadra di «{p['nome']}»: {', '.join(aggiunti)}. Assegna ora KPI e task."))
    return {"stato": "approvata", "aggiunti": aggiunti}


def aggiungi(conn, progetto_id: int, agente_id: int, ruolo: str, nome_progetto: str):
    """Aggrega l'agente al progetto e avvisa lui e il suo manager d'area (che puo' richiamarlo)."""
    nuovo = conn.execute("SELECT 1 FROM progetti_agenti WHERE progetto_id = %s AND agente_id = %s AND squadra", (progetto_id, agente_id)).fetchone() is None
    conn.execute("""INSERT INTO progetti_agenti (progetto_id, agente_id, ruolo_progetto, squadra, aggregato_il) VALUES (%s,%s,%s,TRUE,NOW())
                    ON CONFLICT (progetto_id, agente_id) DO UPDATE SET ruolo_progetto = EXCLUDED.ruolo_progetto, squadra = TRUE, aggregato_il = COALESCE(progetti_agenti.aggregato_il, NOW())""",
                 (progetto_id, agente_id, ruolo or None))
    if not nuovo:
        return
    a = conn.execute("SELECT nome, superiore_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)",
                 (agente_id, f"Sei stato aggregato al progetto «{nome_progetto}»" + (f" come {ruolo}" if ruolo else "") + ": il project manager coordina il tuo lavoro su questo progetto, il tuo manager resta il tuo riferimento per tutto il resto."))
    if a["superiore_id"]:
        conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)",
                     (a["superiore_id"], f"{a['nome']} e' stato aggregato al progetto «{nome_progetto}»" + (f" come {ruolo}" if ruolo else "") + ". Se ti serve, puoi richiamarlo con squadra_richiama."))


def rimuovi(conn, progetto_id: int, agente_id: int):
    conn.execute("DELETE FROM progetti_agenti WHERE progetto_id = %s AND agente_id = %s AND squadra", (progetto_id, agente_id))
    conn.execute("UPDATE kpi_progetto SET chiuso = TRUE WHERE progetto_id = %s AND agente_id = %s", (progetto_id, agente_id))


def richiama(conn, manager_id: int, agente: str, progetto: str, motivo: str) -> str:
    n = ginnasio._nome(agente)
    a = conn.execute("SELECT id, nome FROM agenti WHERE attivo AND lower(nome) = lower(%s)", (n,)).fetchone()
    if a is None:
        raise ErroreSquadra("Agente non trovato")
    if not _ancestor(conn, manager_id, a["id"]):
        raise ErroreSquadra("Puoi richiamare solo agenti che dipendono da te")
    p = conn.execute("SELECT p.id, p.nome, p.pm_agente_id FROM progetti p JOIN progetti_agenti x ON x.progetto_id = p.id AND x.agente_id = %s AND x.squadra WHERE lower(p.nome) LIKE %s LIMIT 1",
                     (a["id"], "%" + str(progetto or "").strip().lower() + "%")).fetchone()
    if p is None:
        raise ErroreSquadra("Quell'agente non e' in una squadra con quel nome")
    motivo = _testo(motivo, 400)
    if len(motivo) < 10:
        raise ErroreSquadra("Spiega il motivo del richiamo")
    rimuovi(conn, p["id"], a["id"])
    m = conn.execute("SELECT nome FROM agenti WHERE id = %s", (manager_id,)).fetchone()
    if p["pm_agente_id"]:
        conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)", (p["pm_agente_id"], f"{m['nome']} ha richiamato {a['nome']} dalla squadra di «{p['nome']}»: {motivo}"))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"{m['nome']} ha richiamato {a['nome']} dal progetto «{p['nome']}»: {motivo[:120]}",))
    return f"{a['nome']} richiamato dalla squadra di «{p['nome']}». Il PM e Lorenzo sono stati avvisati."


# ---------- KPI ----------
def _numero(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ErroreSquadra("Il valore deve essere un numero")


def kpi_assegna(conn, pm_id: int, dati: dict, *, utente_id=None, progetto_id=None) -> int:
    if progetto_id is None:
        progetto_id = progetto_del_pm(conn, pm_id, dati.get("progetto"))["id"]
    n = ginnasio._nome(dati.get("agente"))
    a = conn.execute("""SELECT a.id FROM agenti a JOIN progetti_agenti x ON x.agente_id = a.id AND x.progetto_id = %s WHERE a.attivo AND lower(a.nome) = lower(%s)""", (progetto_id, n)).fetchone()
    if a is None:
        raise ErroreSquadra(f"«{n}» non fa parte di questo progetto")
    nome = _testo(dati.get("nome"), 120)
    if len(nome) < 3:
        raise ErroreSquadra("Dai un nome al KPI (almeno 3 caratteri)")
    if conn.execute("SELECT count(*) AS n FROM kpi_progetto WHERE progetto_id = %s AND agente_id = %s AND NOT chiuso", (progetto_id, a["id"])).fetchone()["n"] >= MAX_KPI_PER_AGENTE:
        raise ErroreSquadra(f"Al massimo {MAX_KPI_PER_AGENTE} KPI aperti per agente")
    sc = None
    if str(dati.get("scadenza") or "").strip():
        try:
            sc = date.fromisoformat(str(dati["scadenza"]).strip())
        except ValueError:
            raise ErroreSquadra("La scadenza deve essere AAAA-MM-GG")
    return conn.execute(
        """INSERT INTO kpi_progetto (progetto_id, agente_id, nome, obiettivo, unita, valore_obiettivo, scadenza, assegnato_da_agente_id, assegnato_da_utente_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (progetto_id, a["id"], nome, _testo(dati.get("obiettivo"), 500), _testo(dati.get("unita"), 30), _numero(dati.get("valore_obiettivo")), sc, pm_id, utente_id)).fetchone()["id"]


def kpi_aggiorna(conn, pm_id: int | None, dati: dict, *, progetto_id=None):
    k = conn.execute("SELECT k.*, p.pm_agente_id FROM kpi_progetto k JOIN progetti p ON p.id = k.progetto_id WHERE k.id = %s", (int(dati.get("id") or 0),)).fetchone()
    if k is None or (pm_id is not None and k["pm_agente_id"] != pm_id) or (progetto_id is not None and k["progetto_id"] != progetto_id):
        raise ErroreSquadra("KPI non trovato nel tuo progetto")
    esito = dati.get("esito")
    if esito and esito not in ESITI:
        raise ErroreSquadra("Esito non valido: " + ", ".join(ESITI))
    conn.execute("""UPDATE kpi_progetto SET valore = COALESCE(%s, valore), esito = COALESCE(%s, esito), nota = COALESCE(%s, nota), chiuso = COALESCE(%s, chiuso), aggiornato_il = NOW() WHERE id = %s""",
                 (_numero(dati.get("valore")), esito or None, _testo(dati.get("nota"), 500) or None, dati.get("chiuso") if isinstance(dati.get("chiuso"), bool) else None, k["id"]))


def kpi_elenco(conn, progetto_id: int, agente_id: int | None = None, solo_aperti: bool = True) -> list[dict]:
    return conn.execute(
        """SELECT k.*, a.nome AS agente FROM kpi_progetto k JOIN agenti a ON a.id = k.agente_id WHERE k.progetto_id = %s AND (%s::int IS NULL OR k.agente_id = %s)
           AND (NOT %s OR NOT k.chiuso) ORDER BY a.nome, k.id""", (progetto_id, agente_id, agente_id, solo_aperti)).fetchall()


def _riga_kpi(k: dict) -> str:
    v = f"{k['valore']:g}" if k["valore"] is not None else "—"
    ob = f" / obiettivo {k['valore_obiettivo']:g}{(' ' + k['unita']) if k['unita'] else ''}" if k["valore_obiettivo"] is not None else ""
    return f"#{k['id']} {k['nome']}: {v}{ob}" + (f" [{k['esito']}]" if k["esito"] else "") + (f", entro {k['scadenza']:%d/%m/%Y}" if k["scadenza"] else "") + (f" — {k['obiettivo']}" if k["obiettivo"] else "")


def metriche_misurate(conn, progetto_id: int, agente_id: int) -> dict:
    """Numeri veri del lavoro nel progetto: task chiuse, aperte, in ritardo, pollici ricevuti."""
    t = conn.execute("""SELECT count(*) FILTER (WHERE stato = 'completata') AS chiuse, count(*) FILTER (WHERE stato <> 'completata') AS aperte,
                               count(*) FILTER (WHERE stato <> 'completata' AND scadenza < CURRENT_DATE) AS in_ritardo
                        FROM task WHERE progetto_id = %s AND assegnato_agente_id = %s""", (progetto_id, agente_id)).fetchone()
    v = conn.execute("SELECT count(*) FILTER (WHERE voto = 1) AS su, count(*) FILTER (WHERE voto = -1) AS giu FROM valutazioni WHERE agente_id = %s AND progetto_id = %s", (agente_id, progetto_id)).fetchone()
    return {"chiuse": int(t["chiuse"]), "aperte": int(t["aperte"]), "in_ritardo": int(t["in_ritardo"]), "pollici_su": int(v["su"]), "pollici_giu": int(v["giu"])}


def squadra(conn, progetto_id: int) -> list[dict]:
    righe = conn.execute(
        """SELECT a.id, a.nome, a.ruolo, x.ruolo_progetto, x.squadra, x.aggregato_il, d.nome AS reparto, (p.pm_agente_id = a.id) AS e_pm
           FROM progetti_agenti x JOIN agenti a ON a.id = x.agente_id JOIN progetti p ON p.id = x.progetto_id LEFT JOIN divisioni d ON d.id = a.divisione_id
           WHERE x.progetto_id = %s AND a.attivo AND (x.squadra OR p.pm_agente_id = a.id) ORDER BY (p.pm_agente_id = a.id) DESC, a.nome""", (progetto_id,)).fetchall()
    for r in righe:
        r["livello_formazione"] = ginnasio.livello_agente(conn, r["id"])
        r["competenze"] = [f"{c['nome']} ({c['livello']})" for c in ginnasio.competenze_agente(conn, r["id"])]
        r["kpi"] = kpi_elenco(conn, progetto_id, r["id"], solo_aperti=False)
        r["misure"] = metriche_misurate(conn, progetto_id, r["id"])
    return righe


# ---------- valutazioni di manager e PM ----------
def valuta(conn, da_id: int, dati: dict) -> str:
    n = ginnasio._nome(dati.get("agente"))
    a = conn.execute("SELECT id, nome, divisione_id FROM agenti WHERE attivo AND lower(nome) = lower(%s)", (n,)).fetchone()
    if a is None:
        raise ErroreSquadra("Agente non trovato (usa il nome esatto)")
    prog = None
    pid = None
    if str(dati.get("progetto") or "").strip():
        prog = conn.execute("SELECT id, nome, pm_agente_id FROM progetti WHERE lower(nome) LIKE %s AND eliminato_il IS NULL LIMIT 1", ("%" + str(dati["progetto"]).strip().lower() + "%",)).fetchone()
        pid = prog["id"] if prog else None
    e_pm_suo = bool(prog and prog["pm_agente_id"] == da_id and conn.execute("SELECT 1 FROM progetti_agenti WHERE progetto_id = %s AND agente_id = %s", (prog["id"], a["id"])).fetchone())
    if not (_ancestor(conn, da_id, a["id"]) or e_pm_suo):
        raise ErroreSquadra("Puoi valutare i tuoi sottoposti o, se sei PM, chi e' nella squadra del tuo progetto")
    v = str(dati.get("voto") or "").lower()
    voto = 1 if v in ("su", "1", "positivo", "+") else -1 if v in ("giu", "-1", "negativo", "-") else 0
    if not voto:
        raise ErroreSquadra("Il voto e' «su» o «giu»")
    nota = _testo(dati.get("nota"), 1000)
    if voto == -1 and len(nota) < 8:
        raise ErroreSquadra("Un voto negativo richiede un motivo concreto")
    oggetto_id = None
    if dati.get("task_id"):
        t = conn.execute("SELECT id FROM task WHERE id = %s AND assegnato_agente_id = %s", (int(dati["task_id"]), a["id"])).fetchone()
        if t is None:
            raise ErroreSquadra("Quella task non e' di quell'agente")
        oggetto_id = t["id"]
        conn.execute("DELETE FROM valutazioni WHERE da_agente_id = %s AND oggetto = 'task' AND oggetto_id = %s", (da_id, oggetto_id))
    conn.execute("INSERT INTO valutazioni (agente_id, da_agente_id, oggetto, oggetto_id, voto, nota, progetto_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                 (a["id"], da_id, "task" if oggetto_id else "altro", oggetto_id, voto, nota or None, pid))
    if voto == -1:
        from . import memoria_lavoro
        chi = conn.execute("SELECT nome FROM agenti WHERE id = %s", (da_id,)).fetchone()["nome"]
        try:
            memoria_lavoro.proponi(conn, f"Da evitare (segnalato da {chi}): {nota}", "errore", divisione_id=a["divisione_id"], fonte="valutazione negativa",
                                   ambito_agente_id=a["id"], origine="valutazione")
        except memoria_lavoro.MemoriaNonValida:
            pass
    return f"Valutazione {'positiva' if voto > 0 else 'negativa'} registrata per {a['nome']}."


# ---------- lato agente ----------
STRUMENTI_PM = [
    {"name": "squadra_cerca",
     "description": "Cerca chi ha le competenze che servono al tuo progetto. competenze: elenco di {competenza, livello_minimo (1-5)}. Per ogni competenza restituisce gli agenti con livello, carico di lavoro, numero di squadre e affidabilita', e segnala le lacune.",
     "input_schema": {"type": "object", "properties": {"competenze": {"type": "array", "items": {"type": "object", "properties": {"competenza": {"type": "string"}, "livello_minimo": {"type": "integer"}}, "required": ["competenza"]}}}, "required": ["competenze"]}},
    {"name": "squadra_proponi",
     "description": "Proponi la squadra del tuo progetto (massimo 8 agenti, ognuno con ruolo e motivo). La approva Lorenzo; poi gli agenti entrano nel progetto e i loro manager d'area vengono avvisati. "
                    "In lacune scrivi le competenze che mancano (le chiedi anche con formazione_richiedi).",
     "input_schema": {"type": "object", "properties": {"progetto": {"type": "string"}, "motivazione": {"type": "string"}, "lacune": {"type": "string"},
                                                       "membri": {"type": "array", "items": {"type": "object", "properties": {"agente": {"type": "string"}, "ruolo": {"type": "string"}, "motivo": {"type": "string"}}, "required": ["agente"]}}},
                      "required": ["motivazione", "membri"]}},
    {"name": "kpi_assegna",
     "description": "Assegna un KPI a un agente della tua squadra: nome, obiettivo a parole, valore_obiettivo numerico e unita (facoltativi), scadenza AAAA-MM-GG. Massimo 5 KPI aperti per agente.",
     "input_schema": {"type": "object", "properties": {"progetto": {"type": "string"}, "agente": {"type": "string"}, "nome": {"type": "string"}, "obiettivo": {"type": "string"},
                                                       "valore_obiettivo": {"type": "number"}, "unita": {"type": "string"}, "scadenza": {"type": "string"}}, "required": ["agente", "nome"]}},
    {"name": "kpi_aggiorna",
     "description": "Aggiorna un KPI della tua squadra (id dall'elenco): valore misurato, esito (in_linea, a_rischio, fuori_rotta, raggiunto), nota; chiuso=true lo chiude.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}, "valore": {"type": "number"}, "esito": {"type": "string", "enum": list(ESITI)}, "nota": {"type": "string"}, "chiuso": {"type": "boolean"}}, "required": ["id"]}},
]
STRUMENTO_VALUTA = {"name": "valuta_agente",
                    "description": "Dai un pollice a un agente che lavora per te (o, se sei PM, alla tua squadra): voto «su» o «giu», nota (obbligatoria per «giu»: cosa non andava), task_id facoltativo. "
                                   "Le tue valutazioni alimentano il suo dossier di affidabilita'. Valuta in modo concreto e con onesta': serve a capire chi lavora bene.",
                    "input_schema": {"type": "object", "properties": {"agente": {"type": "string"}, "voto": {"type": "string", "enum": ["su", "giu"]}, "nota": {"type": "string"}, "task_id": {"type": "integer"}, "progetto": {"type": "string"}}, "required": ["agente", "voto"]}}
STRUMENTO_RICHIAMA = {"name": "squadra_richiama",
                      "description": "Richiama un tuo agente da una squadra di progetto (serve un motivo). Il project manager e Lorenzo vengono avvisati.",
                      "input_schema": {"type": "object", "properties": {"agente": {"type": "string"}, "progetto": {"type": "string"}, "motivo": {"type": "string"}}, "required": ["agente", "progetto", "motivo"]}}

AVVISO_PM = ("\n\nSQUADRA E KPI: dal brief del progetto ricava le competenze che servono (con il livello), cercale con squadra_cerca e proponi la squadra con squadra_proponi: scegli pochi agenti, con un ruolo chiaro. "
             "Le lacune chiedile al Ginnasio con formazione_richiedi. Quando la squadra e' approvata assegna a ciascuno 1-3 KPI misurabili (kpi_assegna), aggiornali con i dati veri (kpi_aggiorna) e valuta il lavoro con valuta_agente. "
             "Il manager d'area resta il proprietario dell'agente: tu comandi sul lavoro dentro il progetto.")
AVVISO_MANAGER = ("\n\nVALUTAZIONI: valuta il lavoro dei tuoi sottoposti con valuta_agente (su/giu, con motivo concreto per il giu): sei tu, non Lorenzo, a monitorarne la qualita'. "
                  "Se un tuo agente e' stato aggregato a una squadra e ti serve, puoi richiamarlo con squadra_richiama.")


def gestore(connessione_, agente_id: int):
    def f(nome, dati):
        try:
            with connessione_() as conn:
                if nome == "squadra_cerca":
                    return cerca(conn, dati.get("competenze"))
                if nome == "squadra_proponi":
                    return proponi(conn, agente_id, dati)
                if nome == "kpi_assegna":
                    return f"KPI #{kpi_assegna(conn, agente_id, dati)} assegnato."
                if nome == "kpi_aggiorna":
                    kpi_aggiorna(conn, agente_id, dati)
                    return "KPI aggiornato."
                if nome == "valuta_agente":
                    return valuta(conn, agente_id, dati)
                if nome == "squadra_richiama":
                    return richiama(conn, agente_id, dati.get("agente"), dati.get("progetto"), dati.get("motivo"))
        except (ErroreSquadra, SchedaNonValida) as e:
            return "ERRORE: " + str(e)
        return "ERRORE: strumento sconosciuto"
    return f


def contesto_kpi(conn, a: dict) -> str:
    """I KPI aperti dell'agente nei suoi progetti: li legge a ogni richiesta."""
    righe = conn.execute(
        """SELECT k.*, p.nome AS progetto FROM kpi_progetto k JOIN progetti p ON p.id = k.progetto_id
           WHERE k.agente_id = %s AND NOT k.chiuso AND NOT p.archiviato AND p.eliminato_il IS NULL ORDER BY k.progetto_id, k.id LIMIT 8""", (a["id"],)).fetchall()
    if not righe:
        return ""
    return "I TUOI KPI (come viene misurato il tuo lavoro nei progetti):\n" + "\n".join(f"- «{r['progetto']}» {_riga_kpi(r)}" for r in righe)


def avanzamento_progetti(conn) -> str:
    """Per chi vede tutto (Aurora): lo stato di ogni progetto attivo, con il suo PM, i numeri e i KPI a rischio."""
    ps = conn.execute("""SELECT p.id, p.nome, p.stato_attuale, p.prossimi_passi, p.nodi_aperti, a.nome AS pm,
                                (SELECT count(*) FROM task t WHERE t.progetto_id = p.id AND t.stato <> 'completata') AS aperte,
                                (SELECT count(*) FROM task t WHERE t.progetto_id = p.id AND t.stato = 'completata') AS chiuse,
                                (SELECT count(*) FROM task t WHERE t.progetto_id = p.id AND t.stato <> 'completata' AND t.scadenza < CURRENT_DATE) AS ritardo
                         FROM progetti p LEFT JOIN agenti a ON a.id = p.pm_agente_id WHERE NOT p.archiviato AND p.eliminato_il IS NULL AND p.pm_agente_id IS NOT NULL
                         ORDER BY p.scheda_il DESC NULLS LAST, p.id DESC LIMIT 8""").fetchall()
    if not ps:
        return ""
    out = []
    for p in ps:
        riga = f"- «{p['nome']}» (PM {p['pm']}): {p['aperte']} task aperte, {p['chiuse']} chiuse" + (f", {p['ritardo']} in ritardo" if p["ritardo"] else "")
        if p["stato_attuale"]:
            riga += f"\n    Stato: {p['stato_attuale'][:300]}"
        if p["nodi_aperti"]:
            riga += f"\n    Nodi aperti: {p['nodi_aperti'][:250]}"
        rischio = conn.execute("SELECT k.nome, k.esito, a.nome AS agente FROM kpi_progetto k JOIN agenti a ON a.id = k.agente_id WHERE k.progetto_id = %s AND NOT k.chiuso AND k.esito IN ('a_rischio','fuori_rotta') LIMIT 4", (p["id"],)).fetchall()
        if rischio:
            riga += "\n    KPI a rischio: " + "; ".join(f"{r['agente']}: {r['nome']} [{r['esito']}]" for r in rischio)
        out.append(riga)
    return ("AVANZAMENTO DEI PROGETTI (i project manager hanno lo stesso ruolo dei manager di dipartimento: quando Lorenzo chiede un avanzamento lavori interrogali con chiedi_a_agente insieme ai manager, "
            "e riporta il loro punto di vista oltre a questi dati):\n" + "\n".join(out))
