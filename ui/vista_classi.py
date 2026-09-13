import streamlit as st
import pandas as pd
from classi import GestoreClassi

def mostra_vista_classi():
    # Recuperiamo il progetto corrente dalla sessione globale
    progetto_corrente = st.session_state.get("progetto_corrente", "Principale")
    
    # Inizializziamo il gestore passandogli il progetto attivo
    db_classi = GestoreClassi(progetto=progetto_corrente)
    
    giorni_def = st.session_state.config_default.get("giorni", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])
    ore_def = st.session_state.config_default.get("ore_standard", 6)

    st.header("📚 Gestione Classi")
    st.info(f"📁 Stai gestendo le classi per il progetto: **{progetto_corrente}**")
    
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
        st.subheader(f"📚 Elenco e Modifica Classi - {progetto_corrente}")
        classi_dict = db_classi.ottieni_tutte_le_classi()
        
        if not classi_dict:
            st.warning(f"Nessuna classe configurata per il progetto '{progetto_corrente}'.")
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
                    
                    # --- ELIMINAZIONE PROTETTA CLASSE (CON DOPPIA CONFERMA) ---
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