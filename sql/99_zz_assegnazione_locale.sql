CREATE TABLE IF NOT EXISTS modelli_prima_locale (
  agente_id INTEGER PRIMARY KEY REFERENCES agenti(id) ON DELETE CASCADE,
  modello_precedente TEXT,
  quando TIMESTAMPTZ NOT NULL DEFAULT now()
);
