-- Messaggi interrotti da un riavvio: se non avevano allegati ripartono da soli (una volta).
ALTER TABLE chat_coda ADD COLUMN IF NOT EXISTS fascia TEXT NOT NULL DEFAULT 'pubblico';
ALTER TABLE chat_coda ADD COLUMN IF NOT EXISTS con_allegati BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE chat_coda ADD COLUMN IF NOT EXISTS riprese INTEGER NOT NULL DEFAULT 0;
