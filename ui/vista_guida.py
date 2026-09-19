import streamlit as st

def mostra_vista_guida():
    st.title("📖 Guida Utente - Profilo Advanced")
    st.write("Benvenuto nella guida ufficiale per gli utenti con profilo **Advanced** dell'applicazione **Orario Scolastico**.")
    
    st.divider()

    with st.expander("1. Panoramica dell'Interfaccia", expanded=True):
        st.markdown("""
        Accedendo con le tue credenziali Advanced, hai accesso esclusivo al tuo progetto personale e agli strumenti di configurazione tramite la barra laterale (sidebar):
        * **Parametri Istituto**: Permette di definire i giorni scolastici standard e il numero di ore giornaliere.
        * **Sezioni Principali (Viste)**:
          * **📚 Classi**: Inserimento e gestione delle classi dell'istituto.
          * **👨‍🏫 Docenti**: Gestione dei docenti e dei relativi vincoli orari.
          * **📖 Materie e Carichi**: Definizione delle materie e dei carichi didattici.
          * **🔗 Assegnazioni**: Collegamento tra classi, materie e docenti (cattedre).
          * **⚙️ Genera Orario**: Avvio del motore di calcolo e visualizzazione del risultato.
          * **📖 Guida Utente**: Questa sezione di supporto e consultazione.
        * **Menu Espandibili di Gestione**:
          * **👥 Gestione Utenti Base**: Creazione e gestione di account di sola lettura associati al tuo progetto.
          * **💾 Salva Progetto**: Esportazione dell'intero progetto in formato `.json`.
          * **🔄 Nuovo / Reset Dati**: Azzeramento dei dati del progetto corrente.
          * **📂 Carica Progetto**: Importazione di un file di progetto `.json` salvato in precedenza.
        """)

    with st.expander("2. Flusso di Lavoro Consigliato"):
        st.markdown("""
        Per ottenere un orario scolastico corretto e privo di errori di coerenza, segui questo ordine operativo:
        
        1. **Imposta i Parametri dell'Istituto**: Espandi l'apposito menu nella barra laterale, seleziona i giorni scolastici attivi e le ore standard, quindi clicca su *Aggiorna Parametri*.
        2. **Inserisci le Classi**: Vai alla sezione *Classi* per aggiungere le sezioni (es. 1A, 2B) e configurare eventuali monte ore specifici.
        3. **Inserisci i Docenti**: Vai alla sezione *Docenti* per aggiungere il personale docente, indicando il monte ore settimanale (es. 18 ore) e i vincoli. 
            Potrai inserire ore indesiderate e giorni/ore indisponibili per ciascun docente, così da evitare conflitti durante la generazione dell'orario.
        4. **Configura le Materie**: Vai alla sezione *Materie e Carichi* per definire gli insegnamenti previsti.
        5. **Crea le Assegnazioni**: Vai alla sezione *Assegnazioni* per unire classi, materie e docenti, impostando anche la preferenza per i blocchi orari.
        6. **Genera l'Orario**: Vai su *Genera Orario* per avviare il calcolo automatico e verificare il quadro risultante.
        """)

    with st.expander("3. Gestione degli Utenti Base (Sola Lettura)"):
        st.markdown("""
        Se desideri condividere l'orario con i docenti o i collaboratori scolastici senza rischiare modifiche accidentali:
        1. Espandi il menu **👥 Gestione Utenti Base** nella barra laterale.
        2. Entra nella tab **➕ Crea** per registrare un nuovo account specificando username e password.
        3. L'utente base potrà effettuare il login e visualizzare esclusivamente l'orario ufficiale associato al tuo progetto.
        """)

    with st.expander("4. Salvataggio e Backup"):
        st.markdown("""
        **È fortemente consigliato eseguire copie di sicurezza periodiche del proprio lavoro anche per mantenere le versioni precedenti dell'orario. Per farlo:**
        * **Salva Progetto**: Espandi il menu *Salva Progetto*, assegna un nome personalizzato e scarica il file `.json` sul computer.
        * **Carica Progetto**: Ti consente di ripristinare in qualsiasi momento una configurazione salvata caricando il relativo file `.json`.
        """)