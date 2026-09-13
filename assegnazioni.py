import sqlite3
import os

class GestoreAssegnazioni:
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
        """Crea o aggiorna la tabella delle assegnazioni isolata per progetto."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            
            # Verifichiamo se la tabella esiste
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assegnazioni'")
            tabella_esiste = cursor.fetchone()
            
            if not tabella_esiste:
                cursor.execute("""
                    CREATE TABLE assegnazioni (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        classe TEXT,
                        materia TEXT,
                        docente TEXT,
                        docente_2 TEXT DEFAULT '',
                        ore INTEGER DEFAULT 0,
                        preferenza_blocchi TEXT DEFAULT 'Standard (1h)',
                        progetto TEXT DEFAULT 'Principale',
                        UNIQUE(classe, materia, progetto)
                    )
                """)
                conn.commit()
            else:
                # Verifichiamo lo schema per eventuali migrazioni sicure
                cursor.execute("PRAGMA table_info(assegnazioni)")
                colonne = [info[1] for info in cursor.fetchall()]
                
                if "progetto" not in colonne:
                    # Migrazione sicura se manca la colonna progetto
                    cursor.execute("ALTER TABLE assegnazioni RENAME TO assegnazioni_old;")
                    
                    cursor.execute("""
                        CREATE TABLE assegnazioni (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            classe TEXT,
                            materia TEXT,
                            docente TEXT,
                            docente_2 TEXT DEFAULT '',
                            ore INTEGER DEFAULT 0,
                            preferenza_blocchi TEXT DEFAULT 'Standard (1h)',
                            progetto TEXT DEFAULT 'Principale',
                            UNIQUE(classe, materia, progetto)
                        )
                    """)
                    
                    cursor.execute("""
                        INSERT INTO assegnazioni (id, classe, materia, docente, docente_2, ore, preferenza_blocchi, progetto)
                        SELECT id, classe, materia, docente, docente_2, ore, preferenza_blocchi, 'Principale'
                        FROM assegnazioni_old
                    """)
                    
                    cursor.execute("DROP TABLE assegnazioni_old;")
                    conn.commit()
                else:
                    # Assicuriamoci che esista l'indice unico corretto per progetto
                    try:
                        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assegnazioni_univoche ON assegnazioni (classe, materia, progetto);")
                        conn.commit()
                    except Exception:
                        pass

    def aggiungi_assegnazione(self, classe, materia, docente, ore, preferenza_blocchi="Standard (1h)", docente_2=""):
        """Associa una materia a un docente (ed eventuale secondo docente) per una classe nel progetto corrente."""
        if not classe or not materia or not docente:
            return False, "Classe, materia e docente sono obbligatori."
            
        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM assegnazioni WHERE classe = ? AND materia = ? AND progetto = ?",
                    (classe, materia, self.progetto)
                )
                esistente = cursor.fetchone()
                
                if esistente:
                    cursor.execute(
                        "UPDATE assegnazioni SET docente = ?, docente_2 = ?, ore = ?, preferenza_blocchi = ? WHERE classe = ? AND materia = ? AND progetto = ?",
                        (docente, docente_2, int(ore), preferenza_blocchi, classe, materia, self.progetto)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO assegnazioni (classe, materia, docente, docente_2, ore, preferenza_blocchi, progetto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (classe, materia, docente, docente_2, int(ore), preferenza_blocchi, self.progetto)
                    )
                conn.commit()
            return True, "Assegnazione salvata con successo."
        except Exception as e:
            return False, f"Errore durante il salvataggio: {str(e)}"

    def aggiungi_assegnazioni_multiple(self, classi_list, materia, docente, ore, preferenza_blocchi="Standard (1h)", docente_2=""):
        """Associa una materia e un docente a un elenco di classi nel progetto corrente."""
        if not classi_list or not materia or not docente:
            return False, "Seleziona almeno una classe, una materia e un docente."
            
        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                for classe in classi_list:
                    cursor.execute(
                        "SELECT id FROM assegnazioni WHERE classe = ? AND materia = ? AND progetto = ?",
                        (classe, materia, self.progetto)
                    )
                    esistente = cursor.fetchone()
                    
                    if esistente:
                        cursor.execute(
                            "UPDATE assegnazioni SET docente = ?, docente_2 = ?, ore = ?, preferenza_blocchi = ? WHERE classe = ? AND materia = ? AND progetto = ?",
                            (docente, docente_2, int(ore), preferenza_blocchi, classe, materia, self.progetto)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO assegnazioni (classe, materia, docente, docente_2, ore, preferenza_blocchi, progetto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (classe, materia, docente, docente_2, int(ore), preferenza_blocchi, self.progetto)
                        )
                conn.commit()
            return True, f"Assegnazioni salvate con successo per {len(classi_list)} classi."
        except Exception as e:
            return False, f"Errore durante il salvataggio multiplo: {str(e)}"

    def ottieni_tutte_le_assegnazioni(self):
        """Restituisce la lista di tutte le cattedre assegnate per il progetto corrente."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, classe, materia, docente, docente_2, ore, preferenza_blocchi FROM assegnazioni WHERE progetto = ?", (self.progetto,))
            rows = cursor.fetchall()
            
        assegnazioni_lista = []
        for row in rows:
            assegnazioni_lista.append({
                "id": row[0],
                "classe": row[1],
                "materia": row[2],
                "docente": row[3],
                "docente_2": row[4] if len(row) > 4 and row[4] else "",
                "ore": row[5] if len(row) > 5 else 0,
                "preferenza_blocchi": row[6] if len(row) > 6 else "Standard (1h)"
            })
        return assegnazioni_lista

    def elimina_assegnazione(self, id_assegnazione):
        """Rimuove un'assegnazione tramite il suo ID univoco (del progetto corrente)."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM assegnazioni WHERE id = ? AND progetto = ?", (id_assegnazione, self.progetto))
            conn.commit()
        return True, "Assegnazione rimossa."

    def elimina_assegnazioni_per_docente(self, docente):
        """Rimuove o pulisce le assegnazioni per un docente all'interno del progetto corrente."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM assegnazioni WHERE docente = ? AND progetto = ?", (docente, self.progetto))
            cursor.execute("UPDATE assegnazioni SET docente_2 = '' WHERE docente_2 = ? AND progetto = ?", (docente, self.progetto))
            conn.commit()
        return True, f"Tutte le cattedre e compresenze per il docente '{docente}' sono state aggiornate/rimosse."