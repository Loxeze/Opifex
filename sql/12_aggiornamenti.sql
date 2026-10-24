-- Aggiornamenti: registro e impostazioni (repository GitHub, token cifrato, automatismo)
CREATE TABLE IF NOT EXISTS aggiornamenti_registro (
  id SERIAL PRIMARY KEY,
  versione TEXT NOT NULL,
  esito TEXT NOT NULL,
  dettagli TEXT,
  creato_il TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO impostazioni_sistema (chiave, valore) VALUES
  ('aggiornamento_automatico', 'no')   -- 'no' | 'patch' (installa da solo solo le correzioni X.Y.Z)
ON CONFLICT (chiave) DO NOTHING;
