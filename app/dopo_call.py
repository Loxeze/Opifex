"""Dopo la call (2.75): riassunto e passi nel CRM, bozza di preventivo con i prezzi di sempre, promemoria se la proposta resta
senza risposta, risposte pronte alle domande frequenti.

- RIASSUNTO E PASSI: l'analisi della call (modello locale, il resoconto resta in casa) scrive anche un riassunto di 3-5 frasi e i passi
  successivi con una scadenza. Vanno nella storia del contatto nel CRM; il primo passo diventa la data «da ricontattare».
- PREVENTIVO VELOCE: subito dopo l'analisi Opifex prepara la bozza del preventivo. I prezzi li prende da quelli che hai gia' usato
  (stesso servizio nei preventivi passati: il valore piu' frequente); dove non ce n'e' uno, il prezzo resta vuoto. La bozza resta tua.
- PROMEMORIA SULLA PROPOSTA: se dopo 5 giorni dall'invio del preventivo il cliente non si e' fatto sentire, Opifex ti avvisa e, se il
  contatto viene da una campagna, prepara un'email gentile per riprendere il discorso (da approvare).
- RISPOSTE PRONTE: scrivi una volta come rispondi alle domande frequenti (prezzi, tempi, come lavorate...). Quando una risposta di un
  contatto contiene una di quelle domande, la bozza di risposta usa il tuo testo.
"""
import json
import re
from collections import Counter
from datetime import date, timedelta

GIORNI_PROPOSTA = 5


def _parole(t: str) -> set:
    return {w for w in re.findall(r"[a-zà-ù0-9]{3,}", (t or "").lower()) if w not in {"della", "delle", "degli", "con", "per", "una", "uno", "che", "dei", "del", "sul", "nel"}}


def _simili(a: str, b: str) -> float:
    pa, pb = _parole(a), _parole(b)
    return len(pa & pb) / max(1, min(len(pa), len(pb))) if pa and pb else 0.0


# ---------- prezzi di sempre ----------
def prezzi_usuali(conn) -> list[dict]:
    """Servizio -> prezzo piu' usato nei preventivi gia' mandati (o accettati)."""
    voci = {}
    for p in conn.execute("SELECT voci FROM preventivi WHERE stato IN ('in_fatture','accettato') ORDER BY id DESC LIMIT 300").fetchall():
        for v in (p["voci"] or []):
            if v.get("prezzo") in (None, "") or not str(v.get("nome") or "").strip():
                continue
            chiave = " ".join(sorted(_parole(v["nome"])))
            if not chiave:
                continue
            voci.setdefault(chiave, {"nome": v["nome"], "prezzi": []})["prezzi"].append(round(float(v["prezzo"]), 2))
    out = []
    for x in voci.values():
        prezzo, volte = Counter(x["prezzi"]).most_common(1)[0]
        out.append({"nome": x["nome"], "prezzo": prezzo, "volte": len(x["prezzi"])})
    return sorted(out, key=lambda x: -x["volte"])


def applica_prezzi(voci: list[dict], usuali: list[dict]) -> list[dict]:
    for v in voci:
        if v.get("prezzo") not in (None, ""):
            continue
        migliore = max(usuali, key=lambda u: _simili(v["nome"], u["nome"]), default=None)
        if migliore and _simili(v["nome"], migliore["nome"]) >= 0.6:
            v["prezzo"] = migliore["prezzo"]
            v["prezzo_da"] = f"come di solito ({migliore['nome']})"
    return voci


# ---------- riassunto e passi ----------
def registra(conn, riunione_id: int, contatto_id: int, opp_id: int | None, j: dict):
    """Riassunto e passi della call nella storia del contatto; il primo passo diventa la data da ricontattare."""
    from . import cassaforte
    riassunto = str(j.get("riassunto") or "").strip()[:1500]
    passi = []
    for p in (j.get("passi") or [])[:6]:
        if isinstance(p, dict) and str(p.get("cosa") or "").strip():
            try:
                g = max(0, min(90, int(p.get("entro_giorni") or 7)))
            except (TypeError, ValueError):
                g = 7
            passi.append({"cosa": str(p["cosa"]).strip()[:200], "entro": (date.today() + timedelta(days=g)).isoformat()})
    if not riassunto and not passi:
        return
    testo = (riassunto + ("\n\nPassi successivi:\n" + "\n".join(f"- {p['cosa']} (entro il {date.fromisoformat(p['entro']):%d/%m})" for p in passi) if passi else "")).strip()
    conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito, note_cifrate, riunione_id) VALUES (%s,'riunione','uscita',%s,'altro',%s,%s)""",
                 (contatto_id, "Riassunto della call e passi successivi", cassaforte.cifra(testo), riunione_id))
    if passi:
        primo = min(passi, key=lambda p: p["entro"])
        conn.execute("UPDATE crm_contatti SET prossimo_passo_il=%s WHERE id=%s", (primo["entro"], contatto_id))
        if opp_id:
            conn.execute("UPDATE crm_opportunita SET prossima_azione=%s, scadenza=%s WHERE id=%s", (primo["cosa"], primo["entro"], opp_id))
    conn.execute("UPDATE crm_analisi_call SET riassunto=%s, passi=%s WHERE riunione_id=%s", (riassunto, json.dumps(passi), riunione_id))


def preventivo_veloce(conn, opp_id: int | None) -> int | None:
    """Dopo la call: la bozza del preventivo, con i prezzi gia' usati. Una sola per opportunita'."""
    from . import preventivi
    from .fornitori import ErroreFornitore
    if not opp_id or conn.execute("SELECT 1 FROM preventivi WHERE opportunita_id=%s", (opp_id,)).fetchone():
        return None
    try:
        pid = preventivi.prepara(conn, opp_id)
    except (ErroreFornitore, LookupError):
        conn.rollback()
        return None
    o = conn.execute("SELECT titolo FROM crm_opportunita WHERE id=%s", (opp_id,)).fetchone()
    p = conn.execute("SELECT voci FROM preventivi WHERE id=%s", (pid,)).fetchone()
    con_prezzo = sum(1 for v in (p["voci"] or []) if v.get("prezzo") not in (None, ""))
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                 (f"Call fatta con «{o['titolo'] if o else 'il cliente'}»: bozza di preventivo pronta ({len(p['voci'] or [])} voci, {con_prezzo} con il prezzo di sempre). "
                  "La trovi nell'opportunità: controllala e mettila in Fatture in Cloud.",))
    conn.commit()
    return pid


# ---------- promemoria sulla proposta ----------
ISTR_PROPOSTA = """Scrivi per Lorenzo Zeppa una breve email (60-100 parole) per riprendere il discorso con un potenziale cliente a cui ha mandato un preventivo
{giorni} giorni fa e che non si e' ancora fatto sentire. Gentile e leggera, mai insistente: chiede se ha avuto modo di guardarlo, si offre per chiarimenti
o per adattarlo, propone eventualmente una breve telefonata. Comincia con {{saluto}} su una riga da sola, firma «Lorenzo Zeppa{firma}».
Rispondi SOLO con JSON: {{"oggetto": "...", "testo": "..."}}"""


def promemoria_proposte(conn) -> int:
    """Preventivi mandati da piu' di 5 giorni senza notizie del cliente: avviso e, se il contatto viene da una campagna, email da approvare."""
    from . import flusso, redattore
    from .fornitori import ErroreFornitore
    n = 0
    for p in conn.execute("""SELECT p.*, o.titolo, o.stato AS opp_stato, o.campagna_id FROM preventivi p JOIN crm_opportunita o ON o.id=p.opportunita_id
                             WHERE p.stato='in_fatture' AND p.sollecito_il IS NULL AND p.inviato_il < NOW() - make_interval(days => %s)
                               AND o.stato NOT IN ('vinta','persa') ORDER BY p.id LIMIT 10""", (GIORNI_PROPOSTA,)).fetchall():
        sentito = conn.execute("""SELECT 1 FROM crm_interazioni WHERE contatto_id=%s AND direzione='entrata' AND quando > %s LIMIT 1""",
                               (p["contatto_id"], p["inviato_il"])).fetchone()
        conn.execute("UPDATE preventivi SET sollecito_il=NOW() WHERE id=%s", (p["id"],))
        if sentito:
            conn.commit()
            continue
        giorni = (date.today() - p["inviato_il"].date()).days
        bozza = ""
        d = conn.execute("SELECT * FROM campagne_posta_dest WHERE opportunita_id=%s ORDER BY id DESC LIMIT 1", (p["opportunita_id"],)).fetchone()
        if d and d["contatto_id"]:
            c = dict(conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.id=%s", (d["campagna_id"],)).fetchone())
            k = flusso.contatto(conn, d["contatto_id"])
            try:
                j, spesa = redattore.chiedi(conn, c["modello"], ISTR_PROPOSTA.format(giorni=giorni, firma=(" — " + c["impresa"]) if c.get("impresa") else "")
                                            + f"\n\nPREVENTIVO: {p['oggetto']}\nENTE: {k['ente'] or '(senza nome)'}", 700)
                flusso._spendi(conn, c, spesa)
            except ErroreFornitore:
                conn.rollback()
                break
            if isinstance(j, dict) and j.get("testo") and "@" in k["email"]:
                from .campagne import _componi
                persona = k["genere"] == "persona" or bool(k["nome"] and k["ente"])
                t = str(j["testo"]).strip()
                t = t if "{saluto}" in t else "{saluto}\n\n" + t
                flusso._crea_email(conn, c, d["id"], k["email"], _componi(str(j.get("oggetto") or ("Re: " + p["oggetto"])), k["nome"], k["ente"], persona)[:200],
                                   _componi(t, k["nome"], k["ente"], persona), "ripresa", automatica=False)
                bozza = " Ti ho preparato un'email gentile per riprendere il discorso: la trovi in Campagne email, da approvare."
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     (f"Il preventivo «{p['oggetto']}» ({p['titolo']}) e' stato mandato {giorni} giorni fa e il cliente non si e' ancora fatto sentire.{bozza}",))
        conn.commit()
        n += 1
    return n


# ---------- risposte pronte ----------
def risposte_pronte(conn) -> list[dict]:
    return conn.execute("SELECT id, domanda, risposta FROM risposte_pronte WHERE attiva ORDER BY id").fetchall()


def per_la_bozza(conn, loro: str) -> str:
    """Le risposte pronte che riguardano quello che hanno scritto, da passare al modello che prepara la bozza."""
    usate = [r for r in risposte_pronte(conn) if _simili(r["domanda"], loro) >= 0.5 or any(w in _parole(loro) for w in _parole(r["domanda"]) if len(w) >= 6)]
    if not usate:
        return ""
    return ("\n\nRISPOSTE PRONTE DI LORENZO (se nella loro email c'e' una di queste domande, rispondi usando il SUO testo, senza cambiarne il contenuto):\n"
            + "\n".join(f"- Domanda: {r['domanda']}\n  Risposta di Lorenzo: {r['risposta']}" for r in usate[:5]))
