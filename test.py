import sqlite3

conn = sqlite3.connect("orario_scolastico.db")
cur = conn.cursor()
cur.execute("SELECT vincoli FROM docenti WHERE nome='Buonopane'")
print("ECCO IL VERO JSON:", cur.fetchone()[0])