-- FARO: il materiale di ogni bando su Drive (Opifex/Bandi/<scadenza - titolo>) con la scheda tecnica; fonti proposte da Faro; chi fa il primo setaccio.
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS drive_cartella_id TEXT;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS drive_scheda_id TEXT;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS drive_stato TEXT NOT NULL DEFAULT '';
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS drive_file JSONB NOT NULL DEFAULT '[]';
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS drive_il TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS faro_bandi_drive ON faro_bandi (drive_stato);

-- fonti proposte da Faro: entrano spente, Lorenzo le accetta o le scarta (una scartata non torna)
ALTER TABLE faro_fonti ADD COLUMN IF NOT EXISTS proposta BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE faro_fonti ADD COLUMN IF NOT EXISTS scartata BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE faro_fonti ADD COLUMN IF NOT EXISTS motivo TEXT NOT NULL DEFAULT '';

INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('faro_setaccio', '') ON CONFLICT (chiave) DO NOTHING;
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('faro_drive', '1') ON CONFLICT (chiave) DO NOTHING;
