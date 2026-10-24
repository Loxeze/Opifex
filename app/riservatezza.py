"""Livello 3 della riservatezza: controllo prima di ogni uscita verso un fornitore esterno.

Regola: un dato esce solo se la sua fascia e' ammessa sia dall'agente sia dal fornitore.
Ordine delle fasce: pubblico < interno < riservato.
Il controllo e' fatto in codice, non lasciato al giudizio dell'agente.
"""
import re

ORDINE = {"pubblico": 0, "interno": 1, "riservato": 2}

# Anonimizzazione di base: email, telefoni, codici fiscali, IBAN.
# E' una rete di sicurezza semplice: NON sostituisce la classificazione corretta dei dati.
_MODELLI = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b"), "[CODICE_FISCALE]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN]"),
    (re.compile(r"(?<!\d)(?:\+39[\s.]?)?3\d{2}[\s.]?\d{6,7}(?!\d)"), "[TELEFONO]"),
]


def anonimizza(testo: str) -> str:
    for modello, sostituto in _MODELLI:
        testo = modello.sub(sostituto, testo)
    return testo


def puo_uscire(fascia_dato: str, fascia_max_agente: str, fascia_max_fornitore: str,
               non_conservazione: bool, dpa_firmato: bool) -> tuple[bool, str | None]:
    """Restituisce (consentito, motivo_del_blocco)."""
    d = ORDINE[fascia_dato]
    if d > ORDINE[fascia_max_agente]:
        return False, f"Dato {fascia_dato} oltre la fascia consentita all'agente ({fascia_max_agente})"
    if d > ORDINE[fascia_max_fornitore]:
        return False, f"Dato {fascia_dato} oltre la fascia consentita al fornitore ({fascia_max_fornitore})"
    # I dati non pubblici escono solo verso fornitori con non conservazione attiva e DPA firmato
    if d >= ORDINE["interno"] and not (non_conservazione and dpa_firmato):
        return False, "Fornitore senza non conservazione attiva o senza DPA firmato"
    return True, None
