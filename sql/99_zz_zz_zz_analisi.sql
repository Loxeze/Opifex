-- 2.74: prova dei due oggetti
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS oggetto_b TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS ab_esito TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS variante TEXT;
