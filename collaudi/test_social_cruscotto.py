import os, sys, tempfile
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
os.environ["OPIFEX_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
import psycopg
from fastapi.testclient import TestClient
from app.main import app
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
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Lorenzo','l@s.it',%s,'titolare')", (cifra_password(PW),))
sql("INSERT INTO utenti (nome,email,password_hash,ruolo_globale) VALUES ('Anna','anna@s.it',%s,'collaboratore')", (cifra_password(PW),))
J = lambda f: open("app/static/" + f, encoding="utf-8").read()
soc = J("social.js")
ok("la panoramica apre con il cruscotto dei dati, prima del calendario", soc.index("cruscotto, h(\"h3\"") < soc.index('class: "cal"'))
ok("il cruscotto legge /panoramica e mostra interazioni, commenti, post", "social-nativo/panoramica" in soc and all(k in soc for k in ('"Interazioni"', '"Commenti"', '"Post pubblicati"', "Interazioni nel tempo", "Canali a confronto")))
with TestClient(app) as c:
    H = {"Authorization": "Bearer " + accedi(c, "l@s.it", PW)}; HA = {"Authorization": "Bearer " + accedi(c, "anna@s.it", PW)}
    v = c.get("/gestione/social-nativo/panoramica?giorni=7", headers=H).json()
    ok("senza canali: nessun canale e serie di 7 giorni a zero", v["canali"] == [] and len(v["serie"]) == 7 and v["ora"]["interazioni"] == 0 and v["seguaci"] is None)
    ok("la panoramica e' solo del titolare", c.get("/gestione/social-nativo/panoramica", headers=HA).status_code in (401, 403))
    a = sql("INSERT INTO account_social (provider, ext_id, nome) VALUES ('meta','a1','Meta') RETURNING id")[0][0]
    ig = sql("INSERT INTO canali_nativi (account_id, rete, ext_id, nome) VALUES (%s,'instagram','i1','Profilo IG') RETURNING id", (a,))[0][0]
    fb = sql("INSERT INTO canali_nativi (account_id, rete, ext_id, nome) VALUES (%s,'facebook','f1','Pagina FB') RETURNING id", (a,))[0][0]
    def post(canale, rete, testo, giorni_fa, mp, cm, vis):
        pid = sql("INSERT INTO post_social (canale_id, canale_nome, servizio, testo, stato, pubblicato_il, ext_post_id) VALUES (%s,%s,%s,%s,'pubblicato', NOW() - make_interval(days => %s), 'x') RETURNING id",
                  (f"n:{canale}", "c", rete, testo, giorni_fa))[0][0]
        sql("INSERT INTO metriche_post (post_id, mi_piace, commenti, visualizzazioni) VALUES (%s,%s,%s,%s)", (pid, mp, cm, vis))
    post(ig, "instagram", "ora1", 1, 40, 10, 1000)      # periodo corrente (7 gg)
    post(fb, "facebook", "ora2", 3, 20, 5, 500)
    post(ig, "instagram", "prima1", 10, 10, 0, 200)     # periodo precedente
    sql("INSERT INTO metriche_canale (canale_id, giorno, seguaci) VALUES (%s, CURRENT_DATE, 1200), (%s, CURRENT_DATE - 9, 1100)", (ig, ig))
    v = c.get("/gestione/social-nativo/panoramica?giorni=7", headers=H).json()
    ok("totali del periodo: 2 post, 75 interazioni, 15 commenti", v["ora"]["post"] == 2 and v["ora"]["interazioni"] == 75 and v["ora"]["commenti"] == 15 and v["ora"]["visualizzazioni"] == 1500, str(v["ora"]))
    ok("periodo precedente: 1 post, 10 interazioni", v["prima"]["post"] == 1 and v["prima"]["interazioni"] == 10, str(v["prima"]))
    ok("serie giornaliera: 7 giorni, somma interazioni = totale", len(v["serie"]) == 7 and sum(x["interazioni"] for x in v["serie"]) == 75 and sum(x["post"] for x in v["serie"]) == 2, str(v["serie"]))
    ig_r = next(x for x in v["canali"] if x["rete"] == "instagram")
    ok("per canale: interazioni, confronto col periodo prima, seguaci e variazione", ig_r["interazioni"] == 50 and ig_r["interazioni_prima"] == 10 and ig_r["post_prima"] == 1 and ig_r["seguaci"] == 1200 and ig_r["seguaci_variazione"] == 100, str(ig_r))
    ok("seguaci totali e post migliori ordinati", v["seguaci"] == 1200 and v["migliori"] and v["migliori"][0]["interazioni"] == 50, str(v["migliori"][:1]))
    v30 = c.get("/gestione/social-nativo/panoramica?giorni=30", headers=H).json()
    ok("a 30 giorni entrano anche i post piu' vecchi e la serie e' di 30 giorni", v30["ora"]["post"] == 3 and len(v30["serie"]) == 30)
print("TOTALE", sum(ris), "/", len(ris)); sys.exit(0 if all(ris) else 1)
