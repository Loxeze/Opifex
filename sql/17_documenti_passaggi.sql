-- Documenti: chi li ha passati a chi (un manager puo' girare un documento ai suoi sottoposti)
ALTER TABLE documenti_agenti ADD COLUMN IF NOT EXISTS passato_da INTEGER REFERENCES agenti(id) ON DELETE SET NULL;
ALTER TABLE documenti_agenti ADD COLUMN IF NOT EXISTS assegnato_il TIMESTAMPTZ DEFAULT NOW();
