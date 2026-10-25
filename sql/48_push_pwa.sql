-- 1.23.0: notifiche push sui dispositivi
CREATE TABLE IF NOT EXISTS push_iscrizioni (
    id SERIAL PRIMARY KEY,
    utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    dispositivo TEXT,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE notifiche ADD COLUMN IF NOT EXISTS push_il TIMESTAMPTZ;
UPDATE notifiche SET push_il = NOW() WHERE push_il IS NULL;   -- le notifiche gia' esistenti non vengono rispedite
