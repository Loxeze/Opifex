import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import agente_browser, esecuzione, dialoghi, strumenti_google, buffer, google
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
import json as _j, httpx
inviati = []
class Resp:
    def __init__(s, code, dati): s.status_code = code; s._d = dati; s.content = b"x"
    def json(s): return s._d
def finto_post(url, json=None, headers=None, timeout=None):
    inviati.append((url, json, headers))
    q = json["query"]
    if headers["Authorization"] != "Bearer CHIAVE-BUFFER-VALIDA": return Resp(401, {})
    if "organizations" in q: return Resp(200, {"data": {"account": {"organizations": [{"id": "org1", "name": "Logos"}]}}})
    if "channels(" in q: return Resp(200, {"data": {"channels": [{"id": "ch-ig", "name": "renovatio_it", "service": "instagram"}, {"id": "ch-li", "name": "Renovatio", "service": "linkedin"}]}})
    if "createPost" in q:
        if "FALLISCI" in q: return Resp(200, {"data": {"createPost": {"message": "Failed to fetch image dimensions: Not Found"}}})
        return Resp(200, {"data": {"createPost": {"post": {"id": "bp1"}}}})
    return Resp(200, {"data": {}})
buffer.httpx.post = finto_post
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    scout = ID("Scout")
    ok("prima del collegamento: non collegato", c.get("/gestione/social/buffer", headers=H).json()["collegato"] is False)
    r = c.put("/gestione/social/buffer", headers=H, json={"chiave": "CHIAVE-SBAGLIATA-xx"})
    ok("chiave rifiutata da Buffer: errore chiaro e nulla resta salvato", r.status_code == 409 and "rifiutato la chiave" in r.json()["detail"] and c.get("/gestione/social/buffer", headers=H).json()["collegato"] is False, r.text)
    r = c.put("/gestione/social/buffer", headers=H, json={"chiave": "CHIAVE-BUFFER-VALIDA"})
    ok("chiave valida: collegato e canali elencati", r.status_code == 200 and [x["service"] for x in r.json()["canali"]] == ["instagram", "linkedin"], r.text)
    ok("la chiave e' cifrata nel database e non viene mai restituita", "CHIAVE-BUFFER-VALIDA" not in sql("SELECT valore FROM impostazioni_sistema WHERE chiave='buffer_chiave_cifrata'")[0][0]
       and "CHIAVE-BUFFER" not in c.get("/gestione/social/buffer", headers=H).text)
    ok("l'interfaccia dice 'solo titolare' per il collegamento (collaboratore 403)", c.put("/gestione/social/buffer", headers={"Authorization": "Bearer x"}, json={"chiave": "CHIAVE-BUFFER-VALIDA"}).status_code in (401, 403))
    # --- l'agente prepara, non pubblica
    ok("accendo il permesso social su Scout", c.put(f"/gestione/agenti/{scout}", headers=H, json={"social_attivo": True}).status_code == 200)
    copione[:] = [chiama("social_elenca_canali", {}, "a"),
                  chiama("social_prepara_post", {"canale_id": "ch-ig", "testo": "Nuovo bando Borghi: scopri come candidarti.", "quando": "2030-11-05T10:30:00+01:00",
                                                 "media": [{"tipo": "image", "url": "https://esempio.it/foto.jpg"}]}, "b"),
                  chiama("social_prepara_post", {"canale_id": "inesistente", "testo": "x"}, "c"),
                  chiama("social_prepara_post", {"canale_id": "ch-li", "testo": "y", "media": [{"tipo": "image", "url": "http://non-sicuro.it/a.jpg"}]}, "d"), fine("Preparato.")]
    ricevuti.clear(); inviati.clear()
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "prepara un post per Instagram", "fascia_dati": "interno"})
    nomi = [t["name"] for t in ricevuti[0]["tools"]]
    ok("l'agente ha solo strumenti per preparare (nessuna pubblicazione diretta)", {"social_elenca_canali", "social_prepara_post"} <= set(nomi) and not any("pubblica" in n or "invia" in n for n in nomi), str(nomi))
    ok("il post e' in coda 'da approvare' e NON e' stato inviato a Buffer", sql("SELECT stato FROM post_social")[0][0] == "da_approvare" and not any("createPost" in b["query"] for _, b, _ in inviati))
    ok("canale inesistente e media non https vengono rifiutati", sql("SELECT count(*) FROM post_social")[0][0] == 1)
    ok("l'utente riceve una notifica", sql("SELECT count(*) FROM notifiche WHERE testo LIKE '%da approvare%'")[0][0] == 1)
    lista = c.get("/gestione/social/post", headers=H).json()
    pid = lista[0]["id"]
    ok("la coda mostra agente, canale e orario", lista[0]["agente"] == "Scout" and lista[0]["servizio"] == "instagram" and lista[0]["programmato_il"])
    # --- approvazione
    inviati.clear()
    ok("modifico il testo prima di approvare", c.put(f"/gestione/social/post/{pid}", headers=H, json={"testo": "Testo corretto da Lorenzo"}).status_code == 200)
    r = c.post(f"/gestione/social/post/{pid}/decisione", headers=H, json={"azione": "approva"})
    q = [b["query"] for _, b, _ in inviati if "createPost" in b["query"]]
    ok("approvato: inviato a Buffer con testo corretto, canale, orario preciso (UTC) e immagine", r.status_code == 200 and len(q) == 1 and "Testo corretto da Lorenzo" in q[0]
       and 'channelId: "ch-ig"' in q[0] and "customScheduled" in q[0] and '2030-11-05T09:30:00.000Z' in q[0] and '{ image: { url: "https://esempio.it/foto.jpg" } }' in q[0], q[0] if q else r.text)
    ok("il post risulta inviato con l'id di Buffer", sql("SELECT stato, buffer_post_id FROM post_social WHERE id=%s", (pid,))[0] == ("inviato", "bp1"))
    ok("non si invia due volte (409)", c.post(f"/gestione/social/post/{pid}/decisione", headers=H, json={"azione": "approva"}).status_code == 409 and len([1 for _, b, _ in inviati if "createPost" in b["query"]]) == 1)
    ok("l'approvazione e' nel registro azioni", sql("SELECT count(*) FROM registro_azioni WHERE azione='post_social_approvato'")[0][0] == 1)
    # --- iniezione nel testo
    sql("INSERT INTO post_social (agente_id, canale_id, canale_nome, servizio, testo) VALUES (%s,'ch-li','Renovatio','linkedin',%s)", (scout, 'Ciao " } ) { x } mutation { deletePost(id: "1") { x } } #'))
    pid2 = sql("SELECT max(id) FROM post_social")[0][0]
    inviati.clear()
    c.post(f"/gestione/social/post/{pid2}/decisione", headers=H, json={"azione": "approva"})
    q = [b["query"] for _, b, _ in inviati if "createPost" in b["query"]][0]
    letto, _ = _j.JSONDecoder().raw_decode(q[q.index("text: ") + 6:])
    ok("un testo con virgolette e comandi GraphQL resta dentro la stringa (nessuna iniezione)", letto == 'Ciao " } ) { x } mutation { deletePost(id: "1") { x } } #', q)
    # --- coda senza orario, orario passato, errore, rifiuto
    sql("INSERT INTO post_social (agente_id, canale_id, canale_nome, servizio, testo) VALUES (%s,'ch-li','Renovatio','linkedin','Senza orario')", (scout,))
    p3 = sql("SELECT max(id) FROM post_social")[0][0]; inviati.clear()
    c.post(f"/gestione/social/post/{p3}/decisione", headers=H, json={"azione": "approva"})
    ok("senza orario va nella coda di Buffer (addToQueue)", "addToQueue" in [b["query"] for _, b, _ in inviati if "createPost" in b["query"]][0])
    sql("INSERT INTO post_social (agente_id, canale_id, canale_nome, servizio, testo, programmato_il) VALUES (%s,'ch-li','Renovatio','linkedin','Vecchio', NOW() - interval '1 day')", (scout,))
    p4 = sql("SELECT max(id) FROM post_social")[0][0]
    ok("orario gia' passato: non si approva (422)", c.post(f"/gestione/social/post/{p4}/decisione", headers=H, json={"azione": "approva"}).status_code == 422)
    sql("INSERT INTO post_social (agente_id, canale_id, canale_nome, servizio, testo) VALUES (%s,'ch-li','Renovatio','linkedin','FALLISCI')", (scout,))
    p5 = sql("SELECT max(id) FROM post_social")[0][0]
    r = c.post(f"/gestione/social/post/{p5}/decisione", headers=H, json={"azione": "approva"})
    ok("errore di Buffer: il post resta modificabile in stato 'errore' con il motivo", r.status_code == 409 and sql("SELECT stato FROM post_social WHERE id=%s", (p5,))[0][0] == "errore" and "Not Found" in sql("SELECT errore FROM post_social WHERE id=%s", (p5,))[0][0])
    ok("rifiuto un post", c.post(f"/gestione/social/post/{p4}/decisione", headers=H, json={"azione": "rifiuta", "nota": "fuori tema"}).json()["stato"] == "rifiutato")
    ok("scollego Buffer: gli strumenti spariscono", c.delete("/gestione/social/buffer", headers=H).status_code == 200 and c.get("/gestione/social/buffer", headers=H).json()["collegato"] is False)
    ricevuti.clear(); copione[:] = [fine("ok")]
    c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "ciao", "fascia_dati": "interno"})
    ok("senza Buffer l'agente non ha strumenti social", not ricevuti or not any(t["name"].startswith("social_") for t in ricevuti[0].get("tools", [])))
    ok("registro decisioni: post approvato e rifiutato registrati", sql("SELECT count(*) FROM registro_decisioni WHERE tipo='post_social' AND utente_nome='L'")[0][0] >= 2)
print(f"TOTALE {sum(ris)}/{len(ris)}")
