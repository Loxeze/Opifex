-- 1.84.1: i file rimasti senza miniatura (es. ffmpeg mancante la prima volta) vengono riprovati dopo qualche ora
ALTER TABLE archivio_file ADD COLUMN IF NOT EXISTS tentato_il TIMESTAMPTZ;
