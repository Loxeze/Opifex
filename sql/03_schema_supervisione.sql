-- Schema aggiuntivo: supervisione, umore degli agenti, token, opportunita', classificazione dati
-- Da eseguire dopo schema.sql e schema_utenti.sql
-- Database: PostgreSQL

-- Gli agenti di sistema (fuori dalle piramidi) sono agenti con divisione_id nullo.
-- Estensione della tabella agenti: tipo di agente e fascia dati massima ammessa
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'divisione'
 CHECK (tipo IN ('divisione', 'sistema'));
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS fascia_dati_max TEXT NOT NULL DEFAULT 'interno'
 CHECK (fascia_dati_max IN ('pubblico', 'interno', 'riservato'));

-- Classificazione dei dati: ogni compito porta una fascia
ALTER TABLE compiti ADD COLUMN IF NOT EXISTS fascia_dati TEXT NOT NULL DEFAULT 'interno'
 CHECK (fascia_dati IN ('pubblico', 'interno', 'riservato'));

-- Imprese di Lorenzo (piu' di una): le aziende esistono gia' nella tabella aziende.

-- Fornitori e modelli AI con tariffe e limiti
CREATE TABLE IF NOT EXISTS fornitori_ai (
 id SERIAL PRIMARY KEY,
 nome TEXT NOT NULL, -- anthropic, openai, xai
 non_conservazione_attiva BOOLEAN DEFAULT FALSE,
 dpa_firmato BOOLEAN DEFAULT FALSE,
 fascia_dati_max TEXT NOT NULL DEFAULT 'interno'
 CHECK (fascia_dati_max IN ('pubblico', 'interno', 'riservato')),
 budget_mensile NUMERIC(10, 2),
 note TEXT
);

CREATE TABLE IF NOT EXISTS modelli_ai (
 id SERIAL PRIMARY KEY,
 fornitore_id INTEGER REFERENCES fornitori_ai(id),
 nome TEXT NOT NULL,
 costo_input_per_milione NUMERIC(10, 4),
 costo_output_per_milione NUMERIC(10, 4),
 fascia TEXT CHECK (fascia IN ('economico', 'standard', 'avanzato'))
);

-- Umore operativo degli agenti: indicatore calcolato, non emozione reale.
-- Stati: 'sereno', 'concentrato', 'sotto_pressione', 'in_difficolta'
CREATE TABLE IF NOT EXISTS umore_agenti (
 id SERIAL PRIMARY KEY,
 agente_id INTEGER REFERENCES agenti(id),
 stato TEXT NOT NULL CHECK (stato IN ('sereno', 'concentrato', 'sotto_pressione', 'in_difficolta')),
 carico_lavoro NUMERIC(5, 2), -- compiti aperti rispetto alla capacita'
 tasso_errori NUMERIC(5, 2),
 tasso_approvazione NUMERIC(5, 2),
 tempo_medio_secondi INTEGER,
 rilevato_il TIMESTAMPTZ DEFAULT NOW()
);

-- Registro delle uscite di dati verso fornitori esterni (livello 3 della riservatezza)
CREATE TABLE IF NOT EXISTS registro_uscite (
 id SERIAL PRIMARY KEY,
 agente_id INTEGER REFERENCES agenti(id),
 fornitore_id INTEGER REFERENCES fornitori_ai(id),
 modello_id INTEGER REFERENCES modelli_ai(id),
 fascia_dati TEXT NOT NULL,
 anonimizzato BOOLEAN DEFAULT TRUE,
 token_input INTEGER,
 bloccato BOOLEAN DEFAULT FALSE, -- vero se il sistema ha impedito l'invio
 motivo_blocco TEXT,
 inviato_il TIMESTAMPTZ DEFAULT NOW()
);

-- Raccomandazioni degli agenti di sistema (Auditor, Guardiano, Consulente, Controllore costi)
CREATE TABLE IF NOT EXISTS raccomandazioni (
 id SERIAL PRIMARY KEY,
 agente_id INTEGER REFERENCES agenti(id), -- agente di sistema che la emette
 categoria TEXT NOT NULL CHECK (categoria IN ('flussi', 'sicurezza', 'organizzazione', 'costi')),
 gravita TEXT NOT NULL DEFAULT 'info' CHECK (gravita IN ('info', 'media', 'alta', 'critica')),
 titolo TEXT NOT NULL,
 descrizione TEXT NOT NULL,
 risparmio_stimato NUMERIC(10, 2),
 stato TEXT NOT NULL DEFAULT 'nuova'
 CHECK (stato IN ('nuova', 'accettata', 'rifiutata', 'attuata')),
 creata_il TIMESTAMPTZ DEFAULT NOW(),
 decisa_il TIMESTAMPTZ
);

-- Sospensioni di emergenza decise dal Guardiano della sicurezza
CREATE TABLE IF NOT EXISTS sospensioni_agenti (
 id SERIAL PRIMARY KEY,
 agente_id INTEGER REFERENCES agenti(id),
 deciso_da INTEGER REFERENCES agenti(id),
 motivo TEXT NOT NULL,
 sospeso_il TIMESTAMPTZ DEFAULT NOW(),
 riattivato_il TIMESTAMPTZ
);

-- Opportunita' di business: pipeline, soldi sul tavolo, incassi
CREATE TABLE IF NOT EXISTS opportunita (
 id SERIAL PRIMARY KEY,
 titolo TEXT NOT NULL,
 azienda_id INTEGER REFERENCES aziende(id),
 divisione_id INTEGER REFERENCES divisioni(id),
 tipo TEXT CHECK (tipo IN ('bando', 'cliente', 'partnership', 'altro')),
 valore_stimato NUMERIC(12, 2),
 probabilita NUMERIC(5, 2), -- da 0 a 100
 stato TEXT NOT NULL DEFAULT 'individuata'
 CHECK (stato IN ('individuata', 'in_lavorazione', 'presentata', 'vinta', 'incassata', 'persa', 'scaduta_non_colta')),
 scadenza DATE,
 trovata_da INTEGER REFERENCES agenti(id),
 creata_il TIMESTAMPTZ DEFAULT NOW()
);

-- Scadenze di bandi e progetti, e dipendenze per il diagramma di Gantt
ALTER TABLE compiti ADD COLUMN IF NOT EXISTS data_inizio DATE;
ALTER TABLE compiti ADD COLUMN IF NOT EXISTS scadenza DATE;
ALTER TABLE compiti ADD COLUMN IF NOT EXISTS avanzamento INTEGER DEFAULT 0
 CHECK (avanzamento BETWEEN 0 AND 100);
ALTER TABLE compiti ADD COLUMN IF NOT EXISTS opportunita_id INTEGER REFERENCES opportunita(id);

-- Assegnazione di compiti anche a persone (Lorenzo e collaboratori), non solo ad agenti.
-- Si assume la tabella utenti definita in schema_utenti.sql
ALTER TABLE compiti ADD COLUMN IF NOT EXISTS assegnato_a_utente INTEGER REFERENCES utenti(id);

CREATE TABLE IF NOT EXISTS dipendenze_compiti (
 compito_id INTEGER REFERENCES compiti(id),
 dipende_da INTEGER REFERENCES compiti(id),
 PRIMARY KEY (compito_id, dipende_da)
);

-- Agenda: eventi sincronizzati da Google Calendar con brief preparato dagli agenti
CREATE TABLE IF NOT EXISTS eventi_agenda (
 id SERIAL PRIMARY KEY,
 id_google TEXT UNIQUE,
 titolo TEXT NOT NULL,
 inizio TIMESTAMPTZ NOT NULL,
 fine TIMESTAMPTZ,
 luogo TEXT,
 azienda_id INTEGER REFERENCES aziende(id),
 brief TEXT, -- promemoria preparato sugli argomenti da trattare
 brief_generato_il TIMESTAMPTZ
);

-- Consumo e crediti per fornitore (per vedere quanto resta di Claude, GPT, Grok)
CREATE TABLE IF NOT EXISTS crediti_fornitori (
 id SERIAL PRIMARY KEY,
 fornitore_id INTEGER REFERENCES fornitori_ai(id),
 credito_residuo NUMERIC(10, 2),
 rilevato_il TIMESTAMPTZ DEFAULT NOW()
);
