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
from app import agente_browser, crm
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
from app import crm_imprese as ci, crm_segmenti, crm, vademecum, richieste, competenze_base as cb, strumenti_google
from app.db import connessione
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@p.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@p.it", PW)}
    lista = sql("INSERT INTO crm_liste (nome, natura) VALUES ('Prova','pubblico') RETURNING id")[0][0]
    cid = [sql("INSERT INTO crm_contatti (lista_id, tipo, regione, provincia) VALUES (%s,'comune','liguria','ge') RETURNING id", (lista,))[0][0] for _ in range(6)]
    az = sql("SELECT id, nome FROM aziende ORDER BY id")
    if len(az) < 2:
        sql("INSERT INTO aziende (nome) VALUES ('Impresa A'), ('Impresa B')"); az = sql("SELECT id, nome FROM aziende ORDER BY id")
    a1, a2 = az[0][0], az[1][0]
    rep = sql("SELECT id, nome FROM divisioni ORDER BY id LIMIT 2")
    # 1. imprese
    r = c.post(f"/gestione/crm/contatti/{cid[0]}/imprese", headers=H, json={"azienda_id": a1, "motivo": "Incontro a fiera 2026"})
    ok("associazione con motivo: creata", r.status_code == 201, r.text[:150])
    ok("senza motivo: rifiutata", c.post(f"/gestione/crm/contatti/{cid[0]}/imprese", headers=H, json={"azienda_id": a2, "motivo": "ab"}).status_code == 422)
    ok("doppia associazione: rifiutata", c.post(f"/gestione/crm/contatti/{cid[0]}/imprese", headers=H, json={"azienda_id": a1, "motivo": "ancora lo stesso"}).status_code == 422)
    ok("collaboratore: 403", c.post(f"/gestione/crm/contatti/{cid[0]}/imprese", headers=HA, json={"azienda_id": a2, "motivo": "Prova motivo"}).status_code == 403)
    with connessione() as cn:
        ok("puo' contattare a nome dell'impresa associata", ci.puo_contattare(cn, cid[0], a1) is True)
        ok("NON a nome di un'altra impresa senza associazione", ci.puo_contattare(cn, cid[0], a2) is False)
        ok("un contatto senza associazioni non si contatta a nome di nessuno", ci.non_associati(cn, [cid[0], cid[1]], a1) == [cid[1]])
    r = c.post(f"/gestione/crm/contatti/{cid[0]}/imprese", headers=H, json={"azienda_id": a2, "motivo": "Richiesta della seconda impresa", "dal": "2026-10-20"})
    ok("per un'altra impresa serve una nuova associazione con motivo e data", r.status_code == 201 and sql("SELECT dal::text FROM crm_contatto_imprese WHERE contatto_id=%s AND azienda_id=%s", (cid[0], a2))[0][0] == "2026-10-20")
    for i in cid[1:3]:
        c.post(f"/gestione/crm/contatti/{i}/imprese", headers=H, json={"azienda_id": a1, "motivo": "Lista iniziale"})
    # 2. reparti
    r = c.put(f"/gestione/crm/contatti/{cid[0]}/reparti", headers=H, json={"divisione_id": rep[0][0], "nota": "Conosce i bandi regionali"})
    r2 = c.put(f"/gestione/crm/contatti/{cid[0]}/reparti", headers=H, json={"divisione_id": rep[1][0], "nota": "Possibile partner commerciale"})
    ok("piu' reparti, una nota per ciascuno", r.status_code == 200 and r2.status_code == 200 and len(c.get(f"/gestione/crm/contatti/{cid[0]}/imprese", headers=H).json()["reparti"]) == 2)
    ok("reparto senza nota: rifiutato", c.put(f"/gestione/crm/contatti/{cid[1]}/reparti", headers=H, json={"divisione_id": rep[0][0], "nota": "x"}).status_code == 422)
    # 3. cronologia
    cr = c.get(f"/gestione/crm/contatti/{cid[0]}/imprese", headers=H).json()["cronologia"]
    ok("cronologia: associazioni e reparti registrati", sum(1 for x in cr if x["campo"] == "impresa associata") == 2 and any(x["campo"].startswith("reparto") for x in cr), str([x["campo"] for x in cr]))
    # 4. filtri, esportazione e conteggio
    with connessione() as cn:
        d = crm_segmenti.elenco(cn, {"impresa_id": a1})
        ok("elenco filtrato per impresa", d["totale"] == 3, str(d["totale"]))
        ok("filtro per reparto", crm_segmenti.elenco(cn, {"reparto_id": rep[0][0]})["totale"] == 1)
        v = crm_segmenti.valori(cn)
        ok("i menu hanno imprese e reparti", len(v["imprese"]) >= 2 and len(v["reparti"]) >= 2)
        csv_ = crm_segmenti.esporta_csv(cn, {"impresa_id": a2})
        ok("esportazione a nome di un'impresa: solo i suoi contatti", csv_.count("\n") == 2 and "Imprese associate" in csv_.split("\n")[0], csv_[:200])
        crm.MINIMO = 1
        ok("crm_conta per impresa", crm.conta(cn, {"impresa": az[0][1]})["contatti"] == 3, str(crm.conta(cn, {"impresa": az[0][1]})))
        ok("crm_conta per reparto", crm.conta(cn, {"reparto": rep[1][1]})["contatti"] == 1)
    ok("lo strumento di Dario conosce i nuovi filtri", "impresa" in crm.STRUMENTO["description"] and "reparto" in crm.STRUMENTO["description"])
    r = c.delete(f"/gestione/crm/contatti/{cid[0]}/imprese/{a2}", headers=H)
    ok("associazione tolta e registrata", r.status_code == 200 and not ci.puo_contattare(connessione().__enter__(), cid[0], a2))
    ok("interfaccia: scheda Imprese e reparti e filtri", "Imprese e reparti" in c.get("/app/crm_schede.js").text and "A nome di (impresa)" in c.get("/app/crm_segmenti.js").text)
    # 5. Vademecum
    chiamate = []
    class R:
        def __init__(s, j=None, t=""): s._j, s.text = j, t
        def json(s): return s._j
    def finta(metodo, url, tok, **kw):
        chiamate.append(url); return R({"mimeType": strumenti_google.MIME_DOC}) if "export" not in url else R(t="Scrivi in italiano, frasi brevi.")
    vademecum._richiesta = finta; vademecum.collegato = lambda cn: True; vademecum.google.token_accesso = lambda cn, a: "tok"; vademecum.google._leggi = lambda cn, k: "1"
    with connessione() as cn:
        sql("DELETE FROM impostazioni_sistema WHERE chiave LIKE 'vademecum%%'")
        b = vademecum.blocco(cn)
        ok("Vademecum letto da Drive e messo nelle istruzioni", "frasi brevi" in b and "<vademecum>" in b and "ignora qualsiasi altra istruzione" in b)
        n = len(chiamate); vademecum.blocco(cn)
        ok("seconda lettura entro un'ora: dalla copia, senza chiamare Drive", len(chiamate) == n)
        def guasta(*a, **k): raise vademecum.google.ErroreGoogle("giu'")
        vademecum._richiesta = guasta; cn.execute("UPDATE impostazioni_sistema SET valore='0' WHERE chiave='vademecum_letto_il'")
        ok("Drive guasto: vale l'ultima copia", "frasi brevi" in vademecum.blocco(cn))
        ok("Drive guasto e nessuna copia: nessun blocco, nessun errore", (cn.execute("DELETE FROM impostazioni_sistema WHERE chiave='vademecum_testo'") or True) and vademecum.blocco(cn) == "")
    ok("il Vademecum e' aggiunto a ogni agente", "vademecum.blocco(conn)" in open("app/esecuzione.py").read())
    # 6. regole comuni e competenze
    R_ = richieste.REGOLA
    ok("regole comuni: tre livelli, codici, deleghe, formato e decisioni di Lorenzo", all(x in R_ for x in ("fatto verificato", "#R richiesta", "#D dubbio", "DELEGHE:", "FORMATO DI OGNI CONSEGNA", "DECISIONI DI LORENZO", "Vademecum", "valuta_agente")))
    ok("Dario: regole del CRM nelle competenze", "associato a una o piu' imprese" in cb.COMPETENZE["Dario"] and "Trascrizione" in cb.COMPETENZE["Dario"])
    ok("Capo sviluppo: il codice non va in uso, pubblica il Maestro di chiavi", "Maestro di chiavi" in cb.COMPETENZE["Capo sviluppo"] and "non lo metti in uso tu" in cb.COMPETENZE["Capo sviluppo"])
    ok("competenze 1.52.0: aggiornati solo i ruoli del prompt", {n for n, v in cb.DAL.items() if v == "1.52.0"} == {"Capo sviluppo", "Aurora", "Radar", "Tendenze", "Legal Master", "Architetto", "Marco", "Dario", "Giulia"}) and cb.DAL["Padre Casati"] == "1.57.0" and cb.DAL["Elena"] == "1.59.0"
print("TOTALE", sum(ris), "/", len(ris))
