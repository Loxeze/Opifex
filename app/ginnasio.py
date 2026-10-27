"""Ginnasio: competenze a cinque livelli (junior → master), coda di formazione con graduatoria e formazione svolta da Padre Casati.
Le richieste arrivano da manager, project manager, segnali automatici o da Lorenzo ed entrano da sole in coda; il budget giornaliero di token e la
graduatoria (riordinabile) decidono cosa si forma oggi. Una competenza scritta da Padre Casati e' una bozza: arriva a un agente solo dopo l'approvazione."""
import re
import threading
from datetime import date, datetime, timedelta, timezone

from .db import connessione
from .memoria_lavoro import SEGRETO

SINCRONO = False   # nei collaudi si esegue nello stesso thread
LIVELLI = {1: "Junior", 2: "Medium", 3: "Senior", 4: "Expert", 5: "Master"}
FOCUS = {
    1: "fondamenti: vocabolario, procedura di base passo per passo, errori tipici dei principianti, cosa chiedere prima di iniziare",
    2: "applicazione a casi reali: scelta degli strumenti, metriche e controlli di qualita', varianti ricorrenti, come lavorare con altre competenze",
    3: "strategia: trade-off, casi complessi, priorita', come impostare un progetto intero e coordinare altri",
    4: "ottimizzazione e diagnosi: come capire perche' qualcosa non funziona, casi limite, norme e fonti da tenere aggiornate",
    5: "eccellenza: giudizio sui casi nuovi, innovazione, quando NON applicare le regole, come formare altri",
}
# stima prudente dei token di una formazione (ricerca + stesura): si affina con i dati reali (token_usati)
STIMA_TOKEN = {1: 8000, 2: 12000, 3: 18000, 4: 25000, 5: 35000}
MAX_TOKEN_ESECUZIONE = {1: 3500, 2: 4500, 3: 5500, 4: 6500, 5: 7500}
MAX_RICHIESTE_SETTIMANA = 3
MAX_TENTATIVI = 2
GIORNI_VERIFICA = 180
MAX_CORPO = 12000


class ErroreGinnasio(Exception):
    pass


def impostazione(conn, chiave: str, default: str = "") -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return (r["valore"] if r else default) or default


def imposta(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, valore))


def _nome(testo, massimo=100) -> str:
    return re.sub(r"\s+", " ", str(testo or "")).strip()[:massimo]


def trova_o_crea(conn, nome: str, descrizione: str = "") -> dict:
    n = _nome(nome)
    if len(n) < 3:
        raise ErroreGinnasio("Il nome della competenza deve avere almeno 3 caratteri")
    r = conn.execute("SELECT * FROM competenze WHERE lower(nome) = lower(%s)", (n,)).fetchone()
    if r:
        return r
    return conn.execute("INSERT INTO competenze (nome, descrizione) VALUES (%s,%s) RETURNING *", (n, _nome(descrizione, 300))).fetchone()


def livello_approvato(conn, competenza_id: int, livello: int) -> dict | None:
    return conn.execute("SELECT * FROM competenze_livelli WHERE competenza_id = %s AND livello = %s AND stato = 'approvata'", (competenza_id, livello)).fetchone()


def ruolo_agente(conn, agente_id: int) -> str:
    """'pm', 'manager' o 'altro': i primi due si formano per primi."""
    if conn.execute("SELECT 1 FROM progetti WHERE pm_agente_id = %s", (agente_id,)).fetchone():
        return "pm"
    r = conn.execute("SELECT livello FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    return "manager" if r and r["livello"] in ("manager", "referente") else "altro"


# ---------- richieste ----------
def richiedi(conn, competenza: str, livello: int, *, agente_id=None, motivo: str = "", progetto_id=None, origine: str = "manuale",
             da_agente_id=None, da_utente_id=None, urgenza: int = 2) -> dict:
    """Mette una richiesta in coda. Una richiesta uguale gia' in coda si unisce (cresce il peso, non il numero)."""
    try:
        livello = int(livello)
        urgenza = int(urgenza)
    except (TypeError, ValueError):
        raise ErroreGinnasio("Livello o urgenza non validi")
    if livello not in LIVELLI:
        raise ErroreGinnasio("Il livello va da 1 (Junior) a 5 (Master)")
    if urgenza not in (1, 2, 3):
        raise ErroreGinnasio("L'urgenza va da 1 a 3")
    nome = _nome(competenza)
    if len(nome) < 3:
        raise ErroreGinnasio("Indica la competenza (almeno 3 caratteri)")
    motivo = re.sub(r"[ \t]+", " ", str(motivo or "")).strip()[:800]
    if SEGRETO.search(motivo):
        raise ErroreGinnasio("Il motivo sembra contenere una chiave o una password")
    if da_agente_id and len(motivo) < 30:
        raise ErroreGinnasio("Spiega il motivo in modo concreto (almeno 30 caratteri): quale lacuna hai visto e in quale progetto")
    if agente_id and not conn.execute("SELECT 1 FROM agenti WHERE id = %s AND attivo", (agente_id,)).fetchone():
        raise ErroreGinnasio("Agente inesistente o spento")
    if progetto_id and not conn.execute("SELECT 1 FROM progetti WHERE id = %s", (progetto_id,)).fetchone():
        raise ErroreGinnasio("Progetto inesistente")
    comp = conn.execute("SELECT id FROM competenze WHERE lower(nome) = lower(%s)", (nome,)).fetchone()
    if comp:
        if livello_approvato(conn, comp["id"], livello):
            if not agente_id or conn.execute("SELECT 1 FROM agenti_competenze WHERE agente_id = %s AND competenza_id = %s AND livello >= %s", (agente_id, comp["id"], livello)).fetchone():
                raise ErroreGinnasio("Questo livello esiste gia'" + (" e l'agente lo ha gia'" if agente_id else ""))
            try:   # il testo c'e' gia': basta assegnarlo, senza spendere token
                assegna(conn, agente_id, comp["id"], livello)
                return {"id": None, "unita": False, "assegnata": True}
            except ErroreGinnasio:
                pass
        if livello > 1 and not livello_approvato(conn, comp["id"], livello - 1) and not conn.execute(
                "SELECT 1 FROM richieste_formazione WHERE competenza_id = %s AND livello = %s AND stato IN ('in_coda','in_corso','da_approvare')", (comp["id"], livello - 1)).fetchone():
            raise ErroreGinnasio(f"Serve prima il livello {livello - 1} ({LIVELLI[livello - 1]}) di «{nome}»")
    elif livello > 1:
        raise ErroreGinnasio(f"La competenza «{nome}» non esiste ancora: si parte dal livello 1 (Junior)")
    if da_agente_id:
        n = conn.execute("SELECT count(*) AS n FROM richieste_formazione WHERE richiesta_da_agente_id = %s AND stato <> 'annullata' AND creata_il > NOW() - interval '7 days'",
                         (da_agente_id,)).fetchone()["n"]
        if n >= MAX_RICHIESTE_SETTIMANA:
            raise ErroreGinnasio(f"Hai gia' fatto {MAX_RICHIESTE_SETTIMANA} richieste di formazione negli ultimi 7 giorni")
    dup = conn.execute("""SELECT id FROM richieste_formazione WHERE stato IN ('in_coda','in_corso','da_approvare') AND lower(competenza_nome) = lower(%s) AND livello = %s
                          AND agente_id IS NOT DISTINCT FROM %s""", (nome, livello, agente_id)).fetchone()
    if dup:
        conn.execute("""UPDATE richieste_formazione SET peso = peso + 1, urgenza = GREATEST(urgenza, %s),
                        motivo = CASE WHEN %s <> '' AND position(%s in motivo) = 0 THEN left(motivo || E'\\n' || %s, 1500) ELSE motivo END WHERE id = %s""",
                     (urgenza, motivo, motivo, motivo, dup["id"]))
        return {"id": dup["id"], "unita": True}
    rid = conn.execute(
        """INSERT INTO richieste_formazione (agente_id, competenza_id, competenza_nome, livello, motivo, progetto_id, origine, richiesta_da_agente_id, richiesta_da_utente_id, urgenza)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (agente_id, comp["id"] if comp else None, nome, livello, motivo, progetto_id, origine, da_agente_id, da_utente_id, urgenza)).fetchone()["id"]
    return {"id": rid, "unita": False}


def punteggio(conn, r: dict) -> int:
    """Quanto e' in alto in graduatoria: urgenza, ruolo di chi va formato (PM e manager per primi), peso, attesa, scadenze del progetto, riequilibrio tra reparti."""
    p = r["urgenza"] * 100 + (r["peso"] - 1) * 25
    if r["agente_id"]:
        p += {"pm": 300, "manager": 200}.get(ruolo_agente(conn, r["agente_id"]), 0)
    p += min(60, max(0, (datetime.now(timezone.utc) - r["creata_il"]).days) * 5)
    if r["progetto_id"] and conn.execute("SELECT 1 FROM task WHERE progetto_id = %s AND stato <> 'completata' AND scadenza BETWEEN CURRENT_DATE AND CURRENT_DATE + 14 LIMIT 1", (r["progetto_id"],)).fetchone():
        p += 50
    if r["agente_id"]:
        recenti = conn.execute("""SELECT count(*) AS n FROM richieste_formazione f JOIN agenti x ON x.id = f.agente_id
                                  WHERE f.stato = 'conclusa' AND f.conclusa_il > NOW() - interval '14 days'
                                    AND x.divisione_id IS NOT DISTINCT FROM (SELECT divisione_id FROM agenti WHERE id = %s)""", (r["agente_id"],)).fetchone()["n"]
        p -= min(60, recenti * 15)
    return p - (r["livello"] - 1) * 5


def coda(conn) -> list[dict]:
    """Richieste in coda in ordine di graduatoria (prima l'ordine deciso a mano, poi il punteggio)."""
    righe = conn.execute("""SELECT f.*, a.nome AS agente, a.divisione_id, ra.nome AS richiedente, ru.nome AS richiedente_persona, p.nome AS progetto
                            FROM richieste_formazione f LEFT JOIN agenti a ON a.id = f.agente_id LEFT JOIN agenti ra ON ra.id = f.richiesta_da_agente_id
                            LEFT JOIN utenti ru ON ru.id = f.richiesta_da_utente_id LEFT JOIN progetti p ON p.id = f.progetto_id
                            WHERE f.stato = 'in_coda'""").fetchall()
    for r in righe:
        r["punteggio"] = punteggio(conn, r)
        r["stima_token"] = stima(conn, r["livello"])
    righe.sort(key=lambda r: (r["ordine_manuale"] is None, r["ordine_manuale"] if r["ordine_manuale"] is not None else 0, -r["punteggio"], r["id"]))
    return righe


def stima(conn, livello: int) -> int:
    """Costo atteso di una formazione di questo livello: media dei casi reali conclusi, altrimenti la stima prudente."""
    r = conn.execute("SELECT avg(token_usati)::int AS m, count(*) AS n FROM richieste_formazione WHERE livello = %s AND stato IN ('da_approvare','conclusa') AND token_usati > 0", (livello,)).fetchone()
    return r["m"] if r and r["n"] else STIMA_TOKEN[livello]


def sposta(conn, rid: int, azione: str):
    ordine = [r["id"] for r in coda(conn)]
    if rid not in ordine:
        raise ErroreGinnasio("La richiesta non e' in coda")
    if azione == "automatico":
        conn.execute("UPDATE richieste_formazione SET ordine_manuale = NULL WHERE id = %s", (rid,))
        return
    i = ordine.index(rid)
    if azione == "cima":
        ordine.insert(0, ordine.pop(i))
    elif azione == "su" and i > 0:
        ordine[i - 1], ordine[i] = ordine[i], ordine[i - 1]
    elif azione == "giu" and i < len(ordine) - 1:
        ordine[i + 1], ordine[i] = ordine[i], ordine[i + 1]
    elif azione not in ("su", "giu"):
        raise ErroreGinnasio("Azione non valida")
    for pos, x in enumerate(ordine):
        conn.execute("UPDATE richieste_formazione SET ordine_manuale = %s WHERE id = %s", (pos, x))


def usati_oggi(conn) -> int:
    return conn.execute("SELECT COALESCE(sum(token_usati), 0)::int AS n FROM richieste_formazione WHERE avviata_il::date = CURRENT_DATE").fetchone()["n"]


def stato_generale(conn) -> dict:
    budget = int(impostazione(conn, "ginnasio_budget_giornaliero", "30000") or 30000)
    usati = usati_oggi(conn)
    return {"attivo": impostazione(conn, "ginnasio_attivo", "0") == "1", "budget": budget, "usati_oggi": usati, "residuo": max(0, budget - usati),
            "in_corso": conn.execute("SELECT count(*) AS n FROM richieste_formazione WHERE stato = 'in_corso'").fetchone()["n"]}


# ---------- svolgimento ----------
def prossima_eseguibile(conn) -> dict | None:
    s = stato_generale(conn)
    for r in coda(conn):
        if r["livello"] == 5 and not r["via_libera"]:
            continue    # il master parte solo con il via libera esplicito di Lorenzo
        if r["stima_token"] <= s["residuo"]:
            return r
    return None


def giro(conn):
    """Chiamato dal lavoro di fondo: se attivo e senza formazioni in corso, avvia la prima della graduatoria che sta nel budget di oggi."""
    s = stato_generale(conn)
    if not s["attivo"] or s["in_corso"]:
        return
    r = prossima_eseguibile(conn)
    if r:
        conn.execute("UPDATE richieste_formazione SET stato = 'in_corso', avviata_il = NOW() WHERE id = %s AND stato = 'in_coda'", (r["id"],))
        conn.commit()
        avvia(r["id"])


def avvia_manuale(conn, rid: int):
    """Prova manuale: esegue una richiesta ora, anche con la formazione in pausa (conta nel budget del giorno)."""
    r = conn.execute("SELECT stato FROM richieste_formazione WHERE id = %s FOR UPDATE", (rid,)).fetchone()
    if r is None or r["stato"] != "in_coda":
        raise ErroreGinnasio("La richiesta non e' in coda")
    if conn.execute("SELECT 1 FROM richieste_formazione WHERE stato = 'in_corso'").fetchone():
        raise ErroreGinnasio("C'e' gia' una formazione in corso: aspetta che finisca")
    conn.execute("UPDATE richieste_formazione SET stato = 'in_corso', avviata_il = NOW(), via_libera = TRUE WHERE id = %s", (rid,))
    conn.commit()
    avvia(rid)


def avvia(rid: int):
    if SINCRONO:
        _lavora(rid)
    else:
        threading.Thread(target=_lavora, args=(rid,), daemon=True).start()


def _prompt(conn, r: dict) -> str:
    comp = conn.execute("SELECT * FROM competenze WHERE id = %s", (r["competenza_id"],)).fetchone() if r["competenza_id"] else None
    precedenti = []
    if comp:
        for lv in conn.execute("SELECT livello, corpo FROM competenze_livelli WHERE competenza_id = %s AND livello < %s AND stato = 'approvata' ORDER BY livello", (comp["id"], r["livello"])).fetchall():
            precedenti.append(f"--- Livello {lv['livello']} ({LIVELLI[lv['livello']]}) gia' scritto ---\n{lv['corpo'][:2500]}")
    chi = ""
    if r["agente_id"]:
        a = conn.execute("SELECT nome, ruolo FROM agenti WHERE id = %s", (r["agente_id"],)).fetchone()
        chi = f"\nLa competenza servira' a {a['nome']} ({a['ruolo']})."
    prog = ""
    if r["progetto_id"]:
        p = conn.execute("SELECT nome, obiettivo, descrizione FROM progetti WHERE id = %s", (r["progetto_id"],)).fetchone()
        prog = f"\nProgetto che la richiede: «{p['nome']}». {(p['obiettivo'] or p['descrizione'] or '')[:400]}"
    return (f"FORMAZIONE #{r['id']} — competenza: {r['competenza_nome']}, livello {r['livello']} ({LIVELLI[r['livello']]}).{chi}{prog}\n"
            f"Motivo della richiesta: {r['motivo'] or 'non indicato'}\n"
            + (f"Note di Lorenzo sulla bozza precedente (tienine conto): {r['note']}\n" if r["note"] else "")
            + f"\nScrivi la competenza per questo livello. Cosa deve contenere un livello {LIVELLI[r['livello']]}: {FOCUS[r['livello']]}.\n"
              "Come procedere: 1) biblioteca_cerca per cio' che c'e' gia'; 2) cerca_fonti (poche ricerche mirate) per integrare, senza dati riservati; "
              "3) se serve un PDF proponilo con proponi_download (non si scarica da solo). Non ripetere cio' che dicono i livelli precedenti: aggiungi.\n"
              "Il testo e' istruzione operativa per un agente che dovra' lavorare cosi': metodo a passi, checklist, formato dei risultati, errori da evitare, "
              "domande da fare prima di iniziare, e in fondo una sezione «Fonti» con titolo e indirizzo di ogni fonte usata. Mai password o chiavi. Italiano, concreto.\n"
              "Chiudi la risposta in questo formato esatto:\nDESCRIZIONE: una riga (max 200 caratteri) che dice a cosa serve la competenza e quando usarla\nCOMPETENZA:\n<il testo>\n"
              + ("\n\n" + "\n\n".join(precedenti) if precedenti else ""))


def _parti(testo: str) -> tuple[str, str]:
    m = re.search(r"DESCRIZIONE\s*:\s*(.+?)\s*(?:\n|$)", testo, re.I)
    d = re.sub(r"\s+", " ", m.group(1))[:300] if m else ""
    c = re.search(r"COMPETENZA\s*:\s*(.+)$", testo, re.S | re.I)
    return d, (c.group(1) if c else testo).strip()[:MAX_CORPO]


def _lavora(rid: int):
    from .esecuzione import esegui_agente
    with connessione() as conn:
        r = conn.execute("SELECT * FROM richieste_formazione WHERE id = %s AND stato = 'in_corso'", (rid,)).fetchone()
        if r is None:
            return
        cas = conn.execute("SELECT id FROM agenti WHERE ruolo_speciale = 'formatore' AND attivo LIMIT 1").fetchone()
        if cas is None:
            conn.execute("UPDATE richieste_formazione SET stato = 'errore', errore = 'Padre Casati non e'' attivo', conclusa_il = NOW() WHERE id = %s", (rid,))
            return
        prompt = _prompt(conn, r)
        conn.commit()
    try:
        out = esegui_agente(cas["id"], prompt, "interno", None, max_token=MAX_TOKEN_ESECUZIONE[r["livello"]])
    except Exception as e:  # noqa: BLE001 - la formazione fallita si vede in pagina e non ferma nulla
        with connessione() as conn:
            conn.execute("UPDATE richieste_formazione SET stato = 'errore', errore = %s, conclusa_il = NOW() WHERE id = %s", (str(e)[:300], rid))
        return
    descr, corpo = _parti(out["risposta"])
    token = out["token_input"] + out["token_output"]
    with connessione() as conn:
        if len(corpo) < 200 or SEGRETO.search(corpo):
            conn.execute("UPDATE richieste_formazione SET stato = 'errore', errore = %s, token_usati = %s, conclusa_il = NOW() WHERE id = %s",
                         ("Padre Casati non ha prodotto un testo utilizzabile: riprova dalla pagina", token, rid))
            return
        comp = trova_o_crea(conn, r["competenza_nome"], descr)
        if descr and not comp["descrizione"]:
            conn.execute("UPDATE competenze SET descrizione = %s WHERE id = %s", (descr, comp["id"]))
        conn.execute("UPDATE competenze_livelli SET stato = 'ritirata' WHERE competenza_id = %s AND livello = %s AND stato = 'bozza'", (comp["id"], r["livello"]))
        ver = conn.execute("SELECT COALESCE(max(versione), 0) + 1 AS v FROM competenze_livelli WHERE competenza_id = %s AND livello = %s", (comp["id"], r["livello"])).fetchone()["v"]
        lid = conn.execute("""INSERT INTO competenze_livelli (competenza_id, livello, corpo, descrizione, versione, token_usati) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (comp["id"], r["livello"], corpo, descr, ver, token)).fetchone()["id"]
        conn.execute("UPDATE richieste_formazione SET stato = 'da_approvare', competenza_id = %s, livello_id = %s, token_usati = %s, conclusa_il = NOW() WHERE id = %s",
                     (comp["id"], lid, token, rid))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     (f"Padre Casati ha scritto «{r['competenza_nome']}» livello {r['livello']} ({LIVELLI[r['livello']]}): leggila e approvala nel Ginnasio.",))


# ---------- approvazione e assegnazione ----------
def modifica_bozza(conn, livello_id: int, corpo: str, descrizione: str | None = None):
    c = _bozza(conn, livello_id)
    corpo = str(corpo or "").strip()
    if len(corpo) < 50 or len(corpo) > MAX_CORPO:
        raise ErroreGinnasio(f"Il testo deve avere da 50 a {MAX_CORPO} caratteri")
    if SEGRETO.search(corpo):
        raise ErroreGinnasio("Il testo sembra contenere una chiave o una password")
    conn.execute("UPDATE competenze_livelli SET corpo = %s, descrizione = COALESCE(%s, descrizione) WHERE id = %s", (corpo, _nome(descrizione, 300) if descrizione else None, c["id"]))


def _bozza(conn, livello_id: int) -> dict:
    c = conn.execute("SELECT * FROM competenze_livelli WHERE id = %s", (livello_id,)).fetchone()
    if c is None or c["stato"] != "bozza":
        raise ErroreGinnasio("Bozza non trovata o gia' decisa")
    return c


def decidi_livello(conn, livello_id: int, approva: bool, utente_id: int, nota: str | None = None) -> dict:
    c = _bozza(conn, livello_id)
    rich = conn.execute("SELECT * FROM richieste_formazione WHERE livello_id = %s AND stato = 'da_approvare'", (livello_id,)).fetchall()
    if not approva:
        conn.execute("UPDATE competenze_livelli SET stato = 'ritirata' WHERE id = %s", (livello_id,))
        for r in rich:
            if r["tentativi"] + 1 >= MAX_TENTATIVI:
                conn.execute("UPDATE richieste_formazione SET stato = 'annullata', tentativi = tentativi + 1, note = %s WHERE id = %s", (_nome(nota, 500) or None, r["id"]))
            else:
                conn.execute("UPDATE richieste_formazione SET stato = 'in_coda', tentativi = tentativi + 1, note = %s, ordine_manuale = NULL WHERE id = %s", (_nome(nota, 500) or None, r["id"]))
        return {"stato": "respinta", "rimessa_in_coda": any(r["tentativi"] + 1 < MAX_TENTATIVI for r in rich)}
    conn.execute("UPDATE competenze_livelli SET stato = 'ritirata' WHERE competenza_id = %s AND livello = %s AND stato = 'approvata'", (c["competenza_id"], c["livello"]))
    conn.execute("UPDATE competenze_livelli SET stato = 'approvata', approvata_il = NOW(), verifica_il = CURRENT_DATE + %s, creato_da_utente_id = %s WHERE id = %s",
                 (GIORNI_VERIFICA, utente_id, livello_id))
    assegnati = []
    for r in rich:
        conn.execute("UPDATE richieste_formazione SET stato = 'conclusa' WHERE id = %s", (r["id"],))
        if r["agente_id"]:
            assegna(conn, r["agente_id"], c["competenza_id"], c["livello"])
            assegnati.append(r["agente_id"])
    return {"stato": "approvata", "assegnati": assegnati}


def assegna(conn, agente_id: int, competenza_id: int, livello: int):
    if not conn.execute("SELECT 1 FROM agenti WHERE id = %s", (agente_id,)).fetchone():
        raise ErroreGinnasio("Agente inesistente")
    for lv in range(1, livello + 1):
        if not livello_approvato(conn, competenza_id, lv):
            raise ErroreGinnasio(f"Il livello {lv} ({LIVELLI[lv]}) di questa competenza non e' ancora approvato")
    conn.execute("""INSERT INTO agenti_competenze (agente_id, competenza_id, livello) VALUES (%s,%s,%s)
                    ON CONFLICT (agente_id, competenza_id) DO UPDATE SET livello = EXCLUDED.livello, assegnata_il = NOW()""", (agente_id, competenza_id, livello))


def togli(conn, agente_id: int, competenza_id: int):
    conn.execute("DELETE FROM agenti_competenze WHERE agente_id = %s AND competenza_id = %s", (agente_id, competenza_id))


def annulla(conn, rid: int):
    if not conn.execute("UPDATE richieste_formazione SET stato = 'annullata' WHERE id = %s AND stato IN ('in_coda','errore') RETURNING 1", (rid,)).fetchone():
        raise ErroreGinnasio("Si possono annullare solo richieste in coda o non riuscite")


def riprova(conn, rid: int):
    if not conn.execute("UPDATE richieste_formazione SET stato = 'in_coda', errore = NULL, ordine_manuale = NULL WHERE id = %s AND stato = 'errore' RETURNING 1", (rid,)).fetchone():
        raise ErroreGinnasio("Si possono riprovare solo richieste non riuscite")


# ---------- lato agente ----------
def livello_agente(conn, agente_id: int) -> int:
    r = conn.execute("SELECT round(avg(livello))::int AS m FROM agenti_competenze WHERE agente_id = %s", (agente_id,)).fetchone()
    return r["m"] or 0


def testo_competenza(conn, competenza_id: int, livello: int) -> str:
    """Il testo completo della competenza fino al livello dell'agente (i livelli sono cumulativi)."""
    c = conn.execute("SELECT nome FROM competenze WHERE id = %s", (competenza_id,)).fetchone()
    parti = conn.execute("SELECT livello, corpo FROM competenze_livelli WHERE competenza_id = %s AND livello <= %s AND stato = 'approvata' ORDER BY livello", (competenza_id, livello)).fetchall()
    return f"COMPETENZA «{c['nome']}» fino al livello {livello} ({LIVELLI[livello]})\n\n" + "\n\n".join(f"== Livello {p['livello']} ({LIVELLI[p['livello']]}) ==\n{p['corpo']}" for p in parti)


def competenze_agente(conn, agente_id: int) -> list[dict]:
    return conn.execute("""SELECT c.id, c.nome, c.descrizione, x.livello FROM agenti_competenze x JOIN competenze c ON c.id = x.competenza_id
                           WHERE x.agente_id = %s ORDER BY x.livello DESC, c.nome""", (agente_id,)).fetchall()


def _parole(testo: str) -> set[str]:
    return {w for w in re.findall(r"[a-zàèéìòù]{5,}", (testo or "").lower())}


def contesto(conn, a: dict, messaggio: str) -> str:
    """Elenco delle competenze dell'agente (poche righe) e, se il messaggio le riguarda, il testo della piu' pertinente."""
    mie = competenze_agente(conn, a["id"])
    if not mie:
        return ""
    righe = [f"- {c['nome']} (livello {c['livello']}, {LIVELLI[c['livello']]}): {c['descrizione']}" for c in mie]
    out = "LE TUE COMPETENZE (il livello dice quanto sei formato: lavora con quel metodo):\n" + "\n".join(righe)
    msg = _parole(messaggio)
    migliore, punti = None, 0
    for c in mie:
        n = len(msg & _parole(c["nome"] + " " + c["descrizione"]))
        if n > punti:
            migliore, punti = c, n
    if migliore:
        out += "\n\n" + testo_competenza(conn, migliore["id"], migliore["livello"])[:4500]
    return out


STRUMENTI = [
    {"name": "competenza_leggi",
     "description": "Legge il testo completo di una delle tue competenze (metodo, checklist, formati, errori da evitare) fino al tuo livello.",
     "input_schema": {"type": "object", "properties": {"competenza": {"type": "string"}}, "required": ["competenza"]}},
    {"name": "formazione_richiedi",
     "description": "Chiedi che un agente (o tu) venga formato su una competenza, quando nel lavoro vedi una lacuna concreta. Indica competenza, livello (1 Junior, 2 Medium, 3 Senior, 4 Expert, 5 Master), "
                    "motivo concreto (quale lacuna, in quale progetto) e urgenza 1-3. La richiesta entra in coda e Padre Casati la elabora secondo la graduatoria e il budget giornaliero. "
                    "Non puoi chiedere piu' di tre richieste a settimana.",
     "input_schema": {"type": "object", "properties": {"competenza": {"type": "string"}, "livello": {"type": "integer"}, "agente": {"type": "string", "description": "Nome dell'agente da formare (omesso: solo la libreria)"},
                                                       "motivo": {"type": "string"}, "progetto": {"type": "string"}, "urgenza": {"type": "integer"}}, "required": ["competenza", "livello", "motivo"]}},
]
AVVISO = ("\n\nFORMAZIONE: se nel lavoro vedi che a te o a un agente manca una competenza, chiedila con formazione_richiedi (motivo concreto, progetto, livello): niente richieste generiche. "
          "Le competenze che hai le leggi con competenza_leggi.")


def gestore(connessione_, agente_id: int):
    def f(nome, dati):
        try:
            with connessione_() as conn:
                if nome == "competenza_leggi":
                    n = _nome(dati.get("competenza")).lower()
                    mie = [c for c in competenze_agente(conn, agente_id) if n and (c["nome"].lower() == n or n in c["nome"].lower())]
                    if not mie:
                        return "ERRORE: non hai questa competenza. Le tue: " + (", ".join(c["nome"] for c in competenze_agente(conn, agente_id)) or "nessuna")
                    return testo_competenza(conn, mie[0]["id"], mie[0]["livello"])
                if nome == "formazione_richiedi":
                    target = None
                    if str(dati.get("agente") or "").strip():
                        t = conn.execute("SELECT id FROM agenti WHERE attivo AND lower(nome) = lower(%s)", (str(dati["agente"]).strip(),)).fetchone()
                        if t is None:
                            return "ERRORE: agente non trovato (usa il nome esatto)"
                        target = t["id"]
                    prog = None
                    if str(dati.get("progetto") or "").strip():
                        p = conn.execute("SELECT id FROM progetti WHERE lower(nome) = lower(%s) AND eliminato_il IS NULL", (str(dati["progetto"]).strip(),)).fetchone()
                        prog = p["id"] if p else None
                    origine = "pm" if ruolo_agente(conn, agente_id) == "pm" else "manager"
                    r = richiedi(conn, dati.get("competenza"), dati.get("livello"), agente_id=target, motivo=dati.get("motivo"), progetto_id=prog,
                                 origine=origine, da_agente_id=agente_id, urgenza=dati.get("urgenza") or 2)
                    if r.get("assegnata"):
                        return "La competenza a quel livello esiste gia': l'ho assegnata subito, senza passare dalla coda."
                    return ("Richiesta unita a una gia' in coda (cresce la sua priorita')." if r["unita"] else f"Richiesta #{r['id']} messa in coda: Padre Casati la elaborera' secondo la graduatoria.")
        except ErroreGinnasio as e:
            return "ERRORE: " + str(e)
        return "ERRORE: strumento sconosciuto"
    return f
