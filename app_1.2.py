import streamlit as st
import pandas as pd
import sqlite3
import json
import os
import zipfile

from ui.vista_classi import mostra_vista_classi
from ui.vista_docenti import mostra_vista_docenti
from ui.vista_materie import mostra_vista_materie
from ui.vista_assegnazioni import mostra_vista_assegnazioni
from ui.vista_generazione import mostra_vista_generazione
from ui.vista_guida import mostra_vista_guida  # <-- Importazione della vista guida
from importatore_xml import importa_xml_orariofacile

st.set_page_config(page_title="Gestione Orario Scolastico", layout="wide")

# --- INIZIALIZZAZIONE STATO GLOBALE UTENTE E CONFIG ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'ruolo' not in st.session_state:
    st.session_state.ruolo = "advanced"
if 'progetto_associato' not in st.session_state:
    st.session_state.progetto_associato = ""
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

# --- INIZIALIZZAZIONE DATABASE (UTENTI + TABELLE PROGETTO BLINDATE) ---
def inizializza_db_locale():
    conn = sqlite3.connect("orario_scolastico.db")
    cursor = conn.cursor()
    
    # Tabella Utenti aggiornata con ruolo e progetto associato
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            ruolo TEXT DEFAULT 'advanced',
            progetto_associato TEXT DEFAULT NULL
        )
    """)
    
    # Creazione account admin di default se la tabella è vuota
    cursor.execute("SELECT COUNT(*) FROM utenti")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT OR IGNORE INTO utenti (username, password, ruolo) VALUES (?, ?, ?)", ("admin", "admin123", "admin"))

    # Migrazione colonne se la tabella esiste già senza
    cursor.execute("PRAGMA table_info(utenti)")
    colonne_utenti = [col[1] for col in cursor.fetchall()]
    if "ruolo" not in colonne_utenti:
        try:
            cursor.execute("ALTER TABLE utenti ADD COLUMN ruolo TEXT DEFAULT 'advanced'")
        except Exception:
            pass
    if "progetto_associato" not in colonne_utenti:
        try:
            cursor.execute("ALTER TABLE utenti ADD COLUMN progetto_associato TEXT DEFAULT NULL")
        except Exception:
            pass
    
    # Creazione tabelle con colonna progetto garantita
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
            motivo TEXT,
            progetto TEXT DEFAULT 'Principale'
        )
    """)
    
    # Migrazione di sicurezza per la colonna 'motivo' in orario_fallimenti
    cursor.execute("PRAGMA table_info(orario_fallimenti)")
    colonne_fallimenti = [col[1] for col in cursor.fetchall()]
    if "motivo" not in colonne_fallimenti:
        try:
            cursor.execute("ALTER TABLE orario_fallimenti ADD COLUMN motivo TEXT")
        except Exception:
            pass

    # Migrazione di sicurezza: aggiunge la colonna 'progetto' se il DB esisteva già senza
    tabelle = ["classi", "docenti", "materie", "assegnazioni", "orario_risultato", "orario_fissati", "orario_fallimenti"]
    for tabella in tabelle:
        cursor.execute(f"PRAGMA table_info({tabella})")
        colonne = [col[1] for col in cursor.fetchall()]
        if "progetto" not in colonne:
            try:
                cursor.execute(f"ALTER TABLE {tabella} ADD COLUMN progetto TEXT DEFAULT 'Principale'")
            except Exception:
                pass

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
                cursor.execute("SELECT password, ruolo, progetto_associato FROM utenti WHERE username = ?", (user_in,))
                row = cursor.fetchone()
                conn.close()
                
                if row and row[0] == pass_in:
                    st.session_state.logged_in = True
                    st.session_state.username = user_in
                    st.session_state.ruolo = row[1] if row[1] else "advanced"
                    st.session_state.progetto_associato = row[2] if row[2] else ""
                    
                    if st.session_state.ruolo == "base":
                        st.session_state.progetto_corrente = st.session_state.progetto_associato if st.session_state.progetto_associato else "Principale"
                    else:
                        st.session_state.progetto_corrente = user_in
                        
                    st.success(f"Benvenuto, {user_in} ({st.session_state.ruolo})!")
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
    st.stop()

# =====================================================================
# GESTIONE ACCESSO UTENTE BASE (SOLA LETTURA)
# =====================================================================
if st.session_state.get("ruolo") == "base":
    st.title("🏫 Orario Scolastico - Visualizzazione Sola Lettura")
    st.write(f"Utente: **{st.session_state.username}** (Profilo Base) | Progetto associato: **{st.session_state.progetto_corrente}**")
    
    if st.button("🚪 Logout", type="primary"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.ruolo = "advanced"
        st.rerun()
        
    st.divider()
    st.info("ℹ️ Stai visualizzando l'orario ufficiale associato al tuo profilo.")
    
    conn = sqlite3.connect("orario_scolastico.db")
    df_risultato_base = pd.read_sql("SELECT * FROM orario_risultato WHERE progetto = ?", conn, params=(st.session_state.progetto_corrente,))
    conn.close()
    
    if df_risultato_base.empty:
        st.warning("Nessun orario disponibile per questo progetto al momento.")
    else:
        tab_c, tab_d, tab_s = st.tabs(["📚 Per Classe", "👨‍🏫 Per Docente", "📊 Quadro Sinottico"])
        ordine_giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"]
        
        with tab_c:
            classi_b = sorted(df_risultato_base["classe"].unique())
            cls_scelta_b = st.selectbox("Seleziona Classe", options=classi_b, key="base_cls")
            df_cl_b = df_risultato_base[df_risultato_base["classe"] == cls_scelta_b].copy()
            df_cl_b["lezione"] = df_cl_b["materia"] + "\n(" + df_cl_b["docente"] + ")"
            pivot_cl_b = df_cl_b.pivot_table(index="ora", columns="giorno", values="lezione", aggfunc=lambda x: ' / '.join(x))
            g_pres = [g for g in ordine_giorni if g in pivot_cl_b.columns]
            st.dataframe(pivot_cl_b[g_pres], use_container_width=True)
            
        with tab_d:
            docenti_b = sorted(df_risultato_base["docente"].dropna().unique())
            doc_scelto_b = st.selectbox("Seleziona Docente", options=docenti_b, key="base_doc")
            df_doc_b = df_risultato_base[df_risultato_base["docente"] == doc_scelto_b].copy()
            df_doc_b["lezione"] = df_doc_b["materia"] + "\n[" + df_doc_b["classe"] + "]"
            pivot_doc_b = df_doc_b.pivot_table(index="ora", columns="giorno", values="lezione", aggfunc=lambda x: ' / '.join(x))
            g_pres_d = [g for g in ordine_giorni if g in pivot_doc_b.columns]
            st.dataframe(pivot_doc_b[g_pres_d] if g_pres_d else pivot_doc_b, use_container_width=True)
            
        with tab_s:
            st.dataframe(df_risultato_base, use_container_width=True)
            
    st.stop()

# =====================================================================
# GESTIONE ACCESSO UTENTE AMMINISTRATORE (PANNELLO ADMIN & SUPPORTO)
# =====================================================================
if st.session_state.get("ruolo") == "admin":
    if "progetto_admin_impersonato" not in st.session_state or not st.session_state["progetto_admin_impersonato"]:
        st.title("🛡️ Pannello Amministratore di Sistema")
        st.write(f"Benvenuto Admin: **{st.session_state.username}**. Gestisci gli utenti o seleziona un progetto in supporto.")
        
        col_top1, col_top2 = st.columns([1, 3])
        with col_top1:
            if st.button("🚪 Logout", type="primary", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.username = ""
                st.session_state.ruolo = "advanced"
                st.rerun()
                
        st.divider()
        
        # --- SEZIONE 1: GESTIONE UTENTI (CREAZIONE, MODIFICA, CANCELLAZIONE A CASCATA) ---
        st.subheader("👥 Gestione Utenti e Account")
        
        conn_adm = sqlite3.connect("orario_scolastico.db")
        df_utenti = pd.read_sql("SELECT username, ruolo, progetto_associato FROM utenti", conn_adm)
        conn_adm.close()
        
        st.dataframe(df_utenti, use_container_width=True)
        
        tab_crea, tab_mod, tab_del = st.tabs(["➕ Crea Utente", "✏️ Modifica Utente", "🗑️ Elimina Utente (Cascata)"])
        
        with tab_crea:
            with st.form("form_crea_utente_admin"):
                nuovo_user = st.text_input("Username").strip()
                nuovo_pass = st.text_input("Password", type="password")
                nuovo_ruolo = st.selectbox("Ruolo", options=["advanced", "base", "admin"])
                
                st.info("💡 **Regole Progetto:**\n- **Advanced**: gestirà un proprio progetto autonomo.\n- **Base**: inserisci l'username dell'utente advanced a cui collegarlo.")
                nuovo_prog = st.text_input("Progetto Associato (obbligatorio se ruolo = base)").strip()
                
                btn_crea = st.form_submit_button("Crea Utente", type="primary")
                if btn_crea:
                    if not nuovo_user or not nuovo_pass:
                        st.error("Inserisci username e password.")
                    else:
                        try:
                            if nuovo_ruolo == "advanced" and not nuovo_prog:
                                nuovo_prog = nuovo_user
                                
                            conn_c = sqlite3.connect("orario_scolastico.db")
                            cursor_c = conn_c.cursor()
                            cursor_c.execute(
                                "INSERT INTO utenti (username, password, ruolo, progetto_associato) VALUES (?, ?, ?, ?)",
                                (nuovo_user, nuovo_pass, nuovo_ruolo, nuovo_prog if nuovo_prog else None)
                            )
                            conn_c.commit()
                            conn_c.close()
                            st.success(f"✅ Utente {nuovo_user} ({nuovo_ruolo}) creato con successo!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore nella creazione (username probabilmente già esistente): {e}")

        with tab_mod:
            st.write("Modifica la password o il ruolo di un utente esistente.")
            utente_mod = st.selectbox("Seleziona utente da modificare", options=df_utenti["username"].tolist(), key="sel_mod_user")
            
            conn_m = sqlite3.connect("orario_scolastico.db")
            cur_m = conn_m.cursor()
            cur_m.execute("SELECT ruolo, progetto_associato FROM utenti WHERE username = ?", (utente_mod,))
            r_mod = cur_m.fetchone()
            conn_m.close()
            
            current_ruolo = r_mod[0] if r_mod else "advanced"
            current_prog = r_mod[1] if r_mod else ""
            
            with st.form("form_mod_utente"):
                mod_pass = st.text_input("Nuova Password (lascia vuoto per non cambiarla)", type="password")
                ruoli_disponibili = ["advanced", "base", "admin"]
                mod_ruolo = st.selectbox("Nuovo Ruolo", options=ruoli_disponibili, index=ruoli_disponibili.index(current_ruolo) if current_ruolo in ruoli_disponibili else 0)
                mod_prog = st.text_input("Nuovo Progetto Associato", value=current_prog if current_prog else "")
                
                btn_salva_mod = st.form_submit_button("Salva Modifiche", type="primary")
                if btn_salva_mod:
                    conn_up = sqlite3.connect("orario_scolastico.db")
                    cur_up = conn_up.cursor()
                    if mod_pass:
                        cur_up.execute("UPDATE utenti SET password = ?, ruolo = ?, progetto_associato = ? WHERE username = ?", 
                                       (mod_pass, mod_ruolo, mod_prog if mod_prog else None, utente_mod))
                    else:
                        cur_up.execute("UPDATE utenti SET ruolo = ?, progetto_associato = ? WHERE username = ?", 
                                       (mod_ruolo, mod_prog if mod_prog else None, utente_mod))
                    conn_up.commit()
                    conn_up.close()
                    st.success(f"✅ Utente {utente_mod} aggiornato con successo!")
                    st.rerun()

        with tab_del:
            st.warning("⚠️ L'eliminazione di un utente **Advanced** rimuoverà anche tutti i dati del suo progetto in modo permanente.")
            utenti_eliminabili = [u for u in df_utenti["username"].tolist() if u != "admin"]
            
            if utenti_eliminabili:
                utente_da_eliminare = st.selectbox("Seleziona utente da eliminare", options=utenti_eliminabili, key="sel_del_user")
                if st.button("🗑️ Elimina Utente e Pulisci a Cascata il Progetto", type="secondary"):
                    conn_del = sqlite3.connect("orario_scolastico.db")
                    cursor_del = conn_del.cursor()
                    
                    cursor_del.execute("DELETE FROM utenti WHERE username = ?", (utente_da_eliminare,))
                    
                    tabelle_progetto = ["classi", "docenti", "materie", "assegnazioni", "orario_risultato", "orario_fissati", "orario_fallimenti"]
                    for tab in tabelle_progetto:
                        cursor_del.execute(f"DELETE FROM {tab} WHERE progetto = ?", (utente_da_eliminare,))
                        
                    conn_del.commit()
                    conn_del.close()
                    st.success(f"🗑️ Utente {utente_da_eliminare} e dati associati eliminati.")
                    st.rerun()
            else:
                st.info("Nessun utente eliminabile.")

        st.divider()

        # --- SEZIONE 2: MODALITÀ SUPPORTO / IMPERSONATE ---
        st.subheader("🛠️ Modalità Supporto (Ispeziona e Modifica Progetto Advanced)")
        st.write("Se un utente Advanced ha bisogno di aiuto, seleziona il suo progetto per aprirlo ed eventualmente correggerlo.")
        
        conn_adv = sqlite3.connect("orario_scolastico.db")
        df_advanced = pd.read_sql("SELECT username FROM utenti WHERE ruolo = 'advanced'", conn_adv)
        conn_adv.close()
        
        lista_advanced = df_advanced["username"].tolist()
        
        if lista_advanced:
            prog_impersonato = st.selectbox("Seleziona il progetto utente", options=["--- Seleziona Progetto ---"] + lista_advanced)
            
            if prog_impersonato != "--- Seleziona Progetto ---":
                if st.button(f"🚀 Apri il progetto di '{prog_impersonato}'", type="primary"):
                    st.session_state["progetto_admin_impersonato"] = prog_impersonato
                    st.success(f"✅ Stai operando in supporto sul progetto di **{prog_impersonato}**.")
                    st.rerun()
        else:
            st.info("Nessun utente Advanced registrato al momento.")
            
        st.stop()
    else:
        st.session_state.progetto_corrente = st.session_state["progetto_admin_impersonato"]

# =====================================================================
# APPLICAZIONE PRINCIPALE (UTENTE ADVANCED O ADMIN IN SUPPORTO)
# =====================================================================

if "progetto_admin_impersonato" not in st.session_state or not st.session_state["progetto_admin_impersonato"]:
    st.session_state.progetto_corrente = st.session_state.username

st.title("🏫 Orario Scolastico")
if st.session_state.get("ruolo") == "admin":
    st.warning(f"⚠️ **Modalità Supporto Attiva:** Stai operando sul progetto di **{st.session_state['progetto_corrente']}**")
    if st.button("🔙 Esci dalla Modalità Supporto (Torna al Pannello Admin)"):
        del st.session_state["progetto_admin_impersonato"]
        st.rerun()
else:
    st.write(f"Utente attivo: **{st.session_state.username}** (Progetto in gestione: **{st.session_state.progetto_corrente}**) | v 1.0 beta")

# --- BARRA LATERALE ---
with st.sidebar:
    st.header(f"👤 {st.session_state.username}")
    
    if st.button("🚪 Logout", type="primary", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.ruolo = "advanced"
        if "progetto_admin_impersonato" in st.session_state:
            del st.session_state["progetto_admin_impersonato"]
        st.rerun()

    # --- BOX DONAZIONE SUBITO SOTTO IL LOGOUT ---
    st.markdown("""
    <div style="font-size: 12px; color: #8b949e; margin-top: 10px; margin-bottom: 6px;">
    Se questo strumento ti è utile, puoi supportare lo sviluppo!
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(
        '<a href="https://www.paypal.com/donate/?business=SNW476G47Y6GG&no_recurring=0&currency_code=EUR" target="_blank">'
        '<button style="width:100%; background-color:#0070ba; color:white; border:none; '
        'padding:6px 10px; border-radius:6px; font-weight:bold; cursor:pointer; font-size:12px;">'
        '☕ Offrimi un Caffè (PayPal)'
        '</button></a>',
        unsafe_allow_html=True
    )

    st.divider()

    # --- 1. PARTE FISSA IN ALTO (Non scorre mai) ---
    scelta_vista = st.radio("Seleziona Sezione", [
        "📚 Classi", 
        "👨‍🏫 Docenti", 
        "📖 Materie e Carichi", 
        "🔗 Assegnazioni",
        "⚙️ Genera Orario",
        "📖 Guida Utente"  # <-- Aggiunto nel menu laterale
    ])

    st.divider()

    # --- PARAMETRI ISTITUTO ESPANDIBILE ---
    with st.expander("⚙️ Parametri Istituto"):
        giorni_salvati = st.session_state.config_default.get("giorni", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])
        ore_salvate = st.session_state.config_default.get("ore_standard", 6)

        giorni_def = st.multiselect(
            "Giorni scolastici standard",
            ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"],
            default=giorni_salvati,
            key="ms_giorni_istituto"
        )
        ore_def = st.slider("Ore giornaliere standard", min_value=4, max_value=8, value=ore_salvate, key="sl_ore_istituto")
        
        if st.button("Aggiorna Parametri", use_container_width=True):
            st.session_state.config_default["giorni"] = giorni_def
            st.session_state.config_default["ore_standard"] = ore_def
            st.success("✅ Parametri aggiornati!")
            st.rerun()

    st.divider()

    # --- 2. PARTE SCORREVOLE (Chiusa dentro il container con scroll) ---
    with st.container(height=450):
        
        # --- GESTIONE UTENTI BASE DEL PROGETTO (SOLO PER ADVANCED) - MENU ESPANDIBILE ---
        if st.session_state.ruolo == "advanced":
            with st.expander("👥 Gestione Utenti Base"):
                st.write("Crea e gestisci gli account di sola lettura associati al tuo progetto.")
                
                tab_c_base, tab_m_base = st.tabs(["➕ Crea", "⚙️ Gestisci"])
                
                with tab_c_base:
                    with st.form("form_crea_base_advanced", clear_on_submit=True):
                        u_base = st.text_input("Username").strip()
                        p_base = st.text_input("Password", type="password")
                        btn_crea_base = st.form_submit_button("Crea Utente Base", use_container_width=True)
                        
                        if btn_crea_base:
                            if not u_base or not p_base:
                                st.error("Inserisci username e password.")
                            else:
                                try:
                                    conn_b = sqlite3.connect("orario_scolastico.db")
                                    cursor_b = conn_b.cursor()
                                    cursor_b.execute(
                                        "INSERT INTO utenti (username, password, ruolo, progetto_associato) VALUES (?, ?, 'base', ?)",
                                        (u_base, p_base, st.session_state.username)
                                    )
                                    conn_b.commit()
                                    conn_b.close()
                                    st.success(f"✅ Utente base '{u_base}' creato!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Errore: username già esistente.")

                with tab_m_base:
                    conn_ub = sqlite3.connect("orario_scolastico.db")
                    df_miei_base = pd.read_sql("SELECT username FROM utenti WHERE ruolo = 'base' AND progetto_associato = ?", conn_ub, params=(st.session_state.username,))
                    conn_ub.close()
                    
                    if df_miei_base.empty:
                        st.info("Nessun utente base associato.")
                    else:
                        lista_base_miei = df_miei_base["username"].tolist()
                        utente_base_scelto = st.selectbox("Seleziona utente", options=lista_base_miei, key="sel_gestione_base")
                        
                        with st.form("form_mod_del_base"):
                            nuova_p_base = st.text_input("Nuova Password (opzionale)", type="password")
                            
                            col_mb1, col_mb2 = st.columns(2)
                            with col_mb1:
                                btn_salva_b = st.form_submit_button("Salva", use_container_width=True)
                            with col_mb2:
                                btn_elimina_b = st.form_submit_button("Elimina", use_container_width=True)
                                
                            if btn_salva_b:
                                conn_up_b = sqlite3.connect("orario_scolastico.db")
                                cur_up_b = conn_up_b.cursor()
                                if nuova_p_base:
                                    cur_up_b.execute("UPDATE utenti SET password = ? WHERE username = ?", (nuova_p_base, utente_base_scelto))
                                    conn_up_b.commit()
                                    st.success(f"✅ Password di '{utente_base_scelto}' aggiornata!")
                                conn_up_b.close()
                                st.rerun()
                                
                            if btn_elimina_b:
                                conn_del_b = sqlite3.connect("orario_scolastico.db")
                                cur_del_b = conn_del_b.cursor()
                                cur_del_b.execute("DELETE FROM utenti WHERE username = ? AND progetto_associato = ?", (utente_base_scelto, st.session_state.username))
                                conn_del_b.commit()
                                conn_del_b.close()
                                st.warning(f"🗑️ Utente '{utente_base_scelto}' eliminato.")
                                st.rerun()

        # --- ESPORTAZIONE (DOWNLOAD JSON) - MENU ESPANDIBILE ---
        with st.expander("💾 Salva Progetto"):
            nome_file_export = st.text_input("Nome file di salvataggio", value=f"orario_{st.session_state.progetto_corrente}")
            
            if st.button("Genera File di Salvataggio", use_container_width=True):
                try:
                    conn = sqlite3.connect("orario_scolastico.db")
                    prog = st.session_state.progetto_corrente
                    df_classi = pd.read_sql("SELECT nome, giorni, orario_ore, note FROM classi WHERE progetto = ?", conn, params=(prog,))
                    df_docenti = pd.read_sql("SELECT nome, ore_settimanali, vincoli FROM docenti WHERE progetto = ?", conn, params=(prog,))
                    df_materie = pd.read_sql("SELECT nome, ore_default, carichi_personalizzati FROM materie WHERE progetto = ?", conn, params=(prog,))
                    df_assegnazioni = pd.read_sql("SELECT classe, materia, docente, docente_2, ore, preferenza_blocchi FROM assegnazioni WHERE progetto = ?", conn, params=(prog,))
                    
                    try:
                        df_risultato = pd.read_sql("SELECT classe, giorno, ora, materia, docente FROM orario_risultato WHERE progetto = ?", conn, params=(prog,))
                    except:
                        df_risultato = pd.DataFrame()
                        
                    try:
                        df_fissati = pd.read_sql("SELECT classe, giorno, ora, materia, docente FROM orario_fissati WHERE progetto = ?", conn, params=(prog,))
                    except:
                        df_fissati = pd.DataFrame()
                        
                    conn.close()
                    
                    progetto_data = {
                        "config": st.session_state.config_default,
                        "classi": df_classi.to_dict(orient="records"),
                        "docenti": df_docenti.to_dict(orient="records"),
                        "materie": df_materie.to_dict(orient="records"),
                        "assegnazioni": df_assegnazioni.to_dict(orient="records"),
                        "orario_risultato": df_risultato.to_dict(orient="records"),
                        "orario_fissati": df_fissati.to_dict(orient="records")
                    }
                    
                    json_str = json.dumps(progetto_data, indent=4, ensure_ascii=False)
                    
                    st.download_button(
                        label="⬇️ Scarica File Progetto",
                        data=json_str,
                        file_name=f"{nome_file_export.strip()}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Errore durante l'esportazione: {e}")

        # --- PULIZIA (RESET DATI UTENTE) - MENU ESPANDIBILE ---
        with st.expander("🔄 Nuovo / Reset Dati"):
            st.warning("⚠️ **Attenzione:** Questa azione eliminerà tutti i dati inseriti in questo progetto.")
            
            if "conferma_svuota_tutto" not in st.session_state:
                st.session_state.conferma_svuota_tutto = False

            if not st.session_state.conferma_svuota_tutto:
                if st.button("🗑️ Svuota i dati del progetto", use_container_width=True):
                    st.session_state.conferma_svuota_tutto = True
                    st.rerun()
            else:
                st.error("❗ Sei sicuro di voler azzerare i dati?")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    if st.button("Sì, procedi", use_container_width=True):
                        try:
                            conn = sqlite3.connect("orario_scolastico.db")
                            cursor = conn.cursor()
                            prog = st.session_state.progetto_corrente
                            
                            cursor.execute("DELETE FROM classi WHERE progetto = ?", (prog,))
                            cursor.execute("DELETE FROM docenti WHERE progetto = ?", (prog,))
                            cursor.execute("DELETE FROM materie WHERE progetto = ?", (prog,))
                            cursor.execute("DELETE FROM assegnazioni WHERE progetto = ?", (prog,))
                            cursor.execute("DELETE FROM orario_risultato WHERE progetto = ?", (prog,))
                            cursor.execute("DELETE FROM orario_fissati WHERE progetto = ?", (prog,))
                            cursor.execute("DELETE FROM orario_fallimenti WHERE progetto = ?", (prog,))
                            
                            conn.commit()
                            conn.close()
                            
                            st.session_state.conferma_svuota_tutto = False
                            st.success("✅ Dati azzerati con successo!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante lo svuotamento: {e}")
                with col_c2:
                    if st.button("Annulla", use_container_width=True):
                        st.session_state.conferma_svuota_tutto = False
                        st.rerun()

        # --- IMPORTAZIONE PROGETTO DA JSON - MENU ESPANDIBILE ---
        with st.expander("📂 Carica Progetto"):
            file_caricato = st.file_uploader("Seleziona file .json del progetto", type=["json"], key="upl_json_side")
            
            if file_caricato is not None:
                if st.button("Carica nel Progetto", use_container_width=True):
                    try:
                        dati_caricati = json.load(file_caricato)
                        conn = sqlite3.connect("orario_scolastico.db")
                        cursor = conn.cursor()
                        prog = st.session_state.progetto_corrente
                        
                        cursor.execute("DELETE FROM classi WHERE progetto = ?", (prog,))
                        cursor.execute("DELETE FROM docenti WHERE progetto = ?", (prog,))
                        cursor.execute("DELETE FROM materie WHERE progetto = ?", (prog,))
                        cursor.execute("DELETE FROM assegnazioni WHERE progetto = ?", (prog,))
                        cursor.execute("DELETE FROM orario_risultato WHERE progetto = ?", (prog,))
                        cursor.execute("DELETE FROM orario_fissati WHERE progetto = ?", (prog,))
                        
                        for c in dati_caricati.get("classi", []):
                            cursor.execute(
                                "INSERT INTO classi (nome, giorni, orario_ore, note, progetto) VALUES (?, ?, ?, ?, ?)",
                                (c.get("nome"), c.get("giorni"), c.get("orario_ore"), c.get("note"), prog)
                            )
                        
                        for d in dati_caricati.get("docenti", []):
                            vincoli_raw = d.get("vincoli")
                            if isinstance(vincoli_raw, dict):
                                vincoli_str = json.dumps(vincoli_raw, ensure_ascii=False)
                            else:
                                vincoli_str = str(vincoli_raw) if vincoli_raw else "{}"
                            cursor.execute(
                                "INSERT INTO docenti (nome, ore_settimanali, vincoli, progetto) VALUES (?, ?, ?, ?)",
                                (d.get("nome"), d.get("ore_settimanali"), vincoli_str, prog)
                            )

                        for m in dati_caricati.get("materie", []):
                            cursor.execute(
                                "INSERT INTO materie (nome, ore_default, carichi_personalizzati, progetto) VALUES (?, ?, ?, ?)",
                                (m.get("nome"), m.get("ore_default"), m.get("carichi_personalizzati", "{}"), prog)
                            )
                        
                        for a in dati_caricati.get("assegnazioni", []):
                            cursor.execute(
                                "INSERT INTO assegnazioni (classe, materia, docente, docente_2, ore, preferenza_blocchi, progetto) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (a.get("classe"), a.get("materia"), a.get("docente"), a.get("docente_2"), a.get("ore"), a.get("preferenza_blocchi"), prog)
                            )
                            
                        for r in dati_caricati.get("orario_risultato", []):
                            cursor.execute(
                                "INSERT INTO orario_risultato (classe, giorno, ora, materia, docente, progetto) VALUES (?, ?, ?, ?, ?, ?)",
                                (r.get("classe"), r.get("giorno"), r.get("ora"), r.get("materia"), r.get("docente"), prog)
                            )

                        for f in dati_caricati.get("orario_fissati", []):
                            cursor.execute(
                                "INSERT INTO orario_fissati (classe, giorno, ora, materia, docente, progetto) VALUES (?, ?, ?, ?, ?, ?)",
                                (f.get("classe"), f.get("giorno"), f.get("ora"), f.get("materia"), f.get("docente"), prog)
                            )
                        
                        conn.commit()
                        conn.close()
                        
                        if "config" in dati_caricati:
                            st.session_state.config_default = dati_caricati["config"]
                        
                        st.success("✅ Progetto caricato con successo!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Errore durante l'importazione del file: {e}")

# --- ROUTER DES VISTE NELLA CARTELLA UI ---
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
elif scelta_vista == "📖 Guida Utente":
    mostra_vista_guida()  # <-- Collegamento della funzione di visualizzazione della guida