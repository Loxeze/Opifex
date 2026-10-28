"""Rigenera docs/COMPETENZE_AGENTI.md dalle competenze di base (python3 crea_docs_competenze.py)."""
import importlib.util
sp = importlib.util.spec_from_file_location("cb", "app/competenze_base.py"); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
open("docs/COMPETENZE_AGENTI.md", "w", encoding="utf-8").write(m.documentazione())
print(len(m.COMPETENZE), "agenti documentati")
