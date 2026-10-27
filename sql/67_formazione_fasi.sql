-- 1.38.1: la formazione procede a fasi (ricerca e download limitati, studio, stesura) e ricorda il materiale scaricato
ALTER TABLE richieste_formazione ADD COLUMN IF NOT EXISTS fase TEXT;
ALTER TABLE richieste_formazione ADD COLUMN IF NOT EXISTS appunti TEXT;
CREATE TABLE IF NOT EXISTS formazione_materiale (
  richiesta_id INTEGER NOT NULL REFERENCES richieste_formazione(id) ON DELETE CASCADE,
  documento_id INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  url TEXT,
  byte INTEGER NOT NULL DEFAULT 0,
  scaricato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (richiesta_id, documento_id)
);
