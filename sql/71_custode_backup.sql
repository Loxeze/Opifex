-- 1.41.0: il Maestro di chiavi scrive sui siti, scarica e carica file e cartelle, e fa il backup notturno su Drive
CREATE TABLE IF NOT EXISTS custode_file (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL CHECK (length(nome) BETWEEN 1 AND 200),
  tipo TEXT NOT NULL DEFAULT 'file' CHECK (tipo IN ('file', 'zip')),
  sito_nome TEXT,
  origine TEXT,
  byte INTEGER NOT NULL,
  contenuto BYTEA NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS custode_backup (
  id SERIAL PRIMARY KEY,
  sito_id INTEGER REFERENCES siti_hosting(id) ON DELETE SET NULL,
  sito_nome TEXT NOT NULL,
  nome_file TEXT,
  drive_file_id TEXT,
  byte_cifrati BIGINT NOT NULL DEFAULT 0,
  file_n INTEGER NOT NULL DEFAULT 0,
  ok BOOLEAN NOT NULL DEFAULT FALSE,
  errore TEXT,
  saltati TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_custode_backup_data ON custode_backup (creato_il DESC);
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('custode_backup_attivo', '1') ON CONFLICT (chiave) DO NOTHING;
UPDATE agenti SET istruzioni = istruzioni || ' AGGIORNAMENTO: ora puoi scrivere direttamente sui siti, anche in produzione (prima di ogni modifica conservi la copia del file); scarichi e carichi file e cartelle (sito_scarica, sito_carica, sito_crea_cartella, deposito_elenca) e ogni notte alle 23:33 il sistema fa il backup cifrato di tutti i siti su Drive con la tua chiave, che nessun altro conosce. Puoi lanciarlo anche a richiesta (sito_backup), consultarlo (backup_elenco) e ripristinare un backup nel deposito (backup_ripristina). Prima di sovrascrivere o ripristinare qualcosa di importante, se hai un dubbio sulla richiesta, chiedi conferma al collega. Non rivelare mai la chiave di backup.'
WHERE ruolo_speciale = 'custode' AND istruzioni NOT LIKE '%AGGIORNAMENTO: ora puoi scrivere direttamente%';
