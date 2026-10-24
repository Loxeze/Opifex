"""Esecuzione reale di un agente: prepara il contesto, controlla la riservatezza,
chiama il modello, registra costi, uscite e azioni.

Principio: l'agente produce testo (risposte, bozze, proposte). Non esegue azioni esterne da solo:
cio' che richiede approvazione finisce nella coda di Lorenzo.
"""
import json

from .db import connessione
from .fornitori import ErroreFornitore, chiama_modello
from . import agente_browser, cassaforte, dialoghi, richieste
from .documenti import pezzi_pertinenti
from .navigatore import ErroreNavigazione, Navigatore
from .riservatezza import anonimizza, puo_uscire


class EsecuzioneBloccata(Exception):
    pass


def _carica_agente(conn, agente_id: int) -> dict:
    riga = conn.execute(
        """
        SELECT a.id, a.nome, a.ruolo, a.istruzioni, a.tipo, a.fascia_dati_max, a.attivo,
               a.modello AS modello_richiesto,
               a.max_token_risposta, a.budget_token_mensile, a.dialoghi_attivi, a.livello, a.accesso_web, a.siti_consentiti, a.max_ricerche,
               m.id AS modello_id, m.nome AS modello_nome,
               m.costo_input_per_milione, m.costo_output_per_milione,
               f.id AS fornitore_id, f.nome AS fornitore, f.fascia_dati_max AS fascia_fornitore,
               f.non_conservazione_attiva, f.dpa_firmato
        FROM agenti a
        LEFT JOIN modelli_ai m ON m.nome = a.modello
        LEFT JOIN fornitori_ai f ON f.id = m.fornitore_id
        WHERE a.id = %s
        """,
        (agente_id,),
    ).fetchone()
    if riga is None:
        raise EsecuzioneBloccata("Agente inesistente")
    return riga


def _sospeso(conn, agente_id: int) -> bool:
    riga = conn.execute(
        "SELECT 1 FROM sospensioni_agenti WHERE agente_id = %s AND riattivato_il IS NULL",
        (agente_id,),
    ).fetchone()
    return riga is not None


def _token_del_mese(conn, agente_id: int) -> int:
    riga = conn.execute(
        """SELECT COALESCE(SUM(COALESCE(token_input, 0) + COALESCE(token_output, 0)), 0) AS t
           FROM costi_api WHERE agente_id = %s AND creato_il >= date_trunc('month', NOW())""",
        (agente_id,),
    ).fetchone()
    return int(riga["t"])


def _costo(a: dict, t_in: int, t_out: int) -> float:
    c_in = float(a["costo_input_per_milione"] or 0)
    c_out = float(a["costo_output_per_milione"] or 0)
    return round(t_in / 1_000_000 * c_in + t_out / 1_000_000 * c_out, 4)


def esegui_agente(agente_id: int, messaggio: str, fascia_dati: str = "interno",
                  utente_id: int | None = None) -> dict:
    with connessione() as conn:
        a = _carica_agente(conn, agente_id)

        a["istruzioni"] = a["istruzioni"] + richieste.REGOLA
        if not a["attivo"]:
            raise EsecuzioneBloccata("Agente spento")
        if _sospeso(conn, agente_id):
            raise EsecuzioneBloccata("Agente sospeso dal Guardiano della sicurezza")
        if a["budget_token_mensile"] is not None and _token_del_mese(conn, agente_id) >= a["budget_token_mensile"]:
            raise EsecuzioneBloccata("Budget mensile di token esaurito per questo agente")
        if a["fornitore"] is None:
            raise EsecuzioneBloccata(
                f"Modello '{a['modello_richiesto']}' non registrato tra i modelli AI")

        consentito, motivo = puo_uscire(
            fascia_dati, a["fascia_dati_max"], a["fascia_fornitore"],
            a["non_conservazione_attiva"], a["dpa_firmato"],
        )
        if not consentito:
            # Il blocco viene registrato: il Guardiano e l'Auditor lo vedono
            conn.execute(
                """INSERT INTO registro_uscite
                   (agente_id, fornitore_id, modello_id, fascia_dati, anonimizzato, bloccato, motivo_blocco)
                   VALUES (%s, %s, %s, %s, FALSE, TRUE, %s)""",
                (agente_id, a["fornitore_id"], a["modello_id"], fascia_dati, motivo),
            )
            # Il blocco deve restare registrato anche se sollevo l'eccezione: confermo prima
            conn.commit()
            raise EsecuzioneBloccata(motivo)

        # Siti collegati con accesso: il contenuto letto ha la fascia scelta per il sito e deve poter uscire verso il fornitore
        siti = conn.execute(
            """SELECT c.nome, s.dominio, s.url_login, s.utente_cifrato, s.password_cifrata, s.fascia_contenuto, s.max_pagine
               FROM agenti_connessioni ac JOIN connessioni c ON c.id = ac.connessione_id AND c.stato = 'attiva'
               JOIN accessi_siti s ON s.connessione_id = c.id WHERE ac.agente_id = %s""", (agente_id,)).fetchall()
        if siti:
            if a["fornitore"] != "anthropic":
                raise EsecuzioneBloccata("La navigazione dei siti e' disponibile solo con modelli Claude")
            for s_ in siti:
                ok_, motivo_ = puo_uscire(s_["fascia_contenuto"], a["fascia_dati_max"], a["fascia_fornitore"],
                                          a["non_conservazione_attiva"], a["dpa_firmato"])
                if not ok_:
                    conn.execute(
                        """INSERT INTO registro_uscite (agente_id, fornitore_id, modello_id, fascia_dati, anonimizzato, bloccato, motivo_blocco)
                           VALUES (%s, %s, %s, %s, FALSE, TRUE, %s)""",
                        (agente_id, a["fornitore_id"], a["modello_id"], s_["fascia_contenuto"],
                         "Contenuto del sito " + s_["nome"] + ": " + motivo_))
                    conn.commit()
                    raise EsecuzioneBloccata("Sito «" + s_["nome"] + "» (dati " + s_["fascia_contenuto"] + "): " + motivo_)

        # Memoria: pezzi di documenti pertinenti. Un pezzo entra solo se la sua fascia puo' uscire verso il fornitore
        usati, esclusi, riferimenti = [], [], []
        for pz in pezzi_pertinenti(conn, agente_id, messaggio):
            ok, _ = puo_uscire(pz["fascia_dati"], a["fascia_dati_max"], a["fascia_fornitore"],
                               a["non_conservazione_attiva"], a["dpa_firmato"])
            if ok:
                riferimenti.append(f"[{pz['nome']}]\n{pz['testo']}")
                if pz["nome"] not in usati:
                    usati.append(pz["nome"])
            elif pz["nome"] not in esclusi:
                esclusi.append(pz["nome"])
        if riferimenti:
            messaggio = ("Documenti di riferimento (usali solo se pertinenti e cita il documento):\n\n"
                         + "\n\n---\n\n".join(riferimenti) + "\n\n=== Richiesta ===\n" + messaggio)
        risposte_l = richieste.risposte_da_consegnare(conn, agente_id)
        if risposte_l:
            messaggio = risposte_l + messaggio
        testo_uscente = anonimizza(messaggio)
        try:
            web = {"siti": a["siti_consentiti"], "max_ricerche": a["max_ricerche"]} if a["accesso_web"] else None
            colleghi_ok = dialoghi.colleghi(conn, agente_id) if (a["dialoghi_attivi"] and a["fornitore"] == "anthropic") else []
            if siti or colleghi_ok:
                conn.commit()  # libera la connessione durante la navigazione/dialoghi (puo' durare minuti)
                extra, gestore, avviso_extra = None, None, ""
                if colleghi_ok:
                    stato_dialogo = {"domande": 0, "conv": {}}
                    max_domande = int(dialoghi.impostazione(conn, "dialoghi_max_domande", "3"))
                    elenco_c = "; ".join(f"{c['nome']} ({c['ruolo']})" for c in colleghi_ok)
                    extra = [{"name": "chiedi_a_agente",
                              "description": "Fai una domanda a un collega e ricevi la sua risposta. Colleghi disponibili: " + elenco_c,
                              "input_schema": {"type": "object", "properties": {"destinatario": {"type": "string"},
                                               "domanda": {"type": "string"}}, "required": ["destinatario", "domanda"]}}]
                    avviso_extra = ("\n\nCOLLEGHI: se non hai chiaro cosa ti viene chiesto o ti servono informazioni di altri, usa chiedi_a_agente "
                                    "invece di indovinare. Nella domanda spiega chi sei, cosa stai facendo, a che punto sei e cosa ti serve esattamente. "
                                    f"Puoi fare al massimo {max_domande} domande per compito.")

                    def gestore(nome, dati):
                        if stato_dialogo["domande"] >= max_domande:
                            return f"ERRORE: limite di {max_domande} domande per compito raggiunto"
                        stato_dialogo["domande"] += 1
                        dest = str(dati.get("destinatario", ""))
                        try:
                            risp, cid = dialoghi.domanda_a_collega(agente_id, dest, str(dati.get("domanda", "")),
                                                                   stato_dialogo["conv"].get(dest.lower()), fascia_dati, utente_id)
                            stato_dialogo["conv"][dest.lower()] = cid
                            return f"Risposta di {dest}:\n{risp}"
                        except (dialoghi.DialogoBloccato, ErroreFornitore) as e:
                            return "ERRORE: " + str(e)
                nav_cm = None
                if siti:
                    elenco = [{"dominio": s_["dominio"], "url_login": s_["url_login"], "max_pagine": s_["max_pagine"],
                               "utente": cassaforte.decifra(s_["utente_cifrato"]),
                               "password": cassaforte.decifra(s_["password_cifrata"])} for s_ in siti]
                    nav_cm = Navigatore(elenco)
                    nav = nav_cm.__enter__()
                else:
                    nav = None
                try:
                    ris = agente_browser.esegui_con_strumenti(a["modello_nome"], a["istruzioni"], testo_uscente,
                                                              a["max_token_risposta"], nav, extra, gestore, avviso_extra)
                    visitati = list(nav.urls_visitati) if nav else []
                finally:
                    if nav_cm is not None:
                        nav_cm.__exit__(None, None, None)
                if siti:
                    conn.execute(
                        "INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) VALUES (%s, 'navigazione_siti', %s::jsonb, %s)",
                        (agente_id, json.dumps({"pagine": visitati[:40]}), utente_id))
            else:
                ris = chiama_modello(a["fornitore"], a["modello_nome"], a["istruzioni"], testo_uscente,
                                     a["max_token_risposta"], web)
        except (ErroreFornitore, cassaforte.CassaforteNonConfigurata, ErroreNavigazione) as e:
            conn.execute(
                "INSERT INTO registro_azioni (agente_id, azione, dettagli, utente_id) "
                "VALUES (%s, 'errore_modello', %s::jsonb, %s)",
                (agente_id, json.dumps({"errore": str(e)[:200]}), utente_id),
            )
            conn.commit()
            raise

        conn.execute(
            """INSERT INTO registro_uscite
               (agente_id, fornitore_id, modello_id, fascia_dati, anonimizzato, token_input, bloccato)
               VALUES (%s, %s, %s, %s, TRUE, %s, FALSE)""",
            (agente_id, a["fornitore_id"], a["modello_id"], fascia_dati, ris.token_input),
        )
        conn.execute(
            """INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato)
               VALUES (%s, %s, %s, %s, %s)""",
            (agente_id, a["modello_nome"], ris.token_input, ris.token_output,
             _costo(a, ris.token_input, ris.token_output)),
        )
        conn.execute(
            "INSERT INTO registro_azioni (agente_id, azione, utente_id) VALUES (%s, 'risposta_generata', %s)",
            (agente_id, utente_id),
        )
        n_richieste = richieste.estrai_e_salva(conn, agente_id, ris.testo)
    return {"agente": a["nome"], "risposta": ris.testo, "richieste_create": n_richieste,
            "token_input": ris.token_input, "token_output": ris.token_output,
            "documenti_usati": usati, "documenti_esclusi_per_riservatezza": esclusi}
