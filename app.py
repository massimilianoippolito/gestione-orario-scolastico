import streamlit as st
import pandas as pd
from classi import GestoreClassi
from docenti import GestoreDocenti

st.set_page_config(page_title="Gestione Orario Scolastico", layout="wide")

st.title("🏫 Pannello di Controllo: Classi e Docenti")
st.write("Architettura modulare con persistenza su database SQLite.")

# --- INIZIALIZZAZIONE DEI GESTORI ---
db_classi = GestoreClassi()
db_docenti = GestoreDocenti()

# --- INIZIALIZZAZIONE DELLO STATO PER IL DEFAULT (solo UI) ---
if 'config_default' not in st.session_state:
    st.session_state.config_default = {
        "giorni": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"],
        "ore_standard": 6
    }

# --- BARRA LATERALE ---
with st.sidebar:
    st.header("⚙️ Profilo Orario Default")
    giorni_def = st.multiselect(
        "Giorni scolastici standard",
        ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"],
        default=st.session_state.config_default["giorni"]
    )
    ore_def = st.slider("Ore giornaliere standard", min_value=4, max_value=8, value=st.session_state.config_default["ore_standard"])
    
    st.divider()
    st.subheader("⚖️ Vincoli Generali Docenti")
    min_ore_giorno_gen = st.number_input("Ore minime giornaliere", min_value=1, max_value=4, value=2)
    max_ore_giorno_gen = st.number_input("Ore massime giornaliere", min_value=4, max_value=8, value=5)
    max_buche_sett_gen = st.number_input("Max ore buche settimanali", min_value=0, max_value=10, value=3)
    max_buche_giorno_gen = st.number_input("Max ore buche giornaliere", min_value=0, max_value=3, value=1)
    max_prime_ore_gen = st.number_input("Max presenze in 1ª ora", min_value=1, max_value=6, value=2)
    
    if st.button("Salva Parametri Istituto"):
        st.session_state.config_default["giorni"] = giorni_def
        st.session_state.config_default["ore_standard"] = ore_def
        st.success("✅ Parametri di istituto aggiornati!")

# --- INTERFACCIA A SCHEDE ---
tab_classi, tab_docenti = st.tabs(["📚 Gestione Classi", "👨‍🏫 Gestione Docenti"])

# ================= TAB 1: CLASSI =================
with tab_classi:
    col_form_c, col_lista_c = st.columns([1, 1.2])
    
    with col_form_c:
        st.subheader("➕ Inserisci Nuova Classe")
        with st.form("form_nuova_classe", clear_on_submit=True):
            nome_classe = st.text_input("Identificativo (es. 1A, 2B)").strip().upper()
            st.write(f"*Eredita default:* {len(giorni_def)} giorni, {ore_def} ore/giorno.")
            usa_personalizzato = st.checkbox("Modifica orario specifico (Eccezione)")
            
            ore_personalizzate = {}
            if usa_personalizzato:
                st.write("Imposta le ore per singolo giorno:")
                for g in giorni_def:
                    ore_personalizzate[g] = st.number_input(f"Ore per {g}", min_value=1, max_value=9, value=ore_def, key=f"ins_c_{g}")
            
            btn_aggiungi_c = st.form_submit_button("Crea Classe")
            
            if btn_aggiungi_c:
                if not nome_classe:
                    st.error("⚠️ Inserisci un nome valido per la classe.")
                else:
                    orario_assegnato = ore_personalizzate if usa_personalizzato else {g: ore_def for g in giorni_def}
                    nota = "Personalizzato" if usa_personalizzato else "Standard"
                    
                    successo, messaggio = db_classi.aggiungi_classe(nome_classe, giorni_def, orario_assegnato, nota)
                    if successo:
                        st.success(f"✅ {messaggio}")
                        st.rerun()
                    else:
                        st.error(f"❌ {messaggio}")

    with col_lista_c:
        st.subheader("📚 Elenco e Modifica Classi")
        classi_dict = db_classi.ottieni_tutte_le_classi()
        
        if not classi_dict:
            st.warning("Nessuna classe configurata.")
        else:
            riepilogo_c = [{"Classe": cls, "Totale Ore/Sett.": sum(dati["ore"].values()), "Profilo": dati["note"]} for cls, dati in classi_dict.items()]
            st.dataframe(pd.DataFrame(riepilogo_c), use_container_width=True, hide_index=True)
            
            classe_sel = st.selectbox("Seleziona classe da gestire", list(classi_dict.keys()), key="sel_c")
            if classe_sel:
                dati_c = classi_dict[classe_sel]
                with st.expander(f"🛠️ Modifica o Elimina: {classe_sel}", expanded=True):
                    with st.form(f"form_mod_classe_{classe_sel}"):
                        nuovo_nome_c = st.text_input("Nome Classe", value=classe_sel).strip().upper()
                        st.write("**Modifica ore giornaliere:**")
                        nuove_ore_c = {}
                        for g in dati_c["giorni"]:
                            val_prec = dati_c["ore"].get(g, 6)
                            nuove_ore_c[g] = st.number_input(f"Ore {g}", min_value=1, max_value=9, value=val_prec, key=f"mod_c_{classe_sel}_{g}")
                        
                        btn_salva_c = st.form_submit_button("Salva Modifiche")
                        
                        if btn_salva_c:
                            suc, msg = db_classi.aggiorna_classe(classe_sel, nuovo_nome_c, dati_c["giorni"], nuove_ore_c, "Personalizzato")
                            if suc:
                                st.success(f"✅ {msg}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                    
# --- ELIMINAZIONE PROTETTA CLASSE ---
                    conf_key_c = f"conferma_del_c_{classe_sel}"
                    if conf_key_c not in st.session_state:
                        st.session_state[conf_key_c] = False

                    if not st.session_state[conf_key_c]:
                        if st.button(f"🗑️ Elimina Classe {classe_sel}", type="secondary", key=f"btn_del_c_{classe_sel}"):
                            st.session_state[conf_key_c] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Sei sicuro di voler eliminare la classe '{classe_sel}'?")
                        col_conf1, col_conf2 = st.columns(2)
                        if col_conf1.button("Sì, elimina", key=f"yes_c_{classe_sel}", type="primary"):
                            db_classi.elimina_classe(classe_sel)
                            st.session_state[conf_key_c] = False
                            st.success(f"🗑️ Classe {classe_sel} rimossa.")
                            st.rerun()
                        if col_conf2.button("Annulla", key=f"no_c_{classe_sel}"):
                            st.session_state[conf_key_c] = False
                            st.rerun()

# ================= TAB 2: DOCENTI =================
with tab_docenti:
    col_form_d, col_lista_d = st.columns([1, 1.2])
    
    with col_form_d:
        st.subheader("➕ Inserisci Nuovo Docente")
        with st.form("form_nuovo_docente", clear_on_submit=True):
            nome_docente = st.text_input("Nome e Cognome Docente").strip()
            ore_docente = st.number_input("Ore Settimanali Contratto", min_value=1, max_value=24, value=18)
            
            st.write("<b>Vincoli specifici:</b>", unsafe_allow_html=True)
            min_o = st.number_input("Min ore giornaliere", min_value=1, max_value=4, value=min_ore_giorno_gen)
            max_o = st.number_input("Max ore giornaliere", min_value=4, max_value=8, value=max_ore_giorno_gen)
            max_b_s = st.number_input("Max buche settimanali", min_value=0, max_value=10, value=max_buche_sett_gen)
            max_b_g = st.number_input("Max buche giornaliere", min_value=0, max_value=3, value=max_buche_giorno_gen)
            max_p_o = st.number_input("Max presenze in 1ª ora", min_value=1, max_value=6, value=max_prime_ore_gen)
            
            btn_aggiungi_d = st.form_submit_button("Crea Docente")
            
            if btn_aggiungi_d:
                if not nome_docente:
                    st.error("⚠️ Inserisci un nome valido per il docente.")
                else:
                    vincoli_personalizzati = {
                        "min_ore_giorno": min_o, "max_ore_giorno": max_o,
                        "max_buche_sett": max_b_s, "max_buche_giorno": max_b_g,
                        "max_prime_ore": max_p_o,
                        "non_disponibili": {},
                        "indesiderate": {}
                    }
                    successo, messaggio = db_docenti.aggiungi_docente(nome_docente, ore_docente, vincoli_personalizzati)
                    if successo:
                        st.success(f"✅ {messaggio}")
                        st.rerun()
                    else:
                        st.error(f"❌ {messaggio}")

    with col_lista_d:
        st.subheader("👨‍🏫 Elenco e Modifica Docenti")
        docenti_dict = db_docenti.ottieni_tutti_i_docenti()
        
        if not docenti_dict:
            st.warning("Nessun docente configurato.")
        else:
            riepilogo_d = []
            for doc, dati in docenti_dict.items():
                v = dati["vincoli"]
                riepilogo_d.append({
                    "Docente": doc, "Ore/Sett.": dati["ore_settimanali"],
                    "Ore Giorno": f"{v.get('min_ore_giorno')} - {v.get('max_ore_giorno')}",
                    "Max Buche S./G.": f"{v.get('max_buche_sett')} / {v.get('max_buche_giorno')}",
                    "Max 1ª Ora": v.get('max_prime_ore')
                })
            st.dataframe(pd.DataFrame(riepilogo_d), use_container_width=True, hide_index=True)
            
            docente_sel = st.selectbox("Seleziona docente da gestire", list(docenti_dict.keys()), key="sel_d")
            if docente_sel:
                dati_d = docenti_dict[docente_sel]
                v_corr = dati_d["vincoli"]
                
                with st.expander(f"🛠️ Modifica o Elimina: {docente_sel}", expanded=True):
                    
                    # --- TABELLA INTERATTIVA DISPONIBILITÀ (DINAMICA IN BASE AI GIORNI) ---
                    st.subheader("📅 Tabella Interattiva Disponibilità")
                    st.caption("Legenda: 🟢 Libero | 🟡 Indesiderata | 🔴 Non disponibile (clicca per cambiare)")
                    
                    # I giorni dipendono direttamente dalle impostazioni generali della barra laterale
                    giorni_settimana = st.session_state.config_default.get("giorni", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])
                    ore_giornata = [1, 2, 3, 4, 5, 6]
                    
                    grid_key = f"grid_state_{docente_sel}"
                    if grid_key not in st.session_state:
                        grid = {}
                        non_disp = v_corr.get("non_disponibili", {})
                        indes = v_corr.get("indesiderate", {})
                        for g in giorni_settimana:
                            for o in ore_giornata:
                                if o in non_disp.get(g, []):
                                    grid[(g, o)] = "non_disponibile"
                                elif o in indes.get(g, []):
                                    grid[(g, o)] = "indesiderata"
                                else:
                                    grid[(g, o)] = "libero"
                        st.session_state[grid_key] = grid

                    cols = st.columns([1] + [2]*len(giorni_settimana))
                    cols[0].markdown("**Ora**")
                    for idx, g in enumerate(giorni_settimana):
                        cols[idx+1].markdown(f"<div style='text-align: center;'><b>{g}</b></div>", unsafe_allow_html=True)
                        
                    grid_corrente = st.session_state[grid_key]
                    
                    for ora in ore_giornata:
                        row_cols = st.columns([1] + [2]*len(giorni_settimana))
                        row_cols[0].markdown(f"**{ora}ª**")
                        
                        for idx, g in enumerate(giorni_settimana):
                            stato = grid_corrente.get((g, ora), "libero")
                            
                            if stato == "libero":
                                etichetta = "🟢"
                            elif stato == "indesiderata":
                                etichetta = "🟡"
                            else:
                                etichetta = "🔴"
                                
                            if row_cols[idx+1].button(etichetta, key=f"btn_{docente_sel}_{g}_{ora}"):
                                if stato == "libero":
                                    grid_corrente[(g, ora)] = "indesiderata"
                                elif stato == "indesiderata":
                                    grid_corrente[(g, ora)] = "non_disponibile"
                                else:
                                    grid_corrente[(g, ora)] = "libero"
                                    
                                st.session_state[grid_key] = grid_corrente
                                st.rerun()

                    st.divider()

                    # --- FORM DI SALVATAGGIO ---
                    with st.form(f"form_mod_doc_{docente_sel}"):
                        nuovo_nome_d = st.text_input("Nome Docente", value=docente_sel).strip()
                        nuove_ore_d = st.number_input("Ore Settimanali", min_value=1, max_value=24, value=dati_d["ore_settimanali"])
                        
                        st.write("**Vincoli di Carico:**")
                        col_v1, col_v2 = st.columns(2)
                        with col_v1:
                            m_min = st.number_input("Min ore/giorno", min_value=1, max_value=4, value=v_corr.get("min_ore_giorno", 2), key=f"md_min_{docente_sel}")
                            m_max = st.number_input("Max ore/giorno", min_value=4, max_value=8, value=v_corr.get("max_ore_giorno", 5), key=f"md_max_{docente_sel}")
                            b_set = st.number_input("Max buche sett.", min_value=0, max_value=10, value=v_corr.get("max_buche_sett", 3), key=f"md_bset_{docente_sel}")
                        with col_v2:
                            b_gio = st.number_input("Max buche giorno", min_value=0, max_value=3, value=v_corr.get("max_buche_giorno", 1), key=f"md_bgio_{docente_sel}")
                            p_ora = st.number_input("Max 1ª ora", min_value=1, max_value=6, value=v_corr.get("max_prime_ore", 2), key=f"md_pora_{docente_sel}")
                        
                        btn_salva_d = st.form_submit_button("Salva Modifiche e Griglia Oraria")
                        
                        if btn_salva_d:
                            nuove_non_disp = {}
                            nuove_indesiderate = {}
                            
                            for (g, o), stato_cella in st.session_state[grid_key].items():
                                if stato_cella == "non_disponibile":
                                    if g not in nuove_non_disp:
                                        nuove_non_disp[g] = []
                                    nuove_non_disp[g].append(o)
                                elif stato_cella == "indesiderata":
                                    if g not in nuove_indesiderate:
                                        nuove_indesiderate[g] = []
                                    nuove_indesiderate[g].append(o)
                                    
                            for g in nuove_non_disp:
                                nuove_non_disp[g].sort()
                            for g in nuove_indesiderate:
                                nuove_indesiderate[g].sort()

                            nuovi_vincoli = {
                                "min_ore_giorno": m_min, 
                                "max_ore_giorno": m_max,
                                "max_buche_sett": b_set, 
                                "max_buche_giorno": b_gio,
                                "max_prime_ore": p_ora,
                                "non_disponibili": nuove_non_disp,
                                "indesiderate": nuove_indesiderate
                            }
                            
                            if grid_key in st.session_state:
                                del st.session_state[grid_key]
                                
                            suc_d, msg_d = db_docenti.aggiorna_docente(docente_sel, nuovo_nome_d, nuove_ore_d, nuovi_vincoli)
                            if suc_d:
                                st.success(f"✅ {msg_d}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg_d}")
                    
                # --- ELIMINAZIONE PROTETTA DOCENTE ---
                    conf_key_d = f"conferma_del_d_{docente_sel}"
                    if conf_key_d not in st.session_state:
                        st.session_state[conf_key_d] = False

                    if not st.session_state[conf_key_d]:
                        if st.button(f"🗑️ Elimina Docente {docente_sel}", type="secondary", key=f"btn_del_d_{docente_sel}"):
                            st.session_state[conf_key_d] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Sei sicuro di voler eliminare il docente '{docente_sel}'?")
                        col_conf1, col_conf2 = st.columns(2)
                        if col_conf1.button("Sì, elimina", key=f"yes_d_{docente_sel}", type="primary"):
                            if grid_key in st.session_state:
                                del st.session_state[grid_key]
                            db_docenti.elimina_docente(docente_sel)
                            st.session_state[conf_key_d] = False
                            st.success(f"🗑️ Docente {docente_sel} rimosso.")
                            st.rerun()
                        if col_conf2.button("Annulla", key=f"no_d_{docente_sel}"):
                            st.session_state[conf_key_d] = False
                            st.rerun()  