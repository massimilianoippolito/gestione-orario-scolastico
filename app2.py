import streamlit as st
import pandas as pd
import sqlite3
from ui.vista_classi import mostra_vista_classi
from ui.vista_docenti import mostra_vista_docenti
from ui.vista_materie import mostra_vista_materie
from ui.vista_assegnazioni import mostra_vista_assegnazioni
from ui.vista_generazione import mostra_vista_generazione

st.set_page_config(page_title="Gestione Orario Scolastico", layout="wide")


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

# --- GESTIONE PROGETTI / ORDINI DI SCUOLA NEL DB ---
def inizializza_progetti_db():
    conn = sqlite3.connect("orario_scolastico.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS progetti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO progetti (id, nome) VALUES (1, 'Principale')")
    conn.commit()
    conn.close()

inizializza_progetti_db()

# --- STATO GLOBALE CONDIVISO DELL'ISTITUTO ---
if 'config_default' not in st.session_state:
    st.session_state.config_default = {
        "giorni": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"],
        "ore_standard": 6
    }

# --- BARRA LATERALE ---
with st.sidebar:
    st.header("🏫 Progetto Orario")

    # Fissiamo il progetto corrente in modo trasparente per il momento
    progetto_corrente = "Principale"
    progetto_selezionato = "Principale"
    st.info(f"Progetto attivo: **{progetto_corrente}**")
    
    # Sarà attivata in versioni future
    # conn = sqlite3.connect("orario_scolastico.db")
    # df_progetti = pd.read_sql("SELECT nome FROM progetti ORDER BY id", conn)
    # conn.close()
    # lista_progetti = df_progetti["nome"].tolist()

    # progetto_selezionato = st.selectbox(
    #     "Ordine di Scuola / Plesso Attivo",
    #     options=lista_progetti,
    #     key="progetto_corrente"
    # )

    # with st.expander("➕ Crea Nuovo Progetto"):
    #     nuovo_progetto = st.text_input("Nome Progetto (es. Primaria)")
    #     if st.button("Crea Progetto"):
    #         if nuovo_progetto.strip():
    #             try:
    #                 conn = sqlite3.connect("orario_scolastico.db")
    #                 cursor = conn.cursor()
    #                 cursor.execute("INSERT INTO progetti (nome) VALUES (?)", (nuovo_progetto.strip(),))
    #                 conn.commit()
    #                 conn.close()
    #                 st.success(f"Progetto '{nuovo_progetto}' creato!")
    #                 st.rerun()
    #             except Exception as e:
    #                 st.error(f"Errore (esiste già?): {e}")
    #         else:
    #             st.warning("Inserisci un nome valido.")

    st.divider()
    st.header("⚙️ Parametri Istituto")
    giorni_def = st.multiselect(
        "Giorni scolastici standard",
        ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"],
        default=st.session_state.config_default["giorni"]
    )
    ore_def = st.slider("Ore giornaliere standard", min_value=4, max_value=8, value=st.session_state.config_default["ore_standard"])
    
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

# Mostriamo un piccolo avviso visivo del progetto su cui si sta operando
st.info(f"📂 Stai lavorando sul progetto: **{progetto_selezionato}**")

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