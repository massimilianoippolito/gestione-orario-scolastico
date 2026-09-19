import sqlite3
import json

class GestoreDocenti:
    def __init__(self, db_path="orario_scolastico.db", progetto="Principale"):
        self.db_path = db_path
        self.progetto = progetto
        self._inizializza_db()

    def _connetti(self):
        return sqlite3.connect(self.db_path)

    def _inizializza_db(self):
        """Ricostruisce la tabella se rileva il vecchio vincolo bloccante su 'nome'."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docenti'")
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE docenti (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT,
                        ore_settimanali INTEGER,
                        vincoli TEXT,
                        progetto TEXT DEFAULT 'Principale',
                        UNIQUE(nome, progetto)
                    )
                """)
                conn.commit()
                return

            # Indaghiamo per scovare il vecchio indice bloccante (il vero colpevole)
            cursor.execute("PRAGMA index_list(docenti)")
            indici = cursor.fetchall()
            deve_migrare = False
            
            # Controlliamo anche se per caso manca la colonna progetto
            cursor.execute("PRAGMA table_info(docenti)")
            colonne = [info[1] for info in cursor.fetchall()]
            if "progetto" not in colonne:
                deve_migrare = True

            # Scorriamo tutti gli indici della tabella
            for idx in indici:
                if idx[2] == 1: # Se l'indice è UNIQUE
                    cursor.execute(f"PRAGMA index_info({idx[1]})")
                    cols = [c[2] for c in cursor.fetchall()]
                    # Se esiste un vincolo UNIQUE che colpisce SOLO 'nome', DOBBIAMO migrare
                    if cols == ["nome"]:
                        deve_migrare = True
                        break

            if not deve_migrare:
                # Se non c'è il vincolo cattivo, ci assicuriamo solo che ci sia quello buono
                try:
                    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_docenti_nome_progetto ON docenti (nome, progetto);")
                    conn.commit()
                except Exception:
                    pass
                return

            # SE SIAMO QUI, IL VECCHIO VINCOLO ESISTE. FACCIAMO LA MIGRAZIONE BLINDATA:
            # 1. Copia di sicurezza
            cursor.execute("DROP TABLE IF EXISTS docenti_temp_backup;")
            cursor.execute("CREATE TABLE docenti_temp_backup AS SELECT * FROM docenti;")
            
            # 2. Distruzione della vecchia tabella colpevole
            cursor.execute("DROP TABLE docenti;")
            
            # 3. Creazione della tabella pulita
            cursor.execute("""
                CREATE TABLE docenti (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT,
                    ore_settimanali INTEGER,
                    vincoli TEXT,
                    progetto TEXT DEFAULT 'Principale',
                    UNIQUE(nome, progetto)
                )
            """)
            
            # 4. Ripristino dei dati
            if "progetto" in colonne:
                cursor.execute("""
                    INSERT INTO docenti (nome, ore_settimanali, vincoli, progetto)
                    SELECT nome, ore_settimanali, vincoli, COALESCE(progetto, 'Principale')
                    FROM docenti_temp_backup
                """)
            else:
                cursor.execute("""
                    INSERT INTO docenti (nome, ore_settimanali, vincoli, progetto)
                    SELECT nome, ore_settimanali, vincoli, 'Principale'
                    FROM docenti_temp_backup
                """)
                
            # 5. Pulizia
            cursor.execute("DROP TABLE docenti_temp_backup;")
            conn.commit()

    def aggiungi_docente(self, nome, ore_settimanali, vincoli=None):
        """Aggiunge un nuovo docente garantendo l'unicità del nome all'interno del progetto."""
        nome_pulito = nome.strip()
        if not nome_pulito:
            return False, "Il nome del docente non può essere vuoto."

        if vincoli is None:
            vincoli = {
                "min_ore_giorno": 2,
                "max_ore_giorno": 5,
                "max_buche_sett": 3,
                "max_buche_giorno": 1,
                "max_prime_ore": 2,
                "giorni_liberi": [],
                "non_disponibili": {},
                "indesiderate": {}
            }

        vincoli_json = json.dumps(vincoli)

        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO docenti (nome, ore_settimanali, vincoli, progetto) VALUES (?, ?, ?, ?)",
                    (nome_pulito, int(ore_settimanali), vincoli_json, self.progetto)
                )
                conn.commit()
            return True, f"Docente '{nome_pulito}' aggiunto con successo a '{self.progetto}'."
        except sqlite3.IntegrityError:
            return False, f"Errore: Il docente '{nome_pulito}' esiste già in questo progetto."
        except Exception as e:
            return False, f"Errore: {str(e)}"

    def aggiorna_docente(self, vecchio_nome, nuovo_nome, ore_settimanali, vincoli):
        """Aggiorna i dati e i vincoli di un docente esistente nel progetto attivo."""
        nuovo_nome_pulito = nuovo_nome.strip()
        if not nuovo_nome_pulito:
            return False, "Il nome del docente non può essere vuoto."

        vincoli_json = json.dumps(vincoli)

        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                
                if vecchio_nome != nuovo_nome_pulito:
                    cursor.execute("SELECT 1 FROM docenti WHERE nome = ? AND progetto = ?", (nuovo_nome_pulito, self.progetto))
                    if cursor.fetchone():
                        return False, f"Errore: Esiste già un docente con il nome '{nuovo_nome_pulito}' in questo progetto."
                    
                    # 1. Aggiorniamo la tabella principale dei docenti via UPDATE limitata al progetto
                    cursor.execute(
                        "UPDATE docenti SET nome = ?, ore_settimanali = ?, vincoli = ? WHERE nome = ? AND progetto = ?",
                        (nuovo_nome_pulito, int(ore_settimanali), vincoli_json, vecchio_nome, self.progetto)
                    )
                    
                    # 2. Propagazione a cascata sulle assegnazioni del progetto
                    cursor.execute("UPDATE assegnazioni SET docente = ? WHERE docente = ? AND progetto = ?", (nuovo_nome_pulito, vecchio_nome, self.progetto))
                    
                    for tabella in ["orario_risultato", "orario_fissati", "orario_fallimenti"]:
                        cursor.execute(f"PRAGMA table_info({tabella})")
                        if cursor.fetchall():
                            cursor.execute(f"UPDATE {tabella} SET docente = ? WHERE docente = ? AND progetto = ?", (nuovo_nome_pulito, vecchio_nome, self.progetto))
                else:
                    cursor.execute(
                        "UPDATE docenti SET ore_settimanali = ?, vincoli = ? WHERE nome = ? AND progetto = ?",
                        (int(ore_settimanali), vincoli_json, vecchio_nome, self.progetto)
                    )
                    
                conn.commit()
            return True, f"Docente '{nuovo_nome_pulito}' aggiornato con successo."
        except Exception as e:
            return False, f"Errore durante l'aggiornamento: {str(e)}"
        
    def ottieni_tutti_i_docenti(self):
        """Restituisce tutti i docenti salvati per il progetto attivo sotto forma di dizionario, gestendo i doppioni."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome, ore_settimanali, vincoli FROM docenti WHERE progetto = ?", (self.progetto,))
            rows = cursor.fetchall()
            
            if not rows and self.progetto != "Principale":
                cursor.execute("SELECT nome, ore_settimanali, vincoli FROM docenti WHERE progetto = 'Principale'")
                rows = cursor.fetchall()
        
        docenti_dict = {}
        for row in rows:
            nome, ore, vincoli_json = row
            
            if isinstance(vincoli_json, str):
                try:
                    vincoli_dict = json.loads(vincoli_json) if vincoli_json else {}
                except:
                    vincoli_dict = {}
            elif isinstance(vincoli_json, dict):
                vincoli_dict = vincoli_json
            else:
                vincoli_dict = {}
            
            if "giorni_liberi" not in vincoli_dict:
                vincoli_dict["giorni_liberi"] = []

            has_vincoli_reali = bool(vincoli_dict.get("non_disponibili") or vincoli_dict.get("indesiderate"))

            # Se il docente non esiste ancora, oppure se il record corrente ha i vincoli reali e quello salvato no, lo sovrascriviamo
            if nome not in docenti_dict:
                docenti_dict[nome] = {
                    "ore_settimanali": ore,
                    "vincoli": vincoli_dict
                }
            else:
                # Se c'è già un doppione, diamo la priorità a quello che ha i vincoli compilati
                esistenti_ha_vincoli = bool(docenti_dict[nome]["vincoli"].get("non_disponibili") or docenti_dict[nome]["vincoli"].get("indesiderate"))
                if has_vincoli_reali and not esistenti_ha_vincoli:
                    docenti_dict[nome] = {
                        "ore_settimanali": ore,
                        "vincoli": vincoli_dict
                    }

        # Stampa di controllo per verificare cosa viene passato alla vista
        print(f"🖥️ [VISTA DOCENTI LEGGE] Per Buonopane -> Non disponibili: {docenti_dict.get('Buonopane', {}).get('vincoli', {}).get('non_disponibili')}", flush=True)

        return docenti_dict

    # def ottieni_tutti_i_docenti(self):
    #     """Restituisce tutti i docenti salvati per il progetto attivo sotto forma di dizionario."""
    #     with self._connetti() as conn:
    #         cursor = conn.cursor()
    #         cursor.execute("SELECT nome, ore_settimanali, vincoli FROM docenti WHERE progetto = ?", (self.progetto,))
    #         rows = cursor.fetchall()
        
    #     docenti_dict = {}
    #     for row in rows:
    #         nome, ore, vincoli_json = row
    #         vincoli_dict = json.loads(vincoli_json) if vincoli_json else {}
            
    #         if "giorni_liberi" not in vincoli_dict:
    #             vincoli_dict["giorni_liberi"] = []

    #         docenti_dict[nome] = {
    #             "ore_settimanali": ore,
    #             "vincoli": vincoli_dict
    #         }
        # --- STAMPA DI CONTROLLO PER LA VISTA ---
        print(f"🖥️ [VISTA DOCENTI LEGGE] Per Buonopane -> Non disponibili: {docenti_dict.get('Buonopane', {}).get('vincoli', {}).get('non_disponibili')}", flush=True)
        return docenti_dict

    def elimina_docente(self, nome):
        """Elimina un docente dal database per il progetto attivo."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM docenti WHERE nome = ? AND progetto = ?", (nome, self.progetto))
            conn.commit()
        return True, f"Docente '{nome}' eliminato."
    
    def importa_docenti_selezionati(self, progetto_origine, lista_docenti_da_importare):
        """Importa una lista specifica di docenti da un altro progetto nel progetto corrente."""
        if not lista_docenti_da_importare:
            return False, "Nessun docente selezionato per l'importazione."
            
        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                importati = 0
                saltati = 0
                
                for nome_doc in lista_docenti_da_importare:
                    # 1. Leggiamo dal progetto di origine
                    cursor.execute(
                        "SELECT nome, ore_settimanali, vincoli FROM docenti WHERE nome = ? AND progetto = ?", 
                        (nome_doc, progetto_origine)
                    )
                    doc_data = cursor.fetchone()
                    
                    if doc_data:
                        nome, ore, vincoli = doc_data
                        
                        # 2. Verifichiamo se esiste già nel progetto corrente
                        cursor.execute(
                            "SELECT 1 FROM docenti WHERE nome = ? AND progetto = ?", 
                            (nome, self.progetto)
                        )
                        if cursor.fetchone():
                            saltati += 1
                            continue
                        
                        # 3. Inseriamo nel progetto corrente
                        cursor.execute(
                            "INSERT INTO docenti (nome, ore_settimanali, vincoli, progetto) VALUES (?, ?, ?, ?)",
                            (nome, ore, vincoli, self.progetto)
                        )
                        importati += 1
                        
                conn.commit()
            return True, f"Importazione completata: {importati} importati, {saltati} già esistenti in questo progetto."
        except Exception as e:
            return False, f"Errore durante l'importazione: {str(e)}"