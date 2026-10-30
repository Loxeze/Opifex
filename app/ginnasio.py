"""Ginnasio: competenze a cinque livelli (junior → master), coda di formazione con graduatoria e formazione svolta da Padre Casati.
Le richieste arrivano da manager, project manager, segnali automatici o da Lorenzo ed entrano da sole in coda; il budget giornaliero di token e la
graduatoria (riordinabile) decidono cosa si forma oggi. Una competenza scritta da Padre Casati e' una bozza: arriva a un agente solo dopo l'approvazione."""
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import casati, eventi
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
STIMA_TOKEN = {1: 60000, 2: 80000, 3: 100000, 4: 125000, 5: 150000}   # ricerca + studio + stesura: si affina con i dati reali
MAX_TOKEN_RICERCA = 2500
MAX_TOKEN_STUDIO = 4500
MAX_TOKEN_ESECUZIONE = {1: 5000, 2: 6000, 3: 7000, 4: 8000, 5: 8000}   # la stesura finale
MAX_TENTATIVI = 2
GIORNI_VERIFICA = 180
MAX_CORPO = 20000


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
    if r.get("minimo"):
        p += 10000   # competenza necessaria ancora al livello zero: passa avanti a tutto
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
    righe.sort(key=lambda r: (not r.get("minimo"), r["ordine_manuale"] is None, r["ordine_manuale"] if r["ordine_manuale"] is not None else 0, -r["punteggio"], r["id"]))
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
    # budget 0 = nessun tetto: la formazione procede senza limite giornaliero di token
    try:
        budget = max(0, int(impostazione(conn, "ginnasio_budget_giornaliero", "0") or 0))
    except ValueError:
        budget = 0
    usati = usati_oggi(conn)
    senza_limite = budget == 0
    return {"senza_limite": senza_limite, "attivo": impostazione(conn, "ginnasio_attivo", "0") == "1", "pausa_studio": impostazione(conn, "ginnasio_pausa_studio", "1") == "1", "budget": budget, "usati_oggi": usati, "residuo": (10**12 if senza_limite else max(0, budget - usati)),
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


def procedi_stesura(conn, rid: int):
    """Dopo la pausa sugli appunti: Lorenzo da' il via alla stesura della competenza."""
    r = conn.execute("SELECT stato FROM richieste_formazione WHERE id = %s FOR UPDATE", (rid,)).fetchone()
    if r is None or r["stato"] != "appunti_pronti":
        raise ErroreGinnasio("La richiesta non e' in attesa di via libera sugli appunti")
    if conn.execute("SELECT 1 FROM richieste_formazione WHERE stato = 'in_corso'").fetchone():
        raise ErroreGinnasio("C'e' gia' una formazione in corso: aspetta che finisca")
    conn.execute("UPDATE richieste_formazione SET stato = 'in_corso' WHERE id = %s", (rid,))
    conn.commit()
    avvia(rid)


def avanzamento(conn, rid: int) -> dict:
    """Tutto cio' che serve per capire a che punto e' una formazione: tappe, ricerche, documenti scaricati, appunti, passaggi."""
    r = conn.execute("""SELECT f.*, a.nome AS agente FROM richieste_formazione f LEFT JOIN agenti a ON a.id = f.agente_id WHERE f.id = %s""", (rid,)).fetchone()
    if r is None:
        raise ErroreGinnasio("Richiesta inesistente")
    ev = conn.execute("SELECT tipo, dettaglio, token, durata_ms, creato_il FROM eventi_lavoro WHERE richiesta_id = %s ORDER BY id", (rid,)).fetchall()
    fasi = []
    for nome in ("ricerca", "studio", "stesura"):
        inizio = [e for e in ev if e["tipo"] == "fase" and e["dettaglio"] == nome]
        fine = [e for e in ev if e["tipo"] == "fase_fine" and e["dettaglio"] == nome]
        stato = "finita" if fine else ("in_corso" if inizio and r["stato"] == "in_corso" else ("saltata" if not inizio and r["appunti"] and nome != "stesura" else "in_attesa"))
        if inizio and not fine and r["stato"] == "errore":
            stato = "interrotta"
        fasi.append({"nome": nome, "stato": stato, "token": fine[-1]["token"] if fine else 0, "durata_ms": fine[-1]["durata_ms"] if fine else None})
    materiali = conn.execute("""SELECT d.id, d.nome, d.autori, d.anno, d.licenza, d.fonte_url, m.byte FROM formazione_materiale m JOIN documenti d ON d.id = m.documento_id
                                 WHERE m.richiesta_id = %s ORDER BY m.scaricato_il""", (rid,)).fetchall()
    passaggi = [e for e in ev if e["tipo"] in ("strumento", "errore_strumento", "errore")]
    bozza = conn.execute("SELECT id, livello, corpo FROM competenze_livelli WHERE id = %s", (r["livello_id"],)).fetchone() if r["livello_id"] else None
    return {"id": r["id"], "competenza": r["competenza_nome"], "livello": r["livello"], "agente": r["agente"], "stato": r["stato"], "fase": r["fase"], "errore": r["errore"], "token_usati": r["token_usati"],
            "fasi": fasi, "materiali": materiali, "appunti": r["appunti"], "passaggi": passaggi[-60:],
            "ricerche": [e["dettaglio"] for e in passaggi if e["dettaglio"].startswith("cerca_fonti")],
            "bozza": bozza["corpo"] if bozza else None}


def avvia(rid: int):
    if SINCRONO:
        _lavora(rid)
    else:
        threading.Thread(target=_lavora, args=(rid,), daemon=True).start()


def _contesto_richiesta(conn, r: dict) -> str:
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
            + f"Cosa deve contenere un livello {LIVELLI[r['livello']]}: {FOCUS[r['livello']]}.\n")


def _precedenti(conn, r: dict) -> str:
    out = []
    if r["competenza_id"]:
        for lv in conn.execute("SELECT livello, corpo FROM competenze_livelli WHERE competenza_id = %s AND livello < %s AND stato = 'approvata' ORDER BY livello", (r["competenza_id"], r["livello"])).fetchall():
            out.append(f"--- Livello {lv['livello']} ({LIVELLI[lv['livello']]}) gia' scritto ---\n{lv['corpo'][:2500]}")
    return ("\n\n" + "\n\n".join(out)) if out else ""


def _prompt_ricerca(conn, r: dict) -> str:
    return (_contesto_richiesta(conn, r) + "\nFASE 1 di 3 — RICERCA DEL MATERIALE. Non scrivere ancora la competenza.\n"
            "1) biblioteca_cerca: guarda cosa c'e' gia'. 2) cerca_fonti con poche ricerche mirate (archivi diversi: openalex, arxiv, wikipedia, semanticscholar), senza dati riservati. "
            f"3) scarica con scarica_materiale i PDF ad accesso aperto davvero utili (quanti ne servono, senza limiti: preferisci manuali, rassegne e linee guida a post e opinioni). "
            "Chiudi con una lista breve: cosa hai scaricato, cosa gia' c'era, cosa non hai trovato.")


def _prompt_studio(conn, r: dict, ricerca: str) -> str:
    return (_contesto_richiesta(conn, r) + "\nFASE 2 di 3 — STUDIO. Esito della ricerca:\n" + ricerca[:2500] + "\n\n"
            "Leggi con biblioteca_cerca e biblioteca_leggi i documenti pertinenti (anche piu' parti dello stesso) e scrivi gli APPUNTI per la stesura: per ogni punto utile "
            "metodo, criteri, errori da evitare, numeri o soglie, con documento e brano di provenienza. Distingui studi rivisti da altri studiosi da opinioni. "
            "Massimo 1200 parole, solo appunti: la competenza si scrive nella fase successiva.")


def _prompt(conn, r: dict, appunti: str = "") -> str:
    return (_contesto_richiesta(conn, r) + "\nFASE 3 di 3 — STESURA. Scrivi ora la competenza per questo livello, senza usare altri strumenti, appoggiandoti agli appunti qui sotto. Non ripetere cio' che dicono i livelli precedenti: aggiungi.\n"
            "Il testo e' istruzione operativa per un agente che dovra' lavorare cosi': metodo a passi, checklist, formato dei risultati, errori da evitare, "
            "domande da fare prima di iniziare, e in fondo una sezione «Fonti» con titolo e indirizzo di ogni fonte usata davvero (se non hai trovato fonti scrivilo, non inventarle). Mai password o chiavi. Italiano, concreto.\n"
            "Chiudi la risposta in questo formato esatto:\nDESCRIZIONE: una riga (max 200 caratteri) che dice a cosa serve la competenza e quando usarla\nCOMPETENZA:\n<il testo>\n"
            + (f"\n=== APPUNTI DI STUDIO ===\n{appunti[:9000]}\n" if appunti else "") + _precedenti(conn, r))


def _parti(testo: str) -> tuple[str, str]:
    m = re.search(r"DESCRIZIONE\s*:\s*(.+?)\s*(?:\n|$)", testo, re.I)
    d = re.sub(r"\s+", " ", m.group(1))[:300] if m else ""
    c = re.search(r"COMPETENZA\s*:\s*(.+)$", testo, re.S | re.I)
    return d, (c.group(1) if c else testo).strip()[:MAX_CORPO]


def _lavora(rid: int):
    from . import casati
    from .esecuzione import esegui_agente
    with connessione() as conn:
        r = conn.execute("SELECT * FROM richieste_formazione WHERE id = %s AND stato = 'in_corso'", (rid,)).fetchone()
        if r is None:
            return
        cas = conn.execute("SELECT id FROM agenti WHERE ruolo_speciale = 'formatore' AND attivo LIMIT 1").fetchone()
        if cas is None:
            conn.execute("UPDATE richieste_formazione SET stato = 'errore', errore = 'Padre Casati non e'' attivo', conclusa_il = NOW() WHERE id = %s", (rid,))
            return
        prompt_ricerca = _prompt_ricerca(conn, r)
        conn.commit()
    token_tot = int(r["token_usati"] or 0)
    ha_appunti = bool((r["appunti"] or "").strip())
    cid = cas["id"]

    def fase(nome, prompt, max_token, scarica=False):
        nonlocal token_tot
        with connessione() as conn:
            conn.execute("UPDATE richieste_formazione SET fase = %s, token_usati = %s WHERE id = %s", (nome, token_tot, rid))
        eventi.registra(cid, "fase", nome, richiesta_id=rid)
        prima, t0 = token_tot, time.monotonic()
        ctx = eventi.CONTESTO.set({"agente": cid, "richiesta": rid})
        tk = casati.FORMAZIONE.set({"richiesta": rid, "n": 0, "byte": 0}) if scarica else casati.FORMAZIONE.set(None)
        try:
            o = esegui_agente(cid, prompt, "interno", None, max_token=max_token)
        finally:
            casati.FORMAZIONE.reset(tk)
            eventi.CONTESTO.reset(ctx)
        token_tot += o["token_input"] + o["token_output"]
        eventi.registra(cid, "fase_fine", nome, richiesta_id=rid, token=token_tot - prima, durata_ms=int((time.monotonic() - t0) * 1000))
        return o["risposta"]

    try:
        if not ha_appunti:
            ricerca = fase("ricerca", prompt_ricerca, MAX_TOKEN_RICERCA, scarica=True)
            with connessione() as conn:
                r = conn.execute("SELECT * FROM richieste_formazione WHERE id = %s", (rid,)).fetchone()
                prompt_studio = _prompt_studio(conn, r, ricerca)
            appunti = fase("studio", prompt_studio, MAX_TOKEN_STUDIO)
            with connessione() as conn:
                conn.execute("UPDATE richieste_formazione SET appunti = %s WHERE id = %s", (appunti[:20000], rid))
                if impostazione(conn, "ginnasio_pausa_studio", "1") == "1":
                    # pausa: Lorenzo legge gli appunti e decide se far scrivere la competenza
                    conn.execute("UPDATE richieste_formazione SET stato = 'appunti_pronti', fase = 'studio', token_usati = %s WHERE id = %s", (token_tot, rid))
                    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                                 (f"Padre Casati ha finito di studiare «{r['competenza_nome']}»: leggi gli appunti nel Ginnasio e decidi se farla scrivere.",))
                    return
        else:
            with connessione() as conn:
                appunti = conn.execute("SELECT appunti FROM richieste_formazione WHERE id = %s", (rid,)).fetchone()["appunti"]
                r = conn.execute("SELECT * FROM richieste_formazione WHERE id = %s", (rid,)).fetchone()
        with connessione() as conn:
            prompt_stesura = _prompt(conn, r, appunti)
        testo_finale = fase("stesura", prompt_stesura, MAX_TOKEN_ESECUZIONE[r["livello"]])
        out = {"risposta": testo_finale, "token_input": token_tot, "token_output": 0}
    except Exception as e:  # noqa: BLE001 - la formazione fallita si vede in pagina e non ferma nulla
        with connessione() as conn:
            conn.execute("UPDATE richieste_formazione SET stato = 'errore', errore = %s, token_usati = %s, conclusa_il = NOW() WHERE id = %s", (str(e)[:300], token_tot, rid))
        eventi.registra(cid, "errore", f"formazione: {str(e)[:200]}", richiesta_id=rid)
        return
    descr, corpo = _parti(out["risposta"])
    token = token_tot
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
        auto = False
        if impostazione(conn, "ginnasio_approva_auto", "1") == "1":
            try:
                with conn.transaction():
                    decidi_livello(conn, lid, True, None)
                auto = True
            except ErroreGinnasio:
                auto = False  # per esempio un livello precedente non ancora approvato: resta da approvare a mano
        if auto:
            conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                         (f"Padre Casati ha scritto «{r['competenza_nome']}» livello {r['livello']} ({LIVELLI[r['livello']]}) e l'ha assegnata: la trovi nel Ginnasio con lo storico.",))
        else:
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
                    "Non c'e' un numero massimo di richieste: chiedi quello che serve davvero, con un motivo concreto.",
     "input_schema": {"type": "object", "properties": {"competenza": {"type": "string"}, "livello": {"type": "integer"}, "agente": {"type": "string", "description": "Nome dell'agente da formare (omesso: solo la libreria)"},
                                                       "motivo": {"type": "string"}, "progetto": {"type": "string"}, "urgenza": {"type": "integer"}}, "required": ["competenza", "livello", "motivo"]}},
]
STRUMENTO_REGISTRO = {"name": "registro_competenze",
                      "description": "Il registro di tutte le competenze: per ogni agente (o solo per quello indicato, o per i sottoposti di un manager) competenze con livello 1-5 e stato delle formazioni (concluse, in corso, in coda). "
                                     "E' lo stesso archivio del Ginnasio: non esiste un altro registro e non serve cercarne l'ID.",
                      "input_schema": {"type": "object", "properties": {"agente": {"type": "string", "description": "Nome di un agente o di un manager (di lui si mostrano i sottoposti); omesso: tutti"}}}}


STRUMENTI.append(STRUMENTO_REGISTRO)


def registro_testo(conn, filtro: str | None = None) -> str:
    righe = conn.execute("SELECT id, nome, ruolo, livello, superiore_id FROM agenti WHERE attivo AND NOT sentinella AND ruolo_speciale IS NULL ORDER BY nome").fetchall()
    f = (filtro or "").strip().lower()
    if f:
        sel = [a for a in righe if a["nome"].lower() == f]
        if sel:
            sott = [a for a in righe if a["superiore_id"] == sel[0]["id"]]
            righe = sott or sel
        else:
            righe = [a for a in righe if f in a["nome"].lower()]
        if not righe:
            return "ERRORE: nessun agente corrisponde (usa il nome esatto)"
    out = [f"Registro competenze ({len(righe)} agenti). Archivio del Ginnasio, livelli 1 Junior - 5 Master:"]
    for a in righe:
        comp = competenze_agente(conn, a["id"])
        fo = conn.execute("""SELECT count(*) FILTER (WHERE stato = 'conclusa') AS c, count(*) FILTER (WHERE stato IN ('in_corso','da_approvare')) AS i, count(*) FILTER (WHERE stato = 'in_coda') AS q
                             FROM richieste_formazione WHERE agente_id = %s""", (a["id"],)).fetchone()
        cs = ", ".join(f"{c['nome']} L{c['livello']}" for c in comp) or "nessuna"
        out.append(f"- {a['nome']} ({a['ruolo'] or a['livello']}): {cs} | formazioni: {fo['c']} concluse, {fo['i']} in corso, {fo['q']} in coda")
    return "\n".join(out)


AVVISO = ("\n\nFORMAZIONE: se nel lavoro vedi che a te o a un agente manca una competenza, chiedila con formazione_richiedi (motivo concreto, progetto, livello): niente richieste generiche. "
          "Le competenze che hai le leggi con competenza_leggi; il quadro di tutti (livelli e formazioni) lo leggi con registro_competenze: e' il registro, non esiste altro.")


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
                if nome == "registro_competenze":
                    return registro_testo(conn, dati.get("agente"))
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
