import sqlite3

conn = sqlite3.connect("orario_scolastico.db")
cursor = conn.cursor()

# 1. Ricreiamo la tabella con il vincolo corretto per progetto e nome
cursor.execute("BEGIN TRANSACTION;")
try:
    cursor.execute("ALTER TABLE classi RENAME TO classi_old;")
    
    cursor.execute("""
        CREATE TABLE classi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            progetto TEXT DEFAULT 'Principale',
            nome TEXT NOT NULL,
            giorni TEXT,
            orario_ore INTEGER,
            note TEXT,
            UNIQUE(progetto, nome)
        );
    """)
    
    # Copia i dati vecchi gestendo il campo progetto se mancante
    cursor.execute("""
        INSERT INTO classi (id, progetto, nome, giorni, orario_ore, note)
        SELECT id, COALESCE(progetto, 'Principale'), nome, giorni, orario_ore, note 
        FROM classi_old;
    """)
    
    cursor.execute("DROP TABLE classi_old;")
    conn.commit()
    print("Tabella classi aggiornata con successo!")
except Exception as e:
    conn.rollback()
    print(f"Errore durante la migrazione: {e}")
finally:
    conn.close()