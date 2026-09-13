import sqlite3

def gestisci_utenti():
    db_path = "orario_scolastico.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    while True:
        print("\n--- GESTIONE UTENTI DB ---")
        print("1. Visualizza tutti gli utenti registrati")
        print("2. Inserisci un nuovo utente")
        print("3. Elimina un utente specifico")
        print("4. Elimina TUTTI gli utenti (Svuota tabella)")
        print("5. Esci")
        
        scelta = input("Scegli un'opzione (1-5): ").strip()
        
        if scelta == "1":
            cursor.execute("SELECT username FROM utenti")
            utenti = cursor.fetchall()
            print("\nUtenti attualmente presenti nel database:")
            if not utenti:
                print("   (Nessun utente registrato)")
            else:
                for u in utenti:
                    print(f" - {u[0]}")
                    
        elif scelta == "2":
            nuovo_user = input("Inserisci il nuovo username: ").strip()
            nuova_pass = input("Inserisci la password: ").strip()
            
            if not nuovo_user or not nuova_pass:
                print("❌ Username e password non possono essere vuoti.")
            else:
                try:
                    cursor.execute("INSERT INTO utenti (username, password) VALUES (?, ?)", (nuovo_user, nuova_pass))
                    conn.commit()
                    print(f"✅ Utente '{nuovo_user}' creato con successo!")
                except sqlite3.IntegrityError:
                    print(f"❌ Errore: l'username '{nuovo_user}' esiste già.")
                    
        elif scelta == "3":
            user_da_eliminare = input("Inserisci l'username esatto da eliminare: ").strip()
            cursor.execute("SELECT username FROM utenti WHERE username = ?", (user_da_eliminare,))
            if cursor.fetchone():
                cursor.execute("DELETE FROM utenti WHERE username = ?", (user_da_eliminare,))
                conn.commit()
                print(f"✅ Utente '{user_da_eliminare}' eliminato con successo.")
            else:
                print(f"❌ Utente '{user_da_eliminare}' non trovato.")
                
        elif scelta == "4":
            conferma = input("⚠️ Sei SICURO di voler eliminare TUTTI gli utenti? (s/N): ").strip().lower()
            if conferma == 's':
                cursor.execute("DELETE FROM utenti")
                conn.commit()
                print("✅ Tabella utenti svuotata completamente.")
            else:
                print("Operazione annullata.")
                
        elif scelta == "5":
            print("Uscita in corso...")
            break
        else:
            print("Scelta non valida. Riprova.")
            
    conn.close()

if __name__ == "__main__":
    gestisci_utenti()