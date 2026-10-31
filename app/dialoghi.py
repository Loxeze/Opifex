"""Dialoghi tra agenti: modello economico dedicato, regole di chiarezza, limiti e registro (feed).

Chi puo' parlare con chi: vedi colleghi(). Ogni dialogo ha una fascia di riservatezza decisa da chi lo avvia.
"""
import json
import re

from .db import connessione
from .fornitori import ErroreFornitore, chiama_modello
from . import catalogo_modelli, codici, memoria, misure, richieste
from .riservatezza import anonimizza, puo_uscire

REGOLE_ESTESE = """Stai dialogando con un collega della stessa organizzazione di Lorenzo Zeppa (un altro agente AI).
Regole del dialogo:
1. Prima di rispondere verifica di aver capito. Se mancano informazioni necessarie NON indovinare: fai domande di chiarimento
   precise e spiega perche' ti servono.
2. Quando scrivi, fatti capire senza altri messaggi: dici chi sei, cosa stai facendo, a che punto sei e cosa ti serve esattamente.
3. Quando rispondi, spiega anche il ragionamento e le ipotesi, non solo il risultato. Niente risposte secche o domande generiche.
4. Non inventare dati: se non lo sai, dillo.
5. RISOLVETE TRA VOI: non rimandare a Lorenzo. Se manca un'informazione, chi e' piu' vicino al tema la fornisce o decide; se resta un dubbio
   non sostanziale, scegliete insieme l'ipotesi piu' ragionevole e dichiaratela. Lorenzo si interpella solo per spese, invii all'esterno a suo nome,
   azioni irreversibili, credenziali o scelte di strategia che nessuno di voi puo' prendere.
6. Se la questione e' completamente chiarita scrivi alla fine [CHIARITO], indicando la decisione presa.
Rispondi in italiano, in modo completo ma senza giri di parole."""

REGOLE_BREVI = """Stai dialogando con un collega della stessa organizzazione di Lorenzo Zeppa (un altro agente AI). Comunicazione INTERNA: brevissima.
Ogni messaggio INIZIA con un codice: """ + codici.LEGENDA + """
Regole:
1. Dopo il codice, solo l'essenziale (massimo 80 parole): niente saluti, presentazioni, riepiloghi di cio' che e' gia' stato detto, ringraziamenti. ECCEZIONE: quando assegni un compito (#R) il prompt va scritto completo e dettagliato, anche lungo, come insegna la scrittura dei prompt: contesto, compito, materiali, risultato atteso, vincoli. Se il codice basta, scrivi solo il codice (es. «#E» oppure «#A»).
2. Rimanda per identificativo (task #12, documento #5, progetto «X») invece di ripetere il contenuto. Il ragionamento solo se te lo chiedono.
3. Se manca un'informazione necessaria NON indovinare: «#D» con UNA domanda precisa. Non inventare dati: se non lo sai, dillo.
4. RISOLVETE TRA VOI: non rimandare a Lorenzo. Chi e' piu' vicino al tema fornisce o decide; se il dubbio non e' sostanziale scegliete l'ipotesi piu' ragionevole e dichiaratela («#C decisione»). Lorenzo si interpella solo per spese, invii all'esterno a suo nome, azioni irreversibili, credenziali o scelte di strategia («#B»).
5. Se il collega ti scrive #E, #C, #A o #I non devi rispondere con altro che «#A», e solo se serve.
Italiano."""

REGOLE = REGOLE_BREVI


MAX_TOKEN_DIALOGO = 16000   # nessun tetto pratico: prompt e consegne tra agenti restano interi (la brevita' si chiede nelle regole, non si impone col taglio)


class DialogoBloccato(Exception):
    pass


def impostazione(conn, chiave: str, default: str) -> str:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return r["valore"] if r else default


def scheda(c: dict) -> str:
    """Scheda di competenza di un collega, in una riga: Nome — Dipartimento — Azienda/e — compito (non fa: a chi rimanda)."""
    parti = [c["nome"], c.get("divisione"), c.get("aziende"), c["ruolo"]]
    t = " — ".join(p for p in parti if p)
    return t + (f" (non si occupa di: {c['rimanda_a']})" if c.get("rimanda_a") else "")


def colleghi(conn, agente_id: int) -> list[dict]:
    """Agenti con cui questo agente puo' parlare.

    Tutti: il proprio superiore e i subordinati diretti. Manager e referente: anche tutti i propri sottoposti (a qualunque
    livello) e gli altri manager/referente. Supervisori esterni (agenti di sistema): qualunque agente attivo.
    """
    a = conn.execute("SELECT id, livello, tipo, sentinella, superiore_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    if a is None:
        return []
    return conn.execute(
        """WITH RECURSIVE sotto AS (
               SELECT id FROM agenti WHERE superiore_id = %(id)s
               UNION SELECT x.id FROM agenti x JOIN sotto s ON x.superiore_id = s.id)
           SELECT a.id, a.nome, a.ruolo, a.rimanda_a, a.ruolo_speciale, d.nome AS divisione,
                  (SELECT string_agg(z.nome, ', ' ORDER BY z.nome) FROM agenti_aziende x JOIN aziende z ON z.id = x.azienda_id WHERE x.agente_id = a.id) AS aziende
           FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id
           WHERE a.attivo AND a.id <> %(id)s AND (
                 a.id = %(sup)s
              OR a.superiore_id = %(id)s
              OR a.ruolo_speciale IS NOT NULL
              OR a.id IN (SELECT pa2.agente_id FROM progetti_agenti pa1 JOIN progetti_agenti pa2 ON pa2.progetto_id = pa1.progetto_id
                          WHERE pa1.agente_id = %(id)s AND (SELECT count(*) FROM progetti_agenti x WHERE x.progetto_id = pa1.progetto_id) <= 12)
              OR (%(gest)s AND (a.id IN (SELECT id FROM sotto) OR a.livello IN ('manager', 'referente')))
              OR %(vigila)s)
           ORDER BY a.id""",
        {"id": agente_id, "sup": a["superiore_id"], "gest": a["livello"] in ("manager", "referente"),
         "vigila": bool(a["sentinella"])}).fetchall()


def _modello_dialogo(conn, agente_id: int) -> dict:
    """Modello usato per PARLARE (non per lavorare): quello scelto per l'agente o il predefinito economico."""
    riga = conn.execute(
        """SELECT a.id, a.nome, a.ruolo, a.istruzioni, a.attivo, a.fascia_dati_max, a.accesso_web, a.siti_consentiti, a.max_ricerche,
                  COALESCE(NULLIF(a.modello_dialogo, ''), %(pred)s) AS modello_nome, COALESCE(a.modello_dialogo, '') AS scelta
           FROM agenti a WHERE a.id = %(id)s""",
        {"id": agente_id, "pred": impostazione(conn, "modello_dialogo_predefinito", "claude-haiku-5-5")}).fetchone()
    if riga is None:
        raise DialogoBloccato("Agente inesistente")
    if not riga["scelta"] and catalogo_modelli.automatico(conn):
        auto = catalogo_modelli.scegli_per_dialogo(conn, riga)
        if auto:
            riga["modello_nome"] = auto
    m = conn.execute(
        """SELECT m.id AS modello_id, m.costo_input_per_milione AS c_in, m.costo_output_per_milione AS c_out,
                  f.id AS fornitore_id, f.nome AS fornitore, f.fascia_dati_max AS fascia_fornitore,
                  f.non_conservazione_attiva, f.dpa_firmato
           FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE m.nome = %s""",
        (riga["modello_nome"],)).fetchone()
    if m is None:
        raise DialogoBloccato(f"Modello per i dialoghi '{riga['modello_nome']}' non registrato")
    return {**riga, **m}


def _token_dialoghi_oggi(conn) -> int:
    r = conn.execute(
        """SELECT COALESCE(SUM(COALESCE(token_input,0) + COALESCE(token_output,0)), 0) AS t
           FROM costi_api WHERE tipo = 'dialogo' AND creato_il >= date_trunc('day', NOW())""").fetchone()
    return int(r["t"])


def _storia(conn, conv_id: int) -> str:
    righe = conn.execute(
        """SELECT m.testo, da.nome AS da FROM messaggi_agenti m LEFT JOIN agenti da ON da.id = m.da_agente_id
           WHERE m.conversazione_id = %s ORDER BY m.id DESC LIMIT %s""",
        (conv_id, max(2, min(int(impostazione(conn, "dialoghi_storia_messaggi", "5") or 5), 20)))).fetchall()
    return "\n\n".join(f"{r['da']}: {r['testo']}" for r in reversed(righe))


def _salva_messaggio(conn, conv_id, da_id, a_id, testo, modello=None, t_in=None, t_out=None):
    conn.execute(
        """INSERT INTO messaggi_agenti (conversazione_id, da_agente_id, a_agente_id, testo, modello, token_input, token_output)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""", (conv_id, da_id, a_id, testo, modello, t_in, t_out))
    conn.execute("UPDATE conversazioni SET ultimo_messaggio_il = NOW() WHERE id = %s", (conv_id,))


def _fai_parlare(conn, parlante_id: int, destinatario_id: int, conv_id: int, istruzione: str, fascia: str,
                 utente_id: int | None) -> str:
    """Il parlante scrive il suo messaggio con il proprio modello per i dialoghi. Registra costi e messaggio."""
    p = _modello_dialogo(conn, parlante_id)
    if not p["attivo"]:
        raise DialogoBloccato(f"{p['nome']} e' spento")
    if conn.execute("SELECT 1 FROM sospensioni_agenti WHERE agente_id = %s AND riattivato_il IS NULL", (parlante_id,)).fetchone():
        raise DialogoBloccato(f"{p['nome']} e' sospeso")
    ok, motivo = puo_uscire(fascia, p["fascia_dati_max"], p["fascia_fornitore"], p["non_conservazione_attiva"], p["dpa_firmato"])
    if not ok:
        conn.execute(
            """INSERT INTO registro_uscite (agente_id, fornitore_id, modello_id, fascia_dati, anonimizzato, bloccato, motivo_blocco)
               VALUES (%s,%s,%s,%s,FALSE,TRUE,%s)""", (parlante_id, p["fornitore_id"], p["modello_id"], fascia, "Dialogo: " + motivo))
        conn.commit()
        raise DialogoBloccato(motivo)
    sistema = p["istruzioni"] + "\n\n" + (REGOLE_BREVI if impostazione(conn, "dialoghi_stile_breve", "true") == "true" else REGOLE_ESTESE) + richieste.REGOLA
    if memoria._ok({**p}, "interno"):
        note = richieste.decisioni_note(conn)
        if note:
            sistema += "\n\n" + note
    storia = _storia(conn, conv_id)
    doc_ctx, _u, _e = memoria.contesto_documenti(conn, p, istruzione + "\n" + storia)  # anche nei dialoghi gli agenti vedono i loro documenti
    contenuto = anonimizza((doc_ctx + "\n\n=====\n\n" if doc_ctx else "") + storia + "\n\n=== Tocca a te ===\n" + istruzione)
    try:
        # chi ha l'accesso al web lo ha anche quando risponde a un collega (prima nei dialoghi non cercava e diceva di non avere l'accesso)
        web = ({"siti": p["siti_consentiti"], "max_ricerche": p["max_ricerche"]} if (p["accesso_web"] and p["fornitore"] == "anthropic") else None)
        if web:
            sistema += "\n\nHAI LA RICERCA WEB (strumento web_search" + (": solo sui siti " + ", ".join(web["siti"]) if web["siti"] else "") + "). Usala quando serve e cita le fonti: non dire di non avere l'accesso."
        r = chiama_modello(p["fornitore"], p["modello_nome"], sistema, contenuto, MAX_TOKEN_DIALOGO, web) if web else \
            chiama_modello(p["fornitore"], p["modello_nome"], sistema, contenuto, MAX_TOKEN_DIALOGO)
    except ErroreFornitore as e:
        conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) VALUES (%s,'errore_modello',%s::jsonb,%s)",
                     (parlante_id, json.dumps({"errore": str(e)[:200], "dialogo": True}), utente_id))
        conn.commit()
        raise
    if not (r.testo or "").strip():  # risposta vuota: un secondo tentativo con piu' spazio, poi un messaggio che dice cosa e' successo
        try:
            r2 = chiama_modello(p["fornitore"], p["modello_nome"], sistema, contenuto, MAX_TOKEN_DIALOGO * 2)
            r = type(r)(r2.testo, r.token_input + r2.token_input, r.token_output + r2.token_output, getattr(r2, "diag", {}))
        except ErroreFornitore:
            pass
        if not (r.testo or "").strip():
            conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) VALUES (%s,'risposta_vuota',%s::jsonb,%s)",
                         (parlante_id, json.dumps({"dialogo": True, "modello": p["modello_nome"], **(getattr(r, "diag", None) or {})}), utente_id))
            r = type(r)("(Nessuna risposta dal modello: riprova o controlla l'agente con «Prova agente».)", r.token_input, r.token_output, {})
    costo = round(r.token_input / 1e6 * float(p["c_in"] or 0) + r.token_output / 1e6 * float(p["c_out"] or 0), 4)
    conn.execute("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato, tipo) VALUES (%s,%s,%s,%s,%s,'dialogo')",
                 (parlante_id, p["modello_nome"], r.token_input, r.token_output, costo))
    conn.execute("INSERT INTO registro_uscite (agente_id, fornitore_id, modello_id, fascia_dati, anonimizzato, token_input, bloccato) VALUES (%s,%s,%s,%s,TRUE,%s,FALSE)",
                 (parlante_id, p["fornitore_id"], p["modello_id"], fascia, r.token_input))
    misure.registra(conn, parlante_id, p["modello_nome"], "Domande tra agenti", r.token_input, r.token_output, costo, 1, None, 0, bool(web),
                    len(sistema), 0, len(istruzione), {"storia": len(storia), "documenti": len(doc_ctx or "")})
    _salva_messaggio(conn, conv_id, parlante_id, destinatario_id, r.testo, p["modello_nome"], r.token_input, r.token_output)
    richieste.estrai_e_salva(conn, parlante_id, r.testo)
    return r.testo


def e_aurora(conn, agente_id: int | None) -> bool:
    if agente_id is None:
        return False
    return conn.execute("SELECT 1 FROM agenti WHERE id = %s AND nome = 'Aurora' AND tipo = 'sistema'", (agente_id,)).fetchone() is not None


PRIORITA_AURORA = "PRIORITA' MASSIMA: questo messaggio e' di Aurora, che coordina l'organizzazione. Mettilo davanti a ogni altro lavoro, eseguilo subito e rispondi con l'esito in una riga.\n"


def _controlli_generali(conn, conv_id: int | None, da_id: int | None = None):
    if e_aurora(conn, da_id):
        return   # i messaggi di Aurora non si fermano per budget o numero di messaggi
    if _token_dialoghi_oggi(conn) >= int(impostazione(conn, "dialoghi_budget_token_giornaliero", "30000000")):
        raise DialogoBloccato("Budget giornaliero dei dialoghi esaurito")
    if conv_id is not None:
        n = conn.execute("SELECT count(*) AS n FROM messaggi_agenti WHERE conversazione_id = %s", (conv_id,)).fetchone()["n"]
        if n >= int(impostazione(conn, "dialoghi_max_messaggi", "12")):
            raise DialogoBloccato("Questa conversazione ha raggiunto il numero massimo di messaggi")


def _risposta_speciale(conn, dest: dict, da_id: int, conv_id: int, domanda: str, fascia: str, utente_id) -> str:
    """Padre Casati e il Cerimoniere rispondono con i loro strumenti (biblioteca, mappa): passano dall'esecuzione completa."""
    from .esecuzione import EsecuzioneBloccata, esegui_agente
    chi = conn.execute("SELECT nome, ruolo FROM agenti WHERE id = %s", (da_id,)).fetchone()
    try:
        r = esegui_agente(dest["id"], (PRIORITA_AURORA if e_aurora(conn, da_id) else "") + f"Domanda del collega {chi['nome']} ({chi['ruolo']}):\n{domanda}", fascia, utente_id, max_token=16000)
    except EsecuzioneBloccata as e:
        raise DialogoBloccato(str(e)) from None
    _salva_messaggio(conn, conv_id, dest["id"], da_id, r["risposta"])
    return r["risposta"]


_RE_FILE = re.compile(r"\b(file|cartell|drive|video|grezz|clip|riprese|trascri|timecode|export|durata|fps|risoluzion|google|foglio|documento)", re.IGNORECASE)


def _serve_esecuzione(conn, dest: dict, domanda: str) -> bool:
    """Una domanda su file o cartelle richiede gli strumenti Drive: il collega risponde allora con l'esecuzione completa (chi risponde in
    chiacchiera non ha strumenti e finiva per dire «non vedo la cartella»)."""
    if dest.get("ruolo_speciale"):
        return True
    if not _RE_FILE.search(domanda or ""):
        return False
    from . import accessi_agenti
    a = conn.execute("""SELECT a.id, a.fascia_dati_max, a.drive_attivo, m.nome AS modello_nome, f.nome AS fornitore, f.fascia_dati_max AS fascia_fornitore,
                               f.non_conservazione_attiva, f.dpa_firmato
                        FROM agenti a LEFT JOIN modelli_ai m ON m.nome = a.modello LEFT JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE a.id = %s""",
                     (dest["id"],)).fetchone()
    return bool(a) and accessi_agenti.motivo_senza_drive(conn, a) is None


def domanda_a_collega(da_id: int, nome_dest: str, domanda: str, conv_id: int | None, fascia: str,
                      utente_id: int | None) -> tuple[str, int]:
    """Un agente fa una domanda a un collega durante il suo lavoro. Restituisce (risposta, id conversazione)."""
    with connessione() as conn:
        permessi = {c["nome"].lower(): c for c in colleghi(conn, da_id)}
        dest = permessi.get(nome_dest.strip().lower())
        if dest is None:
            raise DialogoBloccato("Puoi parlare solo con: " + (", ".join(c["nome"] for c in permessi.values()) or "nessuno"))
        _controlli_generali(conn, conv_id, da_id)
        if conv_id is None:
            conv_id = conn.execute(
                "INSERT INTO conversazioni (titolo, fascia_dati, iniziata_da_agente) VALUES (%s,%s,%s) RETURNING id",
                (domanda.strip().splitlines()[0][:90] or "Domanda", fascia, da_id)).fetchone()["id"]
        else:
            if conn.execute("SELECT 1 FROM conversazioni WHERE id = %s", (conv_id,)).fetchone() is None:
                raise DialogoBloccato("Conversazione inesistente")
        _salva_messaggio(conn, conv_id, da_id, dest["id"], domanda)
        conn.commit()
        if codici.chiude(domanda) and not dest.get("ruolo_speciale"):
            # informazione o conferma (#I, #E, #C, #A): nessuna risposta da generare, niente chiamata al modello
            _salva_messaggio(conn, conv_id, dest["id"], da_id, "#A")
            conn.commit()
            return "#A ricevuto", conv_id
        if _serve_esecuzione(conn, dest, domanda):
            return _risposta_speciale(conn, dest, da_id, conv_id, domanda, fascia, utente_id), conv_id
        risposta = _fai_parlare(conn, dest["id"], da_id, conv_id,
                                (PRIORITA_AURORA if e_aurora(conn, da_id) else "") + "Rispondi al messaggio precedente. Se non e' chiaro, chiedi chiarimenti precisi.", fascia, utente_id)
    return risposta, conv_id


def dialogo_avviato_da_utente(da_id: int, a_id: int, argomento: str, messaggi: int, fascia: str, utente_id: int) -> int:
    """Lorenzo fa dialogare due agenti su un argomento. Si ferma al limite di messaggi o con [CHIARITO]."""
    with connessione() as conn:
        if a_id not in {c["id"] for c in colleghi(conn, da_id)}:
            raise DialogoBloccato("Questi due agenti non possono dialogare tra loro (solo superiore, subordinati e manager tra loro)")
        massimo = int(impostazione(conn, "dialoghi_max_messaggi", "12"))
        messaggi = max(2, min(messaggi, massimo))
        conv_id = conn.execute(
            "INSERT INTO conversazioni (titolo, fascia_dati, iniziata_da_utente) VALUES (%s,%s,%s) RETURNING id",
            (argomento.strip().splitlines()[0][:90], fascia, utente_id)).fetchone()["id"]
        conn.commit()
        parlante, altro = da_id, a_id
        try:
            _scambia(conn, conv_id, parlante, altro, argomento, messaggi, fascia, utente_id)
        except (DialogoBloccato, ErroreFornitore):
            if conn.execute("SELECT count(*) AS n FROM messaggi_agenti WHERE conversazione_id = %s", (conv_id,)).fetchone()["n"] == 0:
                conn.execute("DELETE FROM conversazioni WHERE id = %s", (conv_id,))  # nessun messaggio: non lascio conversazioni vuote
                conn.commit()
            raise
        conn.execute("UPDATE conversazioni SET stato = 'chiusa' WHERE id = %s", (conv_id,))
    return conv_id


def _scambia(conn, conv_id, parlante, altro, argomento, messaggi, fascia, utente_id):
    if True:
        for i in range(messaggi):
            _controlli_generali(conn, conv_id)
            istruzione = (f"Argomento proposto da Lorenzo: {argomento}\n"
                          + ("Apri tu il dialogo con il collega: spiega il contesto e cosa ti serve." if i == 0
                             else "Rispondi al collega. Se non e' chiaro chiedi chiarimenti precisi."))
            testo = _fai_parlare(conn, parlante, altro, conv_id, istruzione, fascia, utente_id)
            conn.commit()
            if codici.chiude(testo):
                break
            parlante, altro = altro, parlante
