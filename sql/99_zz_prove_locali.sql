CREATE TABLE IF NOT EXISTS prove_modelli_locali (
  id SERIAL PRIMARY KEY,
  modello TEXT NOT NULL,
  quando TIMESTAMPTZ NOT NULL DEFAULT now(),
  punteggio INTEGER NOT NULL,
  totale INTEGER NOT NULL,
  secondi REAL NOT NULL DEFAULT 0,
  token_al_secondo REAL,
  dettagli JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS prove_modelli_locali_modello ON prove_modelli_locali (modello, id DESC);
