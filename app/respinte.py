"""Email respinte (2.71).

Quando un'email di campagna torna indietro («indirizzo inesistente», «user unknown», 550...), l'indirizzo viene BLOCCATO per sempre,
in tutte le campagne: niente solleciti, niente nuove email, niente token spesi. Protegge la reputazione della casella da cui partono.

Due modi in cui ce ne accorgiamo:
- il server rifiuta subito l'invio (errore permanente all'invio);
- arriva dopo un avviso di mancata consegna (mailer-daemon, postmaster): la Posta lo legge e ne ricava l'indirizzo.
I rifiuti temporanei (casella piena, server occupato, «riproveremo») NON bloccano.

Se la campagna ha l'opzione «cerca un'email nuova» accesa (spenta di serie: per le liste di poco valore non conviene spendere),
il Ricercatore contatti cerca online un altro indirizzo di lavoro per quell'ente, verifica che il dominio riceva posta,
aggiorna il CRM e rimette il contatto in coda nella stessa campagna."""
import re
import socket

from . import cassaforte, crm

MITTENTI = re.compile(r"^(mailer-daemon|postmaster|mail-daemon|mailerdaemon|bounce[s]?|returned|noreply-dmarc)@", re.I)
OGGETTI = re.compile(r"(delivery status notification|undeliver|undelivered|mail delivery (failed|subsystem)|returned mail|delivery (has )?failed|failure notice|"
                     r"non recapitat|mancato recapito|impossibile recapitare|messaggio non consegnato|notifica sullo stato della consegna|address not found|"
                     r"rejected|nicht zustellbar|non remis)", re.I)
TEMPORANEA = re.compile(r"(temporar|mailbox (is )?full|over quota|quota exceeded|casella piena|spazio esaurito|riprover|will (retry|try again)|"
                        r"delayed|ritardat|still trying|4\.\d\.\d|greylist)", re.I)
PERMANENTE = re.compile(r"(user unknown|unknown user|no such user|does not exist|doesn'?t exist|address not found|couldn'?t be found|not found|"
                        r"inesistente|non esiste|recipient rejected|invalid recipient|mailbox unavailable|account (is )?disabled|"
                        r"5\.1\.1|5\.1\.10|5\.2\.1|5\.4\.1|550|553|554|domain .{0,40}(not|does not) (exist|found)|nxdomain|host not found)", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _imp(conn, k, d=""):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return r["valore"] if r and r["valore"] is not None else d


def _scrivi(conn, k, v):
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))


def e_avviso(mittente: str, oggetto: str) -> bool:
    from .posta_vaglio import _indirizzo
    return bool(MITTENTI.match(_indirizzo(mittente) or "")) or bool(OGGETTI.search(oggetto or ""))


def permanente(testo: str) -> bool:
    """Rifiuto definitivo? Le parole dei rifiuti temporanei vincono: nel dubbio non si blocca."""
    t = testo or ""
    return bool(PERMANENTE.search(t)) and not TEMPORANEA.search(t)


def bloccata(conn, email_o_hash: str) -> bool:
    h = email_o_hash if "@" not in (email_o_hash or "") else crm.hash_email(email_o_hash)
    return bool(conn.execute("SELECT 1 FROM email_bloccate WHERE email_hash=%s", (h,)).fetchone())


def hash_bloccati(conn) -> set:
    return {r["email_hash"] for r in conn.execute("SELECT email_hash FROM email_bloccate").fetchall()}


def segna(conn, dest_id: int, motivo: str) -> bool:
    """Il destinatario e' respinto: indirizzo bloccato ovunque, solleciti annullati, storia nel CRM; se la campagna lo prevede, si cerca un'email nuova."""
    d = conn.execute("""SELECT d.*, c.nome AS campagna, c.cerca_email_nuova FROM campagne_posta_dest d JOIN campagne_posta c ON c.id=d.campagna_id
                        WHERE d.id=%s""", (dest_id,)).fetchone()
    if d is None or d["stato"] == "respinto":
        return False
    motivo = re.sub(r"\s+", " ", motivo or "").strip()[:300] or "indirizzo respinto"
    conn.execute("""INSERT INTO email_bloccate (email_hash, contatto_id, campagna_id, motivo) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (email_hash) DO NOTHING""", (d["email_hash"], d["contatto_id"], d["campagna_id"], motivo))
    cerca = "da_cercare" if d["cerca_email_nuova"] and d["contatto_id"] else ""
    conn.execute("""UPDATE campagne_posta_dest SET stato='respinto', prossimo_il=NULL, ricerca_email=%s, nota=trim(%s), aggiornato_il=NOW() WHERE id=%s""",
                 (cerca, "Respinta: " + motivo[:200], dest_id))
    # lo stesso indirizzo in altre campagne: niente piu' email nemmeno li'
    conn.execute("""UPDATE campagne_posta_dest d SET stato='respinto', prossimo_il=NULL, nota=%s, aggiornato_il=NOW()
                    WHERE email_hash=%s AND id<>%s AND stato IN ('in_attesa','in_studio','da_approvare','approvata','inviata','errore')""",
                 ("Indirizzo respinto in un'altra campagna", d["email_hash"], dest_id))
    conn.execute("""UPDATE email_in_uscita SET stato='rifiutata', errore='indirizzo respinto' WHERE stato IN ('da_approvare','approvata','errore')
                    AND destinatario_id IN (SELECT id FROM campagne_posta_dest WHERE email_hash=%s)""", (d["email_hash"],))
    if d["contatto_id"]:
        conn.execute("""INSERT INTO crm_interazioni (contatto_id, canale, direzione, oggetto, esito, note_cifrate) VALUES (%s,'email','entrata',%s,'altro',%s)""",
                     (d["contatto_id"], "Email respinta: indirizzo non valido", cassaforte.cifra(f"Campagna «{d['campagna']}»: {motivo}")))
    return True


def _dest_per_email(conn, email: str) -> list[dict]:
    return conn.execute("""SELECT id FROM campagne_posta_dest WHERE email_hash=%s AND stato IN ('inviata','approvata','errore','nessuna_risposta')
                           ORDER BY inviata_il DESC NULLS LAST""", (crm.hash_email(email),)).fetchall()


def dopo_errore_invio(conn, riga: dict, errore: str) -> bool:
    """Il server ha rifiutato subito l'invio: se il rifiuto riguarda il destinatario ed e' definitivo, si blocca."""
    if not riga.get("destinatario_id") or not permanente(errore):
        return False
    if re.search(r"(auth|login|password|credenzial|token|quota giornaliera|daily (user )?sending quota|rate limit|too many)", errore or "", re.I):
        return False   # problema della NOSTRA casella, non dell'indirizzo
    return segna(conn, riga["destinatario_id"], "rifiutata all'invio: " + errore)


def giro(conn, limite: int = 200) -> int:
    """Legge gli avvisi di mancata consegna arrivati nelle caselle e blocca gli indirizzi respinti in modo definitivo."""
    from . import posta_vaglio
    ultimo = int(_imp(conn, "respinte_ultima_posta", "0") or 0)
    righe = conn.execute("""SELECT id, origine, casella_id, msg_id, mittente, oggetto FROM posta_vaglio WHERE id > %s AND NOT da_me ORDER BY id LIMIT %s""",
                         (ultimo, limite)).fetchall()
    if not righe:
        return 0
    mie = posta_vaglio._mie(conn)
    n = 0
    for r in righe:
        ultimo = r["id"]
        if not e_avviso(r["mittente"], r["oggetto"]):
            continue
        testo = posta_vaglio._anteprima(conn, dict(r)) or ""
        if not permanente(f"{r['oggetto']}\n{testo}"):
            continue
        visti = set()
        for e in EMAIL.findall(testo):
            e = e.lower().strip(".'")
            if e in visti or e in mie or MITTENTI.match(e):
                continue
            visti.add(e)
            for d in _dest_per_email(conn, e):
                m = PERMANENTE.search(testo)
                if segna(conn, d["id"], f"avviso di mancata consegna ({m.group(0) if m else 'indirizzo non valido'})"):
                    n += 1
    _scrivi(conn, "respinte_ultima_posta", str(ultimo))
    if n:
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                     (f"Campagne email: {n} indirizz{'o' if n == 1 else 'i'} respint{'o' if n == 1 else 'i'} (inesistenti). Bloccat{'o' if n == 1 else 'i'}: non riceveranno altre email.",))
    conn.commit()
    return n


# ---------- il dominio riceve posta? ----------
_CACHE_DOMINI: dict = {}


def dominio_ok(email: str) -> bool | None:
    """True se il dominio ha un server di posta (MX, o almeno un indirizzo), False se non esiste, None se non si puo' sapere (rete)."""
    dom = (email or "").rsplit("@", 1)[-1].strip().lower().rstrip(".")
    if not dom or "." not in dom:
        return False
    if dom in _CACHE_DOMINI:
        return _CACHE_DOMINI[dom]
    esito = None
    try:
        import dns.resolver   # dnspython
        try:
            esito = bool(dns.resolver.resolve(dom, "MX", lifetime=6))
        except (dns.resolver.NXDOMAIN,):
            esito = False
        except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            try:
                esito = bool(dns.resolver.resolve(dom, "A", lifetime=6))
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
                esito = False
        except Exception:  # noqa: BLE001 - timeout o rete: non si sa
            esito = None
    except ImportError:
        try:
            socket.getaddrinfo(dom, 25)
            esito = True
        except socket.gaierror as e:
            esito = False if e.errno in (socket.EAI_NONAME,) else None
        except OSError:
            esito = None
    if esito is not None:
        _CACHE_DOMINI[dom] = esito
    return esito
