-- Posta 2.55: le situazioni nascono dalle conversazioni (filoni), comprese le email inviate da Lorenzo; per ognuna: a chi tocca, prossimo passo, scadenza
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS filo TEXT NOT NULL DEFAULT '';
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS da_me BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS destinatari TEXT NOT NULL DEFAULT '';
ALTER TABLE posta_vaglio DROP CONSTRAINT IF EXISTS posta_vaglio_categoria_check;
ALTER TABLE posta_vaglio ADD CONSTRAINT posta_vaglio_categoria_check CHECK (categoria IN ('da_vagliare', 'importante', 'normale', 'scartabile', 'mia'));
CREATE INDEX IF NOT EXISTS posta_vaglio_filo ON posta_vaglio (origine, casella_id, filo);

ALTER TABLE posta_situazioni ADD COLUMN IF NOT EXISTS filo TEXT NOT NULL DEFAULT '';
ALTER TABLE posta_situazioni ADD COLUMN IF NOT EXISTS tocca_a_te BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE posta_situazioni ADD COLUMN IF NOT EXISTS prossimo_passo TEXT NOT NULL DEFAULT '';
ALTER TABLE posta_situazioni ADD COLUMN IF NOT EXISTS scadenza DATE;
ALTER TABLE posta_situazioni ADD COLUMN IF NOT EXISTS ultimo_da TEXT NOT NULL DEFAULT '';
ALTER TABLE posta_situazioni ADD COLUMN IF NOT EXISTS ultimo_il TIMESTAMPTZ;
ALTER TABLE posta_situazioni ADD COLUMN IF NOT EXISTS da_riassumere BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS posta_situazioni_tocca ON posta_situazioni (aperta, tocca_a_te, ultimo_il DESC);
