import streamlit as st
import pandas as pd
from assegnazioni import GestoreAssegnazioni
from classi import GestoreClassi
from docenti import GestoreDocenti
from materie import GestoreMaterie

def mostra_vista_assegnazioni():
    # Recuperiamo il progetto corrente dalla sessione globale
    progetto_corrente = st.session_state.get("progetto_corrente", "Principale")
    
    # Inizializziamo i gestori passandogli il progetto corrente
    db_ass = GestoreAssegnazioni(progetto=progetto_corrente)
    db_classi = GestoreClassi(progetto=progetto_corrente)
    db_docenti = GestoreDocenti(progetto=progetto_corrente)
    db_materie = GestoreMaterie(progetto=progetto_corrente)

    st.header("🔗 Assegnazione Cattedre e Gestione Carichi")
    st.info(f"📁 Stai gestendo le assegnazioni per il progetto: **{progetto_corrente}**")
    
    classi = db_classi.ottieni_tutte_le_classi()
    docenti = db_docenti.ottieni_tutti_i_docenti()
    materie = db_materie.ottieni_tutte_le_materie()

    if not classi or not docenti or not materie:
        st.warning("⚠️ Per poter assegnare le cattedre, devi prima configurare almeno una Classe, un Docente e una Materia nelle relative sezioni di questo progetto.")
        return

    # Creiamo i tab per separare la gestione/inserimento dalla visualizzazione dettagliata per docente
    tab_gestione, tab_per_docente, tab_per_classe = st.tabs([
        "⚙️ Gestione e Assegnazione Cattedre", 
        "🔍 Visualizza Dettaglio per Docente",
        "🏫 Visualizza Dettaglio per Classe"
    ])

    # =========================================================================
    # TAB 1: GESTIONE, INSERIMENTO E RIMOZIONE
    # =========================================================================
    with tab_gestione:
        col_form, col_lista = st.columns([1, 1.3])

        with col_form:
            st.subheader("➕ Nuova Assegnazione / Compresenza")
            
            docente_scelto = st.selectbox("1. Seleziona Docente Principale", list(docenti.keys()), key="as_docente")
            
            # --- GESTIONE COMPRESENZA ---
            attiva_compresenza = st.checkbox("👥 Aggiungi Compresenza (Secondo Docente)", key="chk_compresenza")
            docente_2_scelto = ""
            if attiva_compresenza:
                altri_docenti = [d for d in docenti.keys() if d != docente_scelto]
                if altri_docenti:
                    docente_2_scelto = st.selectbox("1b. Secondo Docente (Compresenza)", altri_docenti, key="as_docente_2")
                else:
                    st.info("Non ci sono altri docenti disponibili per la compresenza.")

            materia_scelta = st.selectbox("2. Seleziona Materia", list(materie.keys()), key="as_materia")
            
            classi_selezionate = st.multiselect(
                "3. Seleziona Classi di destinazione", 
                options=list(classi.keys()),
                key="as_classi_multi"
            )
            
            dati_materia = materie[materia_scelta]
            ore_default_mat = dati_materia["ore_default"]
            
            # Inizializzazione o aggiornamento dello stato per le ore se cambia la materia (SENZA DUPLICAZIONI)
            if "prev_materia_m" not in st.session_state or st.session_state["prev_materia_m"] != materia_scelta:
                st.session_state["as_ore_multi"] = ore_default_mat
                st.session_state["prev_materia_m"] = materia_scelta
            elif "as_ore_multi" not in st.session_state:
                st.session_state["as_ore_multi"] = ore_default_mat

            # NOTA: Senza 'value=...' per evitare il conflitto con la chiave di session state
            ore_assegnate = st.number_input(
                "4. Ore Settimanali (per ciascuna classe selezionata)", 
                min_value=1, 
                max_value=12, 
                key="as_ore_multi"
            )
            
            opzioni_blocchi = [
                "Standard (1h per volta)",
                "Blocchi da 2 ore",
                "Blocco unico settimanale",
                "Personalizzato (es. 3+2+1)"
            ]
            scelta_pref = st.selectbox("5. Preferenza distribuzione blocchi orari", options=opzioni_blocchi, key="as_pref_blocchi")
            
            if scelta_pref == "Personalizzato (es. 3+2+1)":
                preferenza_blocchi = st.text_input("Inserisci pattern blocchi (somma ore = monte ore)", value="3+2+1", key="as_pattern_custom")
            else:
                preferenza_blocchi = scelta_pref
            
            if st.button("Assegna a tutte le classi selezionate", type="primary"):
                if not classi_selezionate:
                    st.error("⚠️ Seleziona almeno una classe dall'elenco.")
                else:
                    successo, msg = db_ass.aggiungi_assegnazioni_multiple(
                        classi_selezionate, materia_scelta, docente_scelto, ore_assegnate, preferenza_blocchi, docente_2_scelto
                    )
                    if successo:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

        with col_lista:
            st.subheader(f"📋 Elenco Assegnazioni Attive - {progetto_corrente}")
            lista_ass = db_ass.ottieni_tutte_le_assegnazioni()

            if not lista_ass:
                st.info(f"Nessuna cattedra ancora assegnata per il progetto '{progetto_corrente}'.")
            else:
                df_ass = pd.DataFrame(lista_ass)
                
                # Visualizzazione combinata dei docenti se c'è compresenza
                df_ass["Docente Visualizzato"] = df_ass.apply(
                    lambda r: f"{r['docente']} + {r['docente_2']}" if r.get('docente_2') else r['docente'], axis=1
                )
                
                df_display = df_ass[["classe", "materia", "Docente Visualizzato", "ore", "preferenza_blocchi"]].rename(columns={
                    "classe": "Classe",
                    "materia": "Materia",
                    "Docente Visualizzato": "Docente/i",
                    "ore": "Ore",
                    "preferenza_blocchi": "Modalità Blocchi"
                })
                st.dataframe(df_display, width="stretch", hide_index=True)

                # --- RIMUOVI SINGOLA CATTEDRA CON FILTRI A CASCATA ---
                st.write("### 🗑️ Rimuovi Singola Cattedra (Filtri a Cascata)")
                
                col_f1, col_f2 = st.columns(2)
                
                classi_presenti = sorted(list(set(item["classe"] for item in lista_ass)))
                classe_filtro = col_f1.selectbox("Filtra per Classe", options=["Tutte"] + classi_presenti, key="filtro_classe_del")
                
                cattedre_filtrate = lista_ass if classe_filtro == "Tutte" else [i for i in lista_ass if i["classe"] == classe_filtro]
                
                docenti_filtrati = sorted(list(set(i["docente"] for i in cattedre_filtrate)))
                docente_filtro = col_f2.selectbox("Filtra per Docente", options=["Tutti"] + docenti_filtrati, key="filtro_docente_del")
                
                if docente_filtro != "Tutti":
                    cattedre_filtrate = [i for i in cattedre_filtrate if i["docente"] == docente_filtro or i.get("docente_2") == docente_filtro]

                if not cattedre_filtrate:
                    st.info("Nessuna cattedra corrisponde ai filtri selezionati.")
                else:
                    id_da_rimuovere = st.selectbox(
                        "Seleziona la cattedra specifica da eliminare",
                        options=[item["id"] for item in cattedre_filtrate],
                        format_func=lambda x: next(f"{i['classe']} → {i['materia']} ({i['docente']}{' + ' + i['docente_2'] if i.get('docente_2') else ''} - {i['ore']}h - {i['preferenza_blocchi']})" for i in cattedre_filtrate if i["id"] == x),
                        key="select_cattedra_filtrata"
                    )

                    conf_key_ass = f"conferma_del_ass_{id_da_rimuovere}"
                    if conf_key_ass not in st.session_state:
                        st.session_state[conf_key_ass] = False

                    if not st.session_state[conf_key_ass]:
                        if st.button("🗑️ Elimina Cattedra Selezionata", type="secondary", key=f"btn_del_ass_{id_da_rimuovere}"):
                            st.session_state[conf_key_ass] = True
                            st.rerun()
                    else:
                        ass_selezionata = next(i for i in lista_ass if i["id"] == id_da_rimuovere)
                        doc_str = f"{ass_selezionata['docente']}" + (f" + {ass_selezionata['docente_2']}" if ass_selezionata.get('docente_2') else "")
                        st.warning(f"⚠️ Sei sicuro di voler eliminare l'assegnazione: **{ass_selezionata['classe']} | {ass_selezionata['materia']} | {doc_str}**?")
                        
                        col_conf1, col_conf2 = st.columns(2)
                        if col_conf1.button("Sì, elimina", key=f"yes_ass_{id_da_rimuovere}", type="primary"):
                            db_ass.elimina_assegnazione(id_da_rimuovere)
                            st.session_state[conf_key_ass] = False
                            st.success("🗑️ Assegnazione rimossa con successo.")
                            st.rerun()
                        if col_conf2.button("Annulla", key=f"no_ass_{id_da_rimuovere}"):
                            st.session_state[conf_key_ass] = False
                            st.rerun()

                st.divider()

                # --- RIMUOVI TUTTE LE ASSEGNAZIONI PER UN DOCENTE ---
                st.write("### 🗑️ Rimuovi Tutte le Cattedre per Docente")
                docenti_con_ass = list(set([item["docente"] for item in lista_ass] + [item["docente_2"] for item in lista_ass if item.get("docente_2")]))
                docenti_con_ass = sorted([d for d in docenti_con_ass if d])
                
                if not docenti_con_ass:
                    st.caption("Nessun docente ha cattedre assegnate al momento in questo progetto.")
                else:
                    docente_da_eliminare_tutte = st.selectbox(
                        "Seleziona docente di cui eliminare tutte le cattedre",
                        options=docenti_con_ass,
                        key="sel_doc_del_all"
                    )
                    
                    conf_key_all_doc = f"conferma_del_all_{docente_da_eliminare_tutte}"
                    if conf_key_all_doc not in st.session_state:
                        st.session_state[conf_key_all_doc] = False

                    if not st.session_state[conf_key_all_doc]:
                        if st.button(f"🗑️ Elimina TUTTE le cattedre di {docente_da_eliminare_tutte}", type="secondary", key=f"btn_del_all_{docente_da_eliminare_tutte}"):
                            st.session_state[conf_key_all_doc] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Sei sicuro di voler rimuovere **tutte** le cattedre e compresenze associate al docente '{docente_da_eliminare_tutte}' nel progetto '{progetto_corrente}'?")
                        
                        col_c1, col_c2 = st.columns(2)
                        if col_c1.button("Sì, elimina tutte", key=f"yes_all_{docente_da_eliminare_tutte}", type="primary"):
                            db_ass.elimina_assegnazioni_per_docente(docente_da_eliminare_tutte)
                            st.session_state[conf_key_all_doc] = False
                            st.success(f"🗑️ Cattedre e compresenze per {docente_da_eliminare_tutte} aggiornate/rimosse.")
                            st.rerun()
                        if col_c2.button("Annulla", key=f"no_all_{docente_da_eliminare_tutte}"):
                            st.session_state[conf_key_all_doc] = False
                            st.rerun()

        st.divider()
        st.subheader(f"📊 Riepilogo Carico Ore per Docente - {progetto_corrente}")
        
        carico_docenti = {doc: 0 for doc in docenti.keys()}
        lista_ass_generale = db_ass.ottieni_tutte_le_assegnazioni()
        for item in lista_ass_generale:
            d1 = item.get("docente")
            d2 = item.get("docente_2")
            ore = item.get("ore", 0)
            
            if d1 in carico_docenti:
                carico_docenti[d1] += ore
            if d2 and d2 in carico_docenti:
                carico_docenti[d2] += ore

        riepilogo_ore = []
        for doc, dati_d in docenti.items():
            contratto = dati_d["ore_settimanali"]
            assegnate = carico_docenti.get(doc, 0)
            diff = assegnate - contratto
            
            if diff == 0:
                stato = "✅ In regola"
            elif diff > 0:
                stato = f"⚠️ Sovraccarico (+{diff}h)"
            else:
                stato = f"ℹ️ Sottocarico ({diff}h)"
                
            riepilogo_ore.append({
                "Docente": doc,
                "Ore Contratto": contratto,
                "Ore Assegnate": assegnate,
                "Stato": stato
            })
        
        st.dataframe(pd.DataFrame(riepilogo_ore), width="stretch", hide_index=True)

    # =========================================================================
    # TAB 2: VISUALIZZA DETTAGLIO CLASSI E MATERIE PER SINGOLO DOCENTE
    # =========================================================================
    with tab_per_docente:
        st.subheader("👨‍🏫 Dettaglio Insegnamenti per Docente")
        
        docente_scelto_dettaglio = st.selectbox("Seleziona il docente da consultare", options=sorted(list(docenti.keys())), key="filtro_dettaglio_docente")
        
        lista_ass_dettaglio = db_ass.ottieni_tutte_le_assegnazioni()
        assegnazioni_docente = []
        totale_ore_docente = 0
        
        for item in lista_ass_dettaglio:
            d1 = item.get("docente")
            d2 = item.get("docente_2")
            
            if d1 == docente_scelto_dettaglio or d2 == docente_scelto_dettaglio:
                ruolo = "Principale" if d1 == docente_scelto_dettaglio else "Compresenza"
                assegnazioni_docente.append({
                    "Classe": item.get("classe"),
                    "Materia": item.get("materia"),
                    "Ruolo": ruolo,
                    "Ore Settimanali": item.get("ore", 0),
                    "Modalità Blocchi": item.get("preferenza_blocchi", "-")
                })
                totale_ore_docente += item.get("ore", 0)

        ore_contratto_docente = docenti[docente_scelto_dettaglio].get("ore_settimanali", 18)

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric(label="Docente", value=docente_scelto_dettaglio)
        col_m2.metric(label="Ore a Contratto", value=f"{ore_contratto_docente}h")
        col_m3.metric(label="Ore Assegnate", value=f"{totale_ore_docente}h")
        
        st.markdown("---")
        
        if not assegnazioni_docente:
            st.warning(f"Il docente **{docente_scelto_dettaglio}** non ha ancora classi o materie assegnate in questo progetto.")
        else:
            df_docente_dettaglio = pd.DataFrame(assegnazioni_docente)
            st.dataframe(df_docente_dettaglio, width="stretch", hide_index=True)

    st.divider()

    # =========================================================================
    # TAB 3: VISUALIZZA DETTAGLIO MATERIE E DOCENTI PER SINGOLA CLASSE
    # =========================================================================
    with tab_per_classe:
        st.subheader("🏫 Dettaglio Insegnamenti per Classe")
        
        classe_scelta_dettaglio = st.selectbox("Seleziona la classe da consultare", options=sorted(list(classi.keys())), key="filtro_dettaglio_classe")
        
        lista_ass_dettaglio = db_ass.ottieni_tutte_le_assegnazioni()
        assegnazioni_classe = []
        totale_ore_classe = 0
        
        for item in lista_ass_dettaglio:
            if item.get("classe") == classe_scelta_dettaglio:
                d1 = item.get("docente", "")
                d2 = item.get("docente_2", "")
                docente_vis = f"{d1} + {d2}" if d2 else d1
                
                assegnazioni_classe.append({
                    "Materia": item.get("materia"),
                    "Docente/i": docente_vis,
                    "Ruolo": "Compresenza" if d2 else "Principale",
                    "Ore Settimanali": item.get("ore", 0),
                    "Modalità Blocchi": item.get("preferenza_blocchi", "-")
                })
                totale_ore_classe += item.get("ore", 0)
        
        dati_c_selezionata = classi[classe_scelta_dettaglio]
        ore_griglia_dict = dati_c_selezionata.get("ore", {})
        ore_totali_griglia = sum(ore_griglia_dict.values()) if isinstance(ore_griglia_dict, dict) else 0
        
        col_cl1, col_cl2, col_cl3 = st.columns(3)
        col_cl1.metric(label="Classe", value=classe_scelta_dettaglio)
        col_cl2.metric(label="Ore Totali in Griglia", value=f"{ore_totali_griglia}h" if ore_totali_griglia > 0 else "N/D")
        col_cl3.metric(label="Ore Assegnate", value=f"{totale_ore_classe}h")
        
        st.markdown("---")
        
        if not assegnazioni_classe:
            st.warning(f"La classe **{classe_scelta_dettaglio}** non ha ancora materie o docenti assegnati in questo progetto.")
        else:
            df_classe_dettaglio = pd.DataFrame(assegnazioni_classe)
            st.dataframe(df_classe_dettaglio, width="stretch", hide_index=True)
            
            if ore_totali_griglia > 0:
                diff_ore = totale_ore_classe - ore_totali_griglia
                if diff_ore == 0:
                    st.success("✅ Il monte ore assegnato corrisponde perfettamente alla capienza della classe.")
                elif diff_ore > 0:
                    st.warning(f"⚠️ Attenzione: hai assegnato {totale_ore_classe}h a fronte di una capienza in griglia di {ore_totali_griglia}h (Sovraccarico di {diff_ore}h).")
                else:
                    st.info(f"ℹ️ Mancano {abs(diff_ore)}h da assegnare per coprire interamente la griglia oraria della classe.")

    # -------------------------------------------------------------
    # SEZIONE DI EMERGENZA: SVUOTA TUTTE LE ASSEGNAZIONI
    # -------------------------------------------------------------
    with st.expander(f"⚠️ Zona Pericolosa: Gestione Assegnazioni ({progetto_corrente})", expanded=False):
        st.warning(f"Attenzione: questa operazione cancellerà permanentemente tutte le cattedre e le assegnazioni registrate per il progetto **{progetto_corrente}**.")
        
        conferma_reset_ass = st.checkbox(f"Confermo di voler eliminare tutte le assegnazioni del progetto '{progetto_corrente}'", key="chk_conferma_reset_assegnazioni")
        
        if st.button(f"🗑️ Rimuovi Tutte le Assegnazioni di '{progetto_corrente}'", type="primary", width="stretch"):
            if conferma_reset_ass:
                import sqlite3
                import os
                
                base_dir = os.path.dirname(os.path.abspath(__file__))
                if os.path.basename(base_dir) == "ui":
                    db_path = os.path.join(os.path.dirname(base_dir), "orario_scolastico.db")
                else:
                    db_path = os.path.join(base_dir, "orario_scolastico.db")
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                try:
                    cursor.execute("DELETE FROM assegnazioni WHERE progetto = ?", (progetto_corrente,))
                    
                    for tabella in ["orario_risultato", "orario_fallimenti", "orario_fissati"]:
                        cursor.execute(f"PRAGMA table_info({tabella})")
                        cols = [info[1] for info in cursor.fetchall()]
                        if "progetto" in cols:
                            cursor.execute(f"DELETE FROM {tabella} WHERE progetto = ?", (progetto_corrente,))
                    
                    conn.commit()
                    st.success(f"✅ Tutte le assegnazioni del progetto '{progetto_corrente}' sono state rimosse con successo!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Errore durante la rimozione: {e}")
                finally:
                    conn.close()
            else:
                st.error("❌ Per favore, spunta la casella di conferma prima di procedere.")