import json, os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import esecuzione, telegram
from app.fornitori import Risposta
from app.main import app
from aiuto2fa import accedi
from app.sicurezza import cifra_password
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))
sql("UPDATE agenti SET dialoghi_attivi = FALSE")
sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE")

TOKEN = "123456789:AAFprovaTokenFintoDiProva_0123456789"
inviati, coda, chiamate = [], [], []
def finto_telegram(token, metodo, attesa_http=15, **p):
    chiamate.append((token, metodo, p))
    if metodo == "getMe": return {"username": "OpifexProvaBot"}
    if metodo == "getUpdates":
        ups = coda[:]; coda.clear(); return ups
    if metodo == "sendMessage": inviati.append((p["chat_id"], p["text"])); return {}
    return {}
telegram._chiama = finto_telegram
copia = []
def finto_esegui(agente_id, messaggio, fascia, utente_id=None):
    copia.append((agente_id, messaggio, fascia, utente_id)); return {"risposta": "Risposta di Aurora: ricevuto."}
telegram.esegui_agente = finto_esegui
n = [0]
def msg(chat, testo, tipo="private"):
    n[0] += 1; return {"update_id": 100 + n[0], "message": {"chat": {"id": chat, "type": tipo}, "text": testo}}
def ultimo(): return inviati[-1][1] if inviati else ""

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    ok("collaboratore: 403", c.get("/gestione/canali/telegram", headers=HS).status_code == 403)
    ok("stato iniziale: non configurato", c.get("/gestione/canali/telegram", headers=H).json()["configurato"] is False)
    ok("codice senza token -> 409", c.post("/gestione/canali/telegram/codice", headers=H).status_code == 409)
    ok("senza canale il giro non fa nulla", telegram.giro(1) is False)
    ok("token troppo corto -> 422", c.put("/gestione/canali/telegram/token", headers=H, json={"token": "abc"}).status_code == 422)
    r = c.put("/gestione/canali/telegram/token", headers=H, json={"token": TOKEN})
    ok("token salvato, bot riconosciuto", r.status_code == 200 and r.json()["bot"] == "OpifexProvaBot")
    s = c.get("/gestione/canali/telegram", headers=H).json()
    ok("il token non e' mai restituito", TOKEN not in json.dumps(s) and s["configurato"] and s["bot"] == "OpifexProvaBot" and not s["collegato"])
    ok("nel database il token e' cifrato", TOKEN not in sql("SELECT token_cifrato FROM canale_telegram")[0][0])

    # --- abbinamento
    coda.append(msg(555, "ciao, sono un estraneo")); telegram.giro(1)
    ok("estraneo non collegato: silenzio", inviati == [] and copia == [])
    coda.append(msg(555, "/start")); telegram.giro(1)
    ok("/start spiega come collegarsi", "/collega" in ultimo())
    coda.append(msg(555, "/collega SBAGLIATO")); telegram.giro(1)
    ok("senza codice generato: rifiutato", "non valido" in ultimo())
    codice = c.post("/gestione/canali/telegram/codice", headers=H).json()["codice"]
    ok("codice di 8 caratteri", len(codice) == 8)
    ok("il codice e' nel database solo come impronta", codice not in str(sql("SELECT * FROM canale_telegram")))
    coda.append(msg(555, "/collega XXXXXXXX")); telegram.giro(1)
    ok("codice errato -> rifiutato", "non valido" in ultimo() and sql("SELECT chat_id FROM canale_telegram")[0][0] is None)
    coda.append(msg(-100, "/collega " + codice, "group")); telegram.giro(1)
    ok("da un gruppo non ci si collega", sql("SELECT chat_id FROM canale_telegram")[0][0] is None)
    for _ in range(5): coda.append(msg(555, "/collega YYYYYYYY"))
    telegram.giro(1)
    coda.append(msg(555, "/collega " + codice)); telegram.giro(1)
    ok("dopo 5 tentativi sbagliati anche il codice giusto e' bloccato", sql("SELECT chat_id FROM canale_telegram")[0][0] is None)
    codice = c.post("/gestione/canali/telegram/codice", headers=H).json()["codice"]
    coda.append(msg(555, "/collega " + codice.lower())); telegram.giro(1)
    ok("codice giusto -> collegato (maiuscole/minuscole indifferenti)", sql("SELECT chat_id FROM canale_telegram")[0][0] == 555 and "Collegato" in ultimo())
    ok("il codice non e' piu' riutilizzabile", sql("SELECT codice_hash FROM canale_telegram")[0][0] is None)
    coda.append(msg(777, "/collega " + codice)); telegram.giro(1)
    ok("un'altra chat non puo' prendere il posto", sql("SELECT chat_id FROM canale_telegram")[0][0] == 555)

    # --- uso da parte di Lorenzo
    n_prima = len(inviati)
    coda.append(msg(777, "dimmi tutto")); telegram.giro(1)
    ok("chat non abbinata: nessuna risposta e nessuna chiamata all'AI", len(inviati) == n_prima and copia == [])
    coda.append(msg(555, "Aurora, come va oggi?")); telegram.giro(1)
    aur = sql("SELECT id FROM agenti WHERE nome='Aurora'")[0][0]; uid = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
    ok("il testo va ad Aurora con dati 'pubblico' e a nome del titolare", copia[-1] == (aur, "Aurora, come va oggi?", "pubblico", uid), str(copia))
    ok("la risposta di Aurora torna su Telegram", "Risposta di Aurora" in ultimo() and inviati[-1][0] == 555)
    coda.append(msg(555, "/fascia interno")); telegram.giro(1)
    ok("/fascia cambia il livello dei dati", sql("SELECT fascia_dati FROM canale_telegram")[0][0] == "interno")
    coda.append(msg(555, "/fascia segretissimo")); telegram.giro(1)
    ok("/fascia non valida: resta com'era", sql("SELECT fascia_dati FROM canale_telegram")[0][0] == "interno")
    coda.append(msg(555, "ancora una cosa")); telegram.giro(1)
    ok("la nuova fascia viene usata", copia[-1][2] == "interno")

    # --- richieste da Telegram
    sql("INSERT INTO richieste_informazioni (agente_id, domanda, bloccante) SELECT id,'Qual e il codice ATECO?',TRUE FROM agenti WHERE nome='Scout'")
    rid = sql("SELECT id FROM richieste_informazioni")[0][0]
    prima = len(copia)
    coda.append(msg(555, "/richieste")); telegram.giro(1)
    ok("/richieste elenca le domande (senza usare l'AI)", "ATECO" in ultimo() and "BLOCCANTE" in ultimo() and len(copia) == prima)
    coda.append(msg(555, f"/rispondi {rid} 62.01.00")); telegram.giro(1)
    ok("/rispondi registra la risposta", sql("SELECT stato, risposta FROM richieste_informazioni")[0] == ("risposta", "62.01.00"))
    coda.append(msg(555, "/rispondi 9999 x")); telegram.giro(1)
    ok("richiesta inesistente: messaggio chiaro", "non trovata" in ultimo())
    coda.append(msg(555, "/rispondi")); telegram.giro(1)
    ok("uso errato: spiega come fare", "Uso:" in ultimo())
    coda.append(msg(555, "/stato")); telegram.giro(1)
    ok("/stato: riepilogo", "agenti attivi" in ultimo())
    coda.append(msg(555, "/briefing")); telegram.giro(1)
    ok("/briefing senza briefing salvati", "Nessun briefing" in ultimo())
    coda.append(msg(555, "/aiuto")); telegram.giro(1)
    ok("/aiuto", "/richieste" in ultimo())
    coda.append({"update_id": 999, "message": {"chat": {"id": 555, "type": "private"}, "voice": {"file_id": "x"}}}); telegram.giro(1)
    ok("messaggio vocale: spiega che per ora e' solo testo", "solo messaggi di testo" in ultimo())

    # --- notifiche in uscita
    sql("DELETE FROM notifiche")
    sql("INSERT INTO notifiche (testo, urgente) VALUES ('Scout e bloccato', TRUE), ('Briefing pronto', FALSE)")
    telegram.giro(1)
    testi = [t for _, t in inviati[-2:]]
    ok("le notifiche arrivano su Telegram (urgente marcata)", testi == ["URGENTE - Scout e bloccato", "Briefing pronto"], str(testi))
    ok("e non vengono rimandate", (telegram.giro(1), len([1 for _, t in inviati if "Briefing pronto" in t]))[1] == 1
       and sql("SELECT count(*) FROM notifiche WHERE inviata_il IS NULL")[0][0] == 0)
    ok("la prova manuale invia un messaggio", c.post("/gestione/canali/telegram/prova", headers=H).status_code == 200 and "prova" in ultimo())

    # --- il briefing genera una notifica
    from app.briefing import genera_briefing
    genera_briefing("mattina")
    ok("un briefing nuovo produce una notifica per Telegram", sql("SELECT count(*) FROM notifiche WHERE testo LIKE 'Briefing del mattino%%' AND inviata_il IS NULL")[0][0] == 1)

    # --- errori e pulizia
    def rotto(token, metodo, attesa_http=15, **p):
        raise telegram.ErroreTelegram("Telegram non raggiungibile (ConnectError)")
    telegram._chiama = rotto
    try: telegram.giro(1)
    except telegram.ErroreTelegram: pass
    s = c.get("/gestione/canali/telegram", headers=H).json()
    ok("errore di rete: registrato senza token", s["ultimo_errore"] and TOKEN not in json.dumps(s))
    telegram._chiama = finto_telegram
    ok("scollega", c.post("/gestione/canali/telegram/scollega", headers=H).status_code == 200 and not c.get("/gestione/canali/telegram", headers=H).json()["collegato"])
    ok("rimuovi il bot", c.delete("/gestione/canali/telegram", headers=H).status_code == 200 and not c.get("/gestione/canali/telegram", headers=H).json()["configurato"])
    ok("nessuna chiamata ha messo il token in un messaggio inviato", all(TOKEN not in t for _, t in inviati))
print(f"TOTALE: {sum(ris)}/{len(ris)} controlli superati")
