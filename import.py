import xml.etree.ElementTree as ET
import sqlite3
import json
import os

def importa_orario_xml(xml_path="Grotta_2026_27_PROVV_REV_0.xml", db_path="orario_scolastico.db"):
    if not os.path.exists(xml_path):
        print(f"❌ File {xml_path} non trovato nella cartella.")
        return

    print(f"📖 Lettura del file XML: {xml_path}...")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    assegnazioni_dict = {}
    docenti_set = set()
    classi_set = set()

    for lesson in root.findall('LESSON'):
        duration_str = lesson.find('DURATION').text
        ore = int(duration_str.split(':')[0]) if duration_str else 1

        subject = lesson.find('SUBJECT').text or "Materia"
        group = lesson.find('GROUP').text or "Classe"
        classi_set.add(group)

        teachers = [t.text for t in lesson.findall('TEACHER') if t.text]
        if not teachers:
            continue
        
        teacher_name = " + ".join(teachers)
        for t in teachers:
            docenti_set.add(t)

        key = (teacher_name, group, subject)
        assegnazioni_dict[key] = assegnazioni_dict.get(key, 0) + ore

    print(f"🔍 Estratti dal file: {len(docenti_set)} docenti, {len(classi_set)} classi, {len(assegnazioni_dict)} abbinamenti unici.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Pulizia tabelle esistenti
    cursor.execute("DROP TABLE IF EXISTS assegnazioni")
    cursor.execute("DROP TABLE IF EXISTS classi")
    cursor.execute("DROP TABLE IF EXISTS docenti")

    cursor.execute("""
        CREATE TABLE docenti (
            nome TEXT PRIMARY KEY,
            ore_settimanali INTEGER,
            vincoli TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE classi (
            nome TEXT PRIMARY KEY,
            giorni TEXT,
            orario_ore TEXT,
            note TEXT
        )
    """)

    # Tabella assegnazioni allineata con i campi 'ore' e 'preferenza_blocchi'
    cursor.execute("""
        CREATE TABLE assegnazioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classe TEXT,
            materia TEXT,
            docente TEXT,
            ore INTEGER,
            preferenza_blocchi TEXT
        )
    """)

    vincoli_default = json.dumps({
        "min_ore_giorno": 2, "max_ore_giorno": 5, "max_buche_sett": 2,
        "max_buche_giorno": 1, "max_prime_ore": 2, "giorni_liberi": [],
        "non_disponibili": {}, "indesiderate": {}
    })

    for docente in sorted(docenti_set):
        cursor.execute(
            "INSERT OR IGNORE INTO docenti (nome, ore_settimanali, vincoli) VALUES (?, ?, ?)",
            (docente, 18, vincoli_default)
        )

    giorni_standard = json.dumps(["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])
    ore_standard = json.dumps({"Lunedì": 6, "Martedì": 6, "Mercoledì": 6, "Giovedì": 6, "Venerdì": 6})
    
    for classe in sorted(classi_set):
        cursor.execute(
            "INSERT OR IGNORE INTO classi (nome, giorni, orario_ore, note) VALUES (?, ?, ?, ?)",
            (classe, giorni_standard, ore_standard, "Standard")
        )

    for (teacher, group, subject), ore in assegnazioni_dict.items():
        cursor.execute(
            "INSERT INTO assegnazioni (classe, materia, docente, ore, preferenza_blocchi) VALUES (?, ?, ?, ?, ?)",
            (group, subject, teacher, ore, "Libera")
        )

    conn.commit()
    conn.close()
    print("✅ Importazione completata con successo! Schema perfettamente allineato.")

if __name__ == "__main__":
    importa_orario_xml()