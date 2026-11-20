"""Il flusso a blocchi delle campagne email (2.64).

PARTENZA   foglio Google della campagna (solo lettura) e/o contatti scelti dal CRM
INGRESSO   ogni riga diventa un contatto del CRM (senza doppioni) e un destinatario
STUDIO     il Redattore legge il sito (o le note gia' raccolte), verifica la zona, sceglie l'angolo
BOZZA      l'email personale; senza sito, il testo standard della campagna
APPROVAZIONE  di Lorenzo, finche' non accende l'invio automatico (solo dopo 20 bozze approvate senza correzioni)
INVIO      piano, dalla casella scelta; entra nella storia del contatto
ATTESA     N giorni (14 di serie)
SOLLECITO  seconda email breve; poi la terza solo se sul sito c'e' qualcosa di nuovo; altrimenti «nessuna risposta»
USCITE     la Posta (modello locale) legge le risposte: interessato -> opportunita' + bozza di risposta con il link di prenotazione;
           non interessato -> chiuso senza avvisare; «rimuovi» -> fuori da tutte le campagne
"""
import csv
import hashlib
import io
import re
from datetime import datetime, timedelta, timezone

import httpx

from . import cassaforte, crm, fornitori, redattore
from .fornitori import ErroreFornitore

SERVE_PER_AUTONOMIA = 20
PER_GIRO = 5
FOGLIO_OGNI_MINUTI = 10

COLONNE = {"ente": r"^(nome|hotel|struttura|ente|azienda|museo|organizzazione|denominazione|ragione|cliente|sponsor)",
           "sito": r"(sito|web|url|internet)", "email": r"(e-?mail|posta|indirizzo email)", "comune": r"(localit|comune|citt|luogo|paese)",
           "provincia": r"^prov", "regione": r"^region", "note": r"^note"}

ISTR_ESITO = """Leggi la risposta ricevuta a un'email di Lorenzo Zeppa e classificala.
- "interessato": vuole saperne di piu', propone o accetta una chiamata, chiede prezzi o dettagli;
- "dubbio": ne' si' ne' no (es. «mi richiami a gennaio», «giro al responsabile», «ora no ma piu' avanti»);
- "non_interessato": dice di no, non e' interessato, non ha budget;
- "rimuovi": chiede di non ricevere piu' email;
- "automatica": risposta automatica (fuori sede, ferie, conferma di ricezione).
Se il contatto indica QUANDO risentirsi («tra un mese», «a marzo», «dopo l'estate», «tra 2 giorni»), calcola la data a partire da oggi
e mettila in "richiamo" (AAAA-MM-GG; per un mese usa il primo giorno), con le sue parole in "quando". Altrimenti null.
Rispondi SOLO con JSON: {"esito": "...", "sintesi": "una frase in italiano su cosa dice", "richiamo": "AAAA-MM-GG o null", "quando": "le sue parole o vuoto"}"""

ISTR_RISPOSTA = """Scrivi per Lorenzo Zeppa una risposta breve (40-90 parole) a chi si e' detto interessato alla sua email. Tono personale e cordiale,
prima persona. Ringrazia, rispondi in una frase a quello che chiede se puoi farlo senza inventare, e proponi una chiamata di 20 minuti
{link}. Firma: Lorenzo. Rispondi SOLO con JSON: {{"testo": "..."}}"""


def _d(v):
    return cassaforte.decifra(v) if v else ""


def _ora():
    return datetime.now(timezone.utc)


# ---------- contatti ----------
def sito_contatto(conn, cid: int) -> str:
    r = conn.execute("SELECT valore_cifrato FROM crm_recapiti WHERE contatto_id=%s AND tipo='sito' ORDER BY id LIMIT 1", (cid,)).fetchone()
    if r:
        return _d(r["valore_cifrato"])
    r = conn.execute("SELECT attributi->>'sito' AS s FROM crm_contatti WHERE id=%s", (cid,)).fetchone()
    return (r["s"] if r else "") or ""


def contatto(conn, cid: int) -> dict:
    k = conn.execute("SELECT * FROM crm_contatti WHERE id=%s", (cid,)).fetchone()
    return {"id": cid, "ente": _d(k["ente_cifrato"]), "nome": _d(k["nome_cifrato"]), "email": _d(k["email_cifrata"]).strip(), "genere": k["genere"],
            "comune": k["comune"] or "", "provincia": k["provincia"] or "", "regione": k["regione"] or "", "sito": sito_contatto(conn, cid)}


def _localita(k: dict) -> str:
    return ", ".join(x for x in (k["comune"], k["provincia"].upper() if len(k["provincia"]) <= 3 else k["provincia"], k["regione"]) if x) or "(non indicata)"


def _esclusi(conn) -> set:
    return {r["email_hash"] for r in conn.execute("SELECT DISTINCT email_hash FROM campagne_posta_dest WHERE stato='rimosso'").fetchall()}


def aggiungi_destinatario(conn, cid: int, contatto_id: int, email: str) -> bool:
    if "@" not in (email or ""):
        return False
    h = crm.hash_email(email)
    neg = conn.execute("SELECT consenso_marketing IS FALSE AS no FROM crm_contatti WHERE id=%s", (contatto_id,)).fetchone()
    if (neg and neg["no"]) or h in _esclusi(conn):
        return False
    vecchio = conn.execute("SELECT id, email_hash, stato FROM campagne_posta_dest WHERE campagna_id=%s AND contatto_id=%s", (cid, contatto_id)).fetchone()
    if vecchio:
        if vecchio["email_hash"] != h and vecchio["stato"] in ("in_attesa", "errore", "scartata"):   # email corretta nel foglio: si riparte da capo
            conn.execute("UPDATE campagne_posta_dest SET email_hash=%s, stato='in_attesa', nota='', aggiornato_il=NOW() WHERE id=%s", (h, vecchio["id"]))
        return False
    r = conn.execute("""INSERT INTO campagne_posta_dest (campagna_id, contatto_id, email_hash) VALUES (%s,%s,%s)
                        ON CONFLICT (campagna_id, email_hash) DO NOTHING""", (cid, contatto_id, h))
    return bool(r.rowcount)


# ---------- partenza: il foglio Google ----------
def id_foglio(url: str) -> str:
    m = (re.search(r"/(?:spreadsheets|file)/d/([A-Za-z0-9_-]{20,})", url or "") or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url or "")
         or re.fullmatch(r"\s*([A-Za-z0-9_-]{20,})\s*", url or ""))
    return m.group(1) if m else ""


def _account_drive(conn, c: dict) -> list[dict]:
    """Gli account Google con Drive: prima quello scelto per la campagna (o che l'ha gia' letta), poi gli altri."""
    tutti = conn.execute("SELECT id, email FROM account_google WHERE 'drive' = ANY(servizi) ORDER BY id").fetchall()
    return sorted(tutti, key=lambda a: a["id"] != c.get("foglio_account_id"))


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _da_xlsx(contenuto: bytes) -> str:
    """Il primo foglio di un file Excel, in CSV."""
    from .crm import ErroreCrm, _righe_xlsx
    try:
        fogli, righe = _righe_xlsx(contenuto)
    except ErroreCrm as e:
        raise ValueError(str(e)) from None
    if not fogli:
        raise ValueError("Il file Excel non ha fogli")
    out = io.StringIO()
    w = csv.writer(out)
    for r in righe(fogli[0][1]):
        w.writerow(r)
    return out.getvalue()


def scarica_foglio(conn, c: dict) -> str:
    """Il primo foglio in CSV: un foglio Google (esportato) o un file Excel/CSV caricato su Drive (scaricato e letto).
    Prova tutti gli account collegati con Drive e ricorda quello che riesce ad aprirlo. Opifex non scrive mai nel file."""
    from . import google
    fid = id_foglio(c["foglio"])
    if not fid:
        raise ValueError("Indirizzo del foglio non valido: incolla il link del foglio Google o del file Excel su Drive")
    conti = _account_drive(conn, c)
    if not conti:
        raise ValueError("Nessun account Google collegato con Drive: ricollega l'account spuntando Drive")
    base = f"https://www.googleapis.com/drive/v3/files/{fid}"
    for a in conti:
        try:
            h = {"Authorization": "Bearer " + google.token_accesso(conn, a["id"])}
            info = httpx.get(base, params={"fields": "mimeType,name", "supportsAllDrives": "true"}, headers=h, timeout=30)
            if info.status_code in (401, 403, 404):
                continue   # questo account non lo vede: si prova il prossimo
            if info.status_code != 200:
                raise ValueError(f"Google ha risposto {info.status_code}")
            tipo = info.json().get("mimeType", "")
            if tipo == "application/vnd.google-apps.spreadsheet":
                r = httpx.get(base + "/export", params={"mimeType": "text/csv"}, headers=h, timeout=30)
            elif tipo in (XLSX, "text/csv", "text/plain", "application/vnd.ms-excel"):
                r = httpx.get(base, params={"alt": "media", "supportsAllDrives": "true"}, headers=h, timeout=60)
            else:
                raise ValueError(f"Il file «{info.json().get('name', '')}» non è un foglio: serve un foglio Google, un Excel (.xlsx) o un CSV")
            if r.status_code != 200:
                raise ValueError(f"Google ha risposto {r.status_code} leggendo il file")
        except httpx.HTTPError as e:
            raise ValueError(f"Google non risponde ({type(e).__name__})") from None
        except google.ErroreGoogle:
            continue   # collegamento scaduto per questo account
        if c.get("id") and c.get("foglio_account_id") != a["id"]:
            conn.execute("UPDATE campagne_posta SET foglio_account_id=%s WHERE id=%s", (a["id"], c["id"]))
        if tipo == XLSX:
            return _da_xlsx(r.content)
        if tipo == "application/vnd.ms-excel":
            raise ValueError("Il file è nel vecchio formato Excel (.xls): aprilo e salvalo come .xlsx, oppure convertilo in foglio Google")
        return r.content.decode("utf-8-sig", "replace")
    raise ValueError("Nessuno degli account collegati con Drive (" + ", ".join(a["email"] for a in conti) +
                     ") può aprire questo file: condividilo con uno di loro, oppure collega con Drive l'account che lo possiede")


def righe_foglio(testo_csv: str) -> tuple[dict, list[dict]]:
    """Riconosce le colonne dall'intestazione (nome/hotel/ente, sito, email, localita'/comune, provincia, regione, note)."""
    righe = list(csv.reader(io.StringIO(testo_csv)))
    if not righe:
        return {}, []
    testa = [x.strip().lower() for x in righe[0]]
    mappa = {}
    for campo, rx in COLONNE.items():
        for i, t in enumerate(testa):
            if i not in mappa.values() and re.search(rx, t):
                mappa[campo] = i
                break
    out = []
    for r in righe[1:]:
        v = {k: (r[i].strip() if i < len(r) else "") for k, i in mappa.items()}
        if any(v.values()):
            out.append(v)
    return mappa, out


def _lista(conn, c: dict) -> int:
    if c.get("lista_id"):
        return c["lista_id"]
    lid = conn.execute("INSERT INTO crm_liste (nome, natura) VALUES (%s, 'pubblico') RETURNING id", (f"Campagna: {c['nome']}"[:120],)).fetchone()["id"]
    conn.execute("UPDATE campagne_posta SET lista_id=%s WHERE id=%s", (lid, c["id"]))
    return lid


def _trova(conn, email: str, sito: str) -> int | None:
    if "@" in email:
        r = conn.execute("SELECT id FROM crm_contatti WHERE email_hash=%s ORDER BY id LIMIT 1", (crm.hash_email(email),)).fetchone()
        if r:
            return r["id"]
    ks = redattore.chiave_sito(sito)
    if ks:
        for r in conn.execute("SELECT contatto_id, valore_cifrato FROM crm_recapiti WHERE tipo='sito'").fetchall():
            if redattore.chiave_sito(_d(r["valore_cifrato"])) == ks:
                return r["contatto_id"]
    return None


def _imposta_sito(conn, cid: int, sito: str):
    from . import crm_modello
    if sito and redattore.chiave_sito(sito) != redattore.chiave_sito(sito_contatto(conn, cid)):
        try:
            crm_modello.aggiungi_recapito(conn, cid, "sito", sito, fonte="foglio della campagna")
        except Exception:  # noqa: BLE001 - sito non valido: resta senza
            pass


def sincronizza_foglio(conn, c: dict) -> dict:
    """Righe nuove -> contatti nuovi (o gia' esistenti) e destinatari. Righe corrette -> contatto aggiornato, senza ricominciare."""
    c = dict(c)
    try:
        mappa, righe = righe_foglio(scarica_foglio(conn, c))
    except ValueError as e:
        conn.execute("UPDATE campagne_posta SET foglio_errore=%s, foglio_letto_il=NOW() WHERE id=%s", (str(e)[:300], c["id"])); conn.commit()
        return {"errore": str(e)}
    if "ente" not in mappa and "sito" not in mappa and "email" not in mappa:
        msg = "Nel foglio non trovo le colonne: servono almeno nome, sito o email nella prima riga"
        conn.execute("UPDATE campagne_posta SET foglio_errore=%s, foglio_letto_il=NOW() WHERE id=%s", (msg, c["id"])); conn.commit()
        return {"errore": msg}
    lista = _lista(conn, c)
    nuove = aggiornate = destinatari = senza_email = 0
    for v in righe:
        email, sito, ente = v.get("email", "").lower(), v.get("sito", ""), v.get("ente", "")
        chiave = redattore.chiave_sito(sito) or ente.strip().lower() or email   # il sito o il nome: cosi' una email corretta non crea un contatto nuovo
        if not chiave:
            continue
        impronta = hashlib.sha256("|".join(f"{k}={v[k]}" for k in sorted(v)).encode()).hexdigest()[:20]
        gia = conn.execute("SELECT impronta, contatto_id FROM campagne_foglio_righe WHERE campagna_id=%s AND chiave=%s", (c["id"], chiave)).fetchone()
        if gia and gia["impronta"] == impronta:
            continue
        kid = (gia["contatto_id"] if gia else None) or _trova(conn, email, sito)
        if kid is None:
            kid = conn.execute("""INSERT INTO crm_contatti (lista_id, tipo, genere, comune, provincia, regione, ente_cifrato, email_cifrata, email_hash, note_cifrate,
                                                          azienda_id, fonte_url, importato_il)
                                  VALUES (%s,%s,'organizzazione',%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) RETURNING id""",
                               (lista, (c.get("categoria") or "altro")[:40], v.get("comune") or None, v.get("provincia") or None, v.get("regione") or None,
                                cassaforte.cifra(ente) if ente else None, cassaforte.cifra(email) if "@" in email else None,
                                crm.hash_email(email) if "@" in email else None, cassaforte.cifra(v["note"]) if v.get("note") else None,
                                c.get("azienda_id"), "foglio Google della campagna")).fetchone()["id"]
            nuove += 1
        else:   # contatto gia' noto: si aggiornano i dati che il foglio porta
            sets, par = [], []
            if "@" in email:
                sets += ["email_cifrata=%s", "email_hash=%s"]; par += [cassaforte.cifra(email), crm.hash_email(email)]
            for campo in ("comune", "provincia", "regione"):
                if v.get(campo):
                    sets.append(f"{campo}=%s"); par.append(v[campo])
            if ente:
                sets.append("ente_cifrato=%s"); par.append(cassaforte.cifra(ente))
            if sets:
                conn.execute(f"UPDATE crm_contatti SET {', '.join(sets)} WHERE id=%s", par + [kid])
            aggiornate += 1 if gia else 0
        _imposta_sito(conn, kid, sito)
        conn.execute("""INSERT INTO campagne_foglio_righe (campagna_id, chiave, impronta, contatto_id) VALUES (%s,%s,%s,%s)
                        ON CONFLICT (campagna_id, chiave) DO UPDATE SET impronta=EXCLUDED.impronta, contatto_id=EXCLUDED.contatto_id, letta_il=NOW()""",
                     (c["id"], chiave, impronta, kid))
        if "@" in email:
            destinatari += 1 if aggiungi_destinatario(conn, c["id"], kid, email) else 0
        else:
            senza_email += 1
    conn.execute("UPDATE campagne_posta SET foglio_errore='', foglio_letto_il=NOW(), foglio_righe=%s WHERE id=%s", (len(righe), c["id"]))
    conn.commit()
    return {"righe": len(righe), "nuove": nuove, "aggiornate": aggiornate, "destinatari": destinatari, "senza_email": senza_email,
            "colonne": sorted(mappa)}


# ---------- spesa ----------
def _spendi(conn, c: dict, euro: float) -> bool:
    """Aggiunge la spesa; se supera il tetto mette in pausa la campagna e avvisa. False = tetto raggiunto."""
    r = conn.execute("UPDATE campagne_posta SET spesa = spesa + %s WHERE id=%s RETURNING spesa, tetto_spesa", (round(euro, 6), c["id"])).fetchone()
    if r and r["spesa"] >= r["tetto_spesa"]:
        conn.execute("UPDATE campagne_posta SET stato='in_pausa' WHERE id=%s AND stato='in_corso'", (c["id"],))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)",
                     (f"Campagna «{c['nome']}» in pausa: ha raggiunto il tetto di spesa ({float(r['tetto_spesa']):.2f}). Alzalo nella campagna per ripartire.",))
        return False
    return True


def tetto_ok(conn, cid: int) -> bool:
    r = conn.execute("SELECT spesa < tetto_spesa AS ok FROM campagne_posta WHERE id=%s", (cid,)).fetchone()
    return bool(r and r["ok"])


# ---------- studio e bozza ----------
def _brief(conn, c: dict) -> str:
    """Il brief della campagna piu' come scrive Lorenzo (regole ed esempi dalle sue correzioni)."""
    from . import stile
    b = redattore.testo_brief(c, conn)
    s = stile.blocco(conn, c["id"])
    return b + ("\n\n" + s if s else "")



def _crea_email(conn, c: dict, d_id: int, email: str, oggetto: str, testo: str, tipo: str, automatica: bool | None = None, rispondi_a: str | None = None) -> int:
    from .campagne import _mittente
    canale, acc, mitt = _mittente(conn, c["mittente"])
    auto = c["invio_automatico"] if automatica is None else automatica
    eid = conn.execute("""INSERT INTO email_in_uscita (agente_id, canale, account_id, mittente, destinatari, oggetto, testo, oggetto_proposto, testo_proposto,
                                                       campagna_id, destinatario_id, tipo_campagna, stato, decisa_il, rispondi_a)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (redattore.agente(conn) or c["agente_id"], canale, acc, mitt, email, oggetto[:200], testo, oggetto[:200], testo, c["id"], d_id, tipo,
                        "approvata" if auto else "da_approvare", _ora() if auto else None, rispondi_a if canale == "gmail" else None)).fetchone()["id"]
    return eid


TROPPO_SIMILE = 0.5   # quota di gruppi di 3 parole in comune oltre cui due email sono «uguali» per un filtro antispam


def _recenti(conn, cid: int, tipo: str, escluso: int | None = None, n: int = 40) -> list[dict]:
    return conn.execute("""SELECT oggetto, testo FROM email_in_uscita WHERE campagna_id=%s AND tipo_campagna=%s AND stato <> 'rifiutata'
                           AND destinatario_id IS DISTINCT FROM %s ORDER BY id DESC LIMIT %s""", (cid, tipo, escluso, n)).fetchall()


def _troppo_simile(testo: str, recenti: list[dict]) -> float:
    return max((redattore.somiglianza(testo, r["testo"]) for r in recenti), default=0.0)


def _senza_saluto(t: str) -> str:
    t = re.sub(r"(?s)\n*—\nSe non desidera ricevere.*$", "", t or "").strip()
    return t.split("\n", 1)[1].strip() if "\n" in t else t


def _diversifica(conn, c: dict, k: dict, oggetto: str, testo: str, tipo: str, d_id: int) -> tuple[str, str, str, bool]:
    """Ogni email della campagna dev'essere diversa dalle altre (antispam). Il Redattore riscrive il testo per questo contatto,
    senza ripetere le email gia' scritte. Restituisce (oggetto, testo, nota, ok). Solleva ErroreFornitore se il modello non risponde."""
    recenti = _recenti(conn, c["id"], tipo, d_id)
    altre = "\n\n".join(f"- Oggetto: {r['oggetto']}\n{_senza_saluto(r['testo'])[:600]}" for r in recenti[:4]) or "(nessuna ancora)"
    n = redattore.note(conn, k["id"])
    ancora, base, base_o = "", testo, oggetto
    for giro in range(2):
        j, spesa = redattore.chiedi(conn, c["modello"], redattore.COMPITO_VARIA.format(
            brief=_brief(conn, c), oggetto=oggetto, testo=testo, ente=k["ente"] or "(senza nome)", categoria=c.get("categoria") or "(non indicata)",
            localita=_localita(k), note=(n["sintesi"] if n else "(nessuna)"), altre=altre, ancora=ancora), 1400)
        _spendi(conn, c, spesa)
        if not (isinstance(j, dict) and str(j.get("testo") or "").strip() and str(j.get("oggetto") or "").strip()):
            break
        o2, t2 = str(j["oggetto"]).strip(), str(j["testo"]).strip()
        sim = _troppo_simile(t2, recenti + [{"testo": base}])
        if sim < TROPPO_SIMILE and not redattore.QUADRE.search(o2 + t2):
            return o2, t2, "Testo riscritto per questo contatto, diverso dalle altre email.", True
        ancora = (f"\nATTENZIONE: la tua versione precedente era troppo simile ad altre email (circa {round(sim * 100)}% di frasi uguali)"
                  + (" e conteneva ancora parentesi quadre" if redattore.QUADRE.search(o2 + t2) else "") + ". Riscrivila davvero, con frasi tue.\n")
        if not tetto_ok(conn, c["id"]):
            break
    return (redattore.riempi_quadre_semplice(base_o, k), redattore.riempi_quadre_semplice(base, k),
            "Attenzione: il Redattore non e' riuscito a renderla diversa dalle altre: modificala prima di approvarla.", False)


def prepara_uno(conn, c: dict, d: dict) -> str:
    """Studio + bozza per un destinatario. Restituisce lo stato finale."""
    from .campagne import PIEDE, _componi
    k = contatto(conn, d["contatto_id"])
    if "@" not in k["email"]:
        conn.execute("UPDATE campagne_posta_dest SET stato='scartata', nota='senza email', aggiornato_il=NOW() WHERE id=%s", (d["id"],)); return "scartata"
    if not tetto_ok(conn, c["id"]):   # tetto raggiunto: la campagna si ferma e avvisa, il contatto aspetta (niente email identiche al posto di quelle scritte)
        _spendi(conn, c, 0)
        conn.commit()
        return "in_attesa"
    conn.execute("UPDATE campagne_posta_dest SET stato='in_studio', aggiornato_il=NOW() WHERE id=%s", (d["id"],)); conn.commit()
    oggetto = testo = angolo = motivo = zona = ""
    personalizzata = False
    if c["personalizza"] and k["sito"] and tetto_ok(conn, c["id"]):
        n = redattore.note(conn, k["id"])
        sito_testo, pagine = None, []
        if not redattore.note_fresche(n):
            try:
                letto = redattore.leggi_sito(k["sito"])
                sito_testo, pagine = letto["testo"], letto["pagine"]
            except redattore.ErroreSito as e:
                zona = f"Sito non letto ({e}): testo standard."
        if sito_testo or redattore.note_fresche(n):
            firma = f"\n{c['impresa']}" if c.get("impresa") else ""
            j, spesa = redattore.chiedi(conn, c["modello"], redattore.COMPITO_PRIMA.format(
                brief=_brief(conn, c), ente=k["ente"] or "(senza nome)", localita=_localita(k),
                note=n["sintesi"] if n else "(nessuna)", sito=k["sito"], testo=sito_testo or "(non riletto: valgono le note qui sopra)",
                firma=(" — " + c["impresa"]) if c.get("impresa") else ""), 1600)
            _spendi(conn, c, spesa)
            if isinstance(j, dict) and j.get("oggetto") and j.get("testo"):
                personalizzata = True
                oggetto, testo = str(j["oggetto"]).strip(), str(j["testo"]).strip()
                angolo, motivo = str(j.get("angolo") or "")[:300], str(j.get("motivo") or "")[:400]
                sc, sp = str(j.get("comune") or "").strip(), str(j.get("provincia") or "").strip()
                if sito_testo:
                    redattore.salva_note(conn, k["id"], k["sito"], str(j.get("note") or "")[:3000], sc, sp, pagine)
                elif n:
                    sc, sp = sc or n["comune_sito"], sp or n["provincia_sito"]
                esito, zona, corr = redattore.verifica_zona(k["comune"], k["provincia"], sc, sp)
                if esito != "coincide" and k["comune"] and k["comune"].lower() in testo.lower():
                    zona += " Il testo nomina comunque il luogo: controllalo."
                if corr:
                    conn.execute("""INSERT INTO crm_correzioni (contatto_id, campo, valore, motivo) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                                 (k["id"], corr["campo"], corr["valore"][:80], f"Dal sito {k['sito']}"))
            else:
                zona = "La risposta del Redattore non era leggibile: testo standard."
    if not personalizzata:
        if not (c["oggetto"] or "").strip() or not (c["testo"] or "").strip():
            conn.execute("UPDATE campagne_posta_dest SET stato='in_attesa', nota=%s, aggiornato_il=NOW() WHERE id=%s",
                         ("manca il testo standard della campagna" + (f" ({zona})" if zona else ""), d["id"]))
            conn.commit()
            return "in_attesa"
        oggetto, testo = c["oggetto"], c["testo"]
        if not zona:
            zona = "Senza sito: testo standard." if not k["sito"] else "Personalizzazione spenta: testo standard."
    # regola fissa: nessuna email uguale alle altre. Il testo standard si riscrive sempre; quella personalizzata se somiglia troppo alle altre.
    diversa = True
    if not personalizzata or _troppo_simile(testo, _recenti(conn, c["id"], "primo", d["id"])) >= TROPPO_SIMILE or redattore.QUADRE.search(oggetto + testo):
        oggetto, testo, nota_v, diversa = _diversifica(conn, c, k, oggetto, testo, "primo", d["id"])
        zona = (zona + " " if zona else "") + nota_v
    if redattore.QUADRE.search(oggetto + testo):
        resta = ", ".join(dict.fromkeys(redattore.QUADRE.findall(oggetto + testo)))[:200]
        zona = (zona + " " if zona else "") + f"Attenzione: restano da completare {resta}."
    da_vedere = bool(redattore.QUADRE.search(oggetto + testo)) or not diversa   # parti da completare o email uguale alle altre: non parte mai da sola
    if "{saluto}" not in testo:
        testo = "{saluto}\n\n" + testo
    persona = k["genere"] == "persona" or bool(k["nome"] and k["ente"])
    testo_f = _componi(testo, k["nome"], k["ente"], persona) + PIEDE
    oggetto_f = _componi(oggetto, k["nome"], k["ente"], persona)[:200]
    eid = _crea_email(conn, c, d["id"], k["email"], oggetto_f, testo_f, "primo", automatica=False if da_vedere else None)
    stato = "approvata" if c["invio_automatico"] and not da_vedere else "da_approvare"
    conn.execute("""UPDATE campagne_posta_dest SET stato=%s, email_id=%s, angolo=%s, angolo_motivo=%s, zona=%s, personalizzata=%s, passo=1, nota='', aggiornato_il=NOW()
                    WHERE id=%s""", (stato, eid, angolo, motivo, zona[:400], personalizzata, d["id"]))
    conn.commit()
    return stato


def sollecito(conn, c: dict, d: dict) -> str:
    """Dopo l'attesa senza risposta: seconda email; poi la terza solo con qualcosa di nuovo; altrimenti «nessuna risposta»."""
    from .campagne import PIEDE, _componi
    prossimo = d["passo"] + 1
    if prossimo > 1 + c["solleciti"] or not tetto_ok(conn, c["id"]):
        return chiudi_nessuna_risposta(conn, d)
    k = contatto(conn, d["contatto_id"])
    prima = conn.execute("""SELECT oggetto, testo, decisa_il FROM email_in_uscita WHERE destinatario_id=%s AND tipo_campagna='primo' AND stato='inviata'
                            ORDER BY id LIMIT 1""", (d["id"],)).fetchone()
    if prima is None or "@" not in k["email"]:
        return chiudi_nessuna_risposta(conn, d)
    n = redattore.note(conn, k["id"])
    if prossimo == 2:
        compito = redattore.SECONDA
    else:
        if not k["sito"]:
            return chiudi_nessuna_risposta(conn, d)
        try:
            compito = redattore.TERZA.format(testo=redattore.leggi_sito(k["sito"])["testo"])
        except redattore.ErroreSito:
            return chiudi_nessuna_risposta(conn, d)
    testo_prima = re.sub(r"(?s)\n\n—\n.*$", "", prima["testo"])   # senza la riga «RIMUOVI»
    for x in (k["nome"], k["email"]):   # al modello non arrivano ne' il nome della persona ne' l'indirizzo
        if x:
            testo_prima = testo_prima.replace(x, "{nome}" if x == k["nome"] else "")
    j, spesa = redattore.chiedi(conn, c["modello"], redattore.COMPITO_SOLLECITO.format(
        brief=_brief(conn, c), ente=k["ente"] or "(senza nome)", note=(n["sintesi"] if n else "(nessuna)"),
        quando=prima["decisa_il"].strftime("il %d/%m") if prima["decisa_il"] else "", oggetto=prima["oggetto"], testo_prima=testo_prima[:2500],
        compito=compito, firma=(" — " + c["impresa"]) if c.get("impresa") else ""), 1200)
    _spendi(conn, c, spesa)
    if not isinstance(j, dict) or (prossimo == 3 and not j.get("novita")) or not j.get("testo"):
        if prossimo == 2 and not (isinstance(j, dict) and j.get("testo")):   # risposta illeggibile: si riprova al giro dopo
            conn.execute("UPDATE campagne_posta_dest SET prossimo_il = NOW() + INTERVAL '6 hours' WHERE id=%s", (d["id"],)); conn.commit()
            return "inviata"
        return chiudi_nessuna_risposta(conn, d)
    testo = str(j["testo"]).strip()
    if "{saluto}" not in testo:
        testo = "{saluto}\n\n" + testo
    persona = k["genere"] == "persona" or bool(k["nome"] and k["ente"])
    oggetto = str(j.get("oggetto") or "").strip() or ("Re: " + prima["oggetto"])
    diversa, nota_v = True, ""
    if _troppo_simile(testo, _recenti(conn, c["id"], "sollecito", d["id"])) >= TROPPO_SIMILE or redattore.QUADRE.search(oggetto + testo):
        oggetto, testo, nota_v, diversa = _diversifica(conn, c, k, oggetto, testo, "sollecito", d["id"])
    eid = _crea_email(conn, c, d["id"], k["email"], _componi(oggetto, k["nome"], k["ente"], persona)[:200],
                      _componi(testo, k["nome"], k["ente"], persona) + PIEDE, "sollecito", automatica=False if not diversa else None)
    stato = "approvata" if c["invio_automatico"] and diversa else "da_approvare"
    nota = f"Sollecito {prossimo - 1}" + (f" — novità: {j.get('cosa')}" if prossimo == 3 and j.get("cosa") else "") + ("" if diversa else " — " + nota_v)
    conn.execute("UPDATE campagne_posta_dest SET stato=%s, email_id=%s, passo=%s, prossimo_il=NULL, nota=%s, aggiornato_il=NOW() WHERE id=%s",
                 (stato, eid, prossimo, nota[:400], d["id"]))
    conn.commit()
    return stato


def chiudi_nessuna_risposta(conn, d: dict) -> str:
    conn.execute("UPDATE campagne_posta_dest SET stato='nessuna_risposta', prossimo_il=NULL, aggiornato_il=NOW() WHERE id=%s", (d["id"],))
    if d.get("contatto_id"):
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'email','uscita','Campagna chiusa senza risposta','nessuna_risposta')""",
                     (d["contatto_id"],))
    conn.commit()
    return "nessuna_risposta"


# ---------- uscite: le risposte ----------
def segna_interessato(conn, d: dict, sintesi: str = "", utente_id: int | None = None, automatico: bool = True, richiamo=None, quando: str = "") -> int | None:
    """Interessato: opportunita' al primo gradino dell'imbuto, notifica, e la bozza di risposta con il link per prenotare la call."""
    c = conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.id=%s", (d["campagna_id"],)).fetchone()
    conn.execute("UPDATE campagne_posta_dest SET stato='interessato', risposta_sintesi=COALESCE(NULLIF(%s,''), risposta_sintesi), risposta_il=COALESCE(risposta_il, NOW()), aggiornato_il=NOW() WHERE id=%s",
                 (sintesi[:400], d["id"]))
    opp = d.get("opportunita_id")
    if d.get("contatto_id"):
        k = contatto(conn, d["contatto_id"])
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, da_utente_id, oggetto, esito) VALUES (%s,'email','entrata',%s,%s,'interessato')""",
                     (d["contatto_id"], utente_id, (sintesi or f"Campagna «{c['nome']}»")[:200]))
        if not opp:
            titolo = f"{k['ente'] or 'Contatto'} · {c['nome']}"[:200]
            if len(titolo) < 3:
                titolo = "Campagna"
            opp = conn.execute("""INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, azienda_id, responsabile_utente_id, prossima_azione, campagna_id)
                                  VALUES (%s,%s,'cliente','interessato',%s,%s,'Fissare la call di presentazione',%s) RETURNING id""",
                               (d["contatto_id"], titolo, c["azienda_id"], utente_id, c["id"])).fetchone()["id"]
            conn.execute("UPDATE campagne_posta_dest SET opportunita_id=%s WHERE id=%s", (opp, d["id"]))
        if richiamo:   # «ci sentiamo a marzo»: promemoria nel CRM e sull'opportunita'
            from . import imbuto
            imbuto.segna_richiamo(conn, dict(d, opportunita_id=opp), richiamo, quando or sintesi)
        conn.commit()   # prima di leggere la loro email (la lettura puo' annullare la transazione se la casella non risponde)
        if "@" in k["email"] and not conn.execute("SELECT 1 FROM email_in_uscita WHERE destinatario_id=%s AND tipo_campagna='risposta'", (d["id"],)).fetchone():
            if richiamo:
                testo = _riempi(conn, d, "{saluto}\n\nperfetto, grazie della risposta: la ricontatto " + (quando or f"il {richiamo:%d/%m}")
                                + ", come mi ha chiesto.\n\nA presto,\nLorenzo")
            else:
                testo = _bozza_risposta(conn, c, d)
            v = conn.execute("SELECT origine, casella_id, msg_id FROM posta_vaglio WHERE id=%s", (d["risposta_vaglio_id"],)).fetchone() if d.get("risposta_vaglio_id") else None
            rif = v["msg_id"] if v and v["origine"] == "gmail" and c["mittente"] == f"gmail:{v['casella_id']}" else None
            _crea_email(conn, dict(c), d["id"], k["email"], ("Re: " + (d.get("risposta_oggetto") or c["oggetto"] or "")).replace("Re: Re: ", "Re: ")[:200],
                        testo, "risposta", automatica=False, rispondi_a=rif)
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)",
                 (f"Interessato alla campagna «{c['nome']}»" + (f": {sintesi}" if sintesi else "") +
                  (f". Ha chiesto di risentirsi {quando or ''} ({richiamo:%d/%m/%Y}): promemoria nel CRM, e quel giorno ti preparo l'email." if richiamo
                   else ". Ti ho preparato la risposta con il link per la call (Campagne email)."),))
    conn.commit()
    return opp


def _bozza_risposta(conn, c, d) -> str:
    link = (c.get("link_prenotazione") or "").strip()
    base = ("{saluto}\n\ngrazie per la risposta, mi fa piacere. " +
            (f"Se le va, sentiamoci 20 minuti: può scegliere l'orario che preferisce qui:\n{link}" if link
             else "Se le va, sentiamoci 20 minuti: mi dica lei un paio di orari comodi.") + "\n\nA presto,\nLorenzo")
    if not d.get("risposta_vaglio_id"):
        return _riempi(conn, d, base)
    from . import posta_vaglio
    try:
        v = conn.execute("SELECT * FROM posta_vaglio WHERE id=%s", (d["risposta_vaglio_id"],)).fetchone()
        loro = posta_vaglio._anteprima(conn, v)[:2000] if v else ""
        t = posta_vaglio._chiedi(conn, ISTR_RISPOSTA.format(link=f"indicando questo link per prenotarla: {link}" if link else "chiedendo due orari comodi"),
                                 f"LA SUA RISPOSTA:\n{loro}", 600)   # modello locale: la risposta del cliente resta in casa
        j = redattore._json(t)
        if isinstance(j, dict) and j.get("testo") and (not link or link in j["testo"]):
            testo = str(j["testo"]).strip()
            return _riempi(conn, d, testo if "{saluto}" in testo else "{saluto}\n\n" + testo)
    except ErroreFornitore:
        pass
    return _riempi(conn, d, base)


def _riempi(conn, d, testo: str) -> str:
    from .campagne import _componi
    k = contatto(conn, d["contatto_id"])
    return _componi(testo, k["nome"], k["ente"], k["genere"] == "persona" or bool(k["nome"] and k["ente"]))


def classifica_risposte(conn, limite: int = 10) -> int:
    """La Posta legge con il modello locale le risposte ai destinatari: interessati e dubbi -> opportunita' e notifica;
    non interessati -> chiusi senza avvisare; «rimuovi» -> fuori da tutte le campagne; automatiche -> si aspetta ancora."""
    from . import posta_vaglio
    righe = conn.execute("""SELECT d.* FROM campagne_posta_dest d WHERE d.stato='risposto' AND d.risposta_sintesi='' ORDER BY d.risposta_il LIMIT %s""", (limite,)).fetchall()
    n = 0
    for d in righe:
        v = conn.execute("SELECT * FROM posta_vaglio WHERE id=%s", (d["risposta_vaglio_id"],)).fetchone() if d["risposta_vaglio_id"] else None
        try:
            testo = (posta_vaglio._anteprima(conn, v) if v else "") or (d["risposta_oggetto"] or "")
            j = redattore._json(posta_vaglio._chiedi(conn, ISTR_ESITO, f"Oggi e' il {datetime.now():%d/%m/%Y}.\nOggetto: {d['risposta_oggetto'] or ''}\n\n{testo[:2500]}", 400))
        except ErroreFornitore:
            _avvisa_se_ferma(conn, d)
            break
        if not isinstance(j, dict) or j.get("esito") not in ("interessato", "dubbio", "non_interessato", "rimuovi", "automatica"):
            continue
        sintesi = str(j.get("sintesi") or "")[:400]
        from . import imbuto
        richiamo = imbuto.valida_richiamo(j.get("richiamo")) or imbuto.data_richiamo(f"{j.get('quando') or ''} {testo[:1500]}")
        quando = str(j.get("quando") or "")[:120]
        if j["esito"] in ("interessato", "dubbio") or (richiamo and j["esito"] not in ("rimuovi", "automatica")):
            segna_interessato(conn, dict(d), sintesi, richiamo=richiamo, quando=quando)
        elif j["esito"] == "non_interessato":
            conn.execute("UPDATE campagne_posta_dest SET stato='non_interessato', risposta_sintesi=%s, prossimo_il=NULL, aggiornato_il=NOW() WHERE id=%s", (sintesi or "non interessato", d["id"]))
            if d["contatto_id"]:
                conn.execute("INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'email','entrata',%s,'non_interessato')",
                             (d["contatto_id"], sintesi[:200] or "Non interessato"))
        elif j["esito"] == "rimuovi":
            conn.execute("UPDATE campagne_posta_dest SET stato='rimosso', risposta_sintesi=%s, prossimo_il=NULL, aggiornato_il=NOW() WHERE id=%s", (sintesi or "chiede di non ricevere altre email", d["id"]))
            if d["contatto_id"]:
                conn.execute("UPDATE crm_contatti SET consenso_marketing=FALSE WHERE id=%s", (d["contatto_id"],))
                conn.execute("INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito) VALUES (%s,'email','entrata','Chiede di non ricevere altre email','non_interessato')",
                             (d["contatto_id"],))
        else:   # risposta automatica: si torna ad aspettare
            conn.execute("UPDATE campagne_posta_dest SET stato='inviata', risposta_il=NULL, risposta_oggetto=NULL, risposta_vaglio_id=NULL, nota=%s, aggiornato_il=NOW() WHERE id=%s",
                         (("Risposta automatica: " + sintesi)[:400], d["id"]))
        conn.commit()
        n += 1
    return n


def _avvisa_se_ferma(conn, d):
    if d["risposta_il"] and d["risposta_il"] < _ora() - timedelta(hours=6) and "avvisato" not in (d["nota"] or ""):
        conn.execute("UPDATE campagne_posta_dest SET nota = trim(nota || ' avvisato') WHERE id=%s", (d["id"],))
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     ("Una risposta a una campagna aspetta da piu' di 6 ore: la Posta non riesce a leggerla perche' il computer locale non risponde. La trovi in Campagne email.",))
        conn.commit()


# ---------- autonomia ----------
def autonomia(conn, cid: int) -> dict:
    """Quante delle ultime bozze Lorenzo ha approvato SENZA correzioni, di fila. L'invio automatico si accende solo da 20 in su."""
    righe = conn.execute("""SELECT stato, oggetto, testo, oggetto_proposto, testo_proposto FROM email_in_uscita
                            WHERE campagna_id=%s AND tipo_campagna IN ('primo','sollecito') AND decisa_da IS NOT NULL AND stato IN ('approvata','inviata','rifiutata')
                            ORDER BY decisa_il DESC, id DESC LIMIT %s""", (cid, SERVE_PER_AUTONOMIA)).fetchall()
    di_fila = 0
    for r in righe:
        if r["stato"] == "rifiutata" or r["testo"] != r["testo_proposto"] or r["oggetto"] != r["oggetto_proposto"]:
            break
        di_fila += 1
    return {"di_fila": di_fila, "serve": SERVE_PER_AUTONOMIA, "puo": di_fila >= SERVE_PER_AUTONOMIA}


# ---------- il giro ----------
def giro(conn) -> dict:
    """Ogni 5 minuti: foglio, studio e bozze, solleciti, risposte. Solo le campagne «in corso»."""
    fatto = {"fogli": 0, "bozze": 0, "solleciti": 0, "risposte": 0}
    for c in conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.stato='in_corso' ORDER BY c.id").fetchall():
        c = dict(c)
        if c["foglio"] and (c["foglio_letto_il"] is None or c["foglio_letto_il"] < _ora() - timedelta(minutes=FOGLIO_OGNI_MINUTI)):
            sincronizza_foglio(conn, c)
            fatto["fogli"] += 1
        for d in conn.execute("SELECT * FROM campagne_posta_dest WHERE campagna_id=%s AND stato='in_attesa' AND nota='' ORDER BY id LIMIT %s", (c["id"], PER_GIRO)).fetchall():
            c = dict(conn.execute("SELECT c.*, z.nome AS impresa FROM campagne_posta c LEFT JOIN aziende z ON z.id=c.azienda_id WHERE c.id=%s", (c["id"],)).fetchone())
            if c["stato"] != "in_corso":
                break
            try:
                prepara_uno(conn, c, dict(d))
                fatto["bozze"] += 1
            except ErroreFornitore as e:
                conn.rollback()
                conn.execute("UPDATE campagne_posta_dest SET stato='in_attesa', aggiornato_il=NOW() WHERE id=%s", (d["id"],))
                conn.commit()
                break
        for d in conn.execute("""SELECT * FROM campagne_posta_dest WHERE campagna_id=%s AND stato='inviata' AND prossimo_il IS NOT NULL AND prossimo_il <= NOW()
                                 ORDER BY prossimo_il LIMIT %s""", (c["id"], PER_GIRO)).fetchall():
            try:
                sollecito(conn, c, dict(d))
                fatto["solleciti"] += 1
            except ErroreFornitore:
                conn.rollback()
                break
    # chi era rimasto «in studio» per un'interruzione torna in coda
    conn.execute("UPDATE campagne_posta_dest SET stato='in_attesa' WHERE stato='in_studio' AND aggiornato_il < NOW() - INTERVAL '30 minutes'")
    conn.commit()
    fatto["risposte"] = classifica_risposte(conn)
    from . import imbuto
    fatto["richiami"] = imbuto.richiami(conn)
    ultimo = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave='imbuto_calendario_il'").fetchone()
    if not ultimo or ultimo["valore"] < (_ora() - timedelta(minutes=30)).isoformat():   # il calendario ogni mezz'ora
        conn.execute("""INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('imbuto_calendario_il', %s)
                        ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore""", (_ora().isoformat(),))
        conn.commit()
        fatto["call_fissate"] = imbuto.call_fissate(conn)
    fatto["call_fatte"] = imbuto.call_fatte(conn)
    fatto["quadri"] = imbuto.aggiorna_quadri(conn)
    from . import stile
    try:
        fatto["stile"] = stile.studia(conn)
    except ErroreFornitore:
        conn.rollback()
    nuove = conn.execute("""SELECT c.nome, count(*) AS n FROM email_in_uscita e JOIN campagne_posta c ON c.id=e.campagna_id
                            WHERE e.stato='da_approvare' AND e.creata_il > NOW() - INTERVAL '5 minutes' GROUP BY c.nome""").fetchall() if fatto["bozze"] or fatto["solleciti"] else []
    for x in nuove:
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Campagna «{x['nome']}»: {x['n']} email nuove da leggere e approvare.",))
    conn.commit()
    return fatto


def duplica(conn, cid: int) -> int:
    c = conn.execute("SELECT * FROM campagne_posta WHERE id=%s", (cid,)).fetchone()
    if c is None:
        raise LookupError("Campagna inesistente")
    from psycopg.types.json import Jsonb
    return conn.execute("""INSERT INTO campagne_posta (nome, obiettivo, azienda_id, agente_id, mittente, filtri, oggetto, testo, per_ora, categoria, brief, personalizza,
                                                      modello, tetto_spesa, sollecito_giorni, solleciti, link_prenotazione, copiata_da)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        ((c["nome"] + " (copia)")[:120], c["obiettivo"], c["azienda_id"], c["agente_id"], c["mittente"], Jsonb(c["filtri"] or {}), c["oggetto"], c["testo"],
                         c["per_ora"], c["categoria"], Jsonb(c["brief"] or {}), c["personalizza"], c["modello"], c["tetto_spesa"], c["sollecito_giorni"], c["solleciti"],
                         c["link_prenotazione"], cid)).fetchone()["id"]


ISTR_BRIEF = """Aiuti Lorenzo Zeppa a preparare il brief di una campagna di email personali a freddo. Dai suoi appunti ricava un brief chiaro e concreto.
Non inventare offerte o fatti che non ci sono: dove manca qualcosa lascia il campo vuoto. Rispondi SOLO con JSON:
{"destinatari": "chi sono", "occasione": "il motivo concreto per scrivere adesso", "offerta": "cosa proponiamo", "cercare": "cosa cercare sui loro siti",
 "angoli": "2-4 angoli d'attacco possibili", "evitare": "cosa non dire", "tono": "come scrivere", "categoria": "una parola: hotel, musei, sponsor..."}"""


def completa_brief(conn, cid: int, appunti: str) -> dict:
    """Il brief iniziale lo prepara un modello piu' capace (poche chiamate): Lorenzo lo corregge."""
    from .marchi import _fornitore, _modello_buono
    from .campagne import campagna
    c = dict(campagna(conn, cid))
    modello = _modello_buono(conn)
    conn.commit()
    r = fornitori.chiama_modello(_fornitore(conn, modello), modello, ISTR_BRIEF,
                                 f"Campagna: {c['nome']}\nImpresa: {c.get('impresa') or ''}\nObiettivo: {c['obiettivo']}\n\nAPPUNTI DI LORENZO:\n{appunti}", 1200)
    _spendi(conn, c, redattore.costo(conn, modello, r.token_input, r.token_output))
    j = redattore._json(r.testo)
    if not isinstance(j, dict):
        raise ValueError("La proposta di brief non era leggibile: riprova")
    conn.commit()
    return {k: str(j.get(k) or "")[:1500] for k in ("destinatari", "occasione", "offerta", "cercare", "angoli", "evitare", "tono", "categoria")}
