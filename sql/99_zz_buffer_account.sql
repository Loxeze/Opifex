-- Piu' account Buffer collegati insieme. Ogni account ha la sua chiave (cifrata); i canali ricordano a quale account appartengono.
CREATE TABLE IF NOT EXISTS account_buffer (
  id SERIAL PRIMARY KEY,
  etichetta TEXT NOT NULL,
  chiave_cifrata TEXT NOT NULL,
  organizzazione_id TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS canali_buffer (
  canale_id TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES account_buffer(id) ON DELETE CASCADE,
  nome TEXT NOT NULL DEFAULT '',
  servizio TEXT NOT NULL DEFAULT ''
);
-- la chiave unica delle versioni precedenti diventa il primo account
INSERT INTO account_buffer (etichetta, chiave_cifrata, organizzazione_id)
SELECT 'Buffer', k.valore, NULLIF((SELECT valore FROM impostazioni_sistema WHERE chiave = 'buffer_organizzazione_id'), '')
FROM impostazioni_sistema k
WHERE k.chiave = 'buffer_chiave_cifrata' AND k.valore <> '' AND NOT EXISTS (SELECT 1 FROM account_buffer);
UPDATE impostazioni_sistema SET valore = '' WHERE chiave IN ('buffer_chiave_cifrata', 'buffer_organizzazione_id');
