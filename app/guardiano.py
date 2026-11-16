"""Il guardiano (2.62): controlla che il lavoro PRODUCA risultati, non solo che qualcuno sia «al lavoro».

Per ogni lavoro (lo studio di Padre Casati, il filtro della posta, ogni agente, i commenti social, il modello locale) confronta cio' che
c'era da fare con cio' che e' stato fatto davvero, e da' un esito: «va» (verde), «attenzione» (giallo), «fermo» (rosso), con la causa
probabile e cosa fare. Un «fermo» che dura oltre un'ora diventa una notifica urgente (una volta ogni 6 ore per lo stesso problema)
e una riga nel diario. Lo stato si vede in cima alla Plancia: se qualcosa e' fermo, Lorenzo lo sa senza doverlo scoprire da solo.

Il guardiano non usa modelli: solo conteggi nel database."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/guardiano", tags=["guardiano"])
ORDINE = {"fermo": 0, "attenzione": 1, "va": 2}
DOPO = timedelta(hours=1)        # un fermo diventa notifica se dura almeno un'ora
ATTESA = timedelta(hours=6)      # e non si ripete prima di 6 ore


def _imp(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return r["valore"] if r and r["valore"] is not None else d


def _scrivi(conn, k, v):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))


def _esito(chiave, chi, cosa, stato, messaggio, fare="", vista="", numeri=None) -> dict:
    return {"chiave": chiave, "chi": chi, "cosa": cosa, "stato": stato, "messaggio": messaggio, "fare": fare, "vista": vista, "numeri": numeri or {}}


def _quando(dt) -> str:
    if not dt:
        return "mai"
    s = (datetime.now(timezone.utc) - dt).total_seconds()
    return "adesso" if s < 120 else f"{int(s // 60)} minuti fa" if s < 7200 else f"{int(s // 3600)} ore fa" if s < 172800 else f"{int(s // 86400)} giorni fa"


def computer_acceso() -> bool | None:
    """Almeno un computer con il modello locale risponde? None se non ce n'e' nessuno configurato."""
    from . import fornitori
    try:
        m = fornitori.macchine_locali()
    except Exception:  # noqa: BLE001
        return None
    if not m:
        return None
    return any(fornitori.modelli_macchina(x["url"]) is not None for x in m)


# ---------- i controlli ----------
def _casati(conn, acceso) -> dict | None:
    from . import edizione, scuola
    if not edizione.tre():
        return None
    if not scuola.attiva(conn):
        return _esito("casati", "Padre Casati", "studia i canali e scrive le competenze", "attenzione", "Lo studio e' spento.", "Riaccendilo in Squadra → Padre Casati.", "scuola")
    da = conn.execute("SELECT count(*) AS n FROM competenze_fonti f LEFT JOIN casati_target t ON t.id=f.target_id WHERE f.stato='da_studiare' AND f.tentativi < 3 AND (t.id IS NULL OR t.stato='attivo')").fetchone()["n"]
    fatti = conn.execute("""SELECT count(*) FILTER (WHERE studiata_il > NOW() - INTERVAL '6 hours' AND stato IN ('studiata','integrata')) AS sei,
                                   count(*) FILTER (WHERE studiata_il > NOW() - INTERVAL '24 hours' AND stato IN ('studiata','integrata')) AS giorno,
                                   max(studiata_il) FILTER (WHERE stato IN ('studiata','integrata')) AS ultimo,
                                   count(*) FILTER (WHERE studiata_il > NOW() - INTERVAL '24 hours' AND stato = 'saltata') AS saltati
                            FROM competenze_fonti""").fetchone()
    falliti = conn.execute("""SELECT count(*) AS n FROM casati_registro WHERE quando > NOW() - INTERVAL '6 hours'
                              AND (testo LIKE '%%non riuscita%%' OR testo LIKE '%%risposta leggibile%%' OR tipo = 'errore')""").fetchone()["n"]
    riusciti = conn.execute("""SELECT count(*) AS n FROM casati_registro WHERE quando > NOW() - INTERVAL '6 hours'
                               AND tipo IN ('studio','manuale','carta','assegnata','esame') AND testo NOT LIKE '%%non riuscita%%' AND testo NOT LIKE '%%risposta leggibile%%'""").fetchone()["n"]
    elenco_err = conn.execute("SELECT nome, indirizzo, errore FROM casati_target WHERE stato='attivo' AND errore <> '' ORDER BY id LIMIT 3").fetchall()
    num = {"da studiare": da, "studiati in 24 ore": fatti["giorno"], "saltati in 24 ore": fatti["saltati"], "errori in 6 ore": falliti}
    ult = _quando(fatti["ultimo"])
    if scuola.youtube_in_pausa(conn):
        return _esito("casati", "Padre Casati", "studia i canali", "fermo", "YouTube blocca le richieste dal server: nessun video si puo' studiare.",
                      "Serve far passare lo studio dal tuo PC: dillo a Claude.", "scuola", num)
    rotture = conn.execute("SELECT count(*) AS n FROM casati_registro WHERE quando > NOW() - INTERVAL '6 hours' AND testo LIKE '%%chiuso la connessione%%'").fetchone()["n"]
    if rotture >= 3 and not fatti["sei"]:
        return _esito("casati", "Padre Casati", "studia i canali", "fermo", f"Il modello locale chiude la connessione a meta' risposta ({rotture} volte in 6 ore) e nessun video e' stato studiato.",
                      "Tieni il portatile acceso e collegato (niente sospensione); se continua, scegli un modello locale piu' leggero in Computer locali.", "computer", num)
    if acceso is False:
        return _esito("casati", "Padre Casati", "studia i canali", "attenzione", f"Aspetta: nessun computer con il modello locale e' acceso. Ultimo video studiato: {ult}.",
                      "Accendi il portatile con Ollama.", "scuola", num)
    if falliti >= 5 and riusciti == 0:
        return _esito("casati", "Padre Casati", "studia i canali", "fermo", f"Lavora ma non produce: {falliti} tentativi non riusciti nelle ultime 6 ore e nessun risultato.",
                      "Guarda il diario in Squadra → Padre Casati; se il modello locale risponde male, provane un altro.", "scuola", num)
    if da and not fatti["sei"] and (fatti["ultimo"] is None or fatti["ultimo"] < datetime.now(timezone.utc) - timedelta(hours=6)):
        perche = f" Canale con errore: {elenco_err[0]['nome'] or elenco_err[0]['indirizzo']} ({elenco_err[0]['errore'][:80]})." if elenco_err else ""
        return _esito("casati", "Padre Casati", "studia i canali", "fermo", f"{da} video da studiare ma nessuno studiato nelle ultime 6 ore (ultimo: {ult}).{perche}",
                      "Guarda il diario e la scheda Da studiare in Squadra → Padre Casati.", "scuola", num)
    if fatti["saltati"] and fatti["saltati"] > 3 * max(1, fatti["giorno"]):
        return _esito("casati", "Padre Casati", "studia i canali", "attenzione", f"Salta quasi tutti i video ({fatti['saltati']} saltati, {fatti['giorno']} studiati in 24 ore).",
                      "Forse il canale non ha sottotitoli: guarda Da studiare.", "scuola", num)
    if elenco_err:
        return _esito("casati", "Padre Casati", "studia i canali", "attenzione", f"Non riesce a elencare i video di {elenco_err[0]['nome'] or elenco_err[0]['indirizzo']}: {elenco_err[0]['errore'][:100]}",
                      "Controlla il link del canale in Da studiare.", "scuola", num)
    if not da:
        return _esito("casati", "Padre Casati", "studia i canali", "va", "Niente in coda: dagli un canale o un tema da studiare.", "", "scuola", num)
    return _esito("casati", "Padre Casati", "studia i canali", "va", f"Studia: {fatti['giorno']} video in 24 ore, ultimo {ult}.", "", "scuola", num)


def _posta(conn, acceso) -> dict | None:
    if not conn.execute("SELECT 1 FROM posta_vaglio LIMIT 1").fetchone():
        return None
    r = conn.execute("""SELECT count(*) FILTER (WHERE categoria='da_vagliare' AND creata_il < NOW() - INTERVAL '1 hour') AS in_attesa,
                               count(*) FILTER (WHERE vagliata_il > NOW() - INTERVAL '6 hours') AS fatte,
                               max(vagliata_il) AS ultima FROM posta_vaglio""").fetchone()
    num = {"in attesa da piu' di un'ora": r["in_attesa"], "lette in 6 ore": r["fatte"]}
    if r["in_attesa"] and acceso is False:
        return _esito("posta", "Posta", "legge e smista le email", "attenzione", f"{r['in_attesa']} email aspettano: nessun computer con il modello locale e' acceso.",
                      "Accendi il portatile con Ollama.", "posta", num)
    if r["in_attesa"] >= 5 and not r["fatte"]:
        return _esito("posta", "Posta", "legge e smista le email", "fermo", f"{r['in_attesa']} email aspettano da oltre un'ora e nelle ultime 6 ore non ne ha letta nessuna (ultima: {_quando(r['ultima'])}).",
                      "Apri Posta → Il punto e premi «Controlla adesso»: se compare un errore, mandalo a Claude.", "posta", num)
    return _esito("posta", "Posta", "legge e smista le email", "va", f"Ultima email letta: {_quando(r['ultima'])}.", "", "posta", num)


def _agenti(conn) -> list[dict]:
    out = []
    for a in conn.execute("""SELECT a.id, a.nome,
                               count(*) FILTER (WHERE e.tipo='inizio') AS iniziati,
                               count(*) FILTER (WHERE e.tipo='fine') AS finiti,
                               count(*) FILTER (WHERE e.tipo='errore') AS errori
                             FROM agenti a JOIN eventi_lavoro e ON e.agente_id=a.id AND e.creato_il > NOW() - INTERVAL '24 hours'
                             WHERE a.attivo GROUP BY a.id, a.nome""").fetchall():
        num = {"richieste in 24 ore": a["iniziati"], "finite": a["finiti"], "con errore": a["errori"]}
        vuote = conn.execute("SELECT count(*) AS n FROM registro_azioni WHERE agente_id=%s AND azione='risposta_vuota' AND creata_il > NOW() - INTERVAL '24 hours'", (a["id"],)).fetchone()["n"]
        if a["iniziati"] >= 3 and a["errori"] + vuote >= max(3, a["iniziati"] // 2):
            out.append(_esito(f"agente_{a['id']}", a["nome"], "risponde e svolge i compiti", "fermo",
                              f"Meta' delle richieste finisce male: {a['errori']} errori" + (f" e {vuote} risposte vuote" if vuote else "") + f" su {a['iniziati']} nelle ultime 24 ore.",
                              "Apri la Scatola nera per vedere l'errore; spesso e' la chiave o il credito del modello.", "sez:scatolanera", num))
    bloccate = conn.execute("""SELECT a.nome, count(*) AS n, min(r.creata_il) AS da FROM richieste_informazioni r JOIN agenti a ON a.id=r.agente_id
                               WHERE r.stato='aperta' AND r.bloccante AND r.creata_il < NOW() - INTERVAL '12 hours' GROUP BY a.nome""").fetchall()
    for b in bloccate:
        out.append(_esito(f"bloccato_{b['nome']}", b["nome"], "aspetta una tua risposta", "attenzione",
                          f"E' fermo su {b['n']} {'domanda bloccante' if b['n'] == 1 else 'domande bloccanti'} da {_quando(b['da']).replace(' fa', '')}.", "Rispondi in Plancia → Da decidere.", "dashboard", {"domande": b["n"]}))
    ferme = conn.execute("""SELECT t.id, t.titolo, a.nome FROM task t LEFT JOIN agenti a ON a.id=t.assegnato_agente_id
                            WHERE t.stato='in_corso' AND t.assegnato_agente_id IS NOT NULL AND t.aggiornata_il < NOW() - INTERVAL '6 hours' ORDER BY t.id LIMIT 5""").fetchall() \
        if _ha_colonne(conn, "task", ("assegnato_agente_id", "aggiornata_il")) else []
    for t in ferme:
        out.append(_esito(f"task_{t['id']}", t["nome"] or "Un agente", "porta avanti un compito", "attenzione",
                          f"Il compito «{t['titolo'][:60]}» e' «in corso» da oltre 6 ore senza novita'.", "Aprilo in Task e chiedi a che punto e'.", "task", {}))
    return out


def _ha_colonne(conn, tabella, colonne) -> bool:
    n = conn.execute("SELECT count(*) AS n FROM information_schema.columns WHERE table_name=%s AND column_name = ANY(%s)", (tabella, list(colonne))).fetchone()["n"]
    return n == len(colonne)


def _social(conn) -> dict | None:
    if not conn.execute("SELECT 1 FROM social_marchi_canali WHERE canale_id IS NOT NULL LIMIT 1").fetchone():
        return None
    err = conn.execute("""SELECT c.nome, c.rete, c.ultimo_errore FROM canali_nativi c JOIN social_marchi_canali mc ON mc.canale_id = 'n:' || c.id
                          WHERE c.ultimo_errore IS NOT NULL AND c.ultimo_errore <> '' LIMIT 3""").fetchall()
    proposte = conn.execute("SELECT count(*) AS n FROM social_commenti WHERE stato='da_rispondere' AND creato_il < NOW() - INTERVAL '2 hours'").fetchone()["n"]
    if err:
        return _esito("social", "Social", "legge numeri e commenti", "attenzione", f"{err[0]['rete']} «{err[0]['nome']}»: {err[0]['ultimo_errore'][:120]}",
                      "Ricollega il canale in Impostazioni → Social.", "social", {"canali con errore": len(err)})
    if proposte >= 5:
        return _esito("social", "Social", "prepara le risposte ai commenti", "attenzione", f"{proposte} commenti aspettano da ore una risposta preparata.",
                      "Apri Social → Commenti.", "social", {"commenti in attesa": proposte})
    return _esito("social", "Social", "legge numeri e commenti", "va", "Canali e commenti in ordine.", "", "social")


def _locale(conn, acceso) -> dict | None:
    if acceso is None:
        return None
    if acceso:
        return _esito("locale", "Modello locale", "serve posta e Padre Casati", "va", "Almeno un computer risponde.", "", "computer")
    return _esito("locale", "Modello locale", "serve posta e Padre Casati", "attenzione", "Nessun computer con il modello locale risponde: posta e studio aspettano.",
                  "Accendi il portatile e apri Ollama.", "computer")


def controlla(conn) -> list[dict]:
    acceso = computer_acceso()
    out = []
    for f in (lambda: _casati(conn, acceso), lambda: _posta(conn, acceso), lambda: _social(conn), lambda: _locale(conn, acceso)):
        try:
            x = f()
        except Exception as e:  # noqa: BLE001 - un controllo che si rompe non deve fermare gli altri: lo si dice
            conn.rollback()
            x = _esito(f"guasto_{getattr(f, '__name__', 'x')}", "Guardiano", "controlla il lavoro", "attenzione", f"Un controllo non e' riuscito: {type(e).__name__}", "", "")
        if x:
            out.append(x)
    try:
        out += _agenti(conn)
    except Exception:  # noqa: BLE001
        conn.rollback()
    out.sort(key=lambda x: (ORDINE[x["stato"]], x["chi"]))
    return out


def giro(conn) -> list[str]:
    """Ogni 10 minuti: registra quando un lavoro diventa fermo; se resta fermo per un'ora manda una notifica urgente (ogni 6 ore al massimo)."""
    ora = datetime.now(timezone.utc)
    avvisi = []
    esiti = controlla(conn)
    attivi = set()
    for x in esiti:
        k = "guardiano_dal_" + x["chiave"]
        if x["stato"] != "fermo":
            continue
        attivi.add(k)
        dal = _imp(conn, k)
        if not dal:
            _scrivi(conn, k, ora.isoformat())
            continue
        if ora - datetime.fromisoformat(dal) < DOPO:
            continue
        ultimo = _imp(conn, "guardiano_avvisato_" + x["chiave"])
        if ultimo and ora - datetime.fromisoformat(ultimo) < ATTESA:
            continue
        testo = f"{x['chi']} e' fermo: {x['messaggio']} {x['fare']}".strip()
        conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, TRUE, TRUE)", ("GUARDIANO: " + testo,))
        _scrivi(conn, "guardiano_avvisato_" + x["chiave"], ora.isoformat())
        avvisi.append(testo)
    # i problemi risolti si dimenticano (cosi' un nuovo fermo riparte da zero)
    for r in conn.execute("SELECT chiave FROM impostazioni_sistema WHERE chiave LIKE 'guardiano_dal_%%'").fetchall():
        if r["chiave"] not in attivi:
            conn.execute("DELETE FROM impostazioni_sistema WHERE chiave IN (%s, %s)", (r["chiave"], r["chiave"].replace("_dal_", "_avvisato_")))
    _scrivi(conn, "guardiano_ultimo_giro", ora.isoformat())
    return avvisi


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        esiti = controlla(conn)
        for x in esiti:
            dal = _imp(conn, "guardiano_dal_" + x["chiave"])
            x["fermo_da"] = _quando(datetime.fromisoformat(dal)).replace(" fa", "") if dal and x["stato"] == "fermo" else None
        ultimo = _imp(conn, "guardiano_ultimo_giro")
        return {"esiti": esiti, "fermi": sum(x["stato"] == "fermo" for x in esiti), "attenzione": sum(x["stato"] == "attenzione" for x in esiti),
                "ultimo_giro": ultimo or None}
