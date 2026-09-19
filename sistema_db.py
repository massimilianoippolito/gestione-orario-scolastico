import sqlite3

print("Apertura del database orario_scolastico.db...")
conn = sqlite3.connect("orario_scolastico.db")
cursor = conn.cursor()

try:
    print("Ricreazione delle tabelle pulite da vincoli restrittivi...")
    
    # Ricrea classi
    cursor.execute("DROP TABLE IF EXISTS classi;")
    cursor.execute("""
        CREATE TABLE classi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            giorni TEXT,
            orario_ore INTEGER,
            note TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)

    # Ricrea docenti
    cursor.execute("DROP TABLE IF EXISTS docenti;")
    cursor.execute("""
        CREATE TABLE docenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            ore_settimanali INTEGER,
            vincoli TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)

    # Ricrea materie
    cursor.execute("DROP TABLE IF EXISTS materie;")
    cursor.execute("""
        CREATE TABLE materie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            ore_default INTEGER,
            carichi_personalizzati TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)

    # Ricrea assegnazioni
    cursor.execute("DROP TABLE IF EXISTS assegnazioni;")
    cursor.execute("""
        CREATE TABLE assegnazioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classe TEXT,
            materia TEXT,
            docente TEXT,
            docente_2 TEXT,
            ore INTEGER,
            preferenza_blocchi TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)

    # Ricrea orario_risultato
    cursor.execute("DROP TABLE IF EXISTS orario_risultato;")
    cursor.execute("""
        CREATE TABLE orario_risultato (
            classe TEXT,
            giorno TEXT,
            ora INTEGER,
            materia TEXT,
            docente TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)

    # Ricrea orario_fissati
    cursor.execute("DROP TABLE IF EXISTS orario_fissati;")
    cursor.execute("""
        CREATE TABLE orario_fissati (
            classe TEXT,
            giorno TEXT,
            ora INTEGER,
            materia TEXT,
            docente TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)

    conn.commit()
    print("\n✅ Database sistemato con successo!")
    print("Ora puoi lanciare la tua app e importare il file JSON senza errori.")
    
except Exception as e:
    conn.rollback()
    print(f"\n❌ Errore durante l'esecuzione: {e}")
finally:
    conn.close()