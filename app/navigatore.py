"""Browser sul server per leggere siti (anche con login). Sola lettura.

Sicurezza:
- le credenziali sono decifrate solo qui e digitate dal browser: il modello AI non le vede mai
- ogni pagina resta nel dominio del sito collegato; altri domini sono rifiutati
- niente invio di moduli tranne il login e il campo di ricerca; nessun clic arbitrario
- limite di pagine per esecuzione e pausa tra una pagina e l'altra
"""
import ipaddress
import time
from urllib.parse import urljoin, urlparse

from .config import impostazioni

TESTO_MAX = 7000
PAUSA_SECONDI = 1.5
SELETTORI_CAPTCHA = ("iframe[src*='recaptcha']", "iframe[src*='hcaptcha']", "[class*='captcha' i]", "[id*='captcha' i]")


class ErroreNavigazione(Exception):
    pass


def _host_ammesso(host: str) -> bool:
    if not host:
        return False
    if impostazioni.consenti_localhost_prova and host in ("127.0.0.1", "localhost"):
        return True
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global  # rifiuta indirizzi privati, loopback, link-local
    except ValueError:
        return "." in host


def _nel_dominio(host: str, dominio: str) -> bool:
    return host == dominio or host.endswith("." + dominio)


class Navigatore:
    def __init__(self, siti: list[dict], max_pagine: int | None = None):
        """siti: [{dominio, url_login, utente, password}] gia' decifrati."""
        self.siti = {s["dominio"]: s for s in siti}
        for d in self.siti:
            if not _host_ammesso(d):
                raise ErroreNavigazione(f"Dominio non ammesso: {d}")
        self.max_pagine = max_pagine or min(s.get("max_pagine", 12) for s in siti)
        self.pagine_aperte = 0
        self.urls_visitati: list[str] = []
        self.collegato: set[str] = set()
        self.links: list[dict] = []
        self._ultimo = 0.0
        self._pw = self._browser = self._ctx = self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._ctx = self._browser.new_context(accept_downloads=False, java_script_enabled=True,
                                              locale="it-IT", viewport={"width": 1280, "height": 900})
        self._ctx.set_default_timeout(20000)
        self.page = self._ctx.new_page()
        return self

    def __exit__(self, *a):
        for oggetto in (self._ctx, self._browser):
            try:
                oggetto.close()
            except Exception:
                pass
        try:
            self._pw.stop()
        except Exception:
            pass

    # --- utilita'
    def _dominio_di(self, url: str) -> str:
        host = (urlparse(url).hostname or "").lower()
        for d in self.siti:
            if _nel_dominio(host, d):
                return d
        raise ErroreNavigazione("Sito non collegato a questo agente: " + (host or url))

    def _pausa(self):
        attesa = PAUSA_SECONDI - (time.time() - self._ultimo)
        if attesa > 0:
            time.sleep(attesa)
        self._ultimo = time.time()

    def _vai(self, url: str):
        if self.pagine_aperte >= self.max_pagine:
            raise ErroreNavigazione(f"Limite di {self.max_pagine} pagine per esecuzione raggiunto")
        if urlparse(url).scheme not in ("http", "https"):
            raise ErroreNavigazione("Solo indirizzi http/https")
        self._dominio_di(url)
        self._pausa()
        self.pagine_aperte += 1
        try:
            self.page.goto(url, wait_until="domcontentloaded")
            try:
                self.page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
        except Exception as e:
            raise ErroreNavigazione("Pagina non raggiungibile: " + str(e)[:120])
        self._dominio_di(self.page.url)  # dopo eventuali reindirizzamenti: ancora nel sito?
        self.urls_visitati.append(self.page.url)

    def _campo_visibile(self, selettore: str):
        loc = self.page.locator(selettore)
        for i in range(min(loc.count(), 10)):
            if loc.nth(i).is_visible():
                return loc.nth(i)
        return None

    # --- accesso
    def accedi(self, dominio: str):
        if dominio in self.collegato:
            return
        s = self.siti[dominio]
        self._vai(s["url_login"])
        for sel in SELETTORI_CAPTCHA:
            if self.page.locator(sel).count():
                raise ErroreNavigazione("Il sito richiede un CAPTCHA: l'accesso automatico non e' possibile")
        pw = self._campo_visibile("input[type=password]")
        if pw is None:
            raise ErroreNavigazione("Modulo di accesso non trovato nella pagina")
        utente = self._campo_visibile("input[type=email], input[name*=mail i], input[name*=user i], input[name*=login i], input[type=text]")
        if utente is None:
            raise ErroreNavigazione("Campo utente/email non trovato")
        utente.fill(s["utente"])
        pw.fill(s["password"])
        invio = self.page.locator("form:has(input[type=password]) :is(button[type=submit], input[type=submit])")
        try:
            if invio.count():
                invio.first.click()
            else:
                pw.press("Enter")
            self.page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        self._pausa()
        self._dominio_di(self.page.url)
        if self._campo_visibile("input[type=password]") is not None:
            raise ErroreNavigazione("Accesso non riuscito: credenziali errate o modulo diverso dal previsto")
        self.collegato.add(dominio)

    # --- strumenti dell'agente
    def _descrizione(self) -> str:
        testo = self.page.inner_text("body")
        testo = "\n".join(r.strip() for r in testo.splitlines() if r.strip())[:TESTO_MAX]
        dominio = self._dominio_di(self.page.url)
        trovati, visti = [], set()
        for a in self.page.locator("a[href]").all()[:300]:
            try:
                href = urljoin(self.page.url, a.get_attribute("href") or "")
                nome = " ".join((a.inner_text() or "").split())[:80]
            except Exception:
                continue
            host = (urlparse(href).hostname or "").lower()
            if not nome or href in visti or urlparse(href).scheme not in ("http", "https") or not _nel_dominio(host, dominio):
                continue
            visti.add(href); trovati.append({"testo": nome, "url": href})
            if len(trovati) >= 40:
                break
        self.links = trovati
        elenco = "\n".join(f"[{i}] {l['testo']}" for i, l in enumerate(trovati))
        return f"URL: {self.page.url}\n\nTESTO DELLA PAGINA:\n{testo}\n\nLINK (usa segui_link con il numero):\n{elenco}"

    def apri_pagina(self, url: str) -> str:
        dominio = self._dominio_di(url)
        if self.siti[dominio].get("utente"):
            self.accedi(dominio)
        self._vai(url)
        return self._descrizione()

    def segui_link(self, numero: int) -> str:
        if not isinstance(numero, int) or not (0 <= numero < len(self.links)):
            raise ErroreNavigazione("Numero di link non valido")
        self._vai(self.links[numero]["url"])
        return self._descrizione()

    def compila_ricerca(self, testo: str) -> str:
        campo = self._campo_visibile(
            "input[type=search], input[name=q], input[name*=search i], input[name*=cerca i], input[placeholder*=cerca i], input[placeholder*=search i]")
        if campo is None:
            raise ErroreNavigazione("Campo di ricerca non trovato in questa pagina: apri prima la pagina di ricerca")
        if self.pagine_aperte >= self.max_pagine:
            raise ErroreNavigazione(f"Limite di {self.max_pagine} pagine per esecuzione raggiunto")
        self._pausa()
        self.pagine_aperte += 1
        campo.fill(testo[:200])
        campo.press("Enter")
        try:
            self.page.wait_for_load_state("domcontentloaded")
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        self._dominio_di(self.page.url)
        self.urls_visitati.append(self.page.url)
        return self._descrizione()
