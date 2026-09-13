import sqlite3
import json
import os

class GestoreMaterie:
    def __init__(self, db_path=None, progetto="Principale"):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, "orario_scolastico.db")
        else:
            self.db_path = db_path
        self.progetto = progetto
        self._inizializza_db()

    def _connetti(self):
        return sqlite3.connect(self.db_path)

    def _inizializza_db(self):
        """Crea o aggiorna la tabella delle materie rimuovendo vecchi vincoli globali e preservando i dati."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            
            # Verifichiamo lo schema SQL attuale della tabella 'materie' nel database
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='materie'")
            res = cursor.fetchone()
            
            ricrea_tabella = False
            if not res:
                # La tabella non esiste affatto, la creiamo nuova
                ricrea_tabella = True
                fai_migrazione = False
            else:
                table_sql = res[0] or ""
                # Se il vecchio vincolo UNIQUE su 'nome' è ancora presente nello schema e manca quello composto corretto
                if ("UNIQUE" in table_sql.upper() and 
                    "UNIQUE(NOME, PROGETTO)" not in table_sql.upper() and 
                    "UNIQUE (NOME, PROGETTO)" not in table_sql.upper()):
                    ricrea_tabella = True
                    fai_migrazione = True
                elif "progetto" not in table_sql:
                    ricrea_tabella = True
                    fai_migrazione = True
                else:
                    fai_migrazione = False

            if ricrea_tabella:
                if fai_migrazione:
                    # MIGRAZIONE SICURA: Spostiamo i dati nella tabella temporanea, ricreiamo e rimettiamo a posto
                    cursor.execute("ALTER TABLE materie RENAME TO materie_old;")
                    
                    cursor.execute("""
                        CREATE TABLE materie (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT,
                            ore_default INTEGER,
                            carichi_personalizzati TEXT,
                            progetto TEXT DEFAULT 'Principale',
                            UNIQUE(nome, progetto)
                        )
                    """)
                    
                    # Verifico se la tabella vecchia aveva la colonna progetto
                    cursor.execute("PRAGMA table_info(materie_old)")
                    old_cols = [info[1] for info in cursor.fetchall()]
                    
                    if "progetto" in old_cols:
                        cursor.execute("""
                            INSERT INTO materie (id, nome, ore_default, carichi_personalizzati, progetto)
                            SELECT id, nome, ore_default, carichi_personalizzati, COALESCE(progetto, 'Principale')
                            FROM materie_old
                        """)
                    else:
                        cursor.execute("""
                            INSERT INTO materie (id, nome, ore_default, carichi_personalizzati, progetto)
                            SELECT id, nome, ore_default, carichi_personalizzati, 'Principale'
                            FROM materie_old
                        """)
                    
                    cursor.execute("DROP TABLE materie_old;")
                else:
                    # Creazione pulita da zero se la tabella non c'era
                    cursor.execute("""
                        CREATE TABLE materie (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT,
                            ore_default INTEGER,
                            carichi_personalizzati TEXT,
                            progetto TEXT DEFAULT 'Principale',
                            UNIQUE(nome, progetto)
                        )
                    """)
                conn.commit()

            # Inseriamo le materie standard di default solo se il progetto corrente è completamente vuoto
            cursor.execute("SELECT COUNT(*) FROM materie WHERE progetto = ?", (self.progetto,))
            if cursor.fetchone()[0] == 0 and self.progetto == "Principale":
                materie_standard = [
                    ("Italiano", 6),
                    ("Matematica", 4),
                    ("Scienze", 2),
                    ("Storia", 2),
                    ("Geografia", 2),
                    ("Inglese", 3),
                    ("Seconda lingua", 2),
                    ("Tecnologia", 2),
                    ("Arte e Immagine", 2),
                    ("Musica", 2),
                    ("Scienze Motorie", 2),
                    ("Religione", 1),
                    ("Approfondimento", 1)
                ]
                for nome, ore in materie_standard:
                    cursor.execute(
                        "INSERT OR IGNORE INTO materie (nome, ore_default, carichi_personalizzati, progetto) VALUES (?, ?, ?, ?)",
                        (nome, ore, json.dumps({}), self.progetto)
                    )
                conn.commit()

    def aggiungi_materia(self, nome, ore_default):
        """Aggiunge una nuova materia nel progetto corrente."""
        nome_pulito = nome.strip()
        if not nome_pulito:
            return False, "Il nome della materia non può essere vuoto."

        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO materie (nome, ore_default, carichi_personalizzati, progetto) VALUES (?, ?, ?, ?)",
                    (nome_pulito, int(ore_default), json.dumps({}), self.progetto)
                )
                conn.commit()
            return True, f"Materia '{nome_pulito}' aggiunta con successo a '{self.progetto}'."
        except sqlite3.IntegrityError:
            return False, f"Errore: La materia '{nome_pulito}' esiste già in questo progetto."

    def ottieni_tutte_le_materie(self):
        """Restituisce tutte le materie salvate per il progetto corrente."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome, ore_default, carichi_personalizzati FROM materie WHERE progetto = ?", (self.progetto,))
            rows = cursor.fetchall()
        
        materie_dict = {}
        for row in rows:
            nome, ore_def, carichi_json = row
            materie_dict[nome] = {
                "ore_default": ore_def,
                "carichi_per_classe": json.loads(carichi_json) if carichi_json else {}
            }
        return materie_dict

    def aggiorna_materia(self, vecchio_nome, nuovo_nome, ore_default, carichi_per_classe):
        """Aggiorna una materia nel progetto corrente."""
        nuovo_nome_pulito = nuovo_nome.strip()
        if not nuovo_nome_pulito:
            return False, "Il nome della materia non può essere vuoto."

        carichi_json = json.dumps(carichi_per_classe)

        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                
                if vecchio_nome != nuovo_nome_pulito:
                    cursor.execute("SELECT 1 FROM materie WHERE nome = ? AND progetto = ?", (nuovo_nome_pulito, self.progetto))
                    if cursor.fetchone():
                        return False, f"Errore: Esiste già una materia chiamata '{nuovo_nome_pulito}' in questo progetto."
                    
                    cursor.execute(
                        "UPDATE materie SET nome = ?, ore_default = ?, carichi_personalizzati = ? WHERE nome = ? AND progetto = ?",
                        (nuovo_nome_pulito, int(ore_default), carichi_json, vecchio_nome, self.progetto)
                    )
                else:
                    cursor.execute(
                        "UPDATE materie SET ore_default = ?, carichi_personalizzati = ? WHERE nome = ? AND progetto = ?",
                        (int(ore_default), carichi_json, vecchio_nome, self.progetto)
                    )
                conn.commit()
            return True, f"Materia '{nuovo_nome_pulito}' aggiornata con successo."
        except Exception as e:
            return False, f"Errore durante l'aggiornamento: {str(e)}"

    def elimina_materia(self, nome):
        """Elimina una materia dal progetto corrente."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM materie WHERE nome = ? AND progetto = ?", (nome, self.progetto))
            conn.commit()
        return True, f"Materia '{nome}' eliminata."

    def importa_materie_da_progetto(self, progetto_origine):
        """Importa le materie da un altro progetto esistente nel progetto corrente."""
        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                
                # 1. Verifichiamo cosa c'è nel progetto origine
                cursor.execute("SELECT nome, ore_default, carichi_personalizzati FROM materie WHERE progetto = ?", (progetto_origine,))
                materie_origine = cursor.fetchall()
                
                if not materie_origine:
                    return False, f"Nessuna materia trovata nel progetto di origine '{progetto_origine}'."
                
                importate = 0
                saltate = 0
                for nome, ore_def, carichi in materie_origine:
                    # Verifichiamo se esiste già nel progetto corrente
                    cursor.execute("SELECT 1 FROM materie WHERE nome = ? AND progetto = ?", (nome, self.progetto))
                    if cursor.fetchone():
                        saltate += 1
                        continue
                        
                    cursor.execute(
                        "INSERT INTO materie (nome, ore_default, carichi_personalizzati, progetto) VALUES (?, ?, ?, ?)",
                        (nome, ore_def, carichi, self.progetto)
                    )
                    importate += 1
                        
                conn.commit()
            return True, f"Importazione completata: {importate} materie importate, {saltate} già esistenti in questo progetto."
        except Exception as e:
            return False, f"Errore durante l'importazione: {str(e)}"