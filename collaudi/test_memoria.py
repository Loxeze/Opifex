import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import agente_browser, esecuzione, dialoghi, strumenti_google, google
from app.fornitori import Risposta
from app.main import app
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
uid = sql("SELECT id FROM utenti")[0][0]
sql("UPDATE agenti SET dialoghi_attivi = FALSE")
# garanzie: i dati interni possono uscire verso i fornitori
sql("UPDATE fornitori_ai SET non_conservazione_attiva = TRUE, dpa_firmato = TRUE, fascia_dati_max = 'riservato'")
sql("UPDATE agenti SET fascia_dati_max = 'riservato'")

visti = []
def finto(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
    visti.append(messaggio); return Risposta("ok", 10, 5)
esecuzione.chiama_modello = finto
dialoghi.chiama_modello = finto
copione, ricevuti = [], []
def finta_api(corpo):
    ricevuti.append(corpo); return copione.pop(0) if copione else fine('ok')
agente_browser._chiama_api = finta_api
uso = lambda: {"input_tokens": 100, "output_tokens": 20}
def chiama(nome, dati, i="t"): return {"stop_reason": "tool_use", "usage": uso(), "content": [{"type": "tool_use", "id": i, "name": nome, "input": dati}]}
def fine(t): return {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": t}]}

ID = lambda n: sql("SELECT id FROM agenti WHERE nome=%s", (n,))[0][0]
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    aurora, scout, marco = ID("Aurora"), ID("Scout"), ID("Marco")
    ok("Aurora vede tutto e usa Drive di default; Scout no", sql("SELECT vede_tutto, drive_attivo FROM agenti WHERE id=%s", (aurora,))[0] == (True, True)
       and sql("SELECT vede_tutto, drive_attivo FROM agenti WHERE id=%s", (scout,))[0] == (False, False))
    ag = {a["nome"]: a for a in c.get("/gestione/agenti", headers=H).json()}
    ok("l'elenco espone vede_tutto e drive_attivo", ag["Aurora"]["vede_tutto"] is True and ag["Scout"]["drive_attivo"] is False)
    ok("si possono accendere dal modulo", c.put(f"/gestione/agenti/{scout}", headers=H, json={"drive_attivo": True}).status_code == 200
       and sql("SELECT drive_attivo FROM agenti WHERE id=%s", (scout,))[0][0] is True)
    c.put(f"/gestione/agenti/{scout}", headers=H, json={"drive_attivo": False})

    # --- memoria della chat
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "Il codice del progetto e' ZEBRA-42, ricordalo", "fascia_dati": "interno"})
    ok("prima chat ok", r.status_code == 200, r.text)
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "Qual era il codice?", "fascia_dati": "interno"})
    ok("la seconda chat contiene la prima (cronologia)", "ZEBRA-42" in visti[-1] and "Conversazione precedente" in visti[-1], visti[-1][:300])
    ok("gli scambi sono salvati", sql("SELECT count(*) FROM chat_messaggi WHERE agente_id=%s", (scout,))[0][0] == 4)
    sql("INSERT INTO chat_messaggi (agente_id, utente_id, ruolo, testo, fascia_dati) VALUES (%s,%s,'utente','segreto riservato QUOKKA','riservato')", (scout, uid))
    sql("UPDATE agenti SET fascia_dati_max='interno' WHERE id=%s", (scout,))
    sql("UPDATE fornitori_ai SET fascia_dati_max='interno'")
    c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "Ciao", "fascia_dati": "interno"})
    ok("un messaggio riservato non rientra nel contesto di un agente da dati interni", "QUOKKA" not in visti[-1])
    sql("UPDATE agenti SET fascia_dati_max='riservato'"); sql("UPDATE fornitori_ai SET fascia_dati_max='riservato'")

    # --- Aurora vede il lavoro con gli altri
    c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Per Renovatio il budget massimo e' 80000 euro", "fascia_dati": "interno"})
    c.post(f"/agenti/{aurora}/chat", headers=H, json={"messaggio": "Ciao Aurora, a che punto siamo?", "fascia_dati": "interno"})
    ok("Aurora riceve la visione d'insieme con quello detto a Marco", "VISIONE D'INSIEME" in visti[-1] and "80000" in visti[-1], visti[-1][:400])
    ok("Aurora non vede nella panoramica la propria chat come 'altri agenti'", visti[-1].count("Ciao Aurora") == 1)
    c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ricordi il budget?", "fascia_dati": "interno"})
    ok("Scout (senza vede_tutto) NON vede la chat con Marco", "80000" not in visti[-1])

    # --- documenti letti davvero
    d = c.post("/gestione/documenti", headers=H, files={"file": ("renovatio.txt", ("Dossier Renovatio. " + "Associazione di promozione sociale con sede a Genova. " * 30).encode())},
               data={"nome": "Dossier Renovatio", "fascia_dati": "interno", "agenti": f"{scout},{marco}"})
    ok("documento caricato", d.status_code == 201, d.text)
    ricevuti.clear()
    c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "xyz", "fascia_dati": "interno"})
    primo = ricevuti[0]["messages"][0]["content"]
    ok("anche con una domanda senza parole in comune l'agente riceve elenco e inizio del documento",
       "Dossier Renovatio" in primo and "Associazione di promozione sociale" in primo, primo[:300])
    copione[:] = [chiama("leggi_documento", {"nome": "dossier renovatio"}, "d1"), fine("letto")]
    ricevuti.clear()
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "leggi il dossier", "fascia_dati": "interno"})
    esito = str(ricevuti[-1]["messages"][-1]["content"]) if len(ricevuti) > 1 else ""
    ok("lo strumento leggi_documento restituisce il testo", r.status_code == 200 and "parte 1 di" in esito and "Genova" in esito, esito[:200])
    ok("documento non assegnato: non leggibile", "non trovato" in __import__("app.memoria", fromlist=["x"]).leggi_documento(
        __import__("app.db", fromlist=["x"]).connessione().__enter__(), {"id": ID("Leo"), "fascia_dati_max": "riservato", "fascia_fornitore": "riservato", "non_conservazione_attiva": True, "dpa_firmato": True}, "Dossier Renovatio"))
    # nei dialoghi tra agenti
    visti.clear()
    sql("UPDATE agenti SET dialoghi_attivi = TRUE WHERE id IN (%s,%s)", (scout, marco))
    c.post("/gestione/dialoghi", headers=H, json={"da_agente_id": marco, "a_agente_id": scout, "argomento": "parliamo della cosa", "messaggi": 2, "fascia_dati": "interno"})
    ok("nei dialoghi tra agenti il documento e' disponibile", any("Dossier Renovatio" in v for v in visti), str(visti)[:200])
    sql("UPDATE agenti SET dialoghi_attivi = FALSE")

    # --- Google (finto)
    chiamate = []
    stato = {"id": "F1", "parents": ["RAD"]}
    def finta_rich(metodo, url, tok, **kw):
        chiamate.append((metodo, url, kw.get("params"), kw.get("json")))
        class R:
            status_code = 200; text = "Scadenza,Bando\n1/1,Borghi"
            def json(self_):
                if "/files/" in url and metodo == "GET" and "export" not in url:
                    return {"parents": ["RAD"], "name": "Scadenze", "mimeType": strumenti_google.MIME_FOGLIO}
                if metodo == "GET": return {"files": [{"id": "F1", "name": "Scadenze", "mimeType": strumenti_google.MIME_FOGLIO}]}
                return {"id": "NUOVO1", "name": "Scadenze bandi", "webViewLink": "https://docs.google.com/x"}
        return R()
    strumenti_google._richiesta = finta_rich
    google.radice_valida = lambda conn, tok: "RAD"
    google.token_accesso = lambda conn, a: "tok"
    strumenti_google.token_accesso = lambda conn, a: "tok"
    sql("UPDATE impostazioni_sistema SET valore='RAD' WHERE chiave='drive_radice_id'")
    acc = sql("INSERT INTO account_google (etichetta,email,refresh_token_cifrato,servizi) VALUES ('t','t@x.it','x',ARRAY['drive']) RETURNING id")[0][0]
    sql("UPDATE impostazioni_sistema SET valore=%s WHERE chiave='drive_account_id'", (str(acc),))
    copione[:] = [chiama("google_crea_foglio", {"titolo": "Scadenze bandi", "righe": [["Bando", "Scadenza"], ["Borghi", "30/11"]]}, "g1"), fine("Fatto, foglio creato")]
    ricevuti.clear()
    r = c.post(f"/agenti/{aurora}/chat", headers=H, json={"messaggio": "Crea un excel per le scadenze dei bandi", "fascia_dati": "interno"})
    nomi = [t["name"] for t in ricevuti[0]["tools"]]
    ok("Aurora ha gli strumenti Google", "google_crea_foglio" in nomi and "google_aggiorna_foglio" in nomi, str(nomi))
    ok("nessuno strumento per cancellare o condividere", not any("cancell" in n or "elimin" in n or "condivid" in n for n in nomi))
    ok("il foglio e' stato creato e registrato", sql("SELECT count(*) FROM file_google_agenti WHERE file_id='NUOVO1'")[0][0] == 1 and r.status_code == 200, r.text)
    ok("la creazione e' nel registro azioni", sql("SELECT count(*) FROM registro_azioni WHERE azione='google_file_creato'")[0][0] == 1)
    # modifica: solo file propri
    copione[:] = [chiama("google_aggiorna_foglio", {"file_id": "F1", "righe": [["x"]], "aggiungi": True}, "g2"), fine("fatto")]
    ricevuti.clear()
    c.post(f"/agenti/{aurora}/chat", headers=H, json={"messaggio": "aggiungi una riga al foglio F1", "fascia_dati": "interno"})
    esito = str(ricevuti[-1]["messages"][-1]["content"])
    ok("non si modifica un file non creato da un agente", "solo file creati da un agente" in esito, esito[:200])
    copione[:] = [chiama("google_aggiorna_foglio", {"file_id": "NUOVO1", "righe": [["Nuovo", "1/2"]], "aggiungi": True}, "g3"), fine("fatto")]
    ricevuti.clear(); chiamate.clear()
    c.post(f"/agenti/{aurora}/chat", headers=H, json={"messaggio": "aggiungi una riga", "fascia_dati": "interno"})
    ok("si modifica un file creato da un agente (append)", any(m == "POST" and "values/A1:append" in u for m, u, _, _ in chiamate), str(chiamate))
    copione[:] = [chiama("google_leggi", {"file_id": "F1"}, "g4"), fine("letto")]
    ricevuti.clear()
    c.post(f"/agenti/{aurora}/chat", headers=H, json={"messaggio": "leggi F1", "fascia_dati": "interno"})
    ok("lettura di un file nella cartella Opifex", "Borghi" in str(ricevuti[-1]["messages"][-1]["content"]))
    # senza permesso o senza Google collegato
    ricevuti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("Scout (drive_attivo spento) non ha strumenti Google", not ricevuti or not any(t["name"].startswith("google_") for t in ricevuti[0].get("tools", [])))
    sql("UPDATE impostazioni_sistema SET valore='' WHERE chiave='drive_account_id'")
    ricevuti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{aurora}/chat", headers=H, json={"messaggio": "ciao di nuovo", "fascia_dati": "interno"})
    ok("senza account Drive collegato niente strumenti Google", not ricevuti or not any(t["name"].startswith("google_") for t in ricevuti[0].get("tools", [])))
print(f"TOTALE {sum(ris)}/{len(ris)}")
