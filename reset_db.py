import os

db_path = "orario_scolastico.db"

print("🗑️ Avvio pulizia del database...")

if os.path.exists(db_path):
    try:
        os.remove(db_path)
        print(f"✅ Il file '{db_path}' è stato eliminato con successo.")
    except Exception as e:
        print(f"❌ Errore durante la rimozione del file: {e}")
else:
    print(f"⚠️ Il file '{db_path}' non esiste già nella cartella.")

print("✨ Operazione completata! Al prossimo avvio dell'app Streamlit, il database verrà ricreato pulito e vuoto.")