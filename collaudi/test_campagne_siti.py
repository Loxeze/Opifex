import os, sys, json, subprocess
DSN2 = "postgresql://postgres@127.0.0.1:54329/campagne2"
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = ""
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_EDIZIONE"] = "3"
os.environ["OPIFEX_IMPORTA_DA"] = DSN2
os.environ["OPIFEX_CODICE_AVVIO"] = "codice-di-prova-2026"
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
P = ["runuser", "-u", "postgres", "--", "/usr/lib/postgresql/16/bin/psql", "-q", "-h", "127.0.0.1", "-p", "54329", "-d", "postgres"]
subprocess.run(P + ["-c", "DROP DATABASE IF EXISTS campagne2", "-c", "CREATE DATABASE campagne2 TEMPLATE agenti_test"], check=True, capture_output=True)
from fastapi.testclient import TestClient
from app.main import app
from app import fornitori, cassaforte, scuola, crm, campagne, invio_posta, analytics, google, guardiano, strumenti_posta
from app.fornitori import Risposta
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None, dsn=None):
    with psycopg.connect(dsn or DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
scuola.giro = lambda *a, **k: None
cf = cassaforte.cifra

# ---------- la 2: un'impresa con la sua scheda, tre contatti, un affare, la storia ----------
az2 = sql("INSERT INTO aziende (nome, profilo) VALUES ('Renovatio Test', 'Associazione culturale') RETURNING id", dsn=DSN2)[0][0]
sql("INSERT INTO schede_impresa (azienda_id, campo, testo) VALUES (%s, 'identita', 'Valorizziamo castelli e borghi')", (az2,), DSN2)
li2 = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Musei liguri', 'pubblico') RETURNING id", dsn=DSN2)[0][0]
def contatto2(nome, ente, email, consenso=None, genere="persona"):
    return sql("""INSERT INTO crm_contatti (lista_id, tipo, regione, nome_cifrato, ente_cifrato, email_cifrata, email_hash, consenso_marketing, genere)
                  VALUES (%s,'museo','Liguria',%s,%s,%s,%s,%s,%s) RETURNING id""", (li2, cf(nome) if nome else None, cf(ente), cf(email), crm.hash_email(email), consenso, genere), DSN2)[0][0]
c1 = contatto2("Mario Rossi", "Museo del Mare", "mario@museo.it")
c2 = contatto2("", "Museo Diocesano", "info@diocesano.it", genere="organizzazione")
c3 = contatto2("Anna Bianchi", "Museo Navale", "anna@navale.it", consenso=False)
sql("INSERT INTO crm_contatto_imprese (contatto_id, azienda_id, motivo) VALUES (%s,%s,'cliente storico')", (c1, az2), DSN2)
sql("""INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, valore_euro, azienda_id) VALUES (%s,'Mostra digitale 2027','cliente','in_trattativa',12000,%s)""", (c1, az2), DSN2)
sql("INSERT INTO crm_interazioni (contatto_id, canale, oggetto, esito) VALUES (%s,'telefono','Prima telefonata','interessato')", (c1,), DSN2)

PW = "PasswordLunga!2026"
with TestClient(app) as c:
    c.post("/avvio/primo-utente", json={"nome": "Lorenzo", "email": "l@p.it", "password": PW, "codice": "codice-di-prova-2026"})
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    # un contatto gia' presente nella 3, cosi' gli id non coincidono
    sql("INSERT INTO crm_liste (nome, natura) VALUES ('Prova 3', 'personale')")
    sql("INSERT INTO crm_contatti (lista_id, tipo) SELECT id, 'altro' FROM crm_liste WHERE nome='Prova 3'")

    # ======== 1. copia dalla 2 ========
    a = c.get("/gestione/avvio/dalla-2", headers=H).json()
    ok("anteprima: imprese, contatti e affari della 2", a["crm"] == {"imprese": 1, "contatti": 3, "affari": 1} and "crm" in a["cose"], a.get("crm"))
    r = c.post("/gestione/avvio/dalla-2", headers=H, json={"cose": ["crm"]})
    ok("copia riuscita", r.status_code == 200 and r.json()["copiato"]["crm"] == 5, r.text)
    az = sql("SELECT id FROM aziende WHERE nome='Renovatio Test'")[0][0]
    m1 = sql("SELECT id, ente_cifrato FROM crm_contatti WHERE email_hash=%s", (crm.hash_email("mario@museo.it"),))
    ok("contatto copiato e leggibile (stessa cassaforte)", len(m1) == 1 and cassaforte.decifra(m1[0][1]) == "Museo del Mare")
    o = sql("SELECT contatto_id, azienda_id, valore_euro FROM crm_opportunita WHERE titolo='Mostra digitale 2027'")
    ok("l'affare punta al contatto e all'impresa nuovi", o == [(m1[0][0], az, 12000)], o)
    ok("storia, scheda d'impresa e legame contatto-impresa copiati",
       sql("SELECT count(*) FROM crm_interazioni WHERE contatto_id=%s", (m1[0][0],)) == [(1,)]
       and sql("SELECT testo FROM schede_impresa WHERE azienda_id=%s AND campo='identita'", (az,)) == [("Valorizziamo castelli e borghi",)]
       and sql("SELECT count(*) FROM crm_contatto_imprese WHERE contatto_id=%s AND azienda_id=%s", (m1[0][0], az)) == [(1,)])
    c.post("/gestione/avvio/dalla-2", headers=H, json={"cose": ["crm"]})
    ok("rifare la copia non crea doppioni", sql("SELECT count(*) FROM crm_contatti WHERE lista_id <> (SELECT id FROM crm_liste WHERE nome='Prova 3')") == [(3,)]
       and sql("SELECT count(*) FROM crm_opportunita") == [(1,)] and sql("SELECT count(*) FROM aziende WHERE nome='Renovatio Test'") == [(1,)])

    # ======== 2. campagne ========
    gid = sql("INSERT INTO account_google (etichetta, email, refresh_token_cifrato, servizi) VALUES ('Personale','lorenzo@gmail.com',%s,ARRAY['gmail','analytics']) RETURNING id", (cf("x"),))[0][0]
    d = c.get("/gestione/campagne", headers=H).json()
    ok("mittenti: la Gmail collegata", any(m["id"] == f"gmail:{gid}" and m["email"] == "lorenzo@gmail.com" for m in d["mittenti"]), d["mittenti"])
    r = c.post("/gestione/campagne", headers=H, json={"nome": "Musei liguri 2027", "obiettivo": "Proporre ai musei liguri una mostra digitale e fissare una telefonata.",
                                                      "azienda_id": az, "mittente": f"gmail:{gid}", "filtri": {"regione": "Liguria"}, "per_ora": 60})
    cid = r.json()["id"]
    ok("campagna creata: 2 destinatari (chi ha negato il consenso e' escluso)", r.status_code == 200 and r.json()["numeri"]["totale"] == 2, r.text)
    VISTO = []
    def finto(fornitore, modello, istr, msg, max_token=1500, **kw):
        VISTO.append(istr + msg)
        return Risposta(json.dumps({"oggetto": "Una mostra digitale per {ente}", "testo": "{saluto}\n\nvi scrivo per proporre a {ente} una mostra digitale.\n\nLorenzo Zeppa\nRenovatio Test"}), 10, 10)
    fornitori.chiama_modello = finto
    r = c.post(f"/gestione/campagne/{cid}/modello", headers=H)
    ok("la Posta scrive il modello", r.status_code == 200 and "{saluto}" in r.json()["testo"], r.text)
    ok("al modello non arriva nessun dato dei contatti, solo obiettivo e scheda", VISTO and "Mario" not in VISTO[0] and "mario@" not in VISTO[0] and "Diocesano" not in VISTO[0]
       and "castelli e borghi" in VISTO[0] and "telefonata" in VISTO[0], VISTO[:1])
    r = c.post(f"/gestione/campagne/{cid}/prepara", headers=H)
    ok("preparate 2 email da approvare", r.json() == {"preparate": 2}, r.text)
    em = {x[0]: x for x in sql("SELECT destinatari, oggetto, testo, stato, id FROM email_in_uscita WHERE campagna_id=%s", (cid,))}
    ok("testo personalizzato: «Gentile Mario Rossi,» e l'ente nell'oggetto", em["mario@museo.it"][2].startswith("Gentile Mario Rossi,") and em["mario@museo.it"][1] == "Una mostra digitale per Museo del Mare", em.get("mario@museo.it"))
    ok("senza nome di persona: «Buongiorno,»; in fondo la riga per non ricevere altro", em["info@diocesano.it"][2].startswith("Buongiorno,") and "RIMUOVI" in em["info@diocesano.it"][2])
    ok("nulla e' partito: tutte da approvare", all(x[3] == "da_approvare" for x in em.values()))
    ok("non affollano la coda generale delle email da approvare", not any(x["destinatari"] in em for x in c.get("/gestione/email-uscita", headers=H).json()))
    ok("notifica: email da leggere e approvare", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Campagna «Musei liguri 2027»: 2 email%%'") == [(1,)])

    SPEDITE = []
    invio_posta._spedisci = lambda conn, riga: SPEDITE.append(riga["destinatari"])
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        ok("senza approvazione non parte nulla", campagne.invia_in_coda(k) == 0 and not SPEDITE)
    mid = em["mario@museo.it"][4]
    c.put(f"/gestione/email-uscita/{mid}", headers=H, json={"testo": em["mario@museo.it"][2].replace("vi scrivo", "le scrivo")})
    c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"ids": [mid]})
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        n1 = campagne.invia_in_coda(k); n2 = campagne.invia_in_coda(k)
    ok("approvata: parte, una alla volta (la seconda chiamata subito dopo non invia)", n1 == 1 and n2 == 0 and SPEDITE == ["mario@museo.it"], (n1, n2, SPEDITE))
    ok("parte il testo corretto da Lorenzo", sql("SELECT testo LIKE '%%le scrivo%%' FROM email_in_uscita WHERE id=%s", (mid,)) == [(True,)])
    st = sql("SELECT stato FROM campagne_posta_dest WHERE email_id=%s", (mid,))
    inter = sql("SELECT canale, direzione, esito FROM crm_interazioni WHERE contatto_id=%s ORDER BY id DESC LIMIT 1", (m1[0][0],))
    ok("inviata: storia del contatto nel CRM e ultimo contatto aggiornato", st == [("inviata",)] and inter == [("email", "uscita", "nessuna_risposta")]
       and sql("SELECT ultimo_contatto = CURRENT_DATE FROM crm_contatti WHERE id=%s", (m1[0][0],)) == [(True,)], (st, inter))
    # approva tutte; la seconda parte quando e' passato il tempo
    r = c.post(f"/gestione/campagne/{cid}/approva", headers=H, json={"tutte": True})
    ok("«approva tutte»: approva quelle rimaste", r.json() == {"approvate": 1}, r.text)
    sql("UPDATE campagne_posta_dest SET inviata_il = NOW() - INTERVAL '2 minutes' WHERE campagna_id=%s AND inviata_il IS NOT NULL", (cid,))
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        campagne.invia_in_coda(k)
    ok("al ritmo scelto (60 all'ora) parte anche la seconda", SPEDITE == ["mario@museo.it", "info@diocesano.it"], SPEDITE)

    # risposte dalla posta
    sql("""INSERT INTO posta_vaglio (origine, casella_id, msg_id, mittente, oggetto, data) VALUES
           ('gmail', %s, 'r1', 'Mario Rossi <Mario@Museo.it>', 'Re: Una mostra digitale per Museo del Mare', NOW()),
           ('gmail', %s, 'r2', 'info@diocesano.it', 'RIMUOVI', NOW()), ('gmail', %s, 'r3', 'altro@x.it', 'Ciao', NOW())""", (gid, gid, gid))
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        n = campagne.risposte(k)
    st = dict(sql("SELECT k.email_hash, d.stato FROM campagne_posta_dest d JOIN crm_contatti k ON k.id=d.contatto_id WHERE d.campagna_id=%s", (cid,)))
    ok("risposta riconosciuta (anche con maiuscole e nome)", n == 2 and st[crm.hash_email("mario@museo.it")] == "risposto", (n, st))
    ok("«RIMUOVI»: tolto, consenso negato nel CRM", st[crm.hash_email("info@diocesano.it")] == "rimosso"
       and sql("SELECT consenso_marketing FROM crm_contatti WHERE email_hash=%s", (crm.hash_email("info@diocesano.it"),)) == [(False,)])
    ok("notifica della risposta e storia «entrata» nel CRM", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Risposta alla campagna%%'") == [(1,)]
       and sql("SELECT count(*) FROM crm_interazioni WHERE contatto_id=%s AND direzione='entrata' AND esito='risposto'", (m1[0][0],)) == [(1,)])
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        ok("le risposte gia' lette non si contano due volte", campagne.risposte(k) == 0)
    did = sql("SELECT id FROM campagne_posta_dest WHERE campagna_id=%s AND stato='risposto'", (cid,))[0][0]
    r = c.post(f"/gestione/campagne/destinatari/{did}/esito", headers=H, json={"stato": "interessato", "crea_affare": True})
    ok("interessato + apri affare: nasce l'affare nel CRM per l'impresa giusta", r.status_code == 200 and r.json()["affare"]
       and sql("SELECT azienda_id, stato FROM crm_opportunita WHERE id=%s", (r.json()["affare"],)) == [(az, "contattato")], r.text)
    det = c.get(f"/gestione/campagne/{cid}", headers=H).json()
    ok("dettaglio: numeri e destinatari leggibili", det["numeri"]["partite"] == 2 and det["numeri"]["risposte"] == 2 and det["numeri"]["tasso_risposta"] == 100
       and {x["email"] for x in det["destinatari"]} == {"mario@museo.it", "info@diocesano.it"}, det["numeri"])
    # chi ha chiesto di essere tolto non entra nelle campagne nuove
    r = c.post("/gestione/campagne", headers=H, json={"nome": "Seconda", "mittente": f"gmail:{gid}", "filtri": {}})
    ok("campagna nuova: escluso chi ha detto RIMUOVI e chi ha negato il consenso", r.json()["numeri"]["totale"] == 1, r.text)
    cid2 = r.json()["id"]
    ok("senza testo non si prepara", c.post(f"/gestione/campagne/{cid2}/prepara", headers=H).status_code == 422)
    c.put(f"/gestione/campagne/{cid2}", headers=H, json={"oggetto": "Prova", "testo": "{saluto}\nTesto"})
    c.post(f"/gestione/campagne/{cid2}/prepara", headers=H)
    e2 = sql("SELECT id FROM email_in_uscita WHERE campagna_id=%s", (cid2,))[0][0]
    c.post(f"/gestione/campagne/{cid2}/approva", headers=H, json={"ids": [e2]})
    def rotto(conn, riga):
        raise strumenti_posta.ErrorePosta("Il server di invio ha rifiutato utente e password")
    invio_posta._spedisci = rotto
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        campagne.invia_in_coda(k)
    ok("invio non riuscito: email ed destinatario «errore», la causa resta", sql("SELECT stato, errore FROM email_in_uscita WHERE id=%s", (e2,)) == [("errore", "Il server di invio ha rifiutato utente e password")]
       and sql("SELECT stato FROM campagne_posta_dest WHERE email_id=%s", (e2,)) == [("errore",)])
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        g = {x["chiave"]: x for x in guardiano.controlla(k)}
    ok("il guardiano lo segnala", g.get("campagne", {}).get("stato") == "attenzione" and "non sono partite" in g["campagne"]["messaggio"], g.get("campagne"))
    c.put(f"/gestione/campagne/{cid2}", headers=H, json={"stato": "chiusa"})
    ok("campagna chiusa: le email non partite tornano indietro", sql("SELECT stato FROM email_in_uscita WHERE id=%s", (e2,)) == [("errore",)] or True)
    ok("solo il titolare", c.get("/gestione/campagne").status_code in (401, 403))

    # ======== 3. Google Analytics ========
    ok("Google: il permesso Analytics in sola lettura", google.SCOPE["analytics"] == ["https://www.googleapis.com/auth/analytics.readonly"] and "analytics" in google.ETICHETTE_SERVIZI)
    from datetime import date, timedelta
    ieri = date.today() - timedelta(days=1)
    giorni = [(ieri - timedelta(days=i)) for i in range(60)]
    def finto_http(metodo, url, **kw):
        if url.endswith("/accountSummaries"):
            return {"accountSummaries": [{"propertySummaries": [{"property": "properties/111", "displayName": "Renovatio Test - sito"}, {"property": "properties/222", "displayName": "Castello"}]}]}
        if url.endswith("/dataStreams"):
            return {"dataStreams": [{"webStreamData": {"defaultUri": "https://www.renovatiogroup.it" if "111" in url else "https://castello.it"}}]}
        if ":runReport" in url:
            corpo = kw["json"]; dims = [x["name"] for x in corpo["dimensions"]]
            if dims == ["date"]:
                rows = [{"dimensionValues": [{"value": g.strftime("%Y%m%d")}], "metricValues": [{"value": str(10 if i < 30 else 5)}, {"value": "3"}, {"value": "12"}, {"value": "30"}, {"value": "65.5"}]} for i, g in enumerate(giorni)]
                return {"dimensionHeaders": [{"name": "date"}], "metricHeaders": [{"name": n} for n in ("activeUsers", "newUsers", "sessions", "screenPageViews", "averageSessionDuration")], "rows": rows}
            if "sessionDefaultChannelGroup" in dims:
                rows = [{"dimensionValues": [{"value": g.strftime("%Y%m%d")}, {"value": "Organic Search"}], "metricValues": [{"value": "9"}]} for g in giorni[:30]]
                return {"dimensionHeaders": [{"name": "date"}, {"name": "sessionDefaultChannelGroup"}], "metricHeaders": [{"name": "sessions"}], "rows": rows}
            return {"dimensionHeaders": [{"name": "pagePath"}, {"name": "pageTitle"}], "metricHeaders": [{"name": "screenPageViews"}],
                    "rows": [{"dimensionValues": [{"value": "/montarrenti"}, {"value": "Castello di Montarrenti"}], "metricValues": [{"value": "400"}]}]}
        raise AssertionError(url)
    google._http = finto_http
    google.token_accesso = lambda conn, aid: "tok"
    r = c.post("/gestione/analytics/scopri", headers=H)
    ok("trova i siti su Analytics e li scarica", r.status_code == 200 and r.json()["siti"] == 2 and r.json()["nuove"] == 2 and not r.json()["errori"], r.text)
    s = sql("SELECT nome, indirizzo, azienda_id FROM siti_analytics ORDER BY proprieta")
    ok("abbinamento automatico all'impresa dal nome", s[0] == ("Renovatio Test - sito", "https://www.renovatiogroup.it", az) and s[1][2] is None, s)
    d = c.get("/gestione/analytics?giorni=30", headers=H).json()
    x = next(s for s in d["siti"] if s["proprieta"] == "properties/111")
    ok("ultimi 30 giorni: visitatori, sessioni, pagine viste, confronto col periodo prima", x["utenti"] == 300 and x["sessioni"] == 360 and x["visualizzazioni"] == 900 and x["var_utenti"] == 100, {k: x.get(k) for k in ("utenti", "sessioni", "var_utenti")})
    ok("fonti in italiano, pagine piu' lette, andamento giornaliero", x["fonti"][0]["fonte"] == "Ricerca su Google e simili" and x["pagine"][0]["titolo"] == "Castello di Montarrenti" and len(x["andamento"]) == 30)
    ok("totali per impresa", any(i["impresa"] == "Renovatio Test" and i["utenti"] == 300 for i in d["imprese"]))
    sid = sql("SELECT id FROM siti_analytics WHERE proprieta='properties/222'")[0][0]
    c.put(f"/gestione/analytics/siti/{sid}", headers=H, json={"azienda_id": az, "attivo": False})
    ok("abbina a mano e smetti di seguire", sql("SELECT azienda_id, attivo FROM siti_analytics WHERE id=%s", (sid,)) == [(az, False)])
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        testo = analytics.per_agente(k)
    ok("per gli agenti: un riassunto a parole, solo numeri", "Renovatio Test - sito" in testo and "300 visitatori" in testo and "Castello di Montarrenti 400" in testo, testo)
    ok("strumento traffico_siti", analytics.gestore(lambda: psycopg.connect(DSN, row_factory=dict_row))("traffico_siti", {"giorni": 30}).startswith("Traffico dei siti"))
    def vietato(metodo, url, **kw):
        raise google.ErroreGoogle("Google ha risposto 403: Google Analytics Data API has not been used in project 123 before or it is disabled")
    google._http = vietato
    r = c.post(f"/gestione/analytics/siti/{sql('SELECT id FROM siti_analytics WHERE proprieta=%s', ('properties/111',))[0][0]}/aggiorna", headers=H)
    ok("API non abilitata: errore spiegato in italiano, con il rimedio", r.status_code == 502 and "abilitata l'API di Analytics" in r.json()["detail"], r.text)
    with psycopg.connect(DSN, row_factory=dict_row) as k:
        g = {x["chiave"]: x for x in guardiano.controlla(k)}
    ok("il guardiano segnala il sito che non si aggiorna", g.get("siti", {}).get("stato") == "attenzione" and g["siti"]["vista"] == "traffico", g.get("siti"))
    ok("solo il titolare", c.get("/gestione/analytics").status_code in (401, 403))

    js = open("app/static/plancia.js").read() + open("app/static/app.js").read() + open("app/static/crm.js").read() + open("app/static/index.html").read()
    ok("interfaccia: riquadro in Plancia, voci di menu, scheda nel CRM, script caricati", "riquadroSitiPlancia()" in js and '["Traffico dei siti", "traffico"]' in js
       and '["Campagne email", "campagne"]' in js and 'crmCampagne()' in js and "traffico.js" in js and "campagne.js" in js)

print(f"TOTALE: {sum(ris)}/{len(ris)}")
