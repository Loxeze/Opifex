"""Email «come in Gmail» (2.69): testo formattato, link, immagini nel testo e allegati.

- Il testo formattato arriva dall'editor di Opifex come HTML e qui viene ripulito: restano solo grassetto, corsivo, sottolineato, elenchi,
  citazioni, link (http, https, mailto) e immagini interne all'email (cid:). Tutto il resto (script, stili, attributi) sparisce.
- Gli indirizzi web scritti nel testo diventano link da soli.
- Dall'HTML si ricava sempre anche la versione in testo semplice: serve all'email (chi non legge l'HTML), al confronto con la bozza del
  Redattore e all'apprendimento dello stile.
- Allegati: quelli della singola email e quelli della campagna (per esempio una brochure), che partono con ogni prima email
  e, se Lorenzo lo sceglie, anche con i solleciti. Massimo 15 MB a file e 20 MB per email.
"""
import html as _html
import re
import secrets
from html.parser import HTMLParser

MAX_FILE = 15 * 1024 * 1024
MAX_EMAIL = 20 * 1024 * 1024
TAG_OK = {"p", "br", "b", "strong", "i", "em", "u", "a", "ul", "ol", "li", "blockquote", "img", "div", "span", "h2", "h3"}
VUOTI = {"br", "img"}
_URL = re.compile(r"(?<![\"'=>/\w])((?:https?://|www\.)[^\s<>\"']+[^\s<>\"'.,;:!?)\]])", re.I)


class _Pulitore(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.aperti, self.salta = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title", "iframe", "object", "svg", "template"):
            self.salta += 1
            return
        if self.salta or tag not in TAG_OK:
            return
        a = dict(attrs)
        extra = ""
        if tag == "a":
            href = (a.get("href") or "").strip()
            if not re.match(r"(?i)^(https?://|mailto:)", href):
                return
            extra = f' href="{_html.escape(href, quote=True)}"'
        elif tag == "img":
            src = (a.get("src") or "").strip()
            cid = (a.get("data-cid") or "").strip()
            if cid and re.fullmatch(r"[\w.-]{4,80}", cid):
                src = "cid:" + cid
            if not re.fullmatch(r"cid:[\w.-]{4,80}", src):
                return
            alt = (a.get("alt") or "")[:120]
            extra = f' src="{src}" alt="{_html.escape(alt, quote=True)}" style="max-width:100%;height:auto"'
        self.out.append(f"<{tag}{extra}>")
        if tag not in VUOTI:
            self.aperti.append(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title", "iframe", "object", "svg", "template"):
            self.salta = max(0, self.salta - 1)
            return
        if self.salta or tag not in TAG_OK or tag in VUOTI or tag not in self.aperti:
            return
        while self.aperti:
            t = self.aperti.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.salta:
            self.out.append(_html.escape(data, quote=False))

    def risultato(self) -> str:
        while self.aperti:
            self.out.append(f"</{self.aperti.pop()}>")
        return "".join(self.out)


def _collega(h: str) -> str:
    """Gli indirizzi scritti nel testo (fuori dai link) diventano link."""
    pezzi = re.split(r"(<a\b[^>]*>.*?</a>|<[^>]+>)", h, flags=re.S | re.I)
    for i, p in enumerate(pezzi):
        if not p or p.startswith("<"):
            continue
        pezzi[i] = _URL.sub(lambda m: f'<a href="{_html.escape(m.group(1) if m.group(1).lower().startswith("http") else "https://" + m.group(1), quote=True)}">{m.group(1)}</a>', p)
    return "".join(pezzi)


def pulisci(h: str) -> str:
    p = _Pulitore()
    p.feed(h or "")
    p.close()
    out = _collega(p.risultato())
    out = re.sub(r"(<br>\s*){3,}", "<br><br>", out)
    return out.strip()


def in_testo(h: str) -> str:
    """La versione in testo semplice: paragrafi, elenchi e link con l'indirizzo tra parentesi."""
    t = re.sub(r"(?is)<a\b[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>",
               lambda m: m.group(2) if re.sub(r"<[^>]+>", "", m.group(2)).strip() in (_html.unescape(m.group(1)), _html.unescape(m.group(1)).replace("https://", "")) else f"{m.group(2)} ({_html.unescape(m.group(1))})", h or "")
    t = re.sub(r"(?i)<img\b[^>]*>", "[immagine]", t)
    t = re.sub(r"(?i)<li\b[^>]*>", "\n• ", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|h2|h3|blockquote|ul|ol)>", "\n\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def da_testo(t: str) -> str:
    """Un testo semplice (le bozze del Redattore) diventa HTML: paragrafi, a capo e link."""
    parti = [p for p in re.split(r"\n\s*\n", (t or "").strip()) if p.strip()]
    return _collega("".join("<p>" + _html.escape(p, quote=False).replace("\n", "<br>") + "</p>" for p in parti))


def cid_nuovo() -> str:
    return "img" + secrets.token_hex(8)


# ---------- allegati ----------
def _controlla(nome: str, dati: bytes):
    if not dati:
        raise ValueError("File vuoto")
    if len(dati) > MAX_FILE:
        raise ValueError("File troppo grande: al massimo 15 MB")
    if re.search(r"(?i)\.(exe|bat|cmd|com|scr|js|vbs|msi|jar|ps1|sh)$", nome or ""):
        raise ValueError("Questo tipo di file non si allega (programmi e script vengono bloccati dalla posta)")


def nome_pulito(nome: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\r\n]+", " ", nome or "allegato").strip()[:150] or "allegato"


def aggiungi_a_email(conn, eid: int, nome: str, mime: str, dati: bytes, inline: bool) -> dict:
    _controlla(nome, dati)
    tot = conn.execute("SELECT COALESCE(sum(dimensione), 0) AS n FROM email_allegati WHERE email_id=%s", (eid,)).fetchone()["n"]
    if tot + len(dati) > MAX_EMAIL:
        raise ValueError("Gli allegati superano 20 MB: la posta non li consegnerebbe")
    if inline and not (mime or "").startswith("image/"):
        raise ValueError("Nel testo si possono mettere solo immagini")
    return dict(conn.execute("""INSERT INTO email_allegati (email_id, nome, mime, dati, dimensione, inline, cid) VALUES (%s,%s,%s,%s,%s,%s,%s)
                                RETURNING id, nome, mime, dimensione, inline, cid""",
                             (eid, nome_pulito(nome), (mime or "application/octet-stream")[:100], dati, len(dati), inline, cid_nuovo() if inline else None)).fetchone())


def aggiungi_a_campagna(conn, cid_campagna: int, nome: str, mime: str, dati: bytes) -> dict:
    _controlla(nome, dati)
    tot = conn.execute("SELECT COALESCE(sum(dimensione), 0) AS n FROM campagne_allegati WHERE campagna_id=%s", (cid_campagna,)).fetchone()["n"]
    if tot + len(dati) > MAX_EMAIL:
        raise ValueError("Gli allegati della campagna superano 20 MB")
    return dict(conn.execute("""INSERT INTO campagne_allegati (campagna_id, nome, mime, dati, dimensione) VALUES (%s,%s,%s,%s,%s)
                                RETURNING id, nome, mime, dimensione, in_solleciti""",
                             (cid_campagna, nome_pulito(nome), (mime or "application/octet-stream")[:100], dati, len(dati))).fetchone())


def per_invio(conn, riga: dict) -> tuple[list[dict], list[dict]]:
    """(immagini nel testo, allegati) di un'email: i suoi, piu' quelli della campagna se e' una prima email (o un sollecito, se scelto)."""
    propri = conn.execute("SELECT nome, mime, dati, inline, cid FROM email_allegati WHERE email_id=%s ORDER BY id", (riga["id"],)).fetchall()
    imm = [dict(a) for a in propri if a["inline"]]
    alleg = [dict(a) for a in propri if not a["inline"]]
    if riga.get("campagna_id") and riga.get("tipo_campagna") in ("primo", "sollecito"):
        for a in conn.execute("SELECT nome, mime, dati, in_solleciti FROM campagne_allegati WHERE campagna_id=%s ORDER BY id", (riga["campagna_id"],)).fetchall():
            if riga["tipo_campagna"] == "primo" or a["in_solleciti"]:
                alleg.append(dict(a))
    return imm, alleg


def componi(m, testo: str, html: str | None, immagini: list[dict], allegati: list[dict]):
    """Mette nel messaggio (EmailMessage) testo, HTML con le immagini e allegati."""
    m.set_content(testo or in_testo(html or ""))
    if html:
        usati = set(re.findall(r'src="cid:([\w.-]+)"', html))
        m.add_alternative(f'<!doctype html><html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#222">{html}</body></html>', subtype="html")
        parte = m.get_payload()[-1]
        for i in immagini:
            if i["cid"] in usati:
                tipo, _, sotto = (i["mime"] or "image/png").partition("/")
                parte.add_related(bytes(i["dati"]), maintype=tipo, subtype=sotto or "png", cid=f"<{i['cid']}>", filename=i["nome"], disposition="inline")
    for a in allegati:
        tipo, _, sotto = (a["mime"] or "application/octet-stream").partition("/")
        m.add_attachment(bytes(a["dati"]), maintype=tipo or "application", subtype=sotto or "octet-stream", filename=a["nome"])
    return m
