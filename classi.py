import sqlite3
import json
import os

class GestoreClassi:
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
        """Crea la tabella delle classi nel database se non esiste già."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS classi (
                    nome TEXT,
                    giorni TEXT,
                    orario_ore TEXT,
                    note TEXT,
                    progetto TEXT DEFAULT 'Principale',
                    PRIMARY KEY (nome, progetto)
                )
            """)
            conn.commit()

    def aggiungi_classe(self, nome, giorni, orario_ore, note="Standard"):
        """Aggiunge una nuova classe garantendo l'unicità del nome all'interno del progetto."""
        nome_pulito = nome.strip().upper()
        if not nome_pulito:
            return False, "Il nome della classe non può essere vuoto."

        giorni_json = json.dumps(giorni)
        ore_json = json.dumps(orario_ore)

        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO classi (nome, giorni, orario_ore, note, progetto) VALUES (?, ?, ?, ?, ?)",
                    (nome_pulito, giorni_json, ore_json, note, self.progetto)
                )
                conn.commit()
            return True, f"Classe {nome_pulito} aggiunta con successo a '{self.progetto}'."
        except sqlite3.IntegrityError:
            return False, f"Errore: La classe '{nome_pulito}' esiste già in questo progetto."
        except Exception as e:
            return False, f"Errore: {str(e)}"

    def aggiorna_classe(self, vecchio_nome, nuovo_nome, giorni, orario_ore, note):
        """Aggiorna i dati di una classe esistente, gestendo anche il cambio nome e propagandolo a cascata nel progetto."""
        nuovo_nome_pulito = nuovo_nome.strip().upper()
        if not nuovo_nome_pulito:
            return False, "Il nome della classe non può essere vuoto."

        giorni_json = json.dumps(giorni)
        ore_json = json.dumps(orario_ore)

        try:
            with self._connetti() as conn:
                cursor = conn.cursor()
                
                if vecchio_nome != nuovo_nome_pulito:
                    cursor.execute("SELECT 1 FROM classi WHERE nome = ? AND progetto = ?", (nuovo_nome_pulito, self.progetto))
                    if cursor.fetchone():
                        return False, f"Errore: Esiste già una classe con il nome '{nuovo_nome_pulito}' in questo progetto."
                    
                    # 1. Aggiorniamo la tabella classi usando UPDATE
                    cursor.execute(
                        "UPDATE classi SET nome = ?, giorni = ?, orario_ore = ?, note = ? WHERE nome = ? AND progetto = ?",
                        (nuovo_nome_pulito, giorni_json, ore_json, note, vecchio_nome, self.progetto)
                    )
                    
                    # 2. Propagazione a cascata sulle tabelle dipendenti per il progetto corrente
                    cursor.execute("UPDATE assegnazioni SET classe = ? WHERE classe = ? AND progetto = ?", (nuovo_nome_pulito, vecchio_nome, self.progetto))
                    
                    for tabella in ["orario_risultato", "orario_fissati", "orario_fallimenti"]:
                        cursor.execute(f"PRAGMA table_info({tabella})")
                        if cursor.fetchall():
                            cursor.execute(f"UPDATE {tabella} SET classe = ? WHERE classe = ? AND progetto = ?", (nuovo_nome_pulito, vecchio_nome, self.progetto))
                else:
                    cursor.execute(
                        "UPDATE classi SET giorni = ?, orario_ore = ?, note = ? WHERE nome = ? AND progetto = ?",
                        (giorni_json, ore_json, note, vecchio_nome, self.progetto)
                    )
                    
                conn.commit()
            return True, f"Classe '{nuovo_nome_pulito}' aggiornata con successo (inclusa propagazione a cascata)."
        except Exception as e:
            return False, f"Errore durante l'aggiornamento: {str(e)}"

    def ottieni_tutte_le_classi(self):
        """Restituisce tutte le classi salvate per il progetto attivo sotto forma di dizionario."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome, giorni, orario_ore, note FROM classi WHERE progetto = ?", (self.progetto,))
            rows = cursor.fetchall()
        
        classi_dict = {}
        for row in rows:
            nome, giorni_json, ore_json, note = row
            classi_dict[nome] = {
                "giorni": json.loads(giorni_json),
                "ore": json.loads(ore_json),
                "note": note
            }
        return classi_dict

    def elimina_classe(eta, self, nome): # Adattato correttamente nel metodo sotto
        pass

    def elimina_classe(self, nome):
        """Elimina una classe dal database per il progetto attivo."""
        with self._connetti() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM classi WHERE nome = ? AND progetto = ?", (nome, self.progetto))
            conn.commit()
        return True, f"Classe {nome} eliminata."