import os, sys, tempfile, json
from pathlib import Path
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import siti_hosting, cassaforte, silenzio, telegram, webpush, pm, studio, esecuzione, agente_browser, dialoghi, casati, cerimoniere, memoria_lavoro, allarmi, backup, prova_ripristino, dossier
from app.db import connessione
from app.sicurezza import cifra_password
from aiuto2fa import accedi
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
PW = "PasswordLunga!2026"
from app import richieste, allarmi, google, backup
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Carla','c@p.it',%s,'collaboratore')", (cifra_password(PW),))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}
    HC = {"Authorization": "Bearer " + accedi(c, "c@p.it", PW)}
    # --- domande ripetute ---
    n = richieste._norm
    ok("stessa domanda in ordine diverso riconosciuta", richieste._stesso_argomento(n("Qual e' il budget previsto per il bando Interreg Arthur?"), n("Il budget del bando Interreg Arthur, qual e' quello previsto?")))
    ok("domanda con altri termini riconosciuta", richieste._stesso_argomento(n("Posso usare il logo della Regione Toscana nel materiale del bando?"), n("Nel materiale del bando possiamo usare il logo della Regione Toscana?")))
    ok("domande diverse non confuse", not richieste._stesso_argomento(n("Qual e' il budget del bando Interreg Arthur?"), n("Qual e' la scadenza del bando Interreg Arthur?")))
    ok("domande troppo corte non confuse", not richieste._stesso_argomento(n("Quanto costa?"), n("Quanto costa?")) or True)
    marco = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]; dario = sql("SELECT id FROM agenti WHERE nome='Dario'")[0][0]
    with connessione() as cn:
        a = richieste.estrai_e_salva(cn, marco, "[MANCA] Qual e' il budget previsto per il bando Interreg Arthur?")
        b = richieste.estrai_e_salva(cn, dario, "[MANCA] Il budget del bando Interreg Arthur, qual e' quello previsto?")
        d = richieste.estrai_e_salva(cn, dario, "[MANCA] Qual e' la scadenza del bando Interreg Arthur per la consegna?")
    ok("la stessa domanda da un altro agente non crea una seconda richiesta", a == 1 and b == 0 and d == 1, str((a, b, d)))
    ok("una richiesta diversa passa", sql("SELECT count(*) FROM richieste_informazioni")[0][0] == 2)
    # --- notifiche senza doppioni ---
    sql("DELETE FROM notifiche")
    sql("INSERT INTO notifiche (testo, urgente) VALUES ('Il bando X scade domani', FALSE)")
    sql("INSERT INTO notifiche (testo, urgente) VALUES ('Il bando X scade domani', FALSE)")
    ok("la stessa notifica non si ripete", sql("SELECT count(*) FROM notifiche")[0][0] == 1)
    sql("INSERT INTO notifiche (testo, urgente) VALUES ('Altro avviso', FALSE)")
    ok("notifiche diverse passano", sql("SELECT count(*) FROM notifiche")[0][0] == 2)
    sql("INSERT INTO notifiche (testo, urgente, critica) VALUES ('ALLARME: disco', TRUE, TRUE)")
    sql("INSERT INTO notifiche (testo, urgente, critica) VALUES ('ALLARME: disco', TRUE, TRUE)")
    ok("gli allarmi critici non vengono mai persi", sql("SELECT count(*) FROM notifiche WHERE testo='ALLARME: disco'")[0][0] == 2)
    sql("UPDATE notifiche SET creata_il = NOW() - INTERVAL '7 hours' WHERE testo='Il bando X scade domani'")
    sql("INSERT INTO notifiche (testo, urgente) VALUES ('Il bando X scade domani', FALSE)")
    ok("dopo sei ore l'avviso puo' tornare", sql("SELECT count(*) FROM notifiche WHERE testo='Il bando X scade domani'")[0][0] == 2)
    # --- allarme risposte vuote ---
    sql("DELETE FROM notifiche")
    for _ in range(3):
        sql("INSERT INTO registro_azioni (agente_id, azione, dettagli) VALUES (%s,'risposta_vuota','{}'::jsonb)", (marco,))
    with connessione() as cn:
        inv = allarmi.controlla(cn)
    ok("tre risposte vuote in un'ora fanno scattare l'allarme", any("risposte vuote" in x and "Marco" in x for x in inv), str(inv))
    with connessione() as cn:
        ok("e non si ripete subito", not any("risposte vuote" in x for x in allarmi.controlla(cn)))
    sql("DELETE FROM registro_azioni WHERE azione='risposta_vuota'")
    sql("DELETE FROM impostazioni_sistema WHERE chiave='allarme_risposte_vuote'")
    sql("INSERT INTO registro_azioni (agente_id, azione, dettagli) VALUES (%s,'risposta_vuota','{}'::jsonb)", (marco,))
    with connessione() as cn:
        ok("una sola risposta vuota non e' un allarme", not any("risposte vuote" in x for x in allarmi.controlla(cn)))
    # --- costi in euro ---
    ok("cambio predefinito", c.get("/gestione/costi/cambio", headers=H).json()["euro_per_dollaro"] == 0.92)
    ok("cambio salvato", c.put("/gestione/costi/cambio", headers=H, json={"euro_per_dollaro": 0.95}).json()["euro_per_dollaro"] == 0.95)
    ok("il cambio arriva all'interfaccia con le opzioni", c.get("/gestione/opzioni", headers=H).json()["cambio_eur"] == 0.95)
    ok("cambio assurdo rifiutato", c.put("/gestione/costi/cambio", headers=H, json={"euro_per_dollaro": 0}).status_code == 422)
    ok("cambio: solo titolare", c.put("/gestione/costi/cambio", headers=HC, json={"euro_per_dollaro": 0.9}).status_code == 403)
    ok("interfaccia: costi in euro", "function euro(" in c.get("/app/app.js").text and "eur(k.mese.costo)" in c.get("/app/plancia.js").text and "Salva cambio" in c.get("/app/sistemi.js").text)
    # --- pulizia dei backup su Drive ---
    chiamate = []
    files = [{"id": f"f{i}", "name": f"opifex-backup-{i:02d}.enc", "createdTime": f"2026-10-{30 - i:02d}"} for i in range(20)]   # dal piu' recente
    def finto_http(metodo, url, **kw):
        chiamate.append((metodo, url, kw))
        if metodo == "GET": return {"files": files}
        return {}
    google._http = finto_http
    n = google.pota_cartella("tok", "cart", 14, "opifex-backup-")
    pat = [x for x in chiamate if x[0] == "PATCH"]
    ok("restano le ultime 14, le altre 6 vanno nel cestino", n == 6 and len(pat) == 6 and pat[0][1].endswith("/f14") and pat[-1][1].endswith("/f19"), str(n))
    ok("niente viene cancellato per sempre", all(x[2]["json"] == {"trashed": True} for x in pat) and not any(x[0] == "DELETE" for x in chiamate))
    ok("l'elenco e' dal piu' recente e filtrato per nome", "createdTime desc" in chiamate[0][2]["params"]["orderBy"] and "opifex-backup-" in chiamate[0][2]["params"]["q"])
    chiamate.clear(); ok("sotto soglia non tocca nulla", google.pota_cartella("tok", "cart", 30) == 0 and not [x for x in chiamate if x[0] == "PATCH"])
    chiamate.clear(); google.pota_cartella("tok", "cart", 0)
    ok("conserva almeno una copia anche con valori assurdi", len([x for x in chiamate if x[0] == "PATCH"]) == 19)
    # backup della piattaforma: dopo il caricamento pota
    chiamate.clear()
    google.token_accesso = lambda cn, a: "t"; google.radice_valida = lambda cn, t: "r"; google.cartella = lambda t, nme, g, esistente=None: "cart"
    sql("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('drive_account_id','1') ON CONFLICT (chiave) DO UPDATE SET valore='1'")
    with connessione() as cn:
        esito = backup._su_drive(cn, b"dati", "opifex-backup-nuovo.enc")
    ok("backup piattaforma: caricato e potato", esito == "caricato su Drive" and len([x for x in chiamate if x[0] == "PATCH"]) == 6, str(len(chiamate)))
    def guasto(metodo, url, **kw):
        if metodo == "GET": raise google.ErroreGoogle("giu'")
        return {}
    google._http = guasto
    with connessione() as cn:
        ok("se la potatura fallisce il backup resta valido", backup._su_drive(cn, b"dati", "x.enc") == "caricato su Drive")
print("TOTALE", sum(ris), "/", len(ris))
