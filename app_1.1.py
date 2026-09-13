import streamlit as st
import pandas as pd
import sqlite3
import json
from ui.vista_classi import mostra_vista_classi
from ui.vista_docenti import mostra_vista_docenti
from ui.vista_materie import mostra_vista_materie
from ui.vista_assegnazioni import mostra_vista_assegnazioni
from ui.vista_generazione import mostra_vista_generazione

st.set_page_config(page_title="Gestione Orario Scolastico", layout="wide")

# --- INIZIALIZZAZIONE SUBITO DELLO STATO GLOBALE ---
if 'config_default' not in st.session_state:
    st.session_state.config_default = {
        "giorni": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"],
        "ore_standard": 6
    }

# --- FORZATURA GRAFICA BLU SCURO & FONT RIDOTTO ---
st.markdown("""
    <style>
        /* Sfondo principale dell'app */
        .stApp {
            background-color: #0e1117;
            color: #c9d1d9;
        }
        
        /* Sfondo della barra laterale */
        [data-testid="stSidebar"] {
            background-color: #161b22;
        }
        
        /* --- SCURIMENTO DELLE TABELLE --- */
        /* Sfondo generale del componente tabella */
        [data-testid="stDataFrame"] {
            background-color: #0b0e14 !important;
        }
        
        /* Forza il colore di sfondo scuro dentro la griglia di Streamlit */
        div[data-testid="stDataFrame"] iframe {
            background-color: #0b0e14 !important;
        }
        
        /* Target specifico per i canvas/griglie delle tabelle interattive */
        .glideDataGrid, canvas {
            background-color: #0b0e14 !important;
        }
        
        /* Riduce la dimensione solo nei paragrafi normali e nelle tabelle */
        p, .stMarkdown, .stDataFrame {
            font-size: 13px !important;
        }
        
        /* Mantiene i titoli delle sezioni ben leggibili */
        h1 { font-size: 1.9rem !important; }
        h2 { font-size: 1.4rem !important; }
        h3 { font-size: 1.1rem !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🏫 Orario Scolastico")
st.write("v 1.0 beta")

# --- INIZIALIZZAZIONE DATABASE DI LAVORO TEMPORANEO ---
def inizializza_db_locale():
    conn = sqlite3.connect("orario_scolastico.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            giorni TEXT,
            orario_ore INTEGER,
            note TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS docenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            ore_settimanali INTEGER,
            vincoli TEXT,
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orario_risultato (
            classe TEXT,
            giorno TEXT,
            ora INTEGER,
            materia TEXT,
            docente TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orario_fissati (
            classe TEXT,
            giorno TEXT,
            ora INTEGER,
            materia TEXT,
            docente TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
        # --- AGGIUNGI QUESTA TABELLA MANCANTE ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orario_fallimenti (
            classe TEXT,
            giorno TEXT,
            ora INTEGER,
            materia TEXT,
            docente TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    conn.commit()
    conn.close()

inizializza_db_locale()

# --- BARRA LATERALE ---
with st.sidebar:
    st.header("📂 Gestione Progetto su File")
    
    # --- ESPORTAZIONE (DOWNLOAD) ---
    st.subheader("Salva Progetto")
    nome_file_export = st.text_input("Nome file di salvataggio", value="mio_orario")
    
    if st.button("Genera File di Salvataggio"):
        try:
            conn = sqlite3.connect("orario_scolastico.db")
            df_classi = pd.read_sql("SELECT nome, giorni, orario_ore, note FROM classi", conn)
            df_docenti = pd.read_sql("SELECT nome, ore_settimanali, vincoli FROM docenti", conn)
            df_assegnazioni = pd.read_sql("SELECT classe, materia, docente, docente_2, ore, preferenza_blocchi FROM assegnazioni", conn)
            
            try:
                df_risultato = pd.read_sql("SELECT classe, giorno, ora, materia, docente FROM orario_risultato", conn)
            except:
                df_risultato = pd.DataFrame()
                
            try:
                df_fissati = pd.read_sql("SELECT classe, giorno, ora, materia, docente FROM orario_fissati", conn)
            except:
                df_fissati = pd.DataFrame()
                
            conn.close()
            
            progetto_data = {
                "config": st.session_state.config_default,
                "classi": df_classi.to_dict(orient="records"),
                "docenti": df_docenti.to_dict(orient="records"),
                "assegnazioni": df_assegnazioni.to_dict(orient="records"),
                "orario_risultato": df_risultato.to_dict(orient="records"),
                "orario_fissati": df_fissati.to_dict(orient="records")
            }
            
            json_str = json.dumps(progetto_data, indent=4, ensure_ascii=False)
            
            st.download_button(
                label="⬇️ Scarica File Progetto",
                data=json_str,
                file_name=f"{nome_file_export.strip()}.json",
                mime="application/json"
            )
        except Exception as e:
            st.error(f"Errore durante l'esportazione: {e}")

    st.divider()

# --- PULIZIA (SVUOTA TUTTO) ---
    st.subheader("Nuovo / Reset")
    st.warning("⚠️ **Attenzione:** Questa azione eliminerà tutti i dati attuali non salvati.")
    st.info("💡 **Consiglio:** Fai prima una copia di backup scaricando il file JSON del progetto.")

    # Inizializziamo lo stato della conferma se non esiste
    if "conferma_svuota_tutto" not in st.session_state:
        st.session_state.conferma_svuota_tutto = False

    if not st.session_state.conferma_svuota_tutto:
        if st.button("🗑️ Svuota Tutto (Azzera Database)"):
            st.session_state.conferma_svuota_tutto = True
            st.rerun()
    else:
        st.error("❗ Sei davvero sicuro di voler cancellare tutto?")
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            if st.button("Sì, procedi"):
                try:
                    conn = sqlite3.connect("orario_scolastico.db")
                    cursor = conn.cursor()
                    cursor.execute("DROP TABLE IF EXISTS classi;")
                    cursor.execute("DROP TABLE IF EXISTS docenti;")
                    cursor.execute("DROP TABLE IF EXISTS assegnazioni;")
                    cursor.execute("DROP TABLE IF EXISTS orario_risultato;")
                    cursor.execute("DROP TABLE IF EXISTS orario_fissati;")
                    conn.commit()
                    conn.close()
                    
                    inizializza_db_locale()
                    st.session_state.conferma_svuota_tutto = False
                    st.success("✅ Database svuotato!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante lo svuotamento: {e}")
                    
        with col_c2:
            if st.button("Annulla"):
                st.session_state.conferma_svuota_tutto = False
                st.rerun()

    st.divider()

    # --- IMPORTAZIONE (UPLOAD & RESET DB) ---
    st.subheader("Carica Progetto")
    
    # --- AVVISI SULL'IMPORTAZIONE AGGIUNTI ---
    st.info("💡 **Consiglio:** Prima di caricare un nuovo file e reinizializzare il DB, assicurati di aver salvato una copia di backup del progetto attuale.")

    file_caricato = st.file_uploader("Seleziona file .json del progetto", type=["json"])
    
    if file_caricato is not None:
        if st.button("Carica e Reinizializza DB"):
            try:
                dati_caricati = json.load(file_caricato)
                
                conn = sqlite3.connect("orario_scolastico.db")
                cursor = conn.cursor()
                
                # 1. Pulizia totale preventiva con eliminazione sicura di tutte le tabelle
                cursor.execute("DROP TABLE IF EXISTS classi;")
                cursor.execute("DROP TABLE IF EXISTS docenti;")
                cursor.execute("DROP TABLE IF EXISTS materie;")
                cursor.execute("DROP TABLE IF EXISTS assegnazioni;")
                cursor.execute("DROP TABLE IF EXISTS orario_risultato;")
                cursor.execute("DROP TABLE IF EXISTS orario_fissati;")
                cursor.execute("DROP TABLE IF EXISTS orario_fallimenti;")
                conn.commit()
                
                # 2. Ricreazione pulita delle tabelle da zero
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
                cursor.execute("""
                    CREATE TABLE docenti (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL,
                        ore_settimanali INTEGER,
                        vincoli TEXT,
                        progetto TEXT DEFAULT 'Principale'
                    )
                """)
                cursor.execute("""
                    CREATE TABLE materie (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT,
                        ore_default INTEGER,
                        carichi_personalizzati TEXT,
                        progetto TEXT DEFAULT 'Principale'
                    )
                """)
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
                
                # 3. Inserimento classi
                for c in dati_caricati.get("classi", []):
                    cursor.execute(
                        "INSERT INTO classi (nome, giorni, orario_ore, note, progetto) VALUES (?, ?, ?, ?, 'Principale')",
                        (c.get("nome"), c.get("giorni"), c.get("orario_ore"), c.get("note"))
                    )
                
                # 4. Inserimento docenti con normalizzazione robusta dei vincoli
                for d in dati_caricati.get("docenti", []):
                    nome_doc = d.get("nome")
                    ore_doc = d.get("ore_settimanali")
                    vincoli_raw = d.get("vincoli")
                    
                    if isinstance(vincoli_raw, dict):
                        vincoli_str = json.dumps(vincoli_raw, ensure_ascii=False)
                    elif isinstance(vincoli_raw, str):
                        try:
                            parsed = json.loads(vincoli_raw)
                            vincoli_str = json.dumps(parsed, ensure_ascii=False)
                        except:
                            vincoli_str = vincoli_raw
                    else:
                        vincoli_str = json.dumps({
                            "min_ore_giorno": 2, "max_ore_giorno": 5, 
                            "max_prime_ore": 2, "max_ultime_ore": 2, 
                            "max_testacoda": 1, "max_buche_sett": 2, 
                            "max_buche_giorno": 1, "giorni_liberi": [], 
                            "non_disponibili": {}, "indesiderate": {}
                        }, ensure_ascii=False)
                        
                    cursor.execute(
                        "INSERT INTO docenti (nome, ore_settimanali, vincoli, progetto) VALUES (?, ?, ?, 'Principale')",
                        (nome_doc, ore_doc, vincoli_str)
                    )
                
                # Controllo di debug immediato per Buonopane
                cursor.execute("SELECT nome, vincoli FROM docenti WHERE nome = 'Buonopane'")
                row_check = cursor.fetchone()
                if row_check:
                    print(f"🔍 [VERIFICA CARICAMENTO] Docente: {row_check[0]} | Vincoli sul DB: {row_check[1]}", flush=True)

                # 5. Inserimento assegnazioni
                for a in dati_caricati.get("assegnazioni", []):
                    cursor.execute(
                        "INSERT INTO assegnazioni (classe, materia, docente, docente_2, ore, preferenza_blocchi, progetto) VALUES (?, ?, ?, ?, ?, ?, 'Principale')",
                        (a.get("classe"), a.get("materia"), a.get("docente"), a.get("docente_2"), a.get("ore"), a.get("preferenza_blocchi"))
                    )
                    
                # 6. Inserimento orario risultato
                for r in dati_caricati.get("orario_risultato", []):
                    cursor.execute(
                        "INSERT INTO orario_risultato (classe, giorno, ora, materia, docente, progetto) VALUES (?, ?, ?, ?, ?, 'Principale')",
                        (r.get("classe"), r.get("giorno"), r.get("ora"), r.get("materia"), r.get("docente"))
                    )

                # 7. Inserimento orario fissati
                for f in dati_caricati.get("orario_fissati", []):
                    cursor.execute(
                        "INSERT INTO orario_fissati (classe, giorno, ora, materia, docente, progetto) VALUES (?, ?, ?, ?, ?, 'Principale')",
                        (f.get("classe"), f.get("giorno"), f.get("ora"), f.get("materia"), f.get("docente"))
                    )
                
                conn.commit()
                conn.close()
                
                if "config" in dati_caricati:
                    st.session_state.config_default = dati_caricati["config"]
                
                st.success("✅ Progetto e orario caricati con successo!")
                st.rerun()
                
            except Exception as e:
                st.error(f"Errore durante l'importazione del file: {e}")

    st.divider()
    st.header("⚙️ Parametri Istituto")
    
    giorni_salvati = st.session_state.config_default.get("giorni", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])
    ore_salvate = st.session_state.config_default.get("ore_standard", 6)

    giorni_def = st.multiselect(
        "Giorni scolastici standard",
        ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"],
        default=giorni_salvati
    )
    ore_def = st.slider("Ore giornaliere standard", min_value=4, max_value=8, value=ore_salvate)
    
    if st.button("Aggiorna Parametri"):
        st.session_state.config_default["giorni"] = giorni_def
        st.session_state.config_default["ore_standard"] = ore_def
        st.success("✅ Parametri aggiornati!")
        st.rerun()

    st.divider()
    
    # Menu di navigazione tra le sezioni dell'app
    scelta_vista = st.radio("Seleziona Sezione", [
        "📚 Classi", 
        "👨‍🏫 Docenti", 
        "📖 Materie e Carichi", 
        "🔗 Assegnazioni",
        "⚙️ Genera Orario"
    ])

st.info("📂 Modalità file locale attiva: gestisci i tuoi salvataggi tramite file JSON nella barra laterale.")

# --- ROUTER DELLE VISTE NELLA CARTELLA UI ---
if scelta_vista == "📚 Classi":
    mostra_vista_classi()
elif scelta_vista == "👨‍🏫 Docenti":
    mostra_vista_docenti()
elif scelta_vista == "📖 Materie e Carichi":
    mostra_vista_materie()
elif scelta_vista == "🔗 Assegnazioni":
    mostra_vista_assegnazioni()
elif scelta_vista == "⚙️ Genera Orario":
    mostra_vista_generazione()