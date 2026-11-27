"""Social: il resoconto scaricabile di tutti i collegamenti (app delle reti, profili diretti, Buffer, marchi, profili monitorati, post in errore,
eventi recenti) con l'elenco dei problemi trovati. Serve a capire in un colpo solo perche' un social non si collega.
Mai token, segreti o chiavi: solo si'/no, nomi, date ed esiti."""
import re
from datetime import datetime, timezone

from . import social_nativo as sn

_TOKEN = re.compile(r"(access_token|refresh_token|client_secret|code|token)=([^&\s\"']+)", re.I)
_LUNGHI = re.compile(r"\b[A-Za-z0-9_\-\.]{60,}\b")


def pulito(t) -> str:
    """Toglie da un messaggio qualsiasi cosa somigli a un token."""
    t = str(t or "")
    t = _TOKEN.sub(lambda m: m.group(1) + "=…", t)
    return _LUNGHI.sub("…", t)[:500]


def registra(conn, provider: str, evento: str, dettaglio: str = ""):
    try:
        conn.execute("INSERT INTO social_eventi (provider, evento, dettaglio) VALUES (%s,%s,%s)", (provider or "", evento[:80], pulito(dettaglio)))
        conn.execute("DELETE FROM social_eventi WHERE creato_il < NOW() - interval '90 days'")
    except Exception:  # noqa: BLE001 - il registro non deve mai fermare un collegamento
        pass


def _quando(d) -> str:
    return d.astimezone().strftime("%d/%m/%Y %H:%M") if d else "mai"


def resoconto(conn, prova: bool = True) -> str:
    """Il testo del resoconto. prova=True controlla anche dal vivo che ogni accesso funzioni ancora (rinnovo del token, Buffer)."""
    from .versione import versione_corrente
    ora = datetime.now(timezone.utc)
    problemi, r = [], []
    base = sn._leggi(conn, "sn_redirect_base")
    r += [f"RESOCONTO SOCIAL DI OPIFEX — {_quando(ora)}", f"Versione di Opifex: {versione_corrente()}",
          "Nessun token, segreto o chiave compare in questo file.", "",
          f"Indirizzo del sito per i ritorni dalle reti: {base or 'NON IMPOSTATO'}",
          f"Versione delle API di Meta: {sn._leggi(conn, 'sn_graph_versione') or 'v23.0 (predefinita)'}", ""]
    if not base:
        problemi.append("Manca l'indirizzo del sito per i ritorni (es. https://aurora.opifex.space): si imposta salvando le credenziali di una rete.")
    # 1. app delle reti e profili collegati direttamente
    r.append("== 1. COLLEGAMENTO DIRETTO, RETE PER RETE ==")
    for p, et in sn.ETICHETTE_PROVIDER.items():
        cid, sec = sn._leggi(conn, f"sn_{p}_id"), bool(sn._leggi(conn, f"sn_{p}_secret_cifrato"))
        acc = conn.execute("SELECT * FROM account_social WHERE provider=%s ORDER BY id", (p,)).fetchall()
        r += ["", f"--- {et} ---",
              f"ID dell'app: {cid or 'NON INSERITO'} · segreto: {'salvato' if sec else 'NON SALVATO'}",
              f"Indirizzo di ritorno da registrare nel portale sviluppatori: {sn.redirect_uri(conn, p) or '(manca l indirizzo del sito)'}",
              f"Permessi chiesti: {sn._scope(p, {'pagine': True})}"]
        if (cid or sec) and not (cid and sec):
            problemi.append(f"{et}: credenziali dell'app incomplete ({'manca il segreto' if cid else 'manca l ID'}).")
        if not acc:
            r.append("Profili collegati: nessuno")
            if cid and sec:
                problemi.append(f"{et}: l'app c'e' ma nessun profilo e' collegato (il collegamento non e' andato a buon fine: vedi gli eventi in fondo).")
            continue
        for a in acc:
            scad = a["scade_il"]
            stato_t = "senza scadenza" if not scad else (f"SCADUTO il {_quando(scad)}" if scad < ora else f"valido fino al {_quando(scad)}")
            r.append(f"Profilo «{a['nome']}» (n. {a['id']}): accesso {stato_t}; collegato il {_quando(a['creato_il'])}")
            if a["ultimo_errore"]:
                r.append(f"   ultimo errore: {pulito(a['ultimo_errore'])}")
            if prova:
                try:
                    tk = sn.token(conn, a["id"])
                    if p == "meta":   # una domanda innocua a Meta: chi sono e quali permessi ho davvero
                        perm = sn._http("GET", f"{sn._graph(conn)}/me/permissions", params={"access_token": tk}).get("data") or []
                        dati = {x.get("permission"): x.get("status") for x in perm if isinstance(x, dict)}
                        manca = [x for x in sn._scope("meta", {}).split(",") if dati.get(x) != "granted"]
                        r.append("   prova dal vivo: Meta risponde" + (f"; permessi NON concessi: {', '.join(manca)}" if manca else "; tutti i permessi concessi"))
                        if manca:
                            problemi.append(f"{et}, profilo «{a['nome']}»: permessi non concessi ({', '.join(manca)}). Ricollega e lascia tutte le spunte; in modalita' sviluppo l'account deve essere tra gli amministratori o i tester dell'app.")
                    elif p == "linkedin":
                        sn._http("GET", "https://api.linkedin.com/v2/userinfo", headers={"Authorization": "Bearer " + tk})
                        r.append("   prova dal vivo: LinkedIn risponde")
                    else:
                        r.append("   prova dal vivo: accesso valido (non scaduto)")
                except Exception as e:  # noqa: BLE001
                    r.append(f"   prova dal vivo: NON FUNZIONA — {pulito(e)}")
                    problemi.append(f"{et}, profilo «{a['nome']}»: l'accesso non funziona ({pulito(e)[:120]}). Va ricollegato.")
            canali = conn.execute("SELECT * FROM canali_nativi WHERE account_id=%s ORDER BY rete, nome", (a["id"],)).fetchall()
            if not canali:
                r.append("   canali: NESSUNO")
                problemi.append(f"{et}, profilo «{a['nome']}»: collegato ma senza canali (per Instagram serve un account professionale legato a una pagina Facebook).")
            for c in canali:
                r.append(f"   canale {c['rete']}: «{c['nome']}» {'acceso' if c['attivo'] else 'SPENTO'}" + (f" — errore: {pulito(c['ultimo_errore'])}" if c["ultimo_errore"] else ""))
                if c["ultimo_errore"]:
                    problemi.append(f"{et}, canale «{c['nome']}» ({c['rete']}): {pulito(c['ultimo_errore'])[:150]}")
    # 2. Buffer
    r += ["", "== 2. BUFFER =="]
    from . import buffer
    try:
        stati = buffer.stato_account(conn) if prova else [{"etichetta": a["etichetta"], "canali": [], "errore": "(non provato)"} for a in conn.execute("SELECT * FROM account_buffer ORDER BY id").fetchall()]
    except Exception as e:  # noqa: BLE001
        stati = []
        r.append(f"Buffer non leggibile: {pulito(e)}")
    if not stati:
        r.append("Nessun account Buffer collegato.")
    for a in stati:
        r.append(f"Account «{a['etichetta']}»: " + (f"ERRORE — {pulito(a['errore'])}" if a["errore"] else f"{len(a['canali'])} canali"))
        if a["errore"] and a["errore"] != "(non provato)":
            problemi.append(f"Buffer «{a['etichetta']}»: {pulito(a['errore'])[:150]}")
        for c in a["canali"]:
            r.append(f"   {c.get('service') or '?'}: «{c.get('name') or ''}»")
    # 3. marchi
    r += ["", "== 3. MARCHI (a chi serve ogni canale) =="]
    for m in conn.execute("SELECT * FROM social_marchi ORDER BY nome").fetchall():
        canali = conn.execute("SELECT * FROM social_marchi_canali WHERE marchio_id=%s ORDER BY rete", (m["id"],)).fetchall()
        r.append(f"«{m['nome']}» ({m['tipo']}{'' if m['attivo'] else ', SPENTO'}): presente su {', '.join(m['reti']) or 'nessuna rete indicata'}")
        collegate = {c["rete"] for c in canali if c["canale_id"]}
        for c in canali:
            r.append(f"   {c['rete']}: {c['indirizzo'] or '(senza indirizzo)'} → " + (f"collegato al canale {c['canale_id']}" if c["canale_id"] else "NON COLLEGATO a un canale"))
        manca = [x for x in m["reti"] if x not in collegate]
        if m["attivo"] and manca:
            problemi.append(f"Marchio «{m['nome']}»: nessun canale collegato per {', '.join(manca)}.")
    if r[-1].startswith("== 3."):
        r.append("Nessun marchio configurato.")
    # 4. profili monitorati
    r += ["", "== 4. PROFILI MONITORATI (lettura dei profili pubblici) =="]
    for p in conn.execute("SELECT * FROM profili_monitorati ORDER BY piattaforma, nome").fetchall():
        r.append(f"{p['piattaforma']}: «{p['nome']}» {p['url']} — ultimo controllo {_quando(p['ultimo_controllo'])}" + (f" — ERRORE: {pulito(p['errore'])}" if p["errore"] else "") + ("" if p["attivo"] else " (spento)"))
        if p["errore"] and p["attivo"]:
            problemi.append(f"Profilo monitorato «{p['nome']}» ({p['piattaforma']}): {pulito(p['errore'])[:150]}")
    if r[-1].startswith("== 4."):
        r.append("Nessun profilo monitorato.")
    # 5. post
    r += ["", "== 5. POST DEGLI ULTIMI 30 GIORNI =="]
    for x in conn.execute("SELECT stato, count(*) AS n FROM post_social WHERE creato_il > NOW() - interval '30 days' GROUP BY stato ORDER BY stato").fetchall():
        r.append(f"{x['stato']}: {x['n']}")
    err = conn.execute("""SELECT canale_nome, servizio, errore, aggiornato_il FROM post_social WHERE stato='errore' AND errore IS NOT NULL
                          ORDER BY aggiornato_il DESC LIMIT 15""").fetchall()
    if r[-1].startswith("== 5."):
        r.append("Nessun post negli ultimi 30 giorni.")
    if err:
        r.append("Ultimi post non partiti:")
        r += [f"   {_quando(e['aggiornato_il'])} · {e['canale_nome']} ({e['servizio']}): {pulito(e['errore'])}" for e in err]
    # 6. eventi
    r += ["", "== 6. EVENTI DI COLLEGAMENTO RECENTI =="]
    ev = conn.execute("SELECT * FROM social_eventi ORDER BY id DESC LIMIT 60").fetchall()
    r += [f"{_quando(e['creato_il'])} · {sn.ETICHETTE_PROVIDER.get(e['provider'], e['provider'] or '-')} · {e['evento']}" + (f": {e['dettaglio']}" if e["dettaglio"] else "") for e in ev] or ["Nessun evento registrato (il registro parte dalla versione 2.85)."]
    testa = ["== PROBLEMI TROVATI ==", *(f"- {p}" for p in problemi)] if problemi else ["== PROBLEMI TROVATI ==", "Nessun problema evidente: guarda gli eventi in fondo."]
    return "\n".join(r[:6] + testa + [""] + r[6:]) + "\n"
