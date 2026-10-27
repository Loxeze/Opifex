"""CRM con schede: ogni contatto ha la sua storia (interazioni), le opportunita' aperte, il prossimo passo e le riunioni a cui ha partecipato.
Nomi, recapiti e note restano cifrati; solo il titolare apre le schede. Gli agenti continuano a vedere solo conteggi aggregati."""
from datetime import date, datetime, timezone

from . import cassaforte, crm, crm_modello

CANALI = ("email", "telefono", "incontro", "riunione", "messaggio", "social", "altro")
ESITI = ("nessuna_risposta", "risposto", "interessato", "non_interessato", "da_richiamare", "altro")
TIPI_OPP = ("bando", "cliente", "partnership", "sponsor", "consulenza", "altro")
STATI_OPP = ("nuova", "contattato", "in_trattativa", "vinta", "persa", "in_pausa")
APERTE = ("nuova", "contattato", "in_trattativa", "in_pausa")
NOME_RUBRICA = "Rubrica (contatti inseriti a mano)"


class ErroreScheda(Exception):
    pass


def _d(v):
    return cassaforte.decifra(v) if v else ""


def _c(v):
    v = (v or "").strip()
    return cassaforte.cifra(v) if v else None


def rubrica(conn) -> int:
    r = conn.execute("SELECT id FROM crm_liste WHERE nome = %s", (NOME_RUBRICA,)).fetchone()
    if r:
        return r["id"]
    return conn.execute("INSERT INTO crm_liste (nome, fonte, natura, base_giuridica) VALUES (%s,'inserimento manuale','personale','interesse legittimo / rapporto in corso') RETURNING id",
                        (NOME_RUBRICA,)).fetchone()["id"]


def riga(r: dict) -> dict:
    """Un contatto in forma leggibile (dati decifrati) per elenco e scheda."""
    return {"id": r["id"], "nome": _d(r["nome_cifrato"]), "ente": _d(r["ente_cifrato"]), "email": _d(r["email_cifrata"]), "telefono": _d(r["telefono_cifrato"]),
            "tipo": r["tipo"], "regione": r["regione"], "provincia": r["provincia"], "settore": r["settore"], "relazione": r["relazione"],
            "ultimo_contatto": r["ultimo_contatto"], "prossimo_passo": r["prossimo_passo"], "prossimo_passo_il": r["prossimo_passo_il"],
            "responsabile_utente_id": r["responsabile_utente_id"], "azienda_id": r["azienda_id"], "lista_id": r["lista_id"],
            "genere": r.get("genere", "organizzazione"), "comune": r.get("comune")}


def titolo(c: dict) -> str:
    return c["nome"] or c["ente"] or c["email"] or f"Contatto #{c['id']}"


def elenco(conn, q: str = "", filtro: str = "", utente_id: int | None = None, limite: int = 60) -> dict:
    """filtro: '' | 'da_ricontattare' | 'mai_contattati' | 'con_opportunita'."""
    where, par = ["TRUE"], {}
    oggi = date.today()
    if filtro == "da_ricontattare":
        where.append("c.prossimo_passo_il IS NOT NULL AND c.prossimo_passo_il <= %(oggi)s"); par["oggi"] = oggi
    elif filtro == "mai_contattati":
        where.append("c.ultimo_contatto IS NULL")
    elif filtro == "con_opportunita":
        where.append("EXISTS (SELECT 1 FROM crm_opportunita o WHERE o.contatto_id = c.id AND o.stato IN ('nuova','contattato','in_trattativa','in_pausa'))")
    righe = conn.execute(f"""SELECT c.*, (SELECT count(*) FROM crm_opportunita o WHERE o.contatto_id = c.id AND o.stato IN ('nuova','contattato','in_trattativa','in_pausa')) AS opp_aperte
                             FROM crm_contatti c WHERE {' AND '.join(where)}
                             ORDER BY c.prossimo_passo_il NULLS LAST, c.ultimo_contatto NULLS FIRST, c.id DESC LIMIT 20000""", par).fetchall()
    t = (q or "").strip().lower()
    out = []
    for r in righe:
        c = riga(r)
        if t:
            if len(t) < 2:
                raise ErroreScheda("Scrivi almeno 2 caratteri")
            if t not in " ".join((c["nome"], c["ente"], c["email"], c["telefono"], r["tipo"] or "", r["provincia"] or "", r.get("comune") or "")).lower():
                continue
        c["opp_aperte"] = r["opp_aperte"]
        out.append(c)
        if len(out) >= limite:
            break
    crm._registra(conn, None, utente_id, "elenco_titolare", {"ricerca": bool(t), "filtro": filtro}, len(out))
    cont = conn.execute("""SELECT count(*) AS totale, count(*) FILTER (WHERE prossimo_passo_il <= CURRENT_DATE) AS da_ricontattare, count(*) FILTER (WHERE ultimo_contatto IS NULL) AS mai_contattati
                           FROM crm_contatti""").fetchone()
    return {"contatti": out, "conteggi": cont}


def crea(conn, d: dict, utente_id: int) -> int:
    nome, ente, email = (d.get("nome") or "").strip(), (d.get("ente") or "").strip(), (d.get("email") or "").strip()
    if not (nome or ente):
        raise ErroreScheda("Indica almeno il nome o l'ente")
    lista = rubrica(conn)
    h = crm.hash_email(email) if email else None
    if h and conn.execute("SELECT 1 FROM crm_contatti WHERE lista_id = %s AND email_hash = %s", (lista, h)).fetchone():
        raise ErroreScheda("Esiste gia' un contatto con questa email nella rubrica")
    genere = d.get("genere") or ("organizzazione" if ente else "persona")
    if genere not in crm_modello.GENERI:
        raise ErroreScheda("Genere non valido: persona o organizzazione")
    tipo = " ".join(str(d.get("tipo") or "altro").lower().split())[:40]
    cid = conn.execute("""INSERT INTO crm_contatti (lista_id, tipo, regione, provincia, comune, settore, relazione, nome_cifrato, ente_cifrato, email_cifrata, telefono_cifrato, note_cifrate, email_hash,
                                                     responsabile_utente_id, azienda_id, genere)
                           VALUES (%s,%s,%s,%s,%s,%s,'nessuna',%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (lista, tipo, (d.get("regione") or None), (d.get("provincia") or None), (d.get("comune") or None), (d.get("settore") or None), _c(nome), _c(ente), _c(email),
                         _c(d.get("telefono")), _c(d.get("note")), h, utente_id, d.get("azienda_id"), genere)).fetchone()["id"]
    if d.get("attributi"):
        try:
            crm_modello.imposta_attributi(conn, cid, d["attributi"], utente_id)
        except crm_modello.ErroreModello as e:
            raise ErroreScheda(str(e)) from None
    return cid


def modifica(conn, cid: int, d: dict, utente_id: int | None = None):
    r = conn.execute("SELECT * FROM crm_contatti WHERE id = %s", (cid,)).fetchone()
    if r is None:
        raise LookupError("Contatto inesistente")
    cifrati = {"nome": "nome_cifrato", "ente": "ente_cifrato", "email": "email_cifrata", "telefono": "telefono_cifrato", "note": "note_cifrate"}
    sets, par = [], []
    if "genere" in d and d["genere"] not in crm_modello.GENERI:
        raise ErroreScheda("Genere non valido: persona o organizzazione")
    if d.get("genere") and d["genere"] != r["genere"] and conn.execute("SELECT 1 FROM crm_relazioni WHERE persona_id = %s OR organizzazione_id = %s", (cid, cid)).fetchone():
        raise ErroreScheda("Prima di cambiare tra persona e organizzazione togli le relazioni di questa scheda")
    for k, col in cifrati.items():
        if k in d and d[k] is not None:
            if _d(r[col]) != (d[k] or "").strip():
                crm_modello.storico(conn, cid, k, _d(r[col]) or None, (d[k] or "").strip() or None, utente_id)
            sets.append(f"{col} = %s"); par.append(_c(d[k]))
            if k == "email":
                sets.append("email_hash = %s"); par.append(crm.hash_email(d[k]) if (d[k] or "").strip() else None)
    for k in ("tipo", "regione", "provincia", "comune", "settore", "relazione", "prossimo_passo", "prossimo_passo_il", "responsabile_utente_id", "azienda_id", "genere"):
        if k in d:
            nuovo = d[k] or None
            if k == "tipo" and nuovo:
                nuovo = " ".join(str(nuovo).lower().split())[:40]
            if r.get(k) != nuovo and k in ("tipo", "regione", "provincia", "comune", "settore", "relazione", "genere"):
                crm_modello.storico(conn, cid, k, r.get(k), nuovo, utente_id)
            sets.append(f"{k} = %s"); par.append(nuovo)
    if sets:
        conn.execute(f"UPDATE crm_contatti SET {', '.join(sets)} WHERE id = %s", par + [cid])


def scheda(conn, cid: int, utente_id: int) -> dict:
    r = conn.execute("SELECT * FROM crm_contatti WHERE id = %s", (cid,)).fetchone()
    if r is None:
        raise LookupError("Contatto inesistente")
    c = riga(r)
    c["note"] = _d(r["note_cifrate"])
    c["lista"] = conn.execute("SELECT nome, natura FROM crm_liste WHERE id = %s", (r["lista_id"],)).fetchone()
    inter = conn.execute("""SELECT i.id, i.quando, i.canale, i.direzione, i.oggetto, i.esito, i.note_cifrate, i.riunione_id, i.progetto_id, p.nome AS progetto,
                                   COALESCE(u.nome, a.nome) AS da, r.titolo AS riunione
                            FROM crm_interazioni i LEFT JOIN utenti u ON u.id = i.da_utente_id LEFT JOIN agenti a ON a.id = i.da_agente_id
                                 LEFT JOIN progetti p ON p.id = i.progetto_id LEFT JOIN riunioni_importate r ON r.id = i.riunione_id
                            WHERE i.contatto_id = %s ORDER BY i.quando DESC, i.id DESC LIMIT 200""", (cid,)).fetchall()
    for i in inter:
        i["note"] = _d(i.pop("note_cifrate"))
    opp = conn.execute("""SELECT o.*, p.nome AS progetto, z.nome AS azienda, u.nome AS responsabile FROM crm_opportunita o LEFT JOIN progetti p ON p.id = o.progetto_id
                          LEFT JOIN aziende z ON z.id = o.azienda_id LEFT JOIN utenti u ON u.id = o.responsabile_utente_id WHERE o.contatto_id = %s
                          ORDER BY (o.stato IN ('vinta','persa')), o.scadenza NULLS LAST, o.id DESC""", (cid,)).fetchall()
    for o in opp:
        o["note"] = _d(o.pop("note_cifrate"))
    crm._registra(conn, None, utente_id, "scheda_titolare", {"contatto": cid}, 1)
    return {"contatto": c, "interazioni": inter, "opportunita": opp, "modello": crm_modello.dettaglio(conn, cid)}


def nuova_interazione(conn, cid: int, d: dict, utente_id: int | None = None, agente_id: int | None = None) -> int:
    if not conn.execute("SELECT 1 FROM crm_contatti WHERE id = %s", (cid,)).fetchone():
        raise LookupError("Contatto inesistente")
    canale, esito = d.get("canale"), d.get("esito") or "altro"
    if canale not in CANALI:
        raise ErroreScheda("Canale non valido")
    if esito not in ESITI:
        raise ErroreScheda("Esito non valido")
    direzione = d.get("direzione") or "uscita"
    if direzione not in ("uscita", "entrata"):
        raise ErroreScheda("Direzione non valida")
    quando = d.get("quando") or datetime.now(timezone.utc)
    i = conn.execute("""INSERT INTO crm_interazioni (contatto_id, quando, canale, direzione, da_utente_id, da_agente_id, oggetto, esito, note_cifrate, riunione_id, progetto_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                     (cid, quando, canale, direzione, utente_id, agente_id, (d.get("oggetto") or "").strip()[:200] or None, esito, _c(d.get("note")), d.get("riunione_id"), d.get("progetto_id"))).fetchone()["id"]
    if hasattr(quando, "astimezone") and getattr(quando, "tzinfo", None):
        from zoneinfo import ZoneInfo
        quando = quando.astimezone(ZoneInfo("Europe/Rome"))   # il giorno del contatto e' quello di chi lo vive, non quello UTC
    giorno = quando.date() if hasattr(quando, "date") else quando
    conn.execute("""UPDATE crm_contatti SET ultimo_contatto = GREATEST(COALESCE(ultimo_contatto, %s), %s),
                           relazione = CASE WHEN relazione = 'nessuna' THEN 'contattato' ELSE relazione END WHERE id = %s""", (giorno, giorno, cid))
    return i


def nuova_opportunita(conn, cid: int, d: dict) -> int:
    if not conn.execute("SELECT 1 FROM crm_contatti WHERE id = %s", (cid,)).fetchone():
        raise LookupError("Contatto inesistente")
    return _scrivi_opp(conn, None, cid, d)


def _scrivi_opp(conn, oid, cid, d: dict) -> int:
    tipo, stato = d.get("tipo") or "altro", d.get("stato") or "nuova"
    if tipo not in TIPI_OPP or stato not in STATI_OPP:
        raise ErroreScheda("Tipo o stato dell'opportunita' non valido")
    t = " ".join(str(d.get("titolo") or "").split())
    if not 3 <= len(t) <= 200:
        raise ErroreScheda("Il titolo deve essere tra 3 e 200 caratteri")
    val = (t, tipo, stato, d.get("valore_euro"), d.get("azienda_id"), d.get("progetto_id"), d.get("responsabile_utente_id"), (d.get("prossima_azione") or "").strip()[:300] or None,
           d.get("scadenza"), _c(d.get("note")), stato in ("vinta", "persa"))
    if oid is None:
        return conn.execute("""INSERT INTO crm_opportunita (contatto_id, titolo, tipo, stato, valore_euro, azienda_id, progetto_id, responsabile_utente_id, prossima_azione, scadenza, note_cifrate, chiusa_il)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN NOW() END) RETURNING id""", (cid, *val)).fetchone()["id"]
    conn.execute("""UPDATE crm_opportunita SET titolo=%s, tipo=%s, stato=%s, valore_euro=%s, azienda_id=%s, progetto_id=%s, responsabile_utente_id=%s, prossima_azione=%s, scadenza=%s,
                           note_cifrate=%s, chiusa_il = CASE WHEN %s THEN COALESCE(chiusa_il, NOW()) END WHERE id=%s""", (*val, oid))
    return oid


def modifica_opportunita(conn, oid: int, d: dict):
    r = conn.execute("SELECT * FROM crm_opportunita WHERE id = %s", (oid,)).fetchone()
    if r is None:
        raise LookupError("Opportunita' inesistente")
    base = {**r, "note": _d(r["note_cifrate"]), **{k: v for k, v in d.items()}}
    _scrivi_opp(conn, oid, r["contatto_id"], base)


def pipeline(conn, utente_id: int) -> dict:
    righe = conn.execute("""SELECT o.id, o.titolo, o.tipo, o.stato, o.valore_euro, o.scadenza, o.prossima_azione, o.contatto_id, p.nome AS progetto, z.nome AS azienda,
                                   c.nome_cifrato, c.ente_cifrato, c.email_cifrata
                            FROM crm_opportunita o JOIN crm_contatti c ON c.id = o.contatto_id LEFT JOIN progetti p ON p.id = o.progetto_id LEFT JOIN aziende z ON z.id = o.azienda_id
                            WHERE o.stato IN ('nuova','contattato','in_trattativa','in_pausa') OR o.chiusa_il > NOW() - interval '60 days'
                            ORDER BY o.scadenza NULLS LAST, o.id DESC LIMIT 400""").fetchall()
    for r in righe:
        r["contatto"] = _d(r.pop("nome_cifrato")) or _d(r.pop("ente_cifrato", None)) or _d(r.pop("email_cifrata", None))
        r.pop("ente_cifrato", None); r.pop("email_cifrata", None)
    crm._registra(conn, None, utente_id, "pipeline_titolare", {}, len(righe))
    colonne = {s: [r for r in righe if r["stato"] == s] for s in STATI_OPP}
    tot = {s: float(sum((r["valore_euro"] or 0) for r in colonne[s])) for s in STATI_OPP}
    return {"colonne": colonne, "totali": tot}


def promemoria(conn) -> int:
    """Una notifica al giorno con i contatti da ricontattare e le opportunita' in scadenza. Ritorna quante cose segnala."""
    oggi = date.today().isoformat()
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = 'crm_promemoria_il'").fetchone()
    if r and r["valore"] == oggi:
        return 0
    n_c = conn.execute("SELECT count(*) AS n FROM crm_contatti WHERE prossimo_passo_il <= CURRENT_DATE").fetchone()["n"]
    n_o = conn.execute("SELECT count(*) AS n FROM crm_opportunita WHERE stato IN ('nuova','contattato','in_trattativa') AND scadenza <= CURRENT_DATE + 3").fetchone()["n"]
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('crm_promemoria_il', %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (oggi,))
    if n_c or n_o:
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     (f"CRM: {n_c} contatti da ricontattare" + (f" e {n_o} opportunità in scadenza entro 3 giorni" if n_o else "") + ". Li trovi in CRM → Da ricontattare.",))
    return n_c + n_o
