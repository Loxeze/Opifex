import os, sys, json
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
from app import agente_browser, crm, strumenti_gmail, webauthn, chat_coda
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@p.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@p.it',%s,'collaboratore')", (cifra_password(PW),))
sql("UPDATE agenti SET dialoghi_attivi=FALSE"); sql("UPDATE fornitori_ai SET non_conservazione_attiva=TRUE, dpa_firmato=TRUE, fascia_dati_max='riservato'"); sql("UPDATE agenti SET fascia_dati_max='riservato'")
import hashlib, struct, time, base64
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.primitives import hashes
b64u = webauthn.b64u

def cbor_enc(v):
    def testa(t, n):
        if n < 24: return bytes([t << 5 | n])
        if n < 256: return bytes([t << 5 | 24, n])
        return bytes([t << 5 | 25]) + n.to_bytes(2, "big")
    if isinstance(v, bool): return b"\xf5" if v else b"\xf4"
    if isinstance(v, int): return testa(0, v) if v >= 0 else testa(1, -1 - v)
    if isinstance(v, bytes): return testa(2, len(v)) + v
    if isinstance(v, str): return testa(3, len(v.encode())) + v.encode()
    if isinstance(v, dict): return testa(5, len(v)) + b"".join(cbor_enc(k) + cbor_enc(x) for k, x in v.items())
    if isinstance(v, list): return testa(4, len(v)) + b"".join(cbor_enc(x) for x in v)

class Autenticatore:
    def __init__(self, alg=-7, rp="testserver", origine="http://testserver"):
        self.alg, self.rp, self.origine, self.contatore = alg, rp, origine, 0
        self.cred = os.urandom(32)
        if alg == -7:
            self.k = ec.generate_private_key(ec.SECP256R1()); n = self.k.public_key().public_numbers()
            self.cose = {1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")}
        else:
            self.k = rsa.generate_private_key(65537, 2048); n = self.k.public_key().public_numbers()
            self.cose = {1: 3, 3: -257, -1: n.n.to_bytes(256, "big"), -2: n.e.to_bytes(3, "big")}
    def _auth(self, flag, con, con_cred):
        a = hashlib.sha256(self.rp.encode()).digest() + bytes([flag]) + struct.pack(">I", con)
        if con_cred: a += b"\x00" * 16 + struct.pack(">H", len(self.cred)) + self.cred + cbor_enc(self.cose)
        return a
    def registra(self, sfida, flag=0x45, tipo="webauthn.create", origine=None, challenge=None):
        cd = json.dumps({"type": tipo, "challenge": challenge or sfida, "origin": origine or self.origine}).encode()
        att = cbor_enc({"fmt": "none", "attStmt": {}, "authData": self._auth(flag, 0, True)})
        return {"sfida": sfida, "client_data_json": b64u(cd), "attestation_object": b64u(att)}
    def accedi(self, sfida, flag=0x05, avanza=True, firma_errata=False, origine=None):
        if avanza: self.contatore += 1
        cd = json.dumps({"type": "webauthn.get", "challenge": sfida, "origin": origine or self.origine}).encode()
        auth = self._auth(flag, self.contatore, False)
        dati = auth + hashlib.sha256(cd).digest()
        firma = self.k.sign(dati, ec.ECDSA(hashes.SHA256())) if self.alg == -7 else self.k.sign(dati, padding.PKCS1v15(), hashes.SHA256())
        if firma_errata: firma = bytes([firma[0] ^ 1]) + firma[1:]
        return {"sfida": sfida, "credenziale_id": b64u(self.cred), "client_data_json": b64u(cd), "authenticator_data": b64u(auth), "firma": b64u(firma)}

with TestClient(app) as c:
    tok = accedi(c, "l@p.it", PW); H = {"Authorization": "Bearer " + tok}
    tokA = accedi(c, "anna@p.it", PW); HA = {"Authorization": "Bearer " + tokA}
    ok("senza accesso /v1/me e' 401", c.get("/v1/me").status_code == 401)
    ok("/v1/me", c.get("/v1/me", headers=H).json()["nome"] == "Lorenzo")

    # ---- passkey ----
    a = Autenticatore()
    o = c.post("/v1/passkey/registra/opzioni", headers=H).json()
    ok("opzioni: dominio e verifica utente obbligatoria", o["publicKey"]["rp"]["id"] == "testserver" and o["publicKey"]["authenticatorSelection"]["userVerification"] == "required")
    ok("registrazione con sfida errata rifiutata", c.post("/v1/passkey/registra", headers=H, json={**a.registra(o["sfida"], challenge="altra"), "nome": "x"}).status_code == 422)
    o = c.post("/v1/passkey/registra/opzioni", headers=H).json()
    ok("senza verifica utente rifiutata", c.post("/v1/passkey/registra", headers=H, json=a.registra(o["sfida"], flag=0x41)).status_code == 422)
    o = c.post("/v1/passkey/registra/opzioni", headers=H).json()
    ok("origine sbagliata rifiutata", c.post("/v1/passkey/registra", headers=H, json=a.registra(o["sfida"], origine="https://falso.it")).status_code == 422)
    o = c.post("/v1/passkey/registra/opzioni", headers=H).json()
    ok("sfida di un altro utente non vale", c.post("/v1/passkey/registra", headers=HA, json=a.registra(o["sfida"])).status_code == 401)
    o = c.post("/v1/passkey/registra/opzioni", headers=H).json()
    r = c.post("/v1/passkey/registra", headers=H, json={**a.registra(o["sfida"]), "nome": "Pixel di Lorenzo"})
    ok("registrazione riuscita", r.status_code == 201 and r.json()["nome"] == "Pixel di Lorenzo", r.text)
    ok("la sfida non si riusa", c.post("/v1/passkey/registra", headers=H, json=a.registra(o["sfida"])).status_code == 401)
    o = c.post("/v1/passkey/registra/opzioni", headers=H).json()
    ok("stessa credenziale: 409", c.post("/v1/passkey/registra", headers=H, json=a.registra(o["sfida"])).status_code == 409)
    ok("l'elenco non mostra la chiave", c.get("/v1/passkey", headers=H).json()[0].keys() == {"id", "nome", "creata_il", "ultimo_uso"})
    ok("registrazione scritta nel registro", sql("SELECT count(*) FROM registro_decisioni WHERE oggetto_tipo='passkey'")[0][0] == 1)

    # ---- accesso ----
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    r = c.post("/v1/accesso", json=a.accedi(s))
    ok("accesso con passkey", r.status_code == 200 and r.json()["nome"] == "Lorenzo", r.text)
    tp = r.json()["token"]
    ok("il token passkey vale come sessione", c.get("/v1/me", headers={"Authorization": "Bearer " + tp}).json()["nome"] == "Lorenzo")
    import jwt as _jwt
    d_tok = _jwt.decode(tp, options={"verify_signature": False})
    ok("token a durata breve (240 min)", 235 * 60 <= d_tok["exp"] - d_tok["iat"] <= 245 * 60, str(d_tok))
    ok("sfida non riusabile", c.post("/v1/accesso", json=a.accedi(s)).status_code == 401)
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    a.contatore = 1
    ok("contatore che non avanza (clone) rifiutato", c.post("/v1/accesso", json=a.accedi(s, avanza=False)).status_code == 401)
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    ok("firma alterata rifiutata", c.post("/v1/accesso", json=a.accedi(s, firma_errata=True)).status_code == 401)
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    ok("senza verifica utente rifiutato", c.post("/v1/accesso", json=a.accedi(s, flag=0x01)).status_code == 401)
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    ok("origine falsa rifiutata", c.post("/v1/accesso", json=a.accedi(s, origine="https://falso.it")).status_code == 401)
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    sql("DELETE FROM tentativi_accesso")
    ok("accesso valido dopo i rifiuti", c.post("/v1/accesso", json=a.accedi(s)).status_code == 200)
    sql("DELETE FROM tentativi_accesso")
    # RS256
    b = Autenticatore(alg=-257)
    o = c.post("/v1/passkey/registra/opzioni", headers=H).json()
    ok("registra RS256", c.post("/v1/passkey/registra", headers=H, json=b.registra(o["sfida"])).status_code == 201)
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    ok("accesso RS256", c.post("/v1/accesso", json=b.accedi(s)).status_code == 200)
    # utente disattivato
    sql("UPDATE utenti SET attivo=FALSE WHERE email='l@p.it'")
    s = c.post("/v1/accesso/opzioni").json()["sfida"]
    ok("utente disattivato non entra", c.post("/v1/accesso", json=a.accedi(s)).status_code == 401)
    sql("UPDATE utenti SET attivo=TRUE WHERE email='l@p.it'")
    pid = c.get("/v1/passkey", headers=H).json()[1]["id"]
    ok("tolta una passkey", c.delete(f"/v1/passkey/{pid}", headers=H).status_code == 200 and len(c.get("/v1/passkey", headers=H).json()) == 1)
    ok("non si toglie quella di altri", c.delete(f"/v1/passkey/{c.get('/v1/passkey', headers=H).json()[0]['id']}", headers=HA).status_code == 404)
    sql("DELETE FROM tentativi_accesso")
    for _ in range(6):
        s = c.post("/v1/accesso/opzioni").json()["sfida"]
        r = c.post("/v1/accesso", json=a.accedi(s, firma_errata=True))
    ok("troppi errori: blocco (429)", r.status_code == 429, str(r.status_code))
    sql("DELETE FROM tentativi_accesso")

    # ---- briefing, crm, task, agenti, ginnasio ----
    ok("briefing vuoto", c.get("/v1/briefing", headers=H).json()["briefing"] is None)
    bid = sql("INSERT INTO briefing (tipo, contenuto) VALUES ('mattina', %s) RETURNING id", ("# Buongiorno\n\n**Oggi** ci sono tre scadenze importanti sui bandi. " + "Dettaglio lungo. " * 60,))[0][0]
    r = c.get("/v1/briefing?tipo=mattina", headers=H).json()
    ok("briefing con sintesi breve e pulita", r["briefing"]["id"] == bid and len(r["sintesi"]) <= 530 and "#" not in r["sintesi"] and "*" not in r["sintesi"], r["sintesi"][:80])
    ok("briefing riservato al titolare", c.get("/v1/briefing", headers=HA).status_code == 403)
    ok("tipo briefing non valido", c.get("/v1/briefing?tipo=pranzo", headers=H).status_code == 422)
    lid = c.post("/gestione/crm/liste", headers=H, json={"nome": "Prova", "natura": "contatti"}).json()["id"] if False else None
    cid = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Prova','pubblico') RETURNING id")[0][0]
    from app import cassaforte
    cont = sql("INSERT INTO crm_contatti (lista_id, nome_cifrato, ente_cifrato, email_cifrata, tipo) VALUES (%s,%s,%s,%s,'comune') RETURNING id",
               (cid, cassaforte.cifra("Mario Rossi"), cassaforte.cifra("Comune di Genova"), cassaforte.cifra("m@ge.it")))[0][0]
    r = c.get("/v1/crm/cerca?q=genova", headers=H).json()
    ok("ricerca CRM con sintesi", len(r["risultati"]) == 1 and "Mario Rossi" in r["sintesi"], str(r))
    ok("CRM riservato al titolare", c.get("/v1/crm/cerca?q=genova", headers=HA).status_code == 403)
    uid = sql("SELECT id FROM utenti WHERE email='l@p.it'")[0][0]
    sql("INSERT INTO task (titolo, stato, priorita, scadenza, assegnato_utente_id) VALUES ('Consegnare il bando', 'da_fare', 'alta', CURRENT_DATE - 1, %s), ('Telefonare', 'da_fare', 'normale', CURRENT_DATE + 30, %s)", (uid, uid))
    r = c.get("/v1/task", headers=H).json()
    ok("task con sintesi e scadute", len(r["task"]) == 2 and "1 scadute" in r["sintesi"] and "Consegnare il bando" in r["sintesi"], r["sintesi"])
    ok("filtro entro giorni", len(c.get("/v1/task?entro_giorni=7", headers=H).json()["task"]) == 1)
    r = c.get("/v1/agenti", headers=H).json()
    ok("elenco manager", len(r["agenti"]) >= 1 and r["sintesi"].startswith("Ci sono"), str(r)[:200])
    r = c.get("/v1/ginnasio", headers=H).json()
    ok("Ginnasio riepilogo", "sintesi" in r and r["totale_in_coda"] == 0, str(r))

    # ---- note ----
    pr = sql("INSERT INTO progetti (nome) VALUES ('Progetto prova') RETURNING id")[0][0]
    r = c.post("/v1/note", headers=H, json={"testo": "Ricordare di chiamare il sindaco", "contatto_id": cont, "progetto_id": pr})
    ok("nota salvata", r.status_code == 201, r.text)
    ok("la nota compare nello storico del contatto, cifrata", sql("SELECT count(*) FROM crm_storico WHERE contatto_id=%s AND campo='nota_vocale' AND dopo_cifrato NOT LIKE '%%sindaco%%'", (cont,))[0][0] == 1)
    ok("elenco note per contatto", len(c.get(f"/v1/note?contatto_id={cont}", headers=H).json()["note"]) == 1)
    ok("nota su contatto inesistente: 404", c.post("/v1/note", headers=H, json={"testo": "x", "contatto_id": 99999}).status_code == 404)
    ok("collaboratore: nota su contatto vietata", c.post("/v1/note", headers=HA, json={"testo": "x", "contatto_id": cont}).status_code == 403)
    ok("collaboratore: nota semplice ok", c.post("/v1/note", headers=HA, json={"testo": "mia nota"}).status_code == 201)
    ok("collaboratore non vede le note altrui", len(c.get("/v1/note", headers=HA).json()["note"]) == 1)
    ok("nota vuota rifiutata", c.post("/v1/note", headers=H, json={"testo": ""}).status_code == 422)

    # ---- conferme: email ----
    inviati = []
    def finta(metodo, url, tok_, **kw):
        inviati.append((metodo, url, kw)); return {"id": "m1"}
    strumenti_gmail._richiesta = finta
    import app.assistente_v1 as v1
    v1.token_accesso = lambda conn, a_: "tok"
    P = {"azione": "email.invia", "parametri": {"a": "sindaco@ge.it", "oggetto": "Incontro", "testo": "Buongiorno, la contatto per fissare un incontro."}}
    ok("senza casella Gmail: 422 chiaro", c.post("/v1/conferme", headers=H, json=P).status_code == 422)
    ren = sql("INSERT INTO account_google (etichetta,email,refresh_token_cifrato,servizi) VALUES ('Renovatio Group','info@renovatio.it','x',ARRAY['gmail']) RETURNING id")[0][0]
    sql("INSERT INTO account_google (etichetta,email,refresh_token_cifrato,servizi) VALUES ('Xenia','x@x.it','x',ARRAY['gmail'])")
    r = c.post("/v1/conferme", headers=H, json=P)
    ok("passo 1: riepilogo e token, nulla inviato", r.status_code == 201 and "sindaco@ge.it" in r.json()["riepilogo"] and "info@renovatio.it" in r.json()["riepilogo"] and not inviati, r.text)
    t1 = r.json()["conferma_token"]
    ok("collaboratore non puo' confermare", c.post("/v1/conferme/esegui", headers=HA, json={"conferma_token": t1}).status_code == 403)
    ok("token sbagliato: 410", c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": "x" * 30}).status_code == 410)
    r = c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": t1})
    ok("passo 2: email inviata", r.status_code == 200 and len(inviati) == 1 and inviati[0][1].endswith("/messages/send"), r.text)
    raw = base64.urlsafe_b64decode(inviati[0][2]["json"]["raw"]).decode()
    ok("messaggio corretto", "To: sindaco@ge.it" in raw and "Subject: Incontro" in raw and "fissare un incontro" in raw)
    ok("il token non si riusa", c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": t1}).status_code == 410 and len(inviati) == 1)
    ok("invio scritto nel registro", sql("SELECT count(*) FROM registro_decisioni WHERE oggetto_tipo='email_voce'")[0][0] == 1)
    r = c.post("/v1/conferme", headers=H, json=P).json()
    ok("annullamento", c.post("/v1/conferme/annulla", headers=H, json={"conferma_token": r["conferma_token"]}).status_code == 200)
    ok("annullata: non si esegue", c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": r["conferma_token"]}).status_code == 410 and len(inviati) == 1)
    r = c.post("/v1/conferme", headers=H, json=P).json()
    sql("UPDATE conferme_vocali SET scade_il = NOW() - INTERVAL '1 minute' WHERE token_hash=%s", (hashlib.sha256(r["conferma_token"].encode()).hexdigest(),))
    ok("scaduta: non si esegue", c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": r["conferma_token"]}).status_code == 410 and len(inviati) == 1)
    for nome, p in [("indirizzo non valido", {"a": "non-email", "oggetto": "x", "testo": "y"}), ("destinatario con riga extra", {"a": "a@b.it\nBcc: spia@x.it", "oggetto": "x", "testo": "y"}),
                    ("sei destinatari", {"a": ",".join(f"a{i}@b.it" for i in range(6)), "oggetto": "x", "testo": "y"}), ("senza testo", {"a": "a@b.it", "oggetto": "x", "testo": ""})]:
        ok(nome + ": 422", c.post("/v1/conferme", headers=H, json={"azione": "email.invia", "parametri": p}).status_code == 422)
    r = c.post("/v1/conferme", headers=H, json={"azione": "email.invia", "parametri": {"a": "a@b.it", "oggetto": "Ciao\nBcc: spia@x.it", "testo": "y"}})
    ok("oggetto con a capo ripulito", r.status_code == 201 and "Bcc" in r.json()["riepilogo"] and "\n" not in r.json()["riepilogo"].split("oggetto:")[1].split(".")[0])
    c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": r.json()["conferma_token"]})
    ok("nessuna intestazione Bcc nel messaggio", "\nBcc:" not in base64.urlsafe_b64decode(inviati[-1][2]["json"]["raw"]).decode())
    # errore di Gmail: segnalato, token consumato
    def rotta(*a_, **k_): raise v1.ErroreGoogle("Gmail ha risposto 403")
    strumenti_gmail._richiesta = rotta
    r = c.post("/v1/conferme", headers=H, json=P).json()
    e = c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": r["conferma_token"]})
    ok("errore Gmail: 502 e nessun doppio invio", e.status_code == 502 and c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": r["conferma_token"]}).status_code == 410)
    ok("azione sconosciuta (avvio release) non esiste", c.post("/v1/conferme", headers=H, json={"azione": "release.avvia", "parametri": {}}).status_code == 422)

    # ---- conferme: task ----
    r = c.post("/v1/conferme", headers=H, json={"azione": "task.crea", "parametri": {"titolo": "Chiamare Rossi", "scadenza": "2026-11-05", "priorita": "alta"}})
    ok("task: riepilogo", r.status_code == 201 and "Chiamare Rossi" in r.json()["riepilogo"] and sql("SELECT count(*) FROM task WHERE titolo='Chiamare Rossi'")[0][0] == 0, r.text)
    e = c.post("/v1/conferme/esegui", headers=H, json={"conferma_token": r.json()["conferma_token"]})
    ok("task creata dopo la conferma", e.status_code == 200 and sql("SELECT assegnato_utente_id FROM task WHERE titolo='Chiamare Rossi'")[0][0] == uid, e.text)
    ok("task: data non valida", c.post("/v1/conferme", headers=H, json={"azione": "task.crea", "parametri": {"titolo": "x", "scadenza": "domani"}}).status_code == 422)

    # ---- messaggio a un manager ----
    nico = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]
    uso = lambda: {"input_tokens": 100, "output_tokens": 20}
    chat_coda.esegui_agente = lambda *a_, **k_: {"agente": "Marco", "risposta": "Ricevuto. Oggi preparo la bozza del bando con tre punti chiave."}
    _x = lambda corpo: {"stop_reason": "end_turn", "usage": uso(), "content": [{"type": "text", "text": "Ricevuto. Oggi preparo la bozza del bando con tre punti chiave."}]}
    sql("UPDATE agenti SET modello='claude-sonnet-5-5' WHERE id=%s", (nico,))
    r = c.post(f"/v1/agenti/{nico}/messaggio", headers=H, json={"messaggio": "Come procede il bando?"})
    ok("messaggio accodato", r.status_code == 202, r.text)
    mid = r.json()["messaggio_id"]
    for _ in range(50):
        q = c.get(f"/v1/agenti/messaggio/{mid}", headers=H).json()
        if q["risposta"] or q["errore"]: break
        time.sleep(0.2)
    ok("risposta con sintesi", q["risposta"] and "bozza del bando" in q["sintesi"], str(q))
    ok("messaggio altrui non visibile", c.get(f"/v1/agenti/messaggio/{mid}", headers=HA).status_code == 404)
    ok("agente inesistente: 404", c.post("/v1/agenti/99999/messaggio", headers=H, json={"messaggio": "x"}).status_code == 404)

    # ---- sintesi ----
    ok("sintesi taglia a fine frase", v1.sintesi("Questa e' la prima frase, abbastanza lunga da superare la meta' del limite. " + "Seconda frase molto lunga " * 30, 100).endswith("."))
    ok("sintesi toglie link e simboli", "http" not in v1.sintesi("Vedi https://x.it/abc **forte** `codice`"))

print("TOTALE", sum(ris), "/", len(ris))
sys.exit(0 if all(ris) else 1)
