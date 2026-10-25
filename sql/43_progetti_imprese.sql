-- Ogni progetto appartiene a un'impresa e ha un colore; l'eliminazione e' un'archiviazione con recupero.
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS azienda_id INTEGER REFERENCES aziende(id) ON DELETE RESTRICT;
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS colore TEXT CHECK (colore IS NULL OR colore ~ '^#[0-9a-fA-F]{6}$');
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS eliminato_il TIMESTAMPTZ;

-- progetti esistenti: l'impresa si ricava dagli agenti coinvolti se e' una sola, altrimenti la prima attiva
UPDATE progetti p SET azienda_id = x.azienda_id
FROM (SELECT pa.progetto_id, min(aa.azienda_id) AS azienda_id
      FROM progetti_agenti pa JOIN agenti_aziende aa ON aa.agente_id = pa.agente_id GROUP BY pa.progetto_id
      HAVING count(DISTINCT aa.azienda_id) = 1) x
WHERE p.id = x.progetto_id AND p.azienda_id IS NULL;
UPDATE progetti SET azienda_id = (SELECT id FROM aziende ORDER BY attiva DESC, id LIMIT 1) WHERE azienda_id IS NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM progetti WHERE azienda_id IS NULL) THEN
    ALTER TABLE progetti ALTER COLUMN azienda_id SET NOT NULL;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS progetti_azienda ON progetti (azienda_id);
