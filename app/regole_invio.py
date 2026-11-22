"""Regole di invio delle campagne (2.72): meno respingimenti, meno spam, niente doppioni, momento giusto.

- Controllo dell'indirizzo PRIMA di scrivere: se il dominio non esiste o non riceve posta, il contatto e' respinto subito
  (bloccato come in 2.71) senza spendere token per la bozza.
- Non contattare due volte: se la stessa persona, o la stessa azienda (stesso dominio di lavoro), e' gia' in un'altra campagna
  in corso, ha ricevuto un'email da poco o ha risposto da poco, qui la si salta.
- Stagionalita': ogni campagna puo' avere un periodo da evitare (per le cantine, di serie, la vendemmia: 20 agosto - 31 ottobre).
  In quel periodo non parte nulla; le bozze si possono preparare e approvare.
- Orari migliori: le email partono solo in una fascia oraria (ora italiana) e, di serie, nei giorni feriali.
  La fascia di serie dipende dalla categoria (cantine la mattina presto); quando ci sono abbastanza risposte,
  Opifex suggerisce la fascia in cui quella categoria risponde di piu'.
- Riscaldamento delle caselle nuove: una casella appena creata parte da 20 email al giorno e sale fino al tetto in 10 giorni.
"""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROMA = ZoneInfo("Europe/Rome")
GIORNI_DOPPIONE = 60      # un'email ricevuta da un'altra campagna negli ultimi 60 giorni: qui si salta
GIORNI_RISPOSTA = 120     # ha risposto (anche no) negli ultimi 120 giorni: qui si salta
RAMPA = [20, 30, 45, 65, 90, 120, 160, 210, 260, 300]
PUBBLICI = {"gmail.com", "googlemail.com", "libero.it", "hotmail.com", "hotmail.it", "outlook.com", "outlook.it", "live.com", "live.it", "yahoo.com", "yahoo.it",
            "icloud.com", "me.com", "alice.it", "tin.it", "tiscali.it", "virgilio.it", "fastwebnet.it", "email.it", "aruba.it", "pec.it", "legalmail.it",
            "postecert.it", "inwind.it", "gmx.com", "gmx.it", "protonmail.com", "proton.me", "msn.com", "teletu.it", "vodafone.it", "katamail.com"}

# categoria (parole) -> (ora di inizio, ora di fine, periodo da evitare MM-DD, MM-DD)
DI_SERIE = [
    (r"cantin|vin[io]|enolog|viticolt|agrituris|frantoi|oleific", (8, 11, "08-20", "10-31")),
    (r"hotel|albergh|resort|b&b|turis|ristorant", (9, 12, "", "")),
    (r"muse|comun|ente|fondazion|universit|bibliotec|archivi|scuol|gal\b|pubblic", (9, 13, "", "")),
]
FASCIA_BASE = (9, 17, "", "")


def di_serie(categoria: str) -> dict:
    for pat, v in DI_SERIE:
        if re.search(pat, categoria or "", re.I):
            break
    else:
        v = FASCIA_BASE
    return {"ore_dal": v[0], "ore_al": v[1], "evita_dal": v[2], "evita_al": v[3]}


def adesso() -> datetime:
    return datetime.now(ROMA)


# ---------- prima di scrivere ----------
def dominio(email: str) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().lower()


_DOMINI: dict = {}   # email cifrata -> dominio (decifrare migliaia di righe a ogni bozza costerebbe troppo)


def gia_contattato(conn, c: dict, d: dict, email: str) -> str:
    """Il motivo per saltarlo, oppure ''. Guarda le ALTRE campagne: stessa persona (contatto o email) o stessa azienda (dominio di lavoro)."""
    from . import crm
    h = crm.hash_email(email)
    righe = conn.execute(f"""SELECT x.stato, x.inviata_il, x.risposta_il, x.aggiornato_il, p.nome, p.stato AS stato_campagna
                             FROM campagne_posta_dest x JOIN campagne_posta p ON p.id=x.campagna_id
                             WHERE x.campagna_id <> %s AND (x.email_hash=%s {"OR x.contatto_id=%s" if d.get("contatto_id") else ""})""",
                         [c["id"], h] + ([d["contatto_id"]] if d.get("contatto_id") else [])).fetchall()
    dom = dominio(email)
    if dom and dom not in PUBBLICI:   # stessa azienda: altri contatti con lo stesso dominio di lavoro
        from . import cassaforte
        for r in conn.execute("""SELECT x.stato, x.inviata_il, x.risposta_il, x.aggiornato_il, p.nome, p.stato AS stato_campagna, k.email_cifrata
                                 FROM campagne_posta_dest x JOIN campagne_posta p ON p.id=x.campagna_id JOIN crm_contatti k ON k.id=x.contatto_id
                                 WHERE x.campagna_id <> %s AND x.stato IN ('inviata','risposto','interessato','non_interessato','rimosso','approvata','da_approvare')
                                   AND COALESCE(x.inviata_il, x.aggiornato_il) > NOW() - make_interval(days => %s)
                                   AND k.email_cifrata IS NOT NULL AND k.id IS DISTINCT FROM %s""", (c["id"], GIORNI_DOPPIONE, d.get("contatto_id"))).fetchall():
            chiave = r["email_cifrata"][:80]
            if chiave not in _DOMINI:
                try:
                    _DOMINI[chiave] = dominio(cassaforte.decifra(r["email_cifrata"]))
                except Exception:  # noqa: BLE001
                    _DOMINI[chiave] = ""
            if _DOMINI[chiave] == dom:
                righe.append(r)
    ora = datetime.now(ROMA)
    for r in righe:
        if r["stato"] in ("risposto", "interessato", "non_interessato", "rimosso") and r["risposta_il"] and r["risposta_il"] > ora - timedelta(days=GIORNI_RISPOSTA):
            return f"ha gia' risposto a «{r['nome']}»"
        if r["stato"] in ("approvata", "da_approvare", "in_studio") and r["stato_campagna"] in ("in_corso", "bozza", "in_pausa"):
            return f"gia' in lavorazione in «{r['nome']}»"
        if r["inviata_il"] and r["inviata_il"] > ora - timedelta(days=GIORNI_DOPPIONE):
            return f"ha gia' ricevuto un'email da «{r['nome']}» il {r['inviata_il'].astimezone(ROMA):%d/%m}"
    return ""


def prima_di_scrivere(conn, c: dict, d: dict, email: str) -> str | None:
    """None se si puo' scrivere; altrimenti lo stato in cui e' finito il destinatario ('respinto' o 'scartata')."""
    from . import respinte
    if respinte.dominio_ok(email) is False:
        respinte.segna(conn, d["id"], f"il dominio {dominio(email)} non esiste o non riceve posta (controllato prima di scrivere)")
        conn.commit()
        return "respinto"
    perche = gia_contattato(conn, c, d, email)
    if perche:
        conn.execute("UPDATE campagne_posta_dest SET stato='scartata', nota=%s, aggiornato_il=NOW() WHERE id=%s", (("Saltato: " + perche)[:400], d["id"]))
        conn.commit()
        return "scartata"
    return None


# ---------- quando si puo' inviare ----------
def _mmdd(v: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", v or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def in_stagione_da_evitare(c: dict, quando: datetime | None = None) -> bool:
    a, b = _mmdd(c.get("evita_dal") or ""), _mmdd(c.get("evita_al") or "")
    if not a or not b:
        return False
    q = (quando or adesso())
    oggi = (q.month, q.day)
    return a <= oggi <= b if a <= b else (oggi >= a or oggi <= b)


def fuori_orario(c: dict, quando: datetime | None = None) -> bool:
    q = (quando or adesso())
    if c.get("solo_feriali", True) and q.weekday() >= 5:
        return True
    dal, al = c.get("ore_dal"), c.get("ore_al")
    if dal is None or al is None:
        return False
    return not (dal <= q.hour < al)


def perche_non_parte(c: dict, quando: datetime | None = None) -> str:
    if in_stagione_da_evitare(c, quando):
        return f"periodo da evitare ({c['evita_dal']} → {c['evita_al']})"
    if fuori_orario(c, quando):
        return f"fuori dalla fascia oraria ({c.get('ore_dal')}-{c.get('ore_al')}" + (", giorni feriali" if c.get("solo_feriali", True) else "") + ")"
    return ""


# ---------- riscaldamento ----------
def riscaldamento(conn, mittente: str) -> int | None:
    """Il tetto di oggi per una casella in riscaldamento, o None se la casella non e' in riscaldamento (o ha finito)."""
    r = conn.execute("SELECT dal FROM caselle_riscaldamento WHERE mittente=%s", (mittente,)).fetchone()
    if r is None:
        return None
    giorni = (adesso().date() - r["dal"]).days
    if giorni >= len(RAMPA):
        return None
    return RAMPA[max(0, giorni)]


def imposta_riscaldamento(conn, mittente: str, acceso: bool):
    if acceso:
        conn.execute("INSERT INTO caselle_riscaldamento (mittente, dal) VALUES (%s, %s) ON CONFLICT (mittente) DO NOTHING", (mittente, adesso().date()))
    else:
        conn.execute("DELETE FROM caselle_riscaldamento WHERE mittente=%s", (mittente,))


# ---------- ore migliori dai dati ----------
def ore_migliori(conn, categoria: str, minimo_invii: int = 100, minimo_risposte: int = 10) -> dict | None:
    """Fascia di 3 ore in cui questa categoria risponde di piu' (sulle email gia' partite). None se i dati sono ancora pochi."""
    if not (categoria or "").strip():
        return None
    righe = conn.execute("""SELECT extract(hour FROM d.inviata_il AT TIME ZONE 'Europe/Rome')::int AS ora, count(*) AS n,
                                   count(*) FILTER (WHERE d.stato IN ('risposto','interessato','non_interessato')) AS r
                            FROM campagne_posta_dest d JOIN campagne_posta c ON c.id=d.campagna_id
                            WHERE lower(c.categoria)=lower(%s) AND d.inviata_il IS NOT NULL GROUP BY 1""", (categoria.strip(),)).fetchall()
    tot, risp = sum(x["n"] for x in righe), sum(x["r"] for x in righe)
    if tot < minimo_invii or risp < minimo_risposte:
        return None
    per = {x["ora"]: (x["n"], x["r"]) for x in righe}
    migliore, tasso = None, -1.0
    for h in range(6, 20):
        n = sum(per.get(h + i, (0, 0))[0] for i in range(3))
        r = sum(per.get(h + i, (0, 0))[1] for i in range(3))
        if per.get(h, (0, 0))[0] and n >= max(15, tot // 10) and r / n > tasso:
            migliore, tasso = h, r / n
    if migliore is None:
        return None
    return {"ore_dal": migliore, "ore_al": migliore + 3, "tasso": round(tasso * 100), "media": round(risp * 100 / tot), "invii": tot}


def oggi() -> date:
    return adesso().date()
