import os, sys
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
print("TOTALE", sum(ris), "/", len(ris))
