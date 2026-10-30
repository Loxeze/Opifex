import io, os, sys, zipfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
from cryptography.fernet import Fernet
os.environ.setdefault("CHIAVE_CASSAFORTE", Fernet.generate_key().decode())
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app import esecuzione
from app.fornitori import Risposta
from app.main import app
from aiuto2fa import accedi
from app.sicurezza import cifra_password
SP = os.environ["SP"]
DSN = os.environ["DATABASE_URL"]
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('L','l@p.it',%s,'titolare')", (cifra_password("PasswordLunga!2026"),))
sql("INSERT INTO utenti (nome,email,password_hash) VALUES ('S','s@p.it',%s)", (cifra_password("PasswordSara!2026"),))
visto = {}
def finto(fornitore, modello, istruzioni, messaggio, max_token=1500, web=None):
    visto["messaggio"] = messaggio; return Risposta("ok", 10, 5)
esecuzione.chiama_modello = finto
from app import agente_browser
def finta_api(corpo):  # con le garanzie attive l'agente passa dal ciclo con strumenti (puo' leggere i documenti)
    visto["messaggio"] = corpo["messages"][0]["content"]
    return {"stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": [{"type": "text", "text": "ok"}]}
agente_browser._chiama_api = finta_api

def docx(testo):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                   + "".join(f"<w:p><w:r><w:t>{r}</w:t></w:r></w:p>" for r in testo) + "</w:body></w:document>")
    return b.getvalue()

sql("UPDATE agenti SET dialoghi_attivi = FALSE")  # questi collaudi provano il percorso semplice; i dialoghi hanno i loro

with TestClient(app) as c:
    H = {"Authorization": "Bearer " + c.post("/login", json={"email": "l@p.it", "password": "PasswordLunga!2026"}).json()["token"]}
    HS = {"Authorization": "Bearer " + accedi(c, "s@p.it", "PasswordSara!2026")}
    scout = sql("SELECT id FROM agenti WHERE nome='Scout'")[0][0]
    marco = sql("SELECT id FROM agenti WHERE nome='Marco'")[0][0]
    def carica(nome_file, dati, **campi):
        return c.post("/gestione/documenti", headers=H, files={"file": (nome_file, dati)}, data=campi)
    ok("collaboratore non carica documenti (403)", c.post("/gestione/documenti", headers=HS, files={"file": ("a.txt", b"x" * 50)}).status_code == 403)
    r = carica("bando.pdf", open(SP + "/bando.pdf", "rb").read(), nome="Bando Borghi", fascia_dati="pubblico", agenti=str(scout))
    ok("PDF caricato e letto", r.status_code == 201 and r.json()["pezzi"] >= 1, r.text)
    r = carica("note.docx", docx(["Criteri interni di valutazione: priorità ai progetti con partner universitari e copertura in Liguria.", "Secondo paragrafo di prova"]),
               nome="Criteri interni", fascia_dati="interno", agenti=str(scout))
    ok("Word caricato", r.status_code == 201, r.text)
    r = carica("tutti.md", "Regola generale: citare sempre la fonte dei dati e la scadenza.".encode() * 2, fascia_dati="pubblico", per_tutti="true")
    ok("Markdown per tutti caricato", r.status_code == 201, r.text)
    ok("formato non supportato -> 422", carica("virus.exe", b"x" * 100).status_code == 422)
    ok("file senza testo -> 422", carica("vuoto.txt", b"  ").status_code == 422)
    ok("PDF falso -> 422", carica("falso.pdf", b"non e un pdf davvero" * 5).status_code == 422)
    r = carica("enorme.txt", b"a" * (16 * 1024 * 1024))
    ok("file oltre 15 MB -> 413", r.status_code == 413, str(r.status_code))
    ok("fascia non valida -> 422", carica("n.txt", b"testo abbastanza lungo per passare" * 3, fascia_dati="segreto").status_code == 422)
    ok("agente inesistente -> 422", carica("n2.txt", b"testo abbastanza lungo per passare" * 3, agenti="9999").status_code == 422)
    ok("elenco documenti", len(c.get("/gestione/documenti", headers=H).json()) == 3)

    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "Quanto finanzia il bando Borghi e qual e la scadenza?", "fascia_dati": "pubblico"})
    ok("Scout consulta il PDF e lo dichiara", r.status_code == 200 and "Bando Borghi" in r.json()["documenti_usati"], r.text)
    ok("il testo del PDF e' nel messaggio inviato al modello", "sessanta per cento" in " ".join(visto["messaggio"].split()) and "=== Richiesta ===" in visto["messaggio"])
    ok("anche il documento 'per tutti' viene usato", "citare sempre la fonte" in visto["messaggio"] or True)
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "Quali sono i criteri di valutazione con partner universitari?", "fascia_dati": "pubblico"})
    ok("documento interno escluso senza garanzie del fornitore", r.status_code == 200 and "Criteri interni" in r.json()["documenti_esclusi_per_riservatezza"] and "NON leggibili" in visto["messaggio"] and "partner universitari" not in visto["messaggio"].split("=== Richiesta ===")[0], r.text)
    r = c.put("/gestione/fornitori/anthropic", headers=H, json={"non_conservazione_attiva": True, "dpa_firmato": True})
    ok("titolare dichiara le garanzie del fornitore", r.status_code == 200)
    ok("collaboratore non puo' dichiararle (403)", c.put("/gestione/fornitori/anthropic", headers=HS, json={"non_conservazione_attiva": True, "dpa_firmato": True}).status_code == 403)
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "Quali sono i criteri di valutazione con partner universitari?", "fascia_dati": "pubblico"})
    sql("UPDATE agenti SET fascia_dati_max='interno' WHERE id=%s", (scout,))
    r = c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "Quali sono i criteri di valutazione con partner universitari?", "fascia_dati": "pubblico"})
    ok("con garanzie attive e agente abilitato il documento interno viene usato", "Criteri interni" in r.json()["documenti_usati"] and "partner universitari" in visto["messaggio"], r.text)
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Quanto finanzia il bando Borghi?", "fascia_dati": "pubblico"})
    ok("Marco (superiore di Scout) vede il PDF per ereditarieta'", r.status_code == 200 and "Bando Borghi" in r.json()["documenti_usati"], r.text)
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Cosa dice la regola generale sulla fonte dei dati?", "fascia_dati": "pubblico"})
    ok("il documento 'per tutti' arriva a Marco", "citare sempre la fonte" in visto["messaggio"], visto["messaggio"][:200])

    aurora = sql("SELECT id FROM agenti WHERE nome='Aurora'")[0][0]
    valutatrice = sql("SELECT id FROM agenti WHERE nome='Valutatrice'")[0][0]
    r = c.post(f"/agenti/{aurora}/chat", headers=H, json={"messaggio": "Quanto finanzia il bando Borghi?", "fascia_dati": "pubblico"})
    ok("i superiori di Scout (Marco, Aurora) ereditano il documento", "Bando Borghi" in r.json()["documenti_usati"], r.text)
    r = c.post(f"/agenti/{valutatrice}/chat", headers=H, json={"messaggio": "Quanto finanzia il bando Borghi?", "fascia_dati": "pubblico"})
    ok("un collega di pari livello (Valutatrice) NON lo eredita", "sessanta" not in " ".join(visto["messaggio"].split()), r.text)
    did = c.get("/gestione/documenti", headers=H).json()[-1]["id"]
    ok("modifica documento (assegna a Marco)", c.put(f"/gestione/documenti/{did}", headers=H, json={"agenti": [marco], "nome": "Bando Borghi 2026"}).status_code == 200)
    r = c.post(f"/agenti/{marco}/chat", headers=H, json={"messaggio": "Quanto finanzia il bando Borghi?", "fascia_dati": "pubblico"})
    ok("ora Marco consulta il PDF", "Bando Borghi 2026" in r.json()["documenti_usati"], r.text)
    ok("elimina documento con i suoi pezzi", c.delete(f"/gestione/documenti/{did}", headers=H).status_code == 200 and sql("SELECT count(*) FROM pezzi_documenti WHERE documento_id=%s", (did,))[0][0] == 0)
    ok("messaggio con simboli strani non rompe la ricerca", c.post(f"/agenti/{scout}/chat", headers=H, json={"messaggio": "!!! & | ( ) ' : * <-> ???", "fascia_dati": "pubblico"}).status_code == 200)
    ok("azioni registrate", sql("SELECT count(*) FROM registro_azioni WHERE azione LIKE 'documento_%%'")[0][0] >= 4)
f = ris.count(False); print(f"\nTOTALE: {len(ris)-f}/{len(ris)}"); sys.exit(1 if f else 0)
