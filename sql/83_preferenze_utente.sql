-- 1.54.0: preferenze personali (stile, sfondo, densita' del vetro, disposizione dei pannelli della Plancia), salvate sul server per ogni utente
CREATE TABLE IF NOT EXISTS preferenze_utente (
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  chiave TEXT NOT NULL,
  valore JSONB NOT NULL,
  aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (utente_id, chiave)
);
