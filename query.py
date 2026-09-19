import json
import sqlite3

db_path = "orario_scolastico.db"  # se il file .db è nella stessa cartella
query = """
SELECT classe, giorno, ora, materia, docente
FROM orario_fissati
WHERE progetto = 'Principale';
"""

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

rows = conn.execute(query).fetchall()

# trasformo i risultati in lista di dizionari
result = [dict(r) for r in rows]

print(json.dumps(result, ensure_ascii=False, indent=2))

conn.close()