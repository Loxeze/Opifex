"""Copia dalla 2 le imprese del gruppo (con la loro scheda) e il CRM: liste, contatti, recapiti, categorie, relazioni, storia dei contatti
e affari (opportunita'). Si puo' rifare: ogni riga gia' copiata e' ricordata in importazioni_2 e non si duplica.
I dati cifrati restano cifrati (le due installazioni condividono la chiave della cassaforte, quindi anche le impronte delle email coincidono)."""
from psycopg.types.json import Jsonb

# (tabella, come riconoscere una riga gia' presente nella 3). Le tabelle senza "id" si copiano con ON CONFLICT DO NOTHING.
ORDINE = [
    ("aziende", "nome"),
    ("schede_impresa", None),
    ("crm_categorie", None),
    ("crm_attributi_def", None),
    ("crm_segmenti", None),
    ("crm_liste", "nome"),
    ("crm_contatti", None),
    ("crm_contatto_categorie", None),
    ("crm_contatto_imprese", None),
    ("crm_relazioni", None),
    ("crm_recapiti", None),
    ("crm_storico", None),
    ("crm_interazioni", None),
    ("crm_opportunita", None),
]
ETICHETTE = {"aziende": "imprese", "crm_contatti": "contatti", "crm_opportunita": "affari", "crm_interazioni": "storia dei contatti",
             "crm_liste": "liste", "schede_impresa": "schede d'impresa"}


def _colonne(conn, tabella: str) -> dict:
    return {r["column_name"]: r for r in conn.execute(
        """SELECT column_name, is_nullable, column_default, data_type FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s""", (tabella,)).fetchall()}


def _chiavi_esterne(conn, tabella: str) -> dict:
    """colonna -> tabella a cui punta (solo chiavi esterne a una colonna)."""
    righe = conn.execute(
        """SELECT a.attname AS colonna, cl.relname AS verso
           FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_class cl ON cl.oid = c.confrelid
           JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
           WHERE c.contype = 'f' AND t.relname = %s AND array_length(c.conkey, 1) = 1""", (tabella,)).fetchall()
    return {r["colonna"]: r["verso"] for r in righe}


def _esiste(conn, tabella: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s", (tabella,)).fetchone())


def _mappa_salvata(conn, tabella: str) -> dict:
    return {r["vecchio_id"]: r["nuovo_id"] for r in conn.execute("SELECT vecchio_id, nuovo_id FROM importazioni_2 WHERE tabella = %s", (tabella,)).fetchall()}


def _val(v):
    return Jsonb(v) if isinstance(v, (dict, list)) else v


def anteprima(src) -> dict:
    out = {}
    for t in ("aziende", "crm_contatti", "crm_opportunita"):
        try:
            out[t] = src.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"]
        except Exception:  # noqa: BLE001
            src.rollback(); out[t] = 0
    return out


def importa(conn, src) -> dict:
    utenti = {}
    try:
        dst_u = {r["email"].lower(): r["id"] for r in conn.execute("SELECT id, email FROM utenti").fetchall() if r["email"]}
        utenti = {r["id"]: dst_u.get((r["email"] or "").lower()) for r in src.execute("SELECT id, email FROM utenti").fetchall()}
    except Exception:  # noqa: BLE001
        src.rollback()
    dst_a = {r["nome"]: r["id"] for r in conn.execute("SELECT id, nome FROM agenti").fetchall()}
    agenti = {r["id"]: dst_a.get(r["nome"]) for r in src.execute("SELECT id, nome FROM agenti").fetchall()}
    copiate = {t for t, _ in ORDINE}
    mappe: dict[str, dict] = {}
    conteggi: dict[str, int] = {}
    for tabella, naturale in ORDINE:
        if not _esiste(conn, tabella):
            continue
        try:
            righe = src.execute(f"SELECT * FROM {tabella} ORDER BY 1").fetchall()
        except Exception:  # noqa: BLE001 - nella 2 la tabella puo' non esserci
            src.rollback(); continue
        col_dst = _colonne(conn, tabella)
        fk = _chiavi_esterne(conn, tabella)
        con_id = "id" in col_dst
        mappa = _mappa_salvata(conn, tabella) if con_id else {}
        mappe[tabella] = mappa
        nuove = 0
        for r in righe:
            if con_id and r["id"] in mappa:
                continue
            valori, salta = {}, False
            for k, v in r.items():
                if k == "id" or k not in col_dst:
                    continue
                if k in fk and v is not None:
                    verso = fk[k]
                    if verso == "utenti":
                        v = utenti.get(v)
                    elif verso == "agenti":
                        v = agenti.get(v)
                    elif verso in mappe and verso in copiate and "id" in _colonne(conn, verso):
                        v = mappe[verso].get(v)
                    elif verso in copiate:
                        pass                      # chiave di testo (es. categoria): il valore resta quello
                    else:
                        v = None                  # punta a qualcosa che non si copia (progetti, riunioni, reparti...)
                    if v is None and col_dst[k]["is_nullable"] == "NO":
                        salta = True; break
                valori[k] = _val(v)
            if salta:
                continue
            if con_id and naturale and r.get(naturale):
                ora = conn.execute(f"SELECT id FROM {tabella} WHERE lower({naturale}) = lower(%s) ORDER BY id LIMIT 1", (r[naturale],)).fetchone()
                if ora:
                    mappa[r["id"]] = ora["id"]
                    conn.execute("INSERT INTO importazioni_2 (tabella, vecchio_id, nuovo_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (tabella, r["id"], ora["id"]))
                    continue
            cols = list(valori)
            sql = f"INSERT INTO {tabella} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING" + (" RETURNING id" if con_id else "")
            conn.execute("SAVEPOINT riga")
            try:
                ins = conn.execute(sql, [valori[c] for c in cols])
                nuovo = ins.fetchone() if con_id else None
                conn.execute("RELEASE SAVEPOINT riga")
            except Exception:  # noqa: BLE001 - una riga che non rispetta i vincoli della 3 si salta, le altre proseguono
                conn.execute("ROLLBACK TO SAVEPOINT riga")
                continue
            if con_id:
                if nuovo is None:
                    continue
                mappa[r["id"]] = nuovo["id"]
                conn.execute("INSERT INTO importazioni_2 (tabella, vecchio_id, nuovo_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (tabella, r["id"], nuovo["id"]))
                nuove += 1
            elif ins.rowcount:
                nuove += 1
        conteggi[tabella] = nuove
    for t in ("crm_contatti", "crm_opportunita", "crm_interazioni", "crm_liste", "aziende", "crm_relazioni", "crm_recapiti", "crm_storico"):
        if _esiste(conn, t):   # i contatori delle chiavi devono superare gli id copiati
            conn.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), GREATEST((SELECT COALESCE(max(id), 1) FROM {t}), 1))")
    _plaud(conn, src)
    return conteggi


def _plaud(conn, src):
    """Il canale dei resoconti PLAUD: stesse impostazioni della 2, con la casella ritrovata dal suo indirizzo (va gia' collegata nella 3)."""
    try:
        cfg = {r["chiave"]: r["valore"] for r in src.execute("SELECT chiave, valore FROM impostazioni_sistema WHERE chiave IN ('plaud_attivo','plaud_mittente','plaud_casella_id')").fetchall()}
        email = None
        if (cfg.get("plaud_casella_id") or "").isdigit():
            r = src.execute("SELECT email FROM caselle_posta WHERE id=%s", (int(cfg["plaud_casella_id"]),)).fetchone()
            email = r["email"] if r else None
    except Exception:  # noqa: BLE001
        src.rollback(); return
    if not cfg:
        return
    gia = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave='plaud_casella_id'").fetchone()
    if gia and gia["valore"]:
        return   # nella 3 e' gia' impostato: non si tocca
    casella = conn.execute("SELECT id FROM caselle_posta WHERE lower(email)=lower(%s)", (email,)).fetchone() if email else None
    for k, v in (("plaud_mittente", cfg.get("plaud_mittente") or "plaud"), ("plaud_casella_id", str(casella["id"]) if casella else ""),
                 ("plaud_attivo", "1" if casella and cfg.get("plaud_attivo") == "1" else "0")):
        conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))


def riassunto(conteggi: dict) -> str:
    return ", ".join(f"{n} {ETICHETTE.get(t, t)}" for t, n in conteggi.items() if n and t in ETICHETTE) or "niente di nuovo"
