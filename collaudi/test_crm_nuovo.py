import os, sys
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
from cryptography.fernet import Fernet
os.environ["CHIAVE_CASSAFORTE"] = Fernet.generate_key().decode()
sp = os.environ.get("SP", ".")
ris = []
def ok(n, c):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n)
L = lambda f: open(os.path.join("app/static", f)).read()
sch, crm, cru, seg, css = L("crm_schede.js"), L("crm.js"), L("crm_cruscotto.js"), L("crm_segmenti.js"), L("bottega.css")
ok("finestra Nuovo contatto definita, chiudibile con Esc e clic fuori", "function crmNuovoContatto" in sch and "Escape" in sch and "e.target === velo" in sch)
ok("testi inseriti come testo, non HTML", "innerHTML" not in sch[sch.index("function crmNuovoContatto"):sch.index("function crmSchede")])
ok("pulsante in testata CRM (tutte le schede)", "crmNuovoContatto()" in crm)
ok("pulsante nel cruscotto", "crmBottoneNuovoContatto()" in cru)
ok("pulsante nell'elenco contatti", "crmBottoneNuovoContatto()" in sch[sch.index("function crmSchede"):])
ok("dalla nuova opportunita': crea e seleziona il contatto", "+ Crea un nuovo contatto" in seg and "scelto = { id" in seg)
ok("stile della finestra", ".crm-modale" in css)
pl, cs_ = L("plancia.js"), L("crm_cruscotto.js")
ok("Plancia: progetti vinti (anno e totale) e costo di oggi con barre giornaliere", "Progetti vinti" in pl and "Costo di oggi" in pl and "graficoBarre(k.giorni" in pl)
ok("cruscotto CRM: progetti vinti da inizio anno", "Progetti vinti da inizio anno" in cs_)
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
sys.path.insert(0, os.getcwd())
import psycopg
from psycopg.rows import dict_row
from app import plancia, crm_dashboard
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True) as conn:
    cid = conn.execute("INSERT INTO crm_contatti (nome_cifrato) VALUES (NULL) RETURNING id").fetchone()["id"] if False else None
    o = plancia.crm(conn)["operazioni"]
    ok("API plancia: valori vinti presenti", all(k in o for k in ("valore_vinto_anno", "vinte_anno", "valore_vinto_totale", "vinte_totali")))
print("TOTALE", sum(ris), "/", len(ris))
