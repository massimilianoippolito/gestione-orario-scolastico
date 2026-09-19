import json
import sqlite3

def popola_dati_scuola_per_progetto(nome_progetto="utente1"):
    print(f"🧹 Inizializzazione e popolamento database per il progetto: {nome_progetto}...")
    db_path = "orario_scolastico.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Assicuriamoci che le tabelle esistano con la struttura corretta (inclusa la colonna 'progetto')
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            giorni TEXT,
            orario_ore TEXT,
            note TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS docenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            ore_settimanali INTEGER,
            vincoli TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            ore_default INTEGER,
            carichi_personalizzati TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assegnazioni (
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

    # 2. Pulizia preventiva SOLO per questo progetto specifico
    cursor.execute("DELETE FROM classi WHERE progetto = ?", (nome_progetto,))
    cursor.execute("DELETE FROM docenti WHERE progetto = ?", (nome_progetto,))
    cursor.execute("DELETE FROM materie WHERE progetto = ?", (nome_progetto,))
    cursor.execute("DELETE FROM assegnazioni WHERE progetto = ?", (nome_progetto,))

    # 3. Inserimento Materie di base
    materie_default = [
        ("Italiano", 6), ("Matematica", 4), ("Scienze", 2), 
        ("Storia", 2), ("Geografia", 2), ("Inglese", 3), 
        ("Seconda lingua", 2), ("Tecnologia", 2), ("Arte e Immagine", 2), 
        ("Musica", 2), ("Scienze Motorie", 2), ("Religione", 1)
    ]
    for mat, ore_def in materie_default:
        cursor.execute(
            "INSERT INTO materie (nome, ore_default, carichi_personalizzati, progetto) VALUES (?, ?, ?, ?)",
            (mat, ore_def, "{}", nome_progetto)
        )

    # 4. Inserimento Classi
    giorni_standard = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
    classi_normali = ["1ªA", "1ªB", "1ªC", "2ªA", "2ªB", "2ªC", "3ªA", "3ªB", "3ªC", "2ªD", "3ªD"]
    
    # Dizionario ore tempo normale (6 ore per 5 giorni = 30 ore)
    orario_normale_dict = {"Lunedì": 6, "Martedì": 6, "Mercoledì": 6, "Giovedì": 6, "Venerdì": 6}
    
    for c in classi_normali:
        cursor.execute(
            "INSERT INTO classi (nome, giorni, orario_ore, note, progetto) VALUES (?, ?, ?, ?, ?)",
            (c, json.dumps(giorni_standard), json.dumps(orario_normale_dict), "Tempo Normale (30h)", nome_progetto)
        )

    # Classe personalizzata 1ªD (es. 36 ore ripartite in modo personalizzato)
    orario_personalizzato_dict = {"Lunedì": 7, "Martedì": 7, "Mercoledì": 8, "Giovedì": 7, "Venerdì": 7}
    cursor.execute(
        "INSERT INTO classi (nome, giorni, orario_ore, note, progetto) VALUES (?, ?, ?, ?, ?)",
        ("1ªD", json.dumps(giorni_standard), json.dumps(orario_personalizzato_dict), "Personalizzato", nome_progetto)
    )

    # 5. Inserimento Docenti
    nomi_docenti = [
        "Abruzzese", "Ambrosecchia", "Basso", "Bevilacqua", "Brillante", 
        "Bruno", "Buonopane", "Chioccola", "Cobino", "Cozzo", "De Simone", 
        "Flammia", "Galante T", "Galante C", "Giusto", "Grande", "Grieci", 
        "Ippolito Petrilli", "Macchia", "Maffei", "Meninno", "Pascucci", 
        "Penta", "Pugliese", "Sacco", "Schiavone", "Sisto"
    ]

    vincoli_default = {
        "min_ore_giorno": 2,
        "max_ore_giorno": 5,
        "max_buche_sett": 2,
        "max_buche_giorno": 1,
        "max_prime_ore": 2,
        "giorni_liberi": [],
        "non_disponibili": {},
        "indesiderate": {}
    }

    for d in nomi_docenti:
        cursor.execute(
            "INSERT INTO docenti (nome, ore_settimanali, vincoli, progetto) VALUES (?, ?, ?, ?)",
            (d, 18, json.dumps(vincoli_default), nome_progetto)
        )

    conn.commit()
    conn.close()

    print(f"✅ Database popolato correttamente per il progetto '{nome_progetto}'!")
    print(f"   - Classi inserite: 12")
    print(f"   - Docenti inseriti: {len(nomi_docenti)}")
    print(f"   - Materie inserite: {len(materie_default)}")

if __name__ == "__main__":
    popola_dati_scuola_per_progetto("utente1")