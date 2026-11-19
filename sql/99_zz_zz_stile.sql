-- 2.67: le correzioni di Lorenzo alle bozze del Redattore
ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS corretta_il TIMESTAMPTZ;
ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS stile_studiato BOOLEAN NOT NULL DEFAULT FALSE;
