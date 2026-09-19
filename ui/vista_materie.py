import streamlit as st
import pandas as pd
import sqlite3
from materie import GestoreMaterie
from classi import GestoreClassi

def mostra_vista_materie():
    # Recuperiamo il progetto corrente dalla sessione globale
    progetto_corrente = st.session_state.get("progetto_corrente", "Principale")
    
    # Inizializziamo i gestori passandogli il progetto corrente
    db_materie = GestoreMaterie(progetto=progetto_corrente)
    db_classi = GestoreClassi(progetto=progetto_corrente)

    st.header("📖 Gestione Materie e Carichi Orari")
    st.info(f"📁 Stai gestendo le materie per il progetto: **{progetto_corrente}**")
    
    col_form_m, col_lista_m = st.columns([1, 1.2])
    
    with col_form_m:
        st.subheader("➕ Inserisci Nuova Materia")
        with st.form("form_nuova_materia", clear_on_submit=True):
            nome_materia = st.text_input("Nome Materia (es. Italiano, Matematica)").strip()
            ore_default = st.number_input("Monte Ore Standard (Default)", min_value=1, max_value=12, value=3)
            
            btn_aggiungi_m = st.form_submit_button("Crea Materia")
            
            if btn_aggiungi_m:
                if not nome_materia:
                    st.error("⚠️ Inserisci un nome valido per la materia.")
                else:
                    successo, messaggio = db_materie.aggiungi_materia(nome_materia, ore_default)
                    if successo:
                        st.success(f"✅ {messaggio}")
                        st.rerun()
                    else:
                        st.error(f"❌ {messaggio}")

        # --- PULSANTE PER CARICARE LE MATERIE DI DEFAULT ---
        st.divider()
        st.subheader("⚙️ Configurazione Rapida")
        st.caption("Se la lista è vuota, puoi caricare direttamente il quadro orario standard della scuola secondaria di primo grado.")
        
        if st.button("📥 Carica Materie Standard", use_container_width=True):
            materie_dict_check = db_materie.ottieni_tutte_le_materie()
            if materie_dict_check:
                st.warning("⚠️ Attenzione: hai già delle materie configurate. Svuota prima la lista se vuoi ricaricare le standard.")
            else:
                materie_predefinite = [
                    ("Italiano", 6),
                    ("Matematica", 4),
                    ("Scienze", 2),
                    ("Storia", 2),
                    ("Geografia", 2),
                    ("Inglese", 3),
                    ("Seconda lingua", 2),
                    ("Tecnologia", 2),
                    ("Arte e Immagine", 2),
                    ("Musica", 2),
                    ("Scienze Motorie", 2),
                    ("Religione", 1)
                ]
                for nome_mat, ore_def in materie_predefinite:
                    db_materie.aggiungi_materia(nome_mat, ore_def)
                st.success("✅ Materie standard caricate con successo!")
                st.rerun()

    with col_lista_m:
        st.subheader(f"📖 Elenco e Modifica Materie - {progetto_corrente}")
        materie_dict = db_materie.ottieni_tutte_le_materie()
        
        if not materie_dict:
            st.warning(f"Nessuna materia configurata per il progetto '{progetto_corrente}'. Usa il modulo a sinistra o il pulsante 'Carica Materie Standard'.")
        else:
            riepilogo_m = []
            for mat, dati in materie_dict.items():
                riepilogo_m.append({
                    "Materia": mat, 
                    "Ore Standard (Default)": dati["ore_default"],
                    "Eccezioni per Classe": len(dati["carichi_per_classe"])
                })
            st.dataframe(pd.DataFrame(riepilogo_m), use_container_width=True, hide_index=True)
            
            materia_sel = st.selectbox("Seleziona materia da gestire", list(materie_dict.keys()), key="sel_m")
            if materia_sel:
                dati_m = materie_dict[materia_sel]
                
                with st.expander(f"🛠️ Modifica o Elimina: {materia_sel}", expanded=True):
                    
                    # --- FORM DI MODIFICA MATERIA ---
                    with st.form(f"form_mod_materia_{materia_sel}"):
                        nuovo_nome_m = st.text_input("Nome Materia", value=materia_sel).strip()
                        nuove_ore_def = st.number_input("Ore Standard (Default)", min_value=1, max_value=12, value=dati_m["ore_default"])
                    # --- GESTIONE ECCEZIONI PER CLASSE PIÙ PULITA ---
                    st.write("---")
                    st.write("**Monte ore personalizzato (Eccezioni per classe):**")
                    st.caption("Di default tutte le classi seguono il monte ore standard. Aggiungi un'eccezione solo se una classe specifica ha un orario diverso.")
                    
                    classi_disponibili = list(db_classi.ottieni_tutte_le_classi().keys())
                    carichi_attuali = dati_m.get("carichi_per_classe", {})
                    
                    if not classi_disponibili:
                        st.info("Nessuna classe configurata in questo progetto.")
                    else:
                        # Mostriamo le eccezioni esistenti
                        if carichi_attuali:
                            st.write("Eccezioni attuali:")
                            for cls_esclusiva, ore_esclusive in list(carichi_attuali.items()):
                                col_c1, col_c2, col_c3 = st.columns([2, 2, 1])
                                col_c1.text(f"Classe: {cls_esclusiva}")
                                col_c2.text(f"Ore: {ore_esclusive}")
                                if col_c3.button("🗑️ Rimuovi", key=f"del_exc_{materia_sel}_{cls_esclusiva}"):
                                    del carichi_attuali[cls_esclusiva]
                                    # Salviamo subito l'aggiornamento
                                    db_materie.aggiorna_materia(materia_sel, materia_sel, dati_m["ore_default"], carichi_attuali)
                                    st.rerun()
                        else:
                            st.info("Nessuna eccezione impostata. Tutte le classi usano il monte ore standard.")
                        
                        st.write("")
                        # Form rapido per aggiungere/modificare un'eccezione
                        with st.form(f"form_aggiungi_eccezione_{materia_sel}"):
                            st.write("**Aggiungi o modifica eccezione per una classe:**")
                            col_add1, col_add2 = st.columns(2)
                            with col_add1:
                                classe_scelta = st.selectbox("Seleziona Classe", classi_disponibili, key=f"sel_cls_exc_{materia_sel}")
                            with col_add2:
                                ore_scelte = st.number_input("Monte ore specifico", min_value=0, max_value=12, value=dati_m["ore_default"], key=f"num_ore_exc_{materia_sel}")
                            
                            btn_aggiungi_exc = st.form_submit_button("Salva Eccezione")
                            if btn_aggiungi_exc:
                                carichi_attuali[classe_scelta] = ore_scelte
                                suc, msg = db_materie.aggiorna_materia(materia_sel, materia_sel, dati_m["ore_default"], carichi_attuali)
                                if suc:
                                    st.success(f"✅ Eccezione salvata per la classe {classe_scelta}!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg}")   
                    
                    # --- ELIMINAZIONE PROTETTA MATERIA (CON DOPPIA CONFERMA) ---
                    conf_key_m = f"conferma_del_m_{materia_sel}"
                    if conf_key_m not in st.session_state:
                        st.session_state[conf_key_m] = False

                    if not st.session_state[conf_key_m]:
                        if st.button(f"🗑️ Elimina Materia {materia_sel}", type="secondary", key=f"btn_del_m_{materia_sel}"):
                            st.session_state[conf_key_m] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Sei sicuro di voler eliminare la materia '{materia_sel}'?")
                        col_conf1, col_conf2 = st.columns(2)
                        if col_conf1.button("Sì, elimina", key=f"yes_m_{materia_sel}", type="primary"):
                            db_materie.elimina_materia(materia_sel)
                            st.session_state[conf_key_m] = False
                            st.success(f"🗑️ Materia '{materia_sel}' rimossa.")
                            st.rerun()
                        if col_conf2.button("Annulla", key=f"no_m_{materia_sel}"):
                            st.session_state[conf_key_m] = False
                            st.rerun()