-- 1.38.2: eventi di lavoro (cosa sta facendo un agente, a che punto e' una formazione) e pausa dopo lo studio
CREATE TABLE IF NOT EXISTS eventi_lavoro (
  id BIGSERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,
  richiesta_id INTEGER REFERENCES richieste_formazione(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,                 -- inizio, strumento, errore_strumento, fine, errore, fase, fase_fine
  dettaglio TEXT NOT NULL DEFAULT '',
  token INTEGER NOT NULL DEFAULT 0,
  durata_ms INTEGER,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eventi_agente ON eventi_lavoro (agente_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_eventi_richiesta ON eventi_lavoro (richiesta_id, id);
ALTER TABLE richieste_formazione DROP CONSTRAINT IF EXISTS richieste_formazione_stato_check;
ALTER TABLE richieste_formazione ADD CONSTRAINT richieste_formazione_stato_check
  CHECK (stato IN ('in_coda', 'in_corso', 'appunti_pronti', 'da_approvare', 'conclusa', 'annullata', 'errore'));
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('ginnasio_pausa_studio', '1') ON CONFLICT (chiave) DO NOTHING;
