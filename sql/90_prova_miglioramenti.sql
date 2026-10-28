-- 1.66.0: prova delle nuove istruzioni sui casi di prova prima di applicarle
ALTER TABLE miglioramenti ADD COLUMN IF NOT EXISTS prova_stato TEXT CHECK (prova_stato IS NULL OR prova_stato IN ('in_corso','finita','errore'));
ALTER TABLE miglioramenti ADD COLUMN IF NOT EXISTS prova JSONB;
