import os, sys
sys.path.insert(0, os.getcwd())
ris = []
def ok(n, c): ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n)
J = lambda f: open("app/static/" + f, encoding="utf-8").read()
soc, dash, app = J("social.js"), J("dashboard.js"), J("app.js")
ok("la pagina Social ha panoramica, scrivi, post, risultati", all(k in soc for k in ('["panoramica", "Panoramica"]', '["pubblica", "Scrivi e pubblica"]', '["post", "Post e approvazioni"]', '["risultati", "Risultati"]')))
ok("la pagina Social non ha piu' la scheda dei canali", '["canali", "Canali e collegamenti"]' not in soc)
ok("la pagina Social si apre sulla panoramica", 'apri(schedaSocial || "panoramica")' in soc)
ok("c'e' il calendario dei post", 'class: "cal"' in soc and ".cal{" in J("stile.css"))
ok("canali e collegamenti sono in Impostazioni > Social", "social: vistaSocialCanali" in dash and "function vistaSocialCanali" in soc)
ok("la pagina Social porta alle impostazioni dei canali", 'vai("impostazioni", "social")' in soc)
print("TOTALE", sum(ris), "/", len(ris)); sys.exit(0 if all(ris) else 1)
