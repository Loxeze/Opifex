"""Il Cerimoniere: conosce l'organizzazione leggendola dal vivo (nessuna manutenzione quando si aggiungono ruoli),
indica a chi rivolgersi, presenta il richiedente alla figura giusta e propone nuovi ruoli quando nessuno copre un bisogno.
Non svolge il lavoro: instrada."""

MAX_AGENTI = 80
SCHEDA_MINIMA = 25   # caratteri del compito sotto i quali la scheda e' considerata vaga


class ErroreCerimoniere(Exception):
    pass


def _agenti(conn) -> list[dict]:
    return conn.execute(
        """SELECT a.id, a.nome, a.ruolo, a.livello, a.rimanda_a, a.ruolo_speciale, d.nome AS divisione, s.nome AS superiore,
                  (SELECT string_agg(z.nome, ', ' ORDER BY z.nome) FROM agenti_aziende x JOIN aziende z ON z.id = x.azienda_id WHERE x.agente_id = a.id) AS aziende
           FROM agenti a LEFT JOIN divisioni d ON d.id = a.divisione_id LEFT JOIN agenti s ON s.id = a.superiore_id
           WHERE a.attivo ORDER BY d.nome NULLS FIRST, (a.livello = 'operativo'), a.nome""").fetchall()


def scheda_vaga(a: dict) -> bool:
    return len((a["ruolo"] or "").strip()) < SCHEDA_MINIMA and not a["rimanda_a"]


def _riga_agente(a: dict) -> str:
    return (f"- {a['nome']} [{a['livello']}] — " + (a["divisione"] or "trasversale") + (f" — {a['aziende']}" if a["aziende"] else "") + f" — {a['ruolo']}"
            + (f" (non si occupa di: {a['rimanda_a']})" if a["rimanda_a"] else "") + (f" · risponde a {a['superiore']}" if a["superiore"] else "")
            + (" · SCHEDA VAGA" if scheda_vaga(a) else ""))


def mappa(conn, filtro: str = "", cerimoniere_id: int | None = None) -> str:
    agenti = [a for a in _agenti(conn) if a["id"] != cerimoniere_id]
    f = (filtro or "").strip().lower()
    if f:
        agenti = [a for a in agenti if f in " ".join(str(a[k] or "") for k in ("nome", "ruolo", "rimanda_a", "divisione", "aziende")).lower()]
    righe = [_riga_agente(a) for a in agenti[:MAX_AGENTI]]
    testo = "\n".join(righe) or "Nessun agente corrisponde."
    vaghe = [a["nome"] for a in _agenti(conn) if scheda_vaga(a) and a["id"] != cerimoniere_id]
    ultimi = conn.execute("""SELECT i.id, i.bisogno, i.esito, d.nome AS dest FROM instradamenti i LEFT JOIN agenti d ON d.id = i.destinatario_agente_id
                             ORDER BY i.id DESC LIMIT 8""").fetchall()
    if ultimi:
        testo += "\n\nULTIMI INSTRADAMENTI (per imparare da cio' che e' servito):\n" + "\n".join(
            f"- #{u['id']} «{u['bisogno'][:80]}» → {u['dest'] or '?'}: {u['esito'] or 'esito non ancora noto'}" for u in ultimi)
    if vaghe:
        testo += "\n\nSCHEDE DA COMPLETARE (rendono l'agente difficile da trovare): " + ", ".join(vaghe[:15])
    return testo


def _trova(conn, nome: str) -> dict | None:
    return conn.execute("SELECT id, nome, livello, superiore_id FROM agenti WHERE attivo AND lower(nome) = lower(%s)", (nome.strip(),)).fetchone()


def presenta(conn, cerimoniere_id: int, dati: dict) -> str:
    dest = _trova(conn, str(dati.get("destinatario") or ""))
    bisogno = str(dati.get("bisogno") or "").strip()[:600]
    if dest is None:
        raise ErroreCerimoniere("Destinatario sconosciuto: usa il nome esatto dalla mappa")
    if len(bisogno) < 5:
        raise ErroreCerimoniere("Descrivi il bisogno in una frase")
    rich = _trova(conn, str(dati.get("richiedente") or "")) if dati.get("richiedente") else None
    chi = rich["nome"] if rich else "un collega"
    contesto = str(dati.get("contesto") or "").strip()[:800]
    iid = conn.execute("INSERT INTO instradamenti (richiedente_agente_id, bisogno, destinatario_agente_id, motivo) VALUES (%s,%s,%s,%s) RETURNING id",
                       (rich["id"] if rich else None, bisogno, dest["id"], str(dati.get("motivo") or "")[:400] or None)).fetchone()["id"]
    testo = f"Il Cerimoniere ti presenta {chi}: ha questo bisogno — {bisogno}." + (f" Contesto: {contesto}" if contesto else "") + \
            f" Se puoi aiutarlo, mettiti in contatto con lui (presentazione #{iid})."
    conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)", (dest["id"], testo))
    if dest["livello"] == "operativo" and dest["superiore_id"]:
        conn.execute("INSERT INTO avvisi_agente (agente_id, testo) VALUES (%s,%s)",
                     (dest["superiore_id"], f"Il Cerimoniere ha indirizzato a {dest['nome']} (tuo sottoposto) una richiesta di {chi}: {bisogno}"))
    return f"Presentazione inviata a {dest['nome']} (#{iid}). Dopo l'incontro registra se e' servita con esito_instradamento."


def proponi_ruolo(conn, cerimoniere_id: int, dati: dict) -> str:
    titolo = str(dati.get("titolo") or "").strip()[:120]
    descr = str(dati.get("descrizione") or "").strip()[:1200]
    if len(titolo) < 3 or len(descr) < 20:
        raise ErroreCerimoniere("Servono un titolo e una descrizione del ruolo (almeno 20 caratteri)")
    if conn.execute("SELECT 1 FROM proposte_ruoli WHERE stato = 'aperta' AND lower(titolo) = lower(%s)", (titolo,)).fetchone():
        raise ErroreCerimoniere("Una proposta con questo titolo e' gia' aperta")
    pid = conn.execute("INSERT INTO proposte_ruoli (titolo, descrizione, motivo, proposta_da_agente_id) VALUES (%s,%s,%s,%s) RETURNING id",
                       (titolo, descr, str(dati.get("motivo") or "")[:600] or None, cerimoniere_id)).fetchone()["id"]
    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)", (f"Il Cerimoniere propone un nuovo ruolo: {titolo}.",))
    return f"Proposta di ruolo registrata (#{pid}): la valuta Lorenzo."


def esito(conn, dati: dict) -> str:
    try:
        iid = int(dati.get("id"))
    except (TypeError, ValueError):
        raise ErroreCerimoniere("Indica il numero dell'instradamento") from None
    e = str(dati.get("esito") or "")
    if e not in ("utile", "non_utile"):
        raise ErroreCerimoniere("L'esito e' «utile» o «non_utile»")
    if conn.execute("UPDATE instradamenti SET esito = %s, nota = %s WHERE id = %s RETURNING id", (e, str(dati.get("nota") or "")[:300] or None, iid)).fetchone() is None:
        raise ErroreCerimoniere("Instradamento inesistente")
    return "Esito registrato."


STRUMENTI = [
    {"name": "proponi_regola", "description": "Proponi una regola di smistamento (es. i bandi di cultura vanno al manager di Renovatio). La approva Lorenzo prima che valga.",
     "input_schema": {"type": "object", "properties": {"quando": {"type": "string"}, "destinatario": {"type": "string"}}, "required": ["quando", "destinatario"]}},
    {"name": "mappa_organizzazione", "description": "Legge l'organizzazione dal vivo: ogni agente con dipartimento, azienda, compito, cosa non fa e a chi risponde, piu' gli ultimi instradamenti e le schede da completare. "
                                                   "filtro (facoltativo): parola da cercare nelle schede.",
     "input_schema": {"type": "object", "properties": {"filtro": {"type": "string"}}}},
    {"name": "presenta_a_manager", "description": "Presenta il richiedente alla figura giusta: la figura riceve un avviso con il bisogno e il contesto (se e' un operativo lo riceve anche il suo superiore).",
     "input_schema": {"type": "object", "properties": {"destinatario": {"type": "string"}, "richiedente": {"type": "string"}, "bisogno": {"type": "string"},
                                                       "contesto": {"type": "string"}, "motivo": {"type": "string"}}, "required": ["destinatario", "bisogno"]}},
    {"name": "proponi_ruolo", "description": "Se nessuno copre il bisogno, proponi a Lorenzo un nuovo ruolo (titolo e descrizione del compito).",
     "input_schema": {"type": "object", "properties": {"titolo": {"type": "string"}, "descrizione": {"type": "string"}, "motivo": {"type": "string"}}, "required": ["titolo", "descrizione"]}},
    {"name": "esito_instradamento", "description": "Registra se un instradamento e' stato utile, per imparare.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}, "esito": {"type": "string", "enum": ["utile", "non_utile"]}, "nota": {"type": "string"}}, "required": ["id", "esito"]}},
]

AVVISO = ("\n\nORGANIZZAZIONE: parti sempre da mappa_organizzazione (e' letta dal vivo, non fidarti della memoria). Scegli la figura in base a dipartimento, azienda, compito e a cio' che NON fa. "
          "Rispondi con: a chi rivolgersi, perche', e cosa dirgli. Se la scelta e' chiara usa presenta_a_manager. Se due figure si sovrappongono o la scheda e' vaga, segnalalo. "
          "Se nessuno copre il bisogno usa proponi_ruolo. Non svolgere il lavoro tu: instradi.")


def gestore(cerimoniere_id: int, connessione):
    def f(nome, dati):
        try:
            with connessione() as conn:
                if nome == "mappa_organizzazione":
                    return mappa(conn, str(dati.get("filtro") or ""), cerimoniere_id)
                if nome == "presenta_a_manager":
                    return presenta(conn, cerimoniere_id, dati)
                if nome == "proponi_regola":
                    from . import consegne
                    try:
                        return consegne.proponi_regola(conn, cerimoniere_id, dati)
                    except consegne.ErroreConsegna as e:
                        return "ERRORE: " + str(e)
                if nome == "proponi_ruolo":
                    return proponi_ruolo(conn, cerimoniere_id, dati)
                if nome == "esito_instradamento":
                    return esito(conn, dati)
        except ErroreCerimoniere as e:
            return "ERRORE: " + str(e)
        return "ERRORE: strumento sconosciuto"
    return f


# ---------- elenco degli agenti tenuto a memoria, aggiornato ogni giorno ----------
CH_ELENCO, CH_IL, CH_NOMI, CH_NOVITA = "cerimoniere_elenco", "cerimoniere_elenco_il", "cerimoniere_elenco_nomi", "cerimoniere_elenco_novita"
MAX_ELENCO = 150


def _imposta(conn, chiave: str, valore: str):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s, %s) ON CONFLICT (chiave) DO UPDATE SET valore = EXCLUDED.valore", (chiave, valore))


def _leggi(conn, chiave: str) -> str | None:
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave = %s", (chiave,)).fetchone()
    return r["valore"] if r else None


def aggiorna_elenco(conn) -> dict:
    """Rilegge tutti gli agenti attivi, li tiene a memoria e annota cosa e' cambiato dall'ultimo aggiornamento."""
    import json
    ag = _agenti(conn)
    ag = [a for a in ag if a["ruolo_speciale"] != "cerimoniere"][:MAX_ELENCO]
    prima = None
    try:
        prima = set(json.loads(_leggi(conn, CH_NOMI) or "null") or [])
    except ValueError:
        pass
    ora = {a["nome"] for a in ag}
    nuovi = sorted(ora - prima) if prima is not None else []
    usciti = sorted(prima - ora) if prima is not None else []
    novita = ""
    if nuovi:
        novita += "Nuovi dall'ultimo aggiornamento: " + ", ".join(nuovi) + ". "
    if usciti:
        novita += "Non piu' presenti: " + ", ".join(usciti) + ". "
    _imposta(conn, CH_ELENCO, "\n".join(_riga_agente(a) for a in ag))
    _imposta(conn, CH_NOMI, json.dumps(sorted(ora)))
    _imposta(conn, CH_NOVITA, novita.strip())
    _imposta(conn, CH_IL, conn.execute("SELECT NOW()::text AS t").fetchone()["t"])
    return {"agenti": len(ag), "nuovi": nuovi, "usciti": usciti}


def da_fare(conn) -> bool:
    il = _leggi(conn, CH_IL)
    if not il:
        return True
    return conn.execute("SELECT %s::timestamptz < NOW() - INTERVAL '20 hours' AS vecchio", (il,)).fetchone()["vecchio"]


def contesto_elenco(conn) -> str:
    """Testo che il Cerimoniere ha sempre davanti: l'elenco completo degli agenti, aggiornato al massimo di ieri."""
    if da_fare(conn):
        aggiorna_elenco(conn)
    return ("ELENCO COMPLETO DEGLI AGENTI PRESENTI (tenuto a memoria, aggiornato il " + (_leggi(conn, CH_IL) or "")[:16] + "; conoscili tutti a memoria, nome per nome):\n"
            + (_leggi(conn, CH_ELENCO) or "") + (("\n\nNOVITA': " + _leggi(conn, CH_NOVITA)) if _leggi(conn, CH_NOVITA) else ""))
