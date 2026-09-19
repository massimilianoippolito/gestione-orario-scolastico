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

# --- INIZIALIZZAZIONE STATO GLOBALE UTENTE E CONFIG ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'config_default' not in st.session_state:
    st.session_state.config_default = {
        "giorni": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"],
        "ore_standard": 6
    }

# --- FORZATURA GRAFICA BLU SCURO & FONT RIDOTTO ---
st.markdown("""
    <style>
        .stApp {
            background-color: #0e1117;
            color: #c9d1d9;
        }
        [data-testid="stSidebar"] {
            background-color: #161b22;
        }
        [data-testid="stDataFrame"] {
            background-color: #0b0e14 !important;
        }
        div[data-testid="stDataFrame"] iframe {
            background-color: #0b0e14 !important;
        }
        .glideDataGrid, canvas {
            background-color: #0b0e14 !important;
        }
        p, .stMarkdown, .stDataFrame {
            font-size: 13px !important;
        }
        h1 { font-size: 1.9rem !important; }
        h2 { font-size: 1.4rem !important; }
        h3 { font-size: 1.1rem !important; }
    </style>
""", unsafe_allow_html=True)

# --- INIZIALIZZAZIONE DATABASE (INCLUSA TABELLA UTENTI E ADMIN DEFAULT) ---
def inizializza_db_locale():
    conn = sqlite3.connect("orario_scolastico.db")
    cursor = conn.cursor()
    
    # Tabella Utenti
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)
    
    # Creazione automatica di un account admin di default se la tabella è vuota
    cursor.execute("SELECT COUNT(*) FROM utenti")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT OR IGNORE INTO utenti (username, password) VALUES (?, ?)", ("admin", "admin123"))
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            giorni TEXT,
            orario_ore INTEGER,
            note TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS docenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            ore_settimanali INTEGER,
            vincoli TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            ore_default INTEGER,
            carichi_personalizzati TEXT,
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

# =====================================================================
# GESTIONE AUTENTICAZIONE (ACCESSO RISERVATO)
# =====================================================================
if not st.session_state.logged_in:
    st.title("🏫 Orario Scolastico - Accesso Riservato")
    st.write("Area riservata ai beta tester autorizzati. Inserisci le credenziali fornite dall'amministratore.")
    
    with st.form("form_login"):
        user_in = st.text_input("Username").strip()
        pass_in = st.text_input("Password", type="password")
        btn_login = st.form_submit_button("Entra", type="primary", use_container_width=True)
        
        if btn_login:
            if not user_in or not pass_in:
                st.error("Inserisci username e password.")
            else:
                conn = sqlite3.connect("orario_scolastico.db")
                cursor = conn.cursor()
                cursor.execute("SELECT password FROM utenti WHERE username = ?", (user_in,))
                row = cursor.fetchone()
                conn.close()
                
                if row and row[0] == pass_in:
                    st.session_state.logged_in = True
                    st.session_state.username = user_in
                    st.session_state.progetto_corrente = user_in
                    st.success(f"Benvenuto, {user_in}!")
                    st.rerun()
                else:
                    st.error("Credenziali non valide o utente non autorizzato.")

    # --- BOX DONAZIONE NELLA SCHERMATA DI LOGIN ---
    st.divider()
    st.markdown("""
    <div style="text-align: center; color: #8b949e; font-size: 13px; margin-bottom: 8px;">
    Ti piace questo software? Sostieni lo sviluppo offrendo un caffè! ☕
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(
        '<div style="max-width: 300px; margin: 0 auto;">'
        '<a href="https://www.paypal.com/donate/?business=SNW476G47Y6GG&no_recurring=0&currency_code=EUR" target="_blank">'
        '<button style="width:100%; background-color:#0070ba; color:white; border:none; '
        'padding:8px 12px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:13px;">'
        '☕ Offrimi un Caffè (PayPal)'
        '</button></a></div>',
        unsafe_allow_html=True
    )
    # ---------------------------------------------

    st.stop()    

# =====================================================================
# APPLICAZIONE PRINCIPALE (ACCESSIBILE SOLO DOPO IL LOGIN)
# =====================================================================

st.session_state.progetto_corrente = st.session_state.username

st.title("🏫 Orario Scolastico")
st.write(f"Utente attivo: **{st.session_state.username}** (v 1.0 beta)")

# --- BARRA LATERALE ---
with st.sidebar:
    st.header(f"👤 {st.session_state.username}")
    
    if st.button("🚪 Logout", type="primary", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

    # --- BOX DONAZIONE NELLA SIDEBAR ---
    st.divider()
    st.subheader("☕ Sostieni il Progetto")
    st.markdown("""
    <div style="font-size: 12px; color: #8b949e; margin-bottom: 10px;">
    Se questo strumento ti è utile per il tuo lavoro, puoi supportare i futuri sviluppi con un piccolo contributo!
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(
        '<a href="https://www.paypal.com/donate/?business=SNW476G47Y6GG&no_recurring=0&currency_code=EUR" target="_blank">'
        '<button style="width:100%; background-color:#0070ba; color:white; border:none; '
        'padding:8px 12px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:13px;">'
        '☕ Offrimi un Caffè (PayPal)'
        '</button></a>',
        unsafe_allow_html=True
    )
    # ----------------------------------

    st.divider()

    # --- PULIZIA (RESET DATI UTENTE) ---
    st.subheader("Nuovo / Reset Dati")
    st.warning("⚠️ **Attenzione:** Questa azione eliminerà tutti i dati inseriti nel tuo account.")
    
    if "conferma_svuota_tutto" not in st.session_state:
        st.session_state.conferma_svuota_tutto = False

    if not st.session_state.conferma_svuota_tutto:
        if st.button("🗑️ Svuota i miei dati"):
            st.session_state.conferma_svuota_tutto = True
            st.rerun()
    else:
        st.error("❗ Sei sicuro di voler azzerare i tuoi dati?")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("Sì, procedi"):
                conn = sqlite3.connect("orario_scolastico.db")
                cursor = conn.cursor()
                prog = st.session_state.username
                
                cursor.execute("DELETE FROM classi WHERE progetto = ? OR progetto = 'Principale'", (prog,))
                cursor.execute("DELETE FROM docenti WHERE progetto = ? OR progetto = 'Principale'", (prog,))
                cursor.execute("DELETE FROM materie WHERE progetto = ? OR progetto = 'Principale'", (prog,))
                cursor.execute("DELETE FROM assegnazioni WHERE progetto = ? OR progetto = 'Principale'", (prog,))
                cursor.execute("DELETE FROM orario_risultato WHERE progetto = ? OR progetto = 'Principale'", (prog,))
                cursor.execute("DELETE FROM orario_fissati WHERE progetto = ? OR progetto = 'Principale'", (prog,))
                
                conn.commit()
                conn.close()
                
                st.session_state.conferma_svuota_tutto = False
                st.success("✅ Dati azzerati con successo!")
                st.rerun()
        with col_c2:
            if st.button("Annulla"):
                st.session_state.conferma_svuota_tutto = False
                st.rerun()

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