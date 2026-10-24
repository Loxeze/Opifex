-- Schema utenti e permessi (Fase 1)
-- Da eseguire dopo schema.sql

-- Utenti della piattaforma: Lorenzo (titolare) e i suoi collaboratori
-- ruolo_globale: 'titolare' (accesso totale) | 'collaboratore' (accesso solo alle divisioni assegnate)
CREATE TABLE utenti (
 id SERIAL PRIMARY KEY,
 nome TEXT NOT NULL,
 email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL,
 ruolo_globale TEXT NOT NULL DEFAULT 'collaboratore'
 CHECK (ruolo_globale IN ('titolare', 'collaboratore')),
 attivo BOOLEAN DEFAULT TRUE,
 creato_il TIMESTAMPTZ DEFAULT NOW(),
 ultimo_accesso TIMESTAMPTZ
);

-- Accesso dei collaboratori alle singole divisioni
-- puo_approvare: puo' approvare o respingere i passaggi della divisione
-- puo_assegnare: puo' dare nuovi compiti e avviare nuovi progetti agli agenti
CREATE TABLE accessi_divisione (
 id SERIAL PRIMARY KEY,
 utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
 divisione_id INTEGER NOT NULL REFERENCES divisioni(id) ON DELETE CASCADE,
 puo_approvare BOOLEAN DEFAULT TRUE,
 puo_assegnare BOOLEAN DEFAULT TRUE,
 UNIQUE (utente_id, divisione_id)
);

-- Azioni sensibili che richiedono SEMPRE l'approvazione del titolare,
-- anche se il collaboratore ha i permessi sulla divisione
-- Esempi: 'pubblicazione_esterna', 'invio_email_esterno', 'spesa_oltre_soglia'
CREATE TABLE azioni_riservate (
 id SERIAL PRIMARY KEY,
 tipo_azione TEXT NOT NULL UNIQUE,
 descrizione TEXT,
 soglia_euro NUMERIC(10, 2)
);

INSERT INTO azioni_riservate (tipo_azione, descrizione, soglia_euro) VALUES
 ('pubblicazione_esterna', 'Pubblicare contenuti sui social o sul web', NULL),
 ('invio_email_esterno', 'Inviare email a contatti esterni', NULL),
 ('spesa_oltre_soglia', 'Spese oltre la soglia indicata', 50.00);

-- Ogni azione viene registrata anche con il nome della persona che l'ha fatta
ALTER TABLE registro_azioni ADD COLUMN utente_id INTEGER REFERENCES utenti(id);

-- Chi ha deciso ogni approvazione e chi ha assegnato ogni compito
ALTER TABLE approvazioni ADD COLUMN decisa_da INTEGER REFERENCES utenti(id);
ALTER TABLE compiti ADD COLUMN assegnato_da_utente INTEGER REFERENCES utenti(id);
