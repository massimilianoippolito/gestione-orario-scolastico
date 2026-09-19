import streamlit as st
import pandas as pd
from docenti import GestoreDocenti
import sqlite3
import json

def mostra_vista_docenti():
    # 1. Recuperiamo il progetto corrente dalla sessione globale di Streamlit
    progetto_corrente = st.session_state.get("progetto_corrente", "Principale")
    
    # Inizializziamo il gestore passandogli il progetto corrente
    db = GestoreDocenti(progetto=progetto_corrente)
    
    st.header("👨‍🏫 Gestione Docenti e Vincoli")
    st.info(f"📁 Stai gestendo i docenti per il progetto: **{progetto_corrente}**")

    if 'config_default' in st.session_state and "giorni" in st.session_state.config_default:
        GIORNI_SETTIMANA = st.session_state.config_default["giorni"]
    else:
        GIORNI_SETTIMANA = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]

    ORE_GIORNALIERE = [1, 2, 3, 4, 5, 6, 7, 8]

    # Recuperiamo e ordiniamo alfabeticamente l'elenco dei docenti del progetto attivo
    docenti_raw = db.ottieni_tutti_i_docenti()
    docenti = dict(sorted(docenti_raw.items()))

    # -------------------------------------------------------------
    # LAYOUT A DUE COLONNE: SINISTRA (Modifica/Elimina), DESTRA (Aggiungi)
    # -------------------------------------------------------------
    col_mod_sezione, col_add_sezione = st.columns(2, gap="large")

    # =============================================================
    # COLONNA SINISTRA: MODIFICA E RIMOZIONE DOCENTE
    # =============================================================
    with col_mod_sezione:
        st.subheader("✏️ Modifica e Rimozione Docente")
        
        if not docenti:
            st.info(f"Nessun docente presente per il progetto '{progetto_corrente}'.")
        else:
            docente_da_modificare = st.selectbox("Seleziona docente", list(docenti.keys()), key="mod_doc")
            
            # --- PULIZIA CACHE SE CAMBI DOCENTE ---
            if "ultimo_docente_selezionato" not in st.session_state or st.session_state["ultimo_docente_selezionato"] != docente_da_modificare:
                st.session_state["ultimo_docente_selezionato"] = docente_da_modificare
                # Puliamo le vecchie chiavi dei bottoni della griglia per forzare il ricaricamento
                keys_da_rimuovere = [k for k in st.session_state.keys() if k.startswith("mod_grid_")]
                for k in keys_da_rimuovere:
                    del st.session_state[k]

            dati_attuali = docenti[docente_da_modificare]
            v_attuali = dati_attuali["vincoli"]
            
            # --- AGGIUNTA SICUREZZA: Se i vincoli sono una stringa JSON, li convertiamo in dict ---
            if isinstance(v_attuali, str):
                try:
                    v_attuali = json.loads(v_attuali)
                except:
                    v_attuali = {}

            if "ultimo_docente_modificato" not in st.session_state or st.session_state["ultimo_docente_modificato"] != docente_da_modificare:
                st.session_state["ultimo_docente_modificato"] = docente_da_modificare
                st.session_state["mod_nuovo_nome"] = docente_da_modificare
                st.session_state["mod_nuove_ore"] = dati_attuali["ore_settimanali"]

            mod_prefix_key = f"mod_grid_{docente_da_modificare}"
            nd_esistenti = v_attuali.get("non_disponibili", {})
            ind_esistenti = v_attuali.get("indesiderate", {})

            c_n1, c_n2 = st.columns(2)
            nuovo_nome = c_n1.text_input("Nuovo Nome", key="mod_nuovo_nome")
            nuove_ore = c_n2.number_input("Ore Contratto", min_value=1, max_value=40, key="mod_nuove_ore")
            
            with st.expander("⚙️ Vincoli Generali e Carico Orario", expanded=False):
                m_min = st.number_input("Min ore al giorno", min_value=1, max_value=8, value=v_attuali.get("min_ore_giorno", 2), key="mod_min")
                m_max = st.number_input("Max ore al giorno", min_value=1, max_value=8, value=v_attuali.get("max_ore_giorno", 5), key="mod_max")
                
                c_v1, c_v2, c_v3 = st.columns(3)
                m_prime = c_v1.number_input("Max prime ore", min_value=0, max_value=6, value=v_attuali.get("max_prime_ore", 2), key="mod_prime")
                m_ultime = c_v2.number_input("Max ultime ore", min_value=0, max_value=6, value=v_attuali.get("max_ultime_ore", 2), key="mod_ultime")
                m_testacoda = c_v3.number_input("Max testa-coda", min_value=0, max_value=5, value=v_attuali.get("max_testacoda", 1), key="mod_testacoda")

                c_v4, c_v5 = st.columns(2)
                m_bs = c_v4.number_input("Max buche sett.", min_value=0, max_value=10, value=v_attuali.get("max_buche_sett", 3), key="mod_bs")
                m_bg = c_v5.number_input("Max buche giorno", min_value=0, max_value=5, value=v_attuali.get("max_buche_giorno", 1), key="mod_bg")
            
            giorni_esistenti = v_attuali.get("giorni_liberi", [])
            giorni_esistenti = [g for g in giorni_esistenti if g in GIORNI_SETTIMANA]
            nuovi_giorni = st.multiselect("Giorni di Indisponibilità (Intera giornata)", options=GIORNI_SETTIMANA, default=giorni_esistenti, key="mod_giorni")

            st.markdown("##### 🎛️ Quadro Sinottico (Modifica)")
            st.caption("🟢 Disponibile | 🟡 Indesiderato | 🔴 Non Disponibile")

            h_cols_m = st.columns([1.2] + [1] * len(ORE_GIORNALIERE))
            h_cols_m[0].write("**G / O**")
            for i, ora in enumerate(ORE_GIORNALIERE):
                h_cols_m[i+1].markdown(f"<div style='text-align: center;'><b>{ora}ª</b></div>", unsafe_allow_html=True)

            for giorno in GIORNI_SETTIMANA:
                r_cols_m = st.columns([1.2] + [1] * len(ORE_GIORNALIERE))
                r_cols_m[0].write(f"**{giorno[:3]}**")
                
                giorno_intero_off_m = giorno in nuovi_giorni
                ore_nd = nd_esistenti.get(giorno, [])
                ore_ind = ind_esistenti.get(giorno, [])

                for i, ora in enumerate(ORE_GIORNALIERE):
                    k_m = f"{mod_prefix_key}_{giorno}_{ora}"
                    
                    if giorno_intero_off_m or (ora in ore_nd):
                        st.session_state[k_m] = "rosso"
                    elif ora in ore_ind:
                        st.session_state[k_m] = "giallo"
                    else:
                        if k_m not in st.session_state or st.session_state[k_m] == "verde":
                            st.session_state[k_m] = "verde"
                    
                    stato_m = st.session_state[k_m]
                    label_m = "🟢" if stato_m == "verde" else ("🟡" if stato_m == "giallo" else "🔴")
                    
                    if r_cols_m[i+1].button(label_m, key=f"btn_{k_m}"):
                        if not giorno_intero_off_m:
                            if st.session_state[k_m] == "verde":
                                st.session_state[k_m] = "giallo"
                            elif st.session_state[k_m] == "giallo":
                                st.session_state[k_m] = "rosso"
                            else:
                                st.session_state[k_m] = "verde"
                            st.rerun()

            col_btn_mod, col_btn_del = st.columns(2)
            with col_btn_mod:
                if st.button("💾 Salva Modifiche", type="primary", key="btn_salva_mod_doc", use_container_width=True):
                    nd_mod, ind_mod = {}, {}
                    for giorno in GIORNI_SETTIMANA:
                        nd_g, ind_g = [], []
                        for ora in ORE_GIORNALIERE:
                            km = f"{mod_prefix_key}_{giorno}_{ora}"
                            st_m = st.session_state.get(km, "verde")
                            if st_m == "rosso":
                                nd_g.append(ora)
                            elif st_m == "giallo":
                                ind_g.append(ora)
                        if nd_g:
                            nd_mod[giorno] = nd_g
                        if ind_g:
                            ind_mod[giorno] = ind_g

                    nuovi_vincoli = {
                        "min_ore_giorno": int(m_min),
                        "max_ore_giorno": int(m_max),
                        "max_prime_ore": int(m_prime),
                        "max_ultime_ore": int(m_ultime),
                        "max_testacoda": int(m_testacoda),
                        "max_buche_sett": int(m_bs),
                        "max_buche_giorno": int(m_bg),
                        "giorni_liberi": nuovi_giorni,
                        "non_disponibili": nd_mod,
                        "indesiderate": ind_mod
                    }
                    successo, msg = db.aggiorna_docente(docente_da_modificare, nuovo_nome, nuove_ore, nuovi_vincoli)
                    if successo:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

            with col_btn_del:
                conf_key_doc = f"conferma_del_doc_{docente_da_modificare}"
                if conf_key_doc not in st.session_state:
                    st.session_state[conf_key_doc] = False

                if not st.session_state[conf_key_doc]:
                    if st.button("🗑️ Elimina", type="secondary", key=f"btn_del_doc_{docente_da_modificare}", use_container_width=True):
                        st.session_state[conf_key_doc] = True
                        st.rerun()
                else:
                    if st.button("⚠️ Conferma?", type="primary", key=f"yes_del_doc", use_container_width=True):
                        db.elimina_docente(docente_da_modificare)
                        st.session_state[conf_key_doc] = False
                        st.success("Eliminato.")
                        st.rerun()

    # =============================================================
    # COLONNA DESTRA: AGGIUNGI NUOVO DOCENTE
    # =============================================================
    with col_add_sezione:
        st.subheader("➕ Aggiungi Nuovo Docente")
        
        with st.form("form_nuovo_docente_progetto", clear_on_submit=True):
            nome_docente = st.text_input("Nome Docente", key="add_nome_doc")
            ore_docente = st.number_input("Ore Settimanali di Contratto", min_value=1, max_value=40, value=18, key="add_ore_doc")
            
            with st.expander("⚙️ Parametri Generali Avanzati", expanded=False):
                c1, c2 = st.columns(2)
                min_ore = c1.number_input("Min ore/g", min_value=1, max_value=8, value=2, key="add_min_ore")
                max_ore = c2.number_input("Max ore/g", min_value=1, max_value=8, value=5, key="add_max_ore")

                c3, c4, c5 = st.columns(3)
                max_prime = c3.number_input("Max prime", min_value=0, max_value=6, value=2, key="add_max_prime")
                max_ultime = c4.number_input("Max ultime", min_value=0, max_value=6, value=2, key="add_max_ultime")
                max_testacoda = c5.number_input("Max testa-coda", min_value=0, max_value=5, value=1, key="add_max_testacoda")

                c6, c7 = st.columns(2)
                max_buche_s = c6.number_input("Max buche sett.", min_value=0, max_value=10, value=3, key="add_max_buche_s")
                max_buche_g = c7.number_input("Max buche giorno", min_value=0, max_value=5, value=1, key="add_max_buche_g")

            giorni_liberi = st.multiselect("Giorni di Indisponibilità (Intera giornata)", options=GIORNI_SETTIMANA, key="add_giorni_liberi")
            
            st.markdown("") 
            btn_salva_nuovo = st.form_submit_button("💾 Salva Nuovo Docente", type="primary", use_container_width=True)
            
            if btn_salva_nuovo:
                if nome_docente.strip() == "":
                    st.error("Inserisci un nome valido.")
                else:
                    non_disponibili = {}
                    for g in giorni_liberi:
                        non_disponibili[g] = ORE_GIORNALIERE.copy()

                    vincoli_dict = {
                        "min_ore_giorno": int(min_ore),
                        "max_ore_giorno": int(max_ore),
                        "max_prime_ore": int(max_prime),
                        "max_ultime_ore": int(max_ultime),
                        "max_testacoda": int(max_testacoda),
                        "max_buche_sett": int(max_buche_s),
                        "max_buche_giorno": int(max_buche_g),
                        "giorni_liberi": giorni_liberi,
                        "non_disponibili": non_disponibili,
                        "indesiderate": {}
                    }
                    successo, msg = db.aggiungi_docente(nome_docente.strip(), ore_docente, vincoli_dict)
                    if successo:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

    st.divider()

    # -------------------------------------------------------------
    # SEZIONE IN BASSO: ELENCO DOCENTI ATTUALI (ORDINATO ALFABETICAMENTE)
    # -------------------------------------------------------------
    st.subheader(f"📋 Elenco Generale Docenti - {progetto_corrente}")

    if not docenti:
        st.info(f"Nessun docente presente per il progetto '{progetto_corrente}'. Aggiungine uno sopra.")
    else:
        dati_tabella = []
        for nome, info in docenti.items():
            v = info["vincoli"]
            g_liberi = ", ".join(v.get("giorni_liberi", [])) if v.get("giorni_liberi") else "Nessuno"
            nd_count = sum(len(ore) for ore in v.get("non_disponibili", {}).values())
            ind_count = sum(len(ore) for ore in v.get("indesiderate", {}).values())
            dati_tabella.append({
                "Nome Docente": nome,
                "Ore Contratto": info["ore_settimanali"],
                "Giorni Liberi": g_liberi,
                "Range Giornaliero": f"{v.get('min_ore_giorno', 2)} - {v.get('max_ore_giorno', 5)}h",
                "Max 1ª/Ultima": f"{v.get('max_prime_ore', 2)} / {v.get('max_ultime_ore', 2)}",
                "Max Testa-Coda": v.get("max_testacoda", 1),
                "Slot 🔴 (ND)": nd_count,
                "Slot 🟡 (Indesiderate)": ind_count
            })
        
        df = pd.DataFrame(dati_tabella)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # -------------------------------------------------------------
    # SEZIONE DI EMERGENZA: SVUOTA TABELLE DOCENTI E ASSEGNAZIONI (DEL PROGETTO)
    # -------------------------------------------------------------
    with st.expander(f"⚠️ Zona Pericolosa: Svuota Anagrafica e Assegnazioni ({progetto_corrente})", expanded=False):
        st.warning(f"Attenzione: questa operazione cancellerà permanentemente tutti i docenti, le cattedre e gli orari del progetto **{progetto_corrente}**.")
        
        conferma_reset = st.checkbox("Confermo di voler azzerare docenti e assegnazioni di questo progetto", key="chk_conferma_reset_docenti_proj")
        
        if st.button("🗑️ Svuota Docenti e Assegnazioni", type="primary", use_container_width=True):
            if conferma_reset:
                conn = sqlite3.connect("orario_scolastico.db")
                cursor = conn.cursor()
                try:
                    cursor.execute("DELETE FROM assegnazioni WHERE progetto = ?", (progetto_corrente,))
                    cursor.execute("DELETE FROM docenti WHERE progetto = ?", (progetto_corrente,))
                    cursor.execute("DELETE FROM orario_risultato WHERE progetto = ?", (progetto_corrente,))
                    cursor.execute("DELETE FROM orario_fallimenti WHERE progetto = ?", (progetto_corrente,))
                    cursor.execute("DELETE FROM orario_fissati WHERE progetto = ?", (progetto_corrente,))
                    
                    conn.commit()
                    st.success(f"✅ Dati del progetto '{progetto_corrente}' svuotati con successo!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Errore durante lo svuotamento: {e}")
                finally:
                    conn.close()
            else:
                st.error("❌ Per favore, spunta la casella di conferma prima di procedere con lo svuotamento.")