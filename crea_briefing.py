"""Genera un briefing da riga di comando. Pensato per essere lanciato dal server a orari fissi (cron):

    python crea_briefing.py mattina
    python crea_briefing.py sera
"""
import sys

from app.briefing import genera_briefing
from app.db import apri_pool, chiudi_pool

tipo = sys.argv[1] if len(sys.argv) > 1 else ""
if tipo not in ("mattina", "sera"):
    raise SystemExit("Uso: python crea_briefing.py mattina|sera")

apri_pool()
try:
    r = genera_briefing(tipo)
    print(f"Briefing {tipo} creato (id {r['id']}, rifinito da AI: {r['rifinito_da_ai']})")
finally:
    chiudi_pool()
