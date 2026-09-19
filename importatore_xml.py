import sqlite3
import xml.etree.ElementTree as ET
import json
import re

def importa_xml_orariofacile(file_xml_path, db_path="orario_scolastico.db", nome_progetto="Importato_OrarioFacile"):
    try:
        # 1. Lettura e pulizia preventiva del file XML
        with open(file_xml_path, 'r', encoding='cp1252', errors='replace') as f:
            lines = f.readlines()

        cleaned_lines = []
        for line in lines:
            if "value=" in line or "VALUE=" in line or "name=" in line or "NAME=" in line:
                line = line.replace('<', '&lt;').replace('>', '&gt;')
            cleaned_lines.append(line)
            
        content = "".join(cleaned_lines)

        parser = ET.XMLParser(encoding='cp1252')
        root = ET.fromstring(content, parser=parser)
        
    except Exception as e:
        return False, f"Errore nella lettura del file XML: {e}"

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Inizializzazione tabelle progetto
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS progetti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE
            )
        """)
        cursor.execute("DELETE FROM progetti WHERE nome = ?", (nome_progetto,))
        cursor.execute("INSERT OR IGNORE INTO progetti (nome) VALUES (?)", (nome_progetto,))
        
        cursor.execute("DELETE FROM classi WHERE progetto = ?", (nome_progetto,))
        cursor.execute("DELETE FROM docenti WHERE progetto = ?", (nome_progetto,))
        cursor.execute("DELETE FROM materie WHERE progetto = ?", (nome_progetto,))
        cursor.execute("DELETE FROM assegnazioni WHERE progetto = ?", (nome_progetto,))
        cursor.execute("DELETE FROM orario_risultato WHERE progetto = ?", (nome_progetto,))

        classi_trovate = set()
        docenti_trovati = set()
        materie_trovate = set()
        cattedre_mappa = {} 
        lezioni_da_inserire = []

        giorni_mappa = {
            "LUN": "Lunedì", "MAR": "Martedì", "MER": "Mercoledì", 
            "GIO": "Giovedì", "VEN": "Venerdì", "SAB": "Sabato",
            "LUNEDÌ": "Lunedì", "MARTEDÌ": "Martedì", "MERCOLEDÌ": "Mercoledì", 
            "GIOVEDÌ": "Giovedì", "VENERDÌ": "Venerdì", "SABATO": "Sabato"
        }

        # Funzione di supporto per estrarre il nome pulito da un elemento (controlla attributi e testo)
        def estrai_testo(elem):
            if elem is None:
                return ""
            # Cerca negli attributi più comuni
            for attr in ['value', 'NAME', 'name', 'Value', 'SHORTNAME']:
                if attr in elem.attrib:
                    val = elem.attrib[attr].strip()
                    if val and not val.startswith("<") and val.lower() != "materia":
                        return val
            # Altrimenti guarda il testo interno
            if elem.text:
                val = elem.text.strip()
                if val and not val.startswith("<") and val.lower() != "materia":
                    return val
            return ""

        # 2. Scansione mirata di tutti gli elementi alla ricerca dei dati anagrafici
        for elem in root.iter():
            tag = elem.tag.upper()
            
            # Se l'elemento ha un attributo NAME o VALUE significativo
            valore = estrai_testo(elem)
            if not valore:
                continue

            # Riconoscimento in base al tag o al contesto
            if tag in ['TEACHER', 'PROFESSOR'] or ('TEACHER' in tag):
                docenti_trovati.add(valore)
            elif tag in ['SUBJECT'] or ('SUBJECT' in tag):
                materie_trovate.add(valore)
            elif tag in ['GROUP', 'CLASS'] or ('GROUP' in tag) or ('CLASS' in tag):
                classi_trovate.add(valore)
            elif tag == 'NAME':
                # I tag NAME possono appartenere a docenti o materie a seconda di dove si trovano
                # Se sembra un nome proprio o una sigla valida
                if len(valore) > 1 and not valore.isdigit():
                    # Discriminiamo in base ai fratelli o al testo
                    parent_str = "".join(elem.itertext()).upper()
                    if "SEX" in parent_str or "." in valore or len(valore.split()) > 0:
                        docenti_trovati.add(valore)

        # 3. Analisi dei blocchi lezione (<LESSON> o simili)
        for elem in root.iter():
            tag_name = elem.tag.upper()
            if 'LESSON' in tag_name or 'LEZIONE' in tag_name or tag_name == 'ITEM':
                
                # Estrae materia
                subject = "Materia"
                for child in elem:
                    if 'SUBJECT' in child.tag.upper() or 'MATERIA' in child.tag.upper():
                        t = estrai_testo(child)
                        if t: subject = t
                materie_trovate.add(subject)

                # Estrae classe
                group = "Classe"
                for child in elem:
                    if 'GROUP' in child.tag.upper() or 'CLASS' in child.tag.upper() or 'CLASSE' in child.tag.upper():
                        t = estrai_testo(child)
                        if t: group = t
                classi_trovate.add(group)

                # Estrae docenti
                teacher_texts = []
                for child in elem:
                    if 'TEACHER' in child.tag.upper() or 'DOCENTE' in child.tag.upper():
                        t = estrai_testo(child)
                        if t: teacher_texts.append(t)
                
                if not teacher_texts:
                    teacher_str = "N.D."
                elif len(teacher_texts) == 1:
                    teacher_str = teacher_texts[0]
                else:
                    teacher_str = " + ".join(teacher_texts)

                for t in teacher_texts:
                    docenti_trovati.add(t)

                # Estrae giorno
                day_raw = "LUN"
                for child in elem:
                    if 'DAY' in child.tag.upper() or 'GIORNO' in child.tag.upper():
                        t = estrai_testo(child)
                        if t: day_raw = t
                day = giorni_mappa.get(day_raw.upper(), "Lunedì")

                # Estrae orario
                time_str = "8:10"
                for child in elem:
                    if 'TIME' in child.tag.upper() or 'ORA' in child.tag.upper():
                        t = estrai_testo(child)
                        if t: time_str = t

                ora_num = 1
                try:
                    if ":" in time_str:
                        ore_h = int(time_str.split(':')[0])
                        if ore_h <= 8: ora_num = 1
                        elif ore_h == 9: ora_num = 2
                        elif ore_h == 10: ora_num = 3
                        elif ore_h == 11: ora_num = 4
                        elif ore_h == 12: ora_num = 5
                        elif ore_h == 13: ora_num = 6
                        elif ore_h >= 14: ora_num = 7
                    else:
                        ora_num = int(time_str)
                except:
                    ora_num = 1

                # Durata
                durata_ore = 1
                for child in elem:
                    if 'DURATION' in child.tag.upper() or 'DURATA' in child.tag.upper():
                        dur_val = estrai_testo(child)
                        if dur_val:
                            try:
                                durata_ore = int(dur_val.split(':')[0])
                            except:
                                pass

                chiave_cattedra = (group, subject, teacher_str)
                cattedre_mappa[chiave_cattedra] = cattedre_mappa.get(chiave_cattedra, 0) + durata_ore

                for d_offset in range(durata_ore):
                    ora_effettiva = ora_num + d_offset
                    lezioni_da_inserire.append((
                        nome_progetto, group, day, ora_effettiva, subject, teacher_str
                    ))

        # Rimuove eventuali valori di fallback errati se abbiamo trovato dati reali
        if "Materia" in materie_trovate and len(materie_trovate) > 1:
            materie_trovate.remove("Materia")
        if "Classe" in classi_trovate and len(classi_trovate) > 1:
            classi_trovate.remove("Classe")

        # 4. Salvataggio Classi
        for classe in sorted(list(classi_trovate)):
            giorni_default = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
            ore_giornaliere = {g: 6 for g in giorni_default}
            cursor.execute(
                "INSERT OR REPLACE INTO classi (progetto, nome, giorni, orario_ore, note) VALUES (?, ?, ?, ?, ?)",
                (nome_progetto, classe, json.dumps(giorni_default), json.dumps(ore_giornaliere), "Importato da OrarioFacile")
            )

        # 5. Salvataggio Docenti
        for docente in sorted(list(docenti_trovati)):
            if docente and docente != "N.D.":
                cursor.execute(
                    "INSERT OR REPLACE INTO docenti (progetto, nome, ore_settimanali, vincoli) VALUES (?, ?, ?, ?)",
                    (nome_progetto, docente, 18, "{}")
                )

        # 6. Salvataggio Materie
        for materia in sorted(list(materie_trovate)):
            if materia:
                cursor.execute(
                    "INSERT OR REPLACE INTO materie (progetto, nome, ore_default, carichi_personalizzati) VALUES (?, ?, ?, ?)",
                    (nome_progetto, materia, 2, "{}")
                )

        # 7. Salvataggio Assegnazioni
        assegnazioni_accorpate = {}
        for (classe, materia, docente), ore in cattedre_mappa.items():
            chiave_ass = (classe, materia)
            assegnazioni_accorpate[chiave_ass] = assegnazioni_accorpate.get(chiave_ass, 0) + ore

        for (classe, materia), ore in assegnazioni_accorpate.items():
            docente_rif = "N.D."
            for (c, m, d), o in cattedre_mappa.items():
                if c == classe and m == materia:
                    docente_rif = d
                    break
            
            d1 = docente_rif
            d2 = ""
            if " + " in docente_rif:
                parts = docente_rif.split(" + ")
                d1 = parts[0]
                d2 = " + ".join(parts[1:])

            cursor.execute(
                "INSERT OR REPLACE INTO assegnazioni (progetto, classe, materia, docente, docente_2, ore, preferenza_blocchi) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nome_progetto, classe, materia, d1, d2, ore, "Blocchi da 2 ore")
            )

        # 8. Salvataggio Orario Risultato
        for lezione in lezioni_da_inserire:
            cursor.execute(
                "INSERT OR REPLACE INTO orario_risultato (progetto, classe, giorno, ora, materia, docente) VALUES (?, ?, ?, ?, ?, ?)",
                lezione
            )

        conn.commit()
        conn.close()
        return True, f"Importazione completata! Importate {len(classi_trovate)} classi, {len(docenti_trovati)} docenti, {len(materie_trovate)} materie e {len(lezioni_da_inserire)} ore di lezione."
    
    except Exception as e:
        return False, f"Errore interno durante il salvataggio nel database: {e}"