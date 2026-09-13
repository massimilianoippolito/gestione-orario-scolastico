import json
import sqlite3

def popola_dati_scuola():
    print("🧹 Allineamento schema e popolamento database di test...")
    db_path = "orario_scolastico.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Pulizia tabelle esistenti per evitare disallineamenti di schema
    cursor.execute("DROP TABLE IF EXISTS assegnazioni")
    cursor.execute("DROP TABLE IF EXISTS classi")
    cursor.execute("DROP TABLE IF EXISTS docenti")

    # 1. Tabella classi (allineata esattamente a classi.py)
    cursor.execute("""
        CREATE TABLE classi (
            nome TEXT PRIMARY KEY,
            giorni TEXT,
            orario_ore TEXT,
            note TEXT
        )
    """)

    # 2. Tabella docenti
    cursor.execute("""
        CREATE TABLE docenti (
            nome TEXT PRIMARY KEY,
            ore_settimanali INTEGER,
            vincoli TEXT
        )
    """)

    # 3. Tabella assegnazioni
    cursor.execute("""
        CREATE TABLE assegnazioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classe TEXT,
            materia TEXT,
            docente TEXT,
            ore_settimanali INTEGER
        )
    """)

    # 4. Inserimento 12 classi: 11 normali (30h) + 1 prolungata (36h)
    giorni_standard = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
    
    # Tempo Normale: 6 ore al giorno per 5 giorni = 30 ore
    ore_normale = {"Lunedì": 6, "Martedì": 6, "Mercoledì": 6, "Giovedì": 6, "Venerdì": 6}
    classi_normali = ["1ªA", "1ªB", "1ªC", "2ªA", "2ªB", "2ªC", "3ªA", "3ªB", "3ªC", "2ªD", "3ªD"]
    
    for c in classi_normali:
        cursor.execute(
            "INSERT INTO classi (nome, giorni, orario_ore, note) VALUES (?, ?, ?, ?)",
            (c, json.dumps(giorni_standard), json.dumps(ore_normale), "Tempo Normale (30h)")
        )

    # Tempo Prolungato: 36 ore totali (7 ore tutti i giorni tranne il mercoledì che ne fa 8)
    ore_prolungato = {"Lunedì": 7, "Martedì": 7, "Mercoledì": 8, "Giovedì": 7, "Venerdì": 7}
    cursor.execute(
        "INSERT INTO classi (nome, giorni, orario_ore, note) VALUES (?, ?, ?, ?)",
        ("1ªD_PROLUNGATO", json.dumps(giorni_standard), json.dumps(ore_prolungato), "Tempo Prolungato (36h)")
    )

    # 5. Inserimento docenti dall'immagine fornita
    nomi_docenti = [
        "Abruzzese M.", "Ambrosecchia", "Basso", "Bevilacqua", "Brillante", 
        "Bruno", "Buonopane", "Chioccola", "Cobino", "Cozzo", "De Simone", 
        "Flammia", "Galante", "Galante (ITA)", "Giusto", "Grande", "Grieci", 
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
            "INSERT INTO docenti (nome, ore_settimanali, vincoli) VALUES (?, ?, ?)",
            (d, 18, json.dumps(vincoli_default))
        )

    # 6. Creazione assegnazioni per coprire le ore di tutte le classi
    materie = ["Italiano", "Matematica", "Inglese", "Storia", "Geografia", "Tecnologia", "Arte", "Scienze Motorie", "Musica"]
    
    cursor.execute("SELECT nome, orario_ore FROM classi")
    tutte_le_classi = cursor.fetchall()

    docente_idx = 0
    for classe, orario_json in tutte_le_classi:
        ore_dict = json.loads(orario_json)
        ore_rimanenti = sum(ore_dict.values())

        while ore_rimanenti > 0:
            materia = materie[docente_idx % len(materie)]
            ore_assegnate = min(ore_rimanenti, 3)
            docente = nomi_docenti[docente_idx % len(nomi_docenti)]
            
            cursor.execute(
                "INSERT INTO assegnazioni (classe, materia, docente, ore_settimanali) VALUES (?, ?, ?, ?)",
                (classe, materia, docente, ore_assegnate)
            )
            ore_rimanenti -= ore_assegnate
            docente_idx += 1

    conn.commit()
    conn.close()

    print("✅ Database perfettamente allineato e popolato!")
    print(f"   - Classi inserite: 12 (11 normali a 30h, 1 prolungata a 36h)")
    print(f"   - Docenti inseriti: {len(nomi_docenti)}")

if __name__ == "__main__":
    popola_dati_scuola()