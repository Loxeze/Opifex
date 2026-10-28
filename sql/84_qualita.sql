-- 1.57.0: qualita' prima di tutto. Sforzo di ragionamento per agente, tetti di lunghezza larghi, biblioteca del lavoro eccellente.
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS sforzo TEXT;
ALTER TABLE agenti DROP CONSTRAINT IF EXISTS agenti_sforzo_check;
ALTER TABLE agenti ADD CONSTRAINT agenti_sforzo_check CHECK (sforzo IS NULL OR sforzo IN ('low','medium','high'));
ALTER TABLE agenti DROP CONSTRAINT IF EXISTS agenti_max_token_risposta_check;
ALTER TABLE agenti ADD CONSTRAINT agenti_max_token_risposta_check CHECK (max_token_risposta BETWEEN 100 AND 64000);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'migrazione_qualita_1_57_0') THEN
    UPDATE agenti SET max_token_risposta = 16000 WHERE max_token_risposta < 16000;
    ALTER TABLE agenti ALTER COLUMN max_token_risposta SET DEFAULT 16000;
    INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('migrazione_qualita_1_57_0', '1');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS esempi_eccellenti (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  titolo TEXT NOT NULL,
  testo TEXT NOT NULL,
  fonte TEXT NOT NULL DEFAULT 'valutazione positiva',
  task_id INTEGER,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS esempi_eccellenti_task ON esempi_eccellenti(agente_id, task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS esempi_eccellenti_agente ON esempi_eccellenti(agente_id, creato_il DESC);
