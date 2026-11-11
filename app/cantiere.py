"""Cantiere: un compito complesso affidato a un agente sul modello locale viene diretto da un modello forte.
1. CAPOCANTIERE (modello online): legge la richiesta e la divide in schede di lavoro piccole e autosufficienti.
2. OPERAI (modello locale): l'agente esegue una scheda alla volta, con i suoi strumenti e la memoria pertinente a quella scheda.
3. COLLAUDATORE (modello online): controlla ogni scheda sui criteri; quelle respinte si rifanno una volta con la correzione; poi assembla la risposta.
Il modello forte spende pochi token (piano e controllo); il grosso del lavoro gira sul portatile. Tutto e' registrato nella tabella cantieri."""
import json
import re
import sys
import time
from contextvars import ContextVar

from . import fornitori, progresso
from .db import connessione
from .fornitori import ErroreFornitore, chiama_modello
from .riservatezza import anonimizza, puo_uscire

IN_CORSO: ContextVar[bool] = ContextVar("cantiere_in_corso", default=False)
# solo dove qualcuno affida un lavoro all'agente; mai nei dialoghi tra colleghi, nella formazione o nei giri di servizio
ORIGINI = {"chat_coda", "rotte_agenti", "telegram", "iniziative", "trigger", "consegne", "percorsi", "attese", "ripresa"}
MAX_SCHEDE = 5
PAROLE = ("analizz", "prepar", "redig", "relazion", "piano", "pianific", "progett", "propost", "report", "candidatur", "strategi", "budget", "business plan",
          "confront", "valut", "elabor", "svilupp", "sintetizz", "organizz", "bando", "ricerca", "verific", "passo per passo", "dettagliat", "approfondi")

CAPOCANTIERE = """Sei il capocantiere di Opifex. Un agente AI che lavora su un modello locale piccolo deve svolgere il compito qui sotto: da solo, tutto insieme, si perderebbe.
Dividilo in schede di lavoro, al massimo {max}, che lui eseguira' UNA ALLA VOLTA con i suoi strumenti (documenti, memoria, CRM, colleghi).
Ogni scheda deve essere piccola e autosufficiente: chi la legge non vede le altre schede ne' questa conversazione.
Rispondi SOLO con un oggetto JSON, senza altro testo:
{{"semplice": false, "schede": [{{"id": 1, "titolo": "…", "compito": "ordine di lavoro completo: contesto necessario, che cosa fare esattamente, risultato atteso e formato, che cosa NON fare", "dipende_da": [], "criteri": ["criterio verificabile", "…"]}}]}}
Regole: le schede seguono l'ordine di esecuzione; «dipende_da» elenca gli id delle schede il cui risultato serve; i criteri devono essere controllabili leggendo il risultato;
non inventare dati o nomi che non sono nella richiesta; l'ultima scheda NON deve assemblare il testo finale (lo fa il collaudatore).
Se il compito si svolge bene in un solo passaggio (domanda semplice, saluto, risposta breve) rispondi {{"semplice": true, "schede": []}}."""

COLLAUDATORE = """Sei il collaudatore di Opifex. Un agente su modello locale ha svolto le schede di lavoro qui sotto. Controlla ogni risultato rispetto al compito e ai criteri della sua scheda.
Respingi una scheda se: non svolge il compito, manca un criterio, contiene affermazioni che sembrano inventate o non sostenute, si contraddice, e' scritta in parte in un'altra lingua, o e' un rifiuto/una risposta vuota.
Riga 1 della risposta: SOLO un oggetto JSON {{"schede": [{{"id": 1, "ok": true, "problemi": "", "correzione": ""}}]}} (per le respinte, «correzione» = istruzioni precise per rifarla).
{finale}"""
FINALE_SI = """Se TUTTE le schede sono accettate, dopo il JSON scrivi una riga con solo === RISPOSTA === e poi la risposta finale per chi ha fatto la richiesta: completa, ordinata, in italiano,
costruita SOLO con i risultati accettati (non aggiungere fatti nuovi). Se qualcosa resta incerto mettilo in fondo sotto il titolo «Da verificare». Se anche una sola scheda e' respinta, scrivi solo il JSON."""
ASSEMBLA = """Sei il collaudatore di Opifex. Scrivi la risposta finale per chi ha fatto la richiesta, in italiano, completa e ordinata, costruita SOLO con i risultati delle schede qui sotto (non aggiungere fatti nuovi).
Alcune schede hanno problemi segnalati: non nasconderli. Usa cio' che e' affidabile e metti in fondo, sotto il titolo «Da verificare», i punti che il controllo non ha potuto confermare, detti con chiarezza."""


def _imp(conn, chiave: str, pred: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return (r["valore"] if r and r["valore"] is not None else pred)


def _origine() -> str:
    try:
        f = sys._getframe(2)
        while f is not None:
            nome = f.f_globals.get("__name__", "").rsplit(".", 1)[-1]
            if nome not in ("esecuzione", "cantiere", "misure", "db", "threading", "concurrent", "futures", "thread", "anyio", "starlette", "fastapi"):
                return nome
            f = f.f_back
    except Exception:  # noqa: BLE001
        pass
    return "altro"


def sembra_complesso(messaggio: str) -> bool:
    t = " ".join((messaggio or "").lower().split())
    return len(t) >= 400 or (len(t) >= 90 and any(p in t for p in PAROLE))


def da_usare(agente_id: int, messaggio: str, fascia_dati: str, veloce: bool) -> dict | None:
    """Decide se questo lavoro passa dal cantiere. Restituisce il contesto (agente, modello online, origine) oppure None."""
    if IN_CORSO.get() or veloce:
        return None
    origine = _origine()
    with connessione() as conn:
        modo = _imp(conn, "cantiere_modo", "auto")   # auto | sempre | spento
        if modo == "spento" or (modo != "sempre" and (origine not in ORIGINI or not sembra_complesso(messaggio))):
            return None
        a = conn.execute("""SELECT a.id, a.nome, a.ruolo, a.fascia_dati_max, a.attivo, a.max_token_risposta, f.nome AS fornitore
                            FROM agenti a JOIN modelli_ai m ON m.nome = a.modello JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE a.id = %s""", (agente_id,)).fetchone()
        if a is None or not a["attivo"] or a["fornitore"] != "locale":
            return None
        from .delega_online import _modello
        m = _modello(conn)
        if m is None or not fornitori.chiave("anthropic"):
            return None
        # al collaudo arrivano i risultati dell'agente, che possono contenere tutto cio' che l'agente puo' leggere: devono poter uscire sia la richiesta sia il suo livello massimo
        if not puo_uscire(fascia_dati, a["fascia_dati_max"], m["ff"], m["nc"], m["dpa"])[0] or not puo_uscire(a["fascia_dati_max"], a["fascia_dati_max"], m["ff"], m["nc"], m["dpa"])[0]:
            return None
    return {"a": dict(a), "m": dict(m), "origine": origine}


def _json(testo: str):
    t = re.sub(r"<think>.*?</think>", "", testo or "", flags=re.S).strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    i = t.find("{")
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(t[i:])[0]
    except ValueError:
        return None


class _Conti:
    def __init__(self, agente_id, m):
        self.agente_id, self.m, self.tin, self.tout, self.costo = agente_id, m, 0, 0, 0.0

    def online(self, sistema: str, testo: str, max_token: int) -> str:
        r = chiama_modello("anthropic", self.m["nome"], sistema, anonimizza(testo), max_token)
        costo = (r.token_input * float(self.m["ci"] or 0) + r.token_output * float(self.m["co"] or 0)) / 1_000_000
        self.tin += r.token_input; self.tout += r.token_output; self.costo += costo
        with connessione() as conn:
            conn.execute("""INSERT INTO registro_uscite (agente_id, fornitore_id, modello_id, fascia_dati, anonimizzato, token_input, bloccato)
                            VALUES (%s,%s,%s,'interno',TRUE,%s,FALSE)""", (self.agente_id, self.m["fornitore_id"], self.m["modello_id"], r.token_input))
            conn.execute("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,%s,%s,%s,%s)",
                         (self.agente_id, self.m["nome"], r.token_input, r.token_output, costo))
        return r.testo or ""


def _piano(conti: _Conti, a: dict, messaggio: str) -> list | None:
    grezzo = conti.online(CAPOCANTIERE.format(max=MAX_SCHEDE), f"Agente: {a['nome']} ({a['ruolo'] or 'agente'}).\n\nCOMPITO:\n{messaggio[:12000]}", 2500)
    d = _json(grezzo)
    if not isinstance(d, dict) or d.get("semplice") or not isinstance(d.get("schede"), list):
        return None
    schede = []
    for i, s in enumerate(d["schede"][:MAX_SCHEDE], 1):
        if not isinstance(s, dict) or not str(s.get("compito") or "").strip():
            continue
        dip = [int(x) for x in (s.get("dipende_da") or []) if str(x).isdigit() and int(x) < i]
        schede.append({"id": i, "titolo": str(s.get("titolo") or f"Scheda {i}")[:120], "compito": str(s["compito"])[:4000],
                       "dipende_da": dip, "criteri": [str(c)[:300] for c in (s.get("criteri") or [])][:6]})
    return schede if len(schede) >= 2 else None   # una scheda sola = lavoro semplice: lo fa l'agente come sempre


def _ordine(scheda: dict, n: int, richiesta: str, esiti: dict, correzione: str = "") -> str:
    parti = [f"SCHEDA DI LAVORO {scheda['id']} di {n}: {scheda['titolo']}",
             "Fai parte di un lavoro piu' grande, diviso in schede. Obiettivo generale (solo per contesto: NON svolgerlo tutto, svolgi solo la tua scheda):\n" + richiesta[:1500],
             "IL TUO COMPITO IN QUESTA SCHEDA:\n" + scheda["compito"]]
    if scheda["criteri"]:
        parti.append("Il risultato verra' controllato su questi criteri:\n" + "\n".join("- " + c for c in scheda["criteri"]))
    for k in scheda["dipende_da"]:
        if k in esiti:
            parti.append(f"RISULTATO DELLA SCHEDA {k} (gia' svolta: usalo come materiale):\n{esiti[k]['testo'][:6000]}")
    if correzione:
        parti.append("IL COLLAUDATORE HA RESPINTO IL TUO PRIMO RISULTATO. Correzione richiesta:\n" + correzione
                     + "\n\nIl tuo primo risultato era:\n" + esiti[scheda["id"]]["testo"][:4000] + "\n\nRifallo per intero, corretto.")
    parti.append("Consegna SOLO il risultato di questa scheda, completo e in italiano. Se un dato ti manca dillo chiaramente: non inventarlo.")
    return "\n\n".join(parti)


def _scarto_evidente(testo: str) -> str:
    t = (testo or "").strip()
    if len(t) < 40:
        return "risultato vuoto o troppo corto"
    if t.startswith("(L'agente non ha scritto"):
        return "l'agente non ha scritto nessuna risposta"
    return ""


def esegui(ctx: dict, agente_id: int, messaggio: str, fascia_dati: str, utente_id, memorizza: bool, max_token, allegati) -> dict | None:
    """Svolge il lavoro a schede. Restituisce il risultato nello stesso formato di esegui_agente, oppure None se il capocantiere giudica il compito semplice
    (in quel caso l'agente lo svolge come sempre)."""
    from . import esecuzione, memoria
    a, t0 = ctx["a"], time.monotonic()
    conti = _Conti(agente_id, ctx["m"])
    progresso.fase("il capocantiere prepara il piano")
    try:
        schede = _piano(conti, a, messaggio)
    except ErroreFornitore:
        return None   # il modello online non risponde: il lavoro non si ferma, l'agente procede da solo
    if not schede:
        return None
    with connessione() as conn:
        cid = conn.execute("INSERT INTO cantieri (agente_id, utente_id, origine, richiesta, piano) VALUES (%s,%s,%s,%s,%s::jsonb) RETURNING id",
                           (agente_id, utente_id, ctx["origine"], messaggio[:20000], json.dumps(schede))).fetchone()["id"]
    esiti: dict[int, dict] = {}
    file_creati, usati, esclusi, n_rich, tok_loc = [], [], [], 0, 0
    n = len(schede)

    def svolgi(s: dict, correzione: str = ""):
        nonlocal n_rich, tok_loc
        progresso.fase(f"scheda {s['id']} di {n}: {s['titolo']}" + (" (rifatta)" if correzione else ""))
        r = esecuzione.esegui_agente(agente_id, _ordine(s, n, messaggio, esiti, correzione), fascia_dati, utente_id, memorizza=False,
                                     max_token=max_token, allegati=allegati if s["id"] == 1 or not s["dipende_da"] else None)
        esiti[s["id"]] = {"testo": r["risposta"], "ok": None, "problemi": "", "rifatta": bool(correzione)}
        file_creati.extend(r.get("file_creati") or []); usati.extend(r.get("documenti_usati") or []); esclusi.extend(r.get("documenti_esclusi_per_riservatezza") or [])
        n_rich += int(r.get("richieste_create") or 0); tok_loc += int(r.get("token_input") or 0) + int(r.get("token_output") or 0)

    tk = IN_CORSO.set(True)
    stato, finale, rifatte, da_verificare = "riuscito", "", 0, ""
    try:
        for s in schede:
            svolgi(s)
            if _scarto_evidente(esiti[s["id"]]["testo"]):       # un secondo tentativo subito, senza spendere il collaudo
                svolgi(s, "Il primo risultato era " + _scarto_evidente(esiti[s["id"]]["testo"]) + ": svolgi il compito per intero.")
                rifatte += 1

        def materiale() -> str:
            return "RICHIESTA ORIGINALE:\n" + messaggio[:6000] + "\n\n" + "\n\n".join(
                f"=== SCHEDA {s['id']}: {s['titolo']} ===\nCompito: {s['compito']}\nCriteri: " + ("; ".join(s["criteri"]) or "(nessuno)")
                + f"\n--- Risultato ---\n{esiti[s['id']]['testo'][:9000]}" for s in schede)

        progresso.fase("il collaudatore controlla il lavoro")
        mt_fin = min(max(int(max_token or a["max_token_risposta"] or 2500), 1500), 8000)
        grezzo = conti.online(COLLAUDATORE.format(finale=FINALE_SI), materiale(), mt_fin + 800)
        testa, _, coda = grezzo.partition("=== RISPOSTA ===")
        verdetto = _json(testa) or {}
        respinte = {}
        for v in (verdetto.get("schede") or []):
            if isinstance(v, dict) and str(v.get("id")).isdigit() and int(v["id"]) in esiti:
                e = esiti[int(v["id"])]
                e["ok"] = bool(v.get("ok")); e["problemi"] = str(v.get("problemi") or "")[:600]
                if not e["ok"]:
                    respinte[int(v["id"])] = str(v.get("correzione") or v.get("problemi") or "Rifai la scheda rispettando tutti i criteri.")[:1500]
        if not verdetto.get("schede"):
            respinte = {}   # verdetto illeggibile: si assembla dichiarando che il controllo non e' riuscito
            da_verificare = "Il collaudo automatico non ha dato un esito leggibile: l'intero lavoro va riletto."
        if not respinte and coda.strip() and not da_verificare:
            finale = coda.strip()
        else:
            for s in schede:
                if s["id"] in respinte and not esiti[s["id"]]["rifatta"]:
                    svolgi(s, respinte[s["id"]]); rifatte += 1
                    esiti[s["id"]]["ok"] = None
                    esiti[s["id"]]["problemi"] = "rifatta dopo il collaudo; primo controllo: " + respinte[s["id"]][:300]
            ancora = [k for k in respinte if _scarto_evidente(esiti[k]["testo"])]
            progresso.fase("il collaudatore assembla la risposta")
            note = ("\n\nPROBLEMI SEGNALATI DAL PRIMO CONTROLLO (le schede indicate sono state rifatte una volta; ricontrollale mentre assembli):\n"
                    + "\n".join(f"- scheda {k}: {v}" for k, v in respinte.items())) if respinte else ""
            if da_verificare:
                note += "\n\n" + da_verificare
            finale = conti.online(ASSEMBLA, materiale() + note, mt_fin).strip()
            if ancora or da_verificare:
                stato = "con_riserve"
        if "da verificare" in finale.lower():
            stato = "con_riserve"
            da_verificare = (da_verificare + " " if da_verificare else "") + finale[finale.lower().rfind("da verificare"):][:1500]
        if not finale:
            raise ErroreFornitore("Il collaudatore non ha scritto la risposta finale")
    except Exception as e:  # noqa: BLE001 - si registra l'esito del cantiere e si rilancia
        with connessione() as conn:
            conn.execute("UPDATE cantieri SET stato = 'fallito', esiti = %s::jsonb, da_verificare = %s, token_online = %s, token_locali = %s, costo_online = %s, secondi = %s WHERE id = %s",
                         (json.dumps(esiti), f"{type(e).__name__}: {str(e)[:300]}", conti.tin + conti.tout, tok_loc, conti.costo, round(time.monotonic() - t0, 1), cid))
        raise
    finally:
        IN_CORSO.reset(tk)

    piede = f"\n\n—\nLavoro a schede n. {cid}: {n} schede svolte sul modello locale" + (f", {rifatte} rifatte" if rifatte else "") + f", collaudate da {ctx['m']['nome']}" \
            + (". Esito: con riserve, vedi «Da verificare»." if stato == "con_riserve" else ". Esito: collaudo superato.")
    with connessione() as conn:
        conn.execute("""UPDATE cantieri SET stato = %s, esiti = %s::jsonb, rifatte = %s, da_verificare = %s, token_online = %s, token_locali = %s, costo_online = %s, secondi = %s WHERE id = %s""",
                     (stato, json.dumps(esiti), rifatte, da_verificare or None, conti.tin + conti.tout, tok_loc, conti.costo, round(time.monotonic() - t0, 1), cid))
        conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) VALUES (%s, 'cantiere', %s::jsonb, %s)",
                     (agente_id, json.dumps({"cantiere": cid, "schede": n, "rifatte": rifatte, "stato": stato}), utente_id))
        if memorizza:
            memoria.registra_scambio(conn, agente_id, utente_id, messaggio, finale + piede, fascia_dati, file_creati or None)
    return {"agente": a["nome"], "risposta": finale + piede, "file_creati": file_creati, "richieste_create": n_rich,
            "token_input": conti.tin + tok_loc, "token_output": conti.tout, "documenti_usati": usati, "documenti_esclusi_per_riservatezza": esclusi,
            "avvisi": [], "cantiere": cid, "cantiere_stato": stato}
