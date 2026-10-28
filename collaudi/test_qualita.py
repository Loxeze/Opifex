import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from unittest import mock
from app import qualita, revisione, squadre, fornitori, dialoghi, consegne, rotte_chat
from app.db import connessione
from app.main import app
from fastapi.testclient import TestClient
DSN = os.environ["DATABASE_URL"]; ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
with TestClient(app):
    # limiti tolti
    ok("dialoghi: tetto token largo", dialoghi.MAX_TOKEN_DIALOGO >= 16000)
    ok("chat: messaggi lunghissimi accettati", rotte_chat.MAX_BOZZA >= 1_000_000)
    ok("revisione: nessun tetto sulla bozza e limite giornaliero largo", not hasattr(revisione, "MAX_BOZZA") and revisione.MAX_AL_GIORNO >= 50)
    ok("revisione obbligatoria nel prompt", "REVISIONE OBBLIGATORIA" in revisione.AVVISO and "ogni consegna importante" in revisione.AVVISO)
    sql("UPDATE agenti SET max_token_risposta = 60000 WHERE nome = 'Aurora'")
    ok("limite token per agente fino a 64000", sql("SELECT max_token_risposta FROM agenti WHERE nome='Aurora'")[0][0] == 60000)
    # revisore condiviso
    with connessione() as cn:
        n = qualita.applica(cn); cn.commit(); n2 = qualita.applica(cn)
    rv = sql("SELECT id, modello, sforzo FROM agenti WHERE nome=%s", (qualita.NOME_REVISORE,))
    ok("Revisore qualita': Sonnet 5.5 sforzo medio", rv and rv[0][1] == "claude-sonnet-5-5" and rv[0][2] == "medium")
    ok("agenti senza controllore lo usano, seconda volta nulla", n >= 10 and n2 == 0 and sql("SELECT count(*) FROM agenti WHERE controllore_id=%s", (rv[0][0],))[0][0] == n)
    ok("il revisore non si auto-revisiona", sql("SELECT controllore_id FROM agenti WHERE id=%s", (rv[0][0],))[0][0] is None)
    ok("le sentinelle e gli speciali non hanno controllore", sql("SELECT count(*) FROM agenti WHERE controllore_id IS NOT NULL AND (sentinella OR ruolo_speciale IS NOT NULL)")[0][0] == 0)
    # sforzo
    visto = {}
    class R:
        status_code = 200
        text = ""
        headers = {}
        def json(self): return {}
    def finto(url, headers=None, json=None, timeout=0):
        visto.update(json); return R()
    with mock.patch.object(fornitori.httpx, "post", finto):
        tk = fornitori.SFORZO.set("medium")
        fornitori.invia("https://api.anthropic.com/v1/messages", {}, {"model": "x"})
        fornitori.SFORZO.reset(tk)
    ok("sforzo medio inviato all'API Anthropic", visto.get("output_config") == {"effort": "medium"}, str(visto))
    visto.clear()
    with mock.patch.object(fornitori.httpx, "post", finto):
        fornitori.invia("https://api.openai.com/v1/chat/completions", {}, {"model": "x"})
        fornitori.invia("https://api.anthropic.com/v1/messages", {}, {"model": "x"})
    ok("senza sforzo o con altri fornitori nulla viene aggiunto", "output_config" not in visto)
    chiamate = []
    class R400(R):
        status_code = 400
        text = "output_config.effort non supportato"
    def finto400(url, headers=None, json=None, timeout=0):
        chiamate.append("output_config" in json); return R400() if "output_config" in json else R()
    with mock.patch.object(fornitori.httpx, "post", finto400):
        tk = fornitori.SFORZO.set("medium")
        r = fornitori.invia("https://api.anthropic.com/v1/messages", {}, {"model": "x"})
        fornitori.SFORZO.reset(tk)
    ok("modello che rifiuta lo sforzo: si riprova senza", chiamate == [True, False] and r.status_code == 200, str(chiamate))
    # esempi eccellenti
    sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it','x','titolare')")
    mk = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]; sc = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
    sql("UPDATE agenti SET superiore_id=%s WHERE id=%s", (mk, sc))
    t = sql("INSERT INTO task (titolo, stato, assegnato_agente_id, creato_da_agente_id) VALUES ('Scheda bando X','da_fare',%s,%s) RETURNING id", (sc, mk))[0][0]
    lungo = "Esito: bando coerente. " + "Analisi dettagliata del requisito. " * 400
    sql("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,%s)", (t, sc, lungo))
    with connessione() as cn:
        msg = squadre.valuta(cn, mk, {"agente": "Scout", "voto": "su", "task_id": t}); cn.commit()
        b = qualita.blocco(cn, sc)
    ok("voto positivo: la consegna diventa esempio, senza tagli", sql("SELECT count(*) FROM esempi_eccellenti WHERE agente_id=%s AND length(testo)=%s", (sc, len(lungo)))[0][0] == 1)
    ok("l'esempio e' riletto prima di lavorare", "LAVORO ECCELLENTE" in b and "Scheda bando X" in b and len(b) > len(lungo))
    with connessione() as cn:
        squadre.valuta(cn, mk, {"agente": "Scout", "voto": "su", "task_id": t}); cn.commit()
    ok("nessun doppione per la stessa task", sql("SELECT count(*) FROM esempi_eccellenti WHERE agente_id=%s", (sc,))[0][0] == 1)
    # copertura
    with connessione() as cn:
        cop = qualita.copertura(cn, mk); o = squadre.organico(cn, mk)
    ok("copertura: chi ha ricevuto e chi no", cop["con_lavoro"] == 1 and cop["sottoposti"] >= 1 and "Ultimi 7 giorni" in o, str(cop))
    # API: sforzo dall'interfaccia e riepilogo
    from aiuto2fa import accedi
    from app.sicurezza import cifra_password
    sql("UPDATE utenti SET password_hash=%s WHERE email='l@p.it'", (cifra_password("PasswordLunga!2026"),))
    c = TestClient(app)
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", "PasswordLunga!2026")}
    r = c.put(f"/gestione/agenti/{sc}", headers=H, json={"sforzo": "medium", "max_token_risposta": 50000})
    ok("sforzo e tetto 50000 salvati da API", r.status_code == 200 and sql("SELECT sforzo, max_token_risposta FROM agenti WHERE id=%s", (sc,))[0] == ("medium", 50000), r.text[:150])
    c.put(f"/gestione/agenti/{sc}", headers=H, json={"sforzo": ""})
    ok("sforzo vuoto = predefinito", sql("SELECT sforzo FROM agenti WHERE id=%s", (sc,))[0][0] is None)
    ok("sforzo non valido rifiutato", c.put(f"/gestione/agenti/{sc}", headers=H, json={"sforzo": "ultra"}).status_code == 422)
    ok("istruzioni lunghe accettate", c.put(f"/gestione/agenti/{sc}", headers=H, json={"istruzioni": "x" * 50000}).status_code == 200)
    rp = c.get("/gestione/agenti-riepilogo", headers=H).json()["agenti"]
    ok("riepilogo espone esempi, revisioni e copertura", rp[str(sc)].get("esempi") == 1 and rp[str(mk)]["copertura"]["con_lavoro"] == 1, str(rp[str(mk)].get("copertura")))
    ok("interfaccia: sforzo nel form agente", "Sforzo di ragionamento" in c.get("/app/app.js").text and "esempi di lavoro eccellente" in c.get("/app/agenti_carte.js").text)
    from app import ginnasio
    with connessione() as cn:
        tutti = ginnasio.registro_testo(cn); uno = ginnasio.registro_testo(cn, "Marco"); no = ginnasio.registro_testo(cn, "Inesistente")
    ok("registro_competenze: tutti gli agenti con livelli e formazioni", "Registro competenze" in tutti and "formazioni:" in tutti and "Scout" in tutti)
    ok("registro di un manager: mostra i suoi sottoposti", "Scout" in uno and "Marco (" not in uno.split("\n", 1)[1].split("\n")[0] or "Scout" in uno)
    ok("registro: agente inesistente", no.startswith("ERRORE"))
    ok("strumento registrato per i manager", any(x["name"] == "registro_competenze" for x in ginnasio.STRUMENTI) and "registro_competenze" in ginnasio.AVVISO)
    from app import competenze_base as cb
    ok("Padre Casati sa che il registro e' il Ginnasio", "registro_competenze" in cb.COMPETENZE["Padre Casati"] and cb.DAL["Padre Casati"] == "1.57.0")
print("TOTALE", sum(ris), "/", len(ris))
