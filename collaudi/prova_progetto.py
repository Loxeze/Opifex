import psycopg
from playwright.sync_api import sync_playwright
DSN = "postgresql://postgres@127.0.0.1:54329/agenti_test"
tok = open("pacchetto/ux_token.txt").read().strip()
R = []
def ok(n, c, d=""):
    R.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
def sql(q, p=None):
    with psycopg.connect(DSN, autocommit=True) as c:
        cur = c.execute(q, p); return cur.fetchall() if cur.description else None
mg = sql("SELECT id, nome FROM agenti WHERE livello='manager' AND attivo AND NOT COALESCE(sentinella,false) ORDER BY id LIMIT 1")[0]
op = sql("SELECT id FROM agenti WHERE superiore_id=%s AND attivo LIMIT 1", (mg[0],)) or [(mg[0],)]
op = op[0][0]
sql("DELETE FROM progetti WHERE nome='Masha'")
pr = sql("INSERT INTO progetti (nome, descrizione) VALUES ('Masha','Lancio del prodotto Masha') RETURNING id")[0][0]
t1 = sql("INSERT INTO task (titolo, stato, progetto_id, assegnato_agente_id, scadenza) VALUES ('Scheda cliente','in_corso',%s,%s,CURRENT_DATE + 2) RETURNING id", (pr, op))[0][0]
sql("INSERT INTO task (titolo, stato, progetto_id, assegnato_agente_id, scadenza, completata_il, creata_il) VALUES ('Brief','completata',%s,%s,CURRENT_DATE - 5, NOW() - interval '4 days', NOW() - interval '12 days')", (pr, op))
sql("INSERT INTO task (titolo, stato, progetto_id, scadenza, creata_il) VALUES ('Piano editoriale in ritardo','da_fare',%s,CURRENT_DATE - 3, NOW() - interval '9 days')", (pr,))
sql("INSERT INTO task (titolo, stato, progetto_id) VALUES ('Senza scadenza','da_fare',%s)", (pr,))
sql("INSERT INTO task_commenti (task_id, agente_id, testo) VALUES (%s,%s,%s)", (t1, op, "Scheda cliente Masha: " + "contenuto della scheda. " * 25))
d1 = sql("INSERT INTO documenti (nome, nome_file, caratteri, creato_da_agente_id) VALUES ('Analisi mercato','a.pdf',900,%s) RETURNING id", (op,))[0][0]
sql("INSERT INTO task_documenti (task_id, documento_id) VALUES (%s,%s)", (t1, d1))
sql("INSERT INTO milestone (progetto_id, titolo, scadenza) VALUES (%s,'Lancio',CURRENT_DATE + 10)", (pr,))
with sync_playwright() as p:
    b = p.chromium.launch()
    for nome, vp, touch in (("desktop", {"width": 1300, "height": 900}, False), ("telefono", {"width": 390, "height": 800}, True)):
        ctx = b.new_context(viewport=vp, service_workers="block", has_touch=touch, is_mobile=touch)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8765/app/")
        pg.evaluate("([t]) => sessionStorage.setItem('token', t)", [tok]); pg.reload(); pg.wait_for_timeout(2500)
        pg.evaluate("(i) => { stato.progettoAperto = i; stato.progettoTab = 'panoramica'; vai('progetto'); }", pr); pg.wait_for_timeout(2500)
        T = lambda: (pg.locator("main, #contenuto, .contenuto").first.inner_text() if pg.locator("main, #contenuto, .contenuto").count() else pg.inner_text("body")).lower()
        ok(f"[{nome}] schermata iniziale: contenuti prodotti, scadenze, attivita'", all(x.lower() in T() for x in ("materiale prodotto dagli agenti", "analisi mercato", "scheda cliente", "prossime scadenze", "attività recente")), str([x for x in ("materiale prodotto dagli agenti", "analisi mercato", "scheda cliente", "prossime scadenze", "attività recente") if x not in T()]))
        ok(f"[{nome}] indicatori in testa", pg.locator(".cr-kpi").count() == 5)
        ok(f"[{nome}] pulsante Avvia una riunione con loro", pg.get_by_role("button", name="Avvia una riunione con loro").count() >= 1)
        pg.locator(".cr-mat-carta", has_text="Scheda cliente").get_by_role("button", name="Leggi").click(); pg.wait_for_timeout(1200)
        ok(f"[{nome}] il contenuto si legge per intero", "contenuto della scheda" in pg.locator(".cr-mat-testo:not([hidden])").first.inner_text() if pg.locator(".cr-mat-testo:not([hidden])").count() else False)
        ok(f"[{nome}] vista Schede di default, divisa per genere", pg.locator(".cr-mat-carta").count() == 2 and "documenti (1)" in T() and "schede e relazioni degli agenti (1)" in T())
        pg.get_by_role("button", name="Elenco").click(); pg.wait_for_timeout(300)
        ok(f"[{nome}] vista Elenco: una riga per contenuto", pg.locator(".cr-el-riga").count() == 2 and pg.locator(".cr-mat-carta").count() == 0)
        pg.get_by_role("button", name="Leggi").first.click(); pg.wait_for_timeout(1200)
        ok(f"[{nome}] dall'elenco il contenuto si legge", pg.locator(".cr-el-riga .cr-mat-testo:not([hidden])").count() == 1)
        pg.reload(); pg.wait_for_timeout(2500)
        pg.evaluate("(i) => { stato.progettoAperto = i; stato.progettoTab = 'panoramica'; vai('progetto'); }", pr); pg.wait_for_timeout(2500)
        ok(f"[{nome}] la scelta della vista si ricorda", pg.locator(".cr-el-riga").count() == 2)
        pg.get_by_role("button", name="Schede").click(); pg.wait_for_timeout(300)
        ok(f"[{nome}] si torna alle Schede", pg.locator(".cr-mat-carta").count() == 2)
        pg.get_by_role("tab", name="Calendario").click(); pg.wait_for_timeout(500)
        ok(f"[{nome}] calendario con le scadenze", pg.locator(".cal-giorno").count() >= 28 and (pg.locator(".cal-chip").count() >= 1 or pg.locator(".cal-punti i").count() >= 1))
        pg.locator(".cal-giorno.oggi").click(); pg.wait_for_timeout(300)
        pg.get_by_role("button", name="Mese successivo").click(); pg.wait_for_timeout(300)
        ok(f"[{nome}] navigazione tra i mesi", pg.locator(".cal-giorno").count() >= 28)
        pg.get_by_role("tab", name="Gantt").click(); pg.wait_for_timeout(500)
        ok(f"[{nome}] Gantt con barre, milestone e oggi", pg.locator(".gantt-barra").count() == 4 and pg.locator(".gantt-rombo").count() == 1 and pg.locator(".gantt-oggi").count() == 1, str(pg.locator(".gantt-barra").count()))
        ok(f"[{nome}] barra in ritardo e barra senza scadenza distinte", pg.locator(".gantt-barra.ritardo").count() == 1 and pg.locator(".gantt-barra.stimata").count() >= 1)
        pg.get_by_role("tab", name="Task").click(); pg.wait_for_timeout(300)
        ok(f"[{nome}] tab Task con le colonne", "da fare" in T() and "in corso" in T())
        pg.get_by_role("tab", name="Squadra").click(); pg.wait_for_timeout(1500)
        ok(f"[{nome}] tab Squadra: manager, riunione e chi ci lavora", "manager di riferimento" in T() and "chi ci lavora" in T() and pg.get_by_role("button", name="Avvia una riunione con loro").count() >= 1, T()[:400])
        pg.get_by_role("tab", name="Scheda e milestone").click(); pg.wait_for_timeout(1500)
        ok(f"[{nome}] tab Scheda e milestone", "scheda del progetto" in T() and "lancio" in T(), T()[:400])
        ow = pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok(f"[{nome}] nessuno scroll orizzontale della pagina", ow <= 1, str(ow))
        pg.get_by_role("tab", name="Gantt").click(); pg.wait_for_timeout(400)
        ow = pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok(f"[{nome}] Gantt largo ma scorre dentro il suo riquadro", ow <= 1, str(ow))
        pg.screenshot(path=f"prova_progetto_{nome}.png", full_page=False)
        pg.get_by_role("tab", name="Panoramica").click(); pg.wait_for_timeout(500)
        pg.get_by_role("button", name="Avvia una riunione con loro").first.click(); pg.wait_for_timeout(3500)
        ok(f"[{nome}] la riunione si apre nella schermata della call", sql("SELECT count(*) FROM tavoli WHERE progetto_id=%s AND stato='in_corso'", (pr,))[0][0] >= 1 and pg.evaluate("() => stato.vista") == "chat" and pg.evaluate("() => stato.apriCall") is None)
        ok(f"[{nome}] nessun errore JS", not errs, str(errs[:2]))
        sql("UPDATE tavoli SET stato='conclusa' WHERE progetto_id=%s", (pr,))
        ctx.close()
    b.close()
print("TOTALE", sum(R), "/", len(R))
