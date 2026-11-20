import os, sys, json
from datetime import date, timedelta
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient
from app.main import app
from app import fornitori, scuola, legale, competenze_base, cassaforte
from app.fornitori import Risposta
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
def K():
    return psycopg.connect(DSN, row_factory=dict_row)
scuola.giro = lambda *a, **k: None

CHIAMATE = []
OGGI = date.today()
RISPOSTE = {
    "parere": {"consiglio": "Prima di usare le foto, fai firmare una liberatoria a chi e' riconoscibile.", "perche": "Il ritratto non si diffonde senza consenso.",
               "prossimo_passo": "Prepara un modulo di liberatoria.", "rischio": "alto", "ricerche": ["norma sul diritto all'immagine per le foto di Renovatio fatte da Mario Rossi"]},
    "appunti": {"tipo_documento": "contratto", "parti": ["Giulia Bianchi", "Renovatio"], "controparte": "Giulia Bianchi", "fatti": ["collaborazione dal 2022"],
                "obblighi": ["consegnare i report mensili"], "scadenze": [{"data": (OGGI + timedelta(days=20)).isoformat(), "cosa": "udienza"}], "penali": [], "riservatezza": ["clausola di riservatezza"]},
    "studio": {"fatti": ["collaborazione dal 2022"], "questioni": ["natura del rapporto"], "ricerche": [{"tipo": "sentenza", "domanda": "Giulia Bianchi chiede a Renovatio il lavoro subordinato dopo una collaborazione"}],
               "domande_per_lorenzo": ["Avevate un orario fisso concordato?"], "strategia": "Dimostrare l'autonomia della collaboratrice.", "mosse": [{"mossa": "proporre una conciliazione", "pro": "costi bassi", "contro": "si paga", "rischio": "medio"}], "rischi": ["riqualificazione"]},
    "relazione": "SINTESI\nLa collaborazione appare autonoma.\nPRECEDENTI E NORME\nCass. civ. n. 6893/2021 conferma l'autonomia; vedi anche n. 99999/2020.",
    "vigilanza": {"osservazioni": [{"ambito": "Campagne email", "situazione": "Email a freddo agli hotel", "consiglio": "Inserisci sempre come hai trovato l'indirizzo e la riga per non ricevere altro.",
                                    "perche": "GDPR e legittimo interesse.", "prossimo_passo": "Controlla il testo standard.", "rischio": "medio", "ricerche": []}]},
}
def finto_modello(fornitore, modello, istr, msg, max_token=1500, **kw):
    chiave = {legale.ISTR_PARERE: "parere", legale.ISTR_APPUNTI: "appunti", legale.ISTR_SCHEDA: "appunti", legale.ISTR_STUDIO: "studio",
              legale.ISTR_RELAZIONE: "relazione", legale.ISTR_VIGILANZA: "vigilanza"}.get(istr, "altro")
    CHIAMATE.append((fornitore, chiave, msg))
    r = RISPOSTE.get(chiave, {})
    if chiave == "appunti" and "Tipografia" in msg:
        r = {"tipo_documento": "contratto di fornitura", "parti": ["Logos", "Tipografia Alfa Srl"], "controparte": "Tipografia Alfa Srl",
             "obblighi": ["consegna in 10 giorni lavorativi"], "scadenze": [{"data": (OGGI + timedelta(days=5)).isoformat(), "cosa": "disdetta del contratto"}],
             "penali": ["50 euro per giorno di ritardo"], "riservatezza": [], "punti_critici": ["rinnovo tacito"], "sintesi": "Fornitura di stampa."}
    return Risposta(r if isinstance(r, str) else json.dumps(r), 500, 200)
fornitori.chiama_modello = finto_modello

WEB = []
def finto_web(conn, domanda, siti, max_ricerche=5):
    WEB.append((domanda, siti))
    fonti = [{"tipo": "sentenza", "estremi": "Cass. civ., sez. lav., 12/03/2021, n. 6893", "numero": "6893", "data": "2021-03-12", "ente": "Corte di cassazione",
              "url": "https://www.italgiure.giustizia.it/sncass/6893", "fatti": "Collaboratrice chiede la subordinazione.", "decisione": "Rigettata: mancava l'eterodirezione.", "perche_serve": "Caso simile."},
             {"tipo": "sentenza", "estremi": "Cass. civ. n. 11111/2019", "numero": "11111", "url": "https://www.cortedicassazione.it/inventata", "decisione": "x"},
             {"tipo": "sentenza", "estremi": "Trib. Milano n. 222/2020", "numero": "222", "url": "https://www.blog-giuridico.example/222", "decisione": "y"}]
    return json.dumps({"fonti": fonti}), {"https://www.italgiure.giustizia.it/sncass/6893", "https://www.blog-giuridico.example/222"}, 1000, 300, "claude-sonnet-5-5"
legale._cerca_web = finto_web
legale.scarica_pagina = lambda url: "Sentenza n. 6893 del 12 marzo 2021, sezione lavoro" if "6893" in url else "pagina senza numeri"
LOCALE = [False]
legale._locale_c_e = lambda: LOCALE[0]
fornitori.locale_occupato = lambda pausa=20.0: False

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    # un vecchio reparto legale (2.x) attivato a mano
    vecchio = sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, istruzioni) VALUES ('Legal Master','vecchio','manager','divisione','claude-sonnet-5-5','vecchie istruzioni') RETURNING id")[0][0]
    sql("INSERT INTO agenti (nome, ruolo, livello, tipo, modello, istruzioni) VALUES ('Legale Terzo settore','vecchio','operativo','divisione','claude-sonnet-5-5','x')")
    sql("INSERT INTO aziende (nome) VALUES ('Renovatio') ON CONFLICT DO NOTHING")

    q = c.get("/gestione/legale", headers=H).json()
    ok("nasce il legale: il vecchio Legal Master diventa il nuovo, con il Ricercatore", q["attivo"] and q["agenti"]["master"]["id"] == vecchio and q["agenti"]["ricercatore"]
       and sql("SELECT ruolo_speciale, accesso_web FROM agenti WHERE id=%s", (vecchio,)) == [("legale", False)]
       and sql("SELECT ruolo_speciale, accesso_web FROM agenti WHERE nome='Ricercatore legale'") == [("ricercatore_legale", True)], q.get("agenti"))
    ok("le vecchie figure legali si spengono", sql("SELECT attivo FROM agenti WHERE nome='Legale Terzo settore'") == [(False,)])
    ok("formazione: Padre Casati studia i rami del diritto e la strategia", len(q["formazione"]) >= len(legale.TEMI) + 1
       and sql("SELECT count(*) FROM casati_target WHERE tipo='tema' AND motivo LIKE '%%Legal Master%%'")[0][0] == len(legale.TEMI))
    ok("il sapere del vecchio legale diventa manuale", sql("""SELECT count(*) FROM competenze_sezioni s JOIN competenze c ON c.id=s.competenza_id
                                                              WHERE c.nome='Metodo del legale di Opifex' AND s.titolo LIKE 'Dal vecchio legale%%'""")[0][0] == 4)
    with K() as k:
        sql("DELETE FROM impostazioni_sistema WHERE chiave='competenze_base_versione'")
        competenze_base.applica(k); k.commit()
    ok("le competenze di base non riscrivono il nuovo Legal Master", sql("SELECT istruzioni FROM agenti WHERE id=%s", (vecchio,))[0][0] == legale.ISTR_MASTER)
    with K() as k:
        legale.assicura(k); k.commit()
    ok("rifarlo non duplica niente", sql("SELECT count(*) FROM agenti WHERE ruolo_speciale IN ('legale','ricercatore_legale')") == [(2,)]
       and sql("SELECT count(*) FROM casati_target WHERE tipo='tema' AND motivo LIKE '%%Legal Master%%'")[0][0] == len(legale.TEMI))

    # 1. un parere subito, senza blocco; il rischio alto avvisa Lorenzo
    r = c.post("/gestione/legale/pareri", headers=H, json={"domanda": "Posso pubblicare le foto dell'evento al castello?", "ambito": "Renovatio"}).json()
    ok("parere subito: consiglio, rischio, prossimo passo", r["stato"] == "pronto" and r["rischio"] == "alto" and "liberatoria" in r["consiglio"], r)
    ok("rischio alto: avviso urgente a Lorenzo, nessun blocco", sql("SELECT count(*) FROM notifiche WHERE urgente AND testo LIKE 'Legale — rischio ALTO%%Il lavoro prosegue%%'") == [(1,)])
    ok("il parere lo scrive il modello capace (non riservato)", CHIAMATE[-1][0] == "anthropic" and CHIAMATE[-1][1] == "parere")
    with K() as k:
        txt = legale.gestore(lambda: K(), 1)("parere_legale", {"domanda": "Serve il consenso per le foto?", "ambito": "Renovatio"})
    ok("per gli agenti: strumento parere_legale, risponde e dice di andare avanti", "CONSIGLIO DEL LEGAL MASTER" in txt and "non un blocco" in txt, txt)

    # 2. il Ricercatore legale: domande anonime, fonti verificate
    WEB.clear()
    with K() as k:
        esito = legale._passo_ricerche_pareri(k)
    dom, siti = WEB[-1]
    ok("ricerca anonima: niente nomi di imprese o persone", esito and "Renovatio" not in dom and "Mario Rossi" not in dom and "[parte]" in dom and "normattiva.it" in siti, dom)
    f = {r[0]: r[1:] for r in sql("SELECT estremi, verificata, ufficiale, verifica FROM legale_fonti")}
    ok("fonte ufficiale, uscita dalla ricerca e con il numero nella pagina: verificata", f["Cass. civ., sez. lav., 12/03/2021, n. 6893"][0] is True, f)
    ok("link non uscito dalla ricerca: scartato", f["Cass. civ. n. 11111/2019"][0] is False and "non e' fra quelli trovati" in f["Cass. civ. n. 11111/2019"][2])
    ok("sito non ufficiale: spunto, non citabile", f["Trib. Milano n. 222/2020"][0] is False and f["Trib. Milano n. 222/2020"][1] is False)
    ok("la pagina si apre ma senza il numero: non verificata", legale.verifica({"url": "https://www.normattiva.it/x", "numero": "123"}, set())[0] is False)

    # 3. fascicolo riservato: solo modello locale
    fid = c.post("/gestione/legale/fascicoli", headers=H, json={"titolo": "Causa con ex collaboratrice", "tipo": "causa", "descrizione": "Giulia Bianchi ha collaborato dal 2022.",
                                                               "parti": "Giulia Bianchi", "riservato": True}).json()["id"]
    r = c.post(f"/gestione/legale/fascicoli/{fid}/documenti", headers=H, files=[("file", ("ricorso.txt", ("Ricorso di Giulia Bianchi contro Renovatio. " * 40).encode(), "text/plain"))]).json()
    ok("documento caricato nel fascicolo", r["caricati"] == 1 and not r["errori"], r)
    ok("il testo resta cifrato nel database", "Bianchi" not in sql("SELECT testo_cifrato FROM legale_documenti WHERE fascicolo_id=%s", (fid,))[0][0])
    c.post(f"/gestione/legale/fascicoli/{fid}/incarichi", headers=H, json={"ordine": "Studia questi documenti e imposta la difesa"})
    CHIAMATE.clear()
    with K() as k:
        for _ in range(3):
            legale.giro(k)
    ok("senza computer locale il fascicolo riservato aspetta (e non va online)", not [x for x in CHIAMATE if "Bianchi" in x[2]]
       and sql("SELECT stato FROM legale_documenti WHERE fascicolo_id=%s", (fid,)) == [("da_leggere",)])
    LOCALE[0] = True
    CHIAMATE.clear(); WEB.clear()
    with K() as k:
        for _ in range(12):
            legale.giro(k)
    riservate = [x for x in CHIAMATE if x[1] in ("appunti", "studio", "relazione")]
    ok("fascicolo riservato: letto, studiato e relazionato solo dal modello locale", riservate and all(x[0] == "locale" for x in riservate), [(x[0], x[1]) for x in CHIAMATE])
    inc = sql("SELECT stato, risultato_cifrato FROM legale_incarichi WHERE fascicolo_id=%s", (fid,))[0]
    rel = cassaforte.decifra(inc[1]) if inc[1] else ""
    ok("incarico consegnato con la relazione", inc[0] == "consegnato" and "SINTESI" in rel, inc[0])
    ok("in relazione solo le fonti verificate; quelle non verificate a parte", "FONTI VERIFICATE\n- Cass. civ., sez. lav., 12/03/2021, n. 6893" in rel and "TROVATE MA NON VERIFICATE" in rel and "11111" in rel.split("TROVATE MA NON VERIFICATE")[1], rel[-900:])
    ok("un numero d'atto non verificato nel testo viene segnalato", "ATTENZIONE" in rel and "99999" in rel.split("ATTENZIONE")[1])
    ok("la ricerca del fascicolo e' anonima (niente parti)", WEB and all("Bianchi" not in d and "Giulia" not in d and "Renovatio" not in d for d, s in WEB), [d for d, s in WEB])
    ok("domande per Lorenzo in elenco, il lavoro non si e' fermato", sql("SELECT domanda, stato FROM legale_domande WHERE fascicolo_id=%s", (fid,)) == [("Avevate un orario fisso concordato?", "aperta")])
    ok("consegna notificata", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Il legale ha consegnato il lavoro sul fascicolo «Causa con ex collaboratrice»%%'") == [(1,)])
    qid = sql("SELECT id FROM legale_domande WHERE fascicolo_id=%s", (fid,))[0][0]
    c.post(f"/gestione/legale/domande/{qid}", headers=H, json={"risposta": "No, orari liberi"})
    with K() as k:
        dossier = legale._dossier(k, dict(k.execute("SELECT * FROM legale_fascicoli WHERE id=%s", (fid,)).fetchone()), 20000)
    ok("le risposte di Lorenzo entrano nel prossimo studio", "No, orari liberi" in dossier)
    det = c.get(f"/gestione/legale/fascicoli/{fid}", headers=H).json()
    ok("scheda del fascicolo: documenti, incarico, fonti", det["documenti"][0]["stato"] == "letto" and det["incarichi"][0]["risultato"] and det["fonti"], det["documenti"][0]["stato"])
    ok("il documento riservato non finisce nel registro visibile agli agenti", sql("SELECT controparte FROM legale_documenti WHERE fascicolo_id=%s", (fid,)) == [("",)])

    # 4. contratto con un fornitore: scheda, scadenze, condizioni agli agenti
    r = c.post("/gestione/legale/documenti", headers=H, data={"categoria": "fornitore"},
               files=[("file", ("contratto tipografia.txt", ("Contratto di fornitura tra Logos e Tipografia Alfa Srl. Consegna in 10 giorni. " * 20).encode(), "text/plain"))]).json()
    with K() as k:
        for _ in range(4):
            legale.giro(k)
    d = sql("SELECT stato, controparte, categoria FROM legale_documenti WHERE nome='contratto tipografia.txt'")[0]
    ok("contratto letto: scheda con la controparte", d == ("letto", "Tipografia Alfa Srl", "fornitore"), d)
    with K() as k:
        legale._passo_scadenze(k); legale._passo_scadenze(k)
    ok("scadenza vicina: un promemoria (una volta sola)", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Legale — scadenza tra 5 giorni%%disdetta%%'") == [(1,)])
    with K() as k:
        ctx = legale.contesto(k, "Manda le bozze alla Tipografia Alfa entro venerdi")
        ctx2 = legale.contesto(k, "Scrivi a Giulia Bianchi")
    ok("gli agenti che lavorano con quel fornitore vedono le condizioni", "CONDIZIONI CON TIPOGRAFIA ALFA SRL" in ctx and "50 euro per giorno di ritardo" in ctx, ctx)
    ok("le parti di un fascicolo riservato non escono mai nel contesto", ctx2 == "")

    # 5. vigilanza sul lavoro della squadra
    sql("INSERT INTO task (titolo, descrizione) VALUES ('Campagna email agli hotel di Sharm', 'Email a freddo a 300 hotel')")
    with K() as k:
        legale._passo_vigilanza(k, forza=True)
    ok("vigilanza: un consiglio, nessun blocco", sql("SELECT origine, rischio, ambito FROM legale_pareri WHERE origine='vigilanza'") == [("vigilanza", "medio", "Campagne email")]
       and "Campagna email agli hotel" in [x for x in CHIAMATE if x[1] == "vigilanza"][-1][2])

    # 6. Drive «Legale»: una cartella per causa, categorie dalle sottocartelle, archiviazione dei caricati
    CART = {n: "id-" + n for n in ["Legale"] + list(legale.SOTTOCARTELLE)}
    legale._token_drive = lambda conn: "tok"
    legale._cartelle = lambda conn, tok: (legale._scrivi(conn, "legale_drive_id", "id-Legale"), CART)[1]
    ALBERO = {"id-Cause": [{"id": "cart-x", "name": "Causa Rossi", "mimeType": "application/vnd.google-apps.folder"}],
              "cart-x": [{"id": "f1", "name": "atto.txt", "mimeType": "text/plain", "modifiedTime": "1"}],
              "id-Polizze": [{"id": "f2", "name": "polizza RC.txt", "mimeType": "text/plain", "modifiedTime": "1"}]}
    legale._elenco_drive = lambda tok, cid: ALBERO.get(cid, [])
    legale._scarica_drive = lambda tok, f: (f["name"], ("Testo del documento " + f["name"] + ". ") .encode() * 10)
    CARICATI = []
    legale._carica_drive = lambda tok, cart, nome, dati: (CARICATI.append((cart, nome)), "nuovo-" + nome)[1]
    legale._cartella_drive = lambda tok, nome, gen: "cart-" + nome
    with K() as k:
        legale._passo_drive(k, forza=True)
    ok("Drive: la cartella in Cause diventa un fascicolo riservato", sql("SELECT titolo, riservato FROM legale_fascicoli WHERE drive_id='cart-x'") == [("Causa Rossi", True)])
    ok("Drive: il documento della polizza entra con la sua categoria", sql("SELECT categoria, origine FROM legale_documenti WHERE drive_id='f2'") == [("polizza", "drive")])
    ok("i caricati a mano vengono archiviati nella sottocartella giusta", ("id-Fornitori", "contratto tipografia.txt") in CARICATI
       and sql("SELECT da_archiviare, contenuto_cifrato IS NULL FROM legale_documenti WHERE nome='contratto tipografia.txt'") == [(False, True)], CARICATI)
    with K() as k:
        n0 = sql("SELECT count(*) FROM legale_documenti")[0][0]
        legale._passo_drive(k, forza=True)
    ok("rileggere il Drive non duplica", sql("SELECT count(*) FROM legale_documenti")[0][0] == n0)

    # 7. la sezione
    q = c.get("/gestione/legale", headers=H).json()
    ok("sezione Legale: tutto quello che serve", all(k in q for k in ("fase", "formazione", "pareri", "fascicoli", "scadenze", "domande", "fonti", "registro", "luoghi"))
       and q["conteggi"]["alto"] == 2 and q["drive"].endswith("id-Legale"), q["conteggi"])
    r = c.put("/gestione/legale/luoghi", headers=H, json={"testo": "Comune di Sovicille (SI)\n\nComune di Masone (GE)"}).json()
    ok("luoghi da sorvegliare modificabili", r["luoghi"] == "Comune di Sovicille (SI)\nComune di Masone (GE)")
    ok("solo il titolare", c.get("/gestione/legale").status_code in (401, 403))
    js = open("app/static/legale.js").read()
    ok("interfaccia: schede del legale", all(x in js for x in ("Cosa sta facendo", "Consigli", "Fascicoli", "Contratti e scadenze", "Da chiarire", "Biblioteca", "Formazione", "Affida al legale")))

print(f"TOTALE: {sum(ris)}/{len(ris)}")
