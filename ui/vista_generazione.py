import streamlit as st
import pandas as pd
import sqlite3
import json

def mostra_vista_generazione():
    st.header("⚙️ Generazione Orario Scolastico")
    st.write("Da qui puoi lanciare l'algoritmo di calcolo che pianifica le lezioni sulla griglia settimanale incastrando classi, docenti e vincoli.")

    st.info("💡 Assicurati di aver completato le assegnazioni delle cattedre prima di avviare l'elaborazione.")

    # Recupera il progetto attivo dalla sessione di Streamlit
    progetto_corrente = st.session_state.get("progetto_corrente", "Principale")

    if st.button("🚀 Avvia Elaborazione Orario", type="primary", use_container_width=True):
        with st.spinner("Elaborazione in corso... Il motore sta analizzando i vincoli e calcolando la griglia."):
            from motore import MotoreOrario
            
            # Passa il progetto al motore
            motore = MotoreOrario(progetto=progetto_corrente)
            
            succes, messaggio = motore.genera()
            
            if succes:
                st.success(f"✅ {messaggio}")
                st.rerun()
            else:
                st.error(f"❌ {messaggio}")

    # --- SEZIONE DIAGNOSTICA FALLIMENTI ---
    conn = sqlite3.connect("orario_scolastico.db")
    try:
        df_fallimenti = pd.read_sql("SELECT * FROM orario_fallimenti", conn)
    except Exception:
        df_fallimenti = pd.DataFrame()
    conn.close()

    if not df_fallimenti.empty:
        with st.expander(f"⚠️ Diagnostica: {len(df_fallimenti)} blocchi non assegnati (clicca per espandere)", expanded=True):
            st.warning("I seguenti blocchi orari non sono stati inseriti a causa di conflitti con i vincoli o saturazione della griglia:")
            st.dataframe(df_fallimenti, use_container_width=True)

    st.divider()
    st.subheader("📅 Visualizzazione Tabellone Orario")

    # LETTURA FILTRATA PER PROGETTO
    conn = sqlite3.connect("orario_scolastico.db")
    try:
        df_risultato = pd.read_sql("SELECT * FROM orario_risultato WHERE progetto = ?", conn, params=(progetto_corrente,))
    except Exception:
        df_risultato = pd.DataFrame()
    conn.close()

    if df_risultato.empty:
        st.info("ℹ️ Nessun orario generato trovato per questo progetto. Clicca su 'Avvia Elaborazione Orario' per calcolarlo.")
    else:
        tab_classi, tab_docenti, tab_sinottico, tab_fissa = st.tabs([
            "📚 Per Classe", 
            "👨‍🏫 Per Docente", 
            "📊 Quadro Sinottico Generale", 
            "📌 Fissa Ore Manuali"
        ])
        
        ordine_giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]

        with tab_classi:
            classi_disponibili = sorted(df_risultato["classe"].unique())
            classe_scelta = st.selectbox("Seleziona la classe da visualizzare", options=classi_disponibili, key="sel_classe_orario")

            df_classe = df_risultato[df_risultato["classe"] == classe_scelta].copy()
            df_classe["lezione"] = df_classe["materia"] + "\n(" + df_classe["docente"] + ")"

            pivot_classe = df_classe.pivot_table(
                index="ora", 
                columns="giorno", 
                values="lezione", 
                aggfunc=lambda x: ' / '.join(x)
            )

            giorni_presenti = [g for g in ordine_giorni if g in pivot_classe.columns]
            pivot_classe = pivot_classe[giorni_presenti]

            st.markdown(f"### Orario Settimanale Classe: **{classe_scelta}**")
            st.dataframe(pivot_classe, use_container_width=True)

        with tab_docenti:
            tutti_docenti = set()
            for d_str in df_risultato["docente"].dropna():
                for singolo in d_str.split("+"):
                    tutti_docenti.add(singolo.strip())
            
            docenti_disponibili = sorted(list(tutti_docenti))
            docente_scelto = st.selectbox("Seleziona il docente da visualizzare", options=docenti_disponibili, key="sel_docente_orario")

            df_docente = df_risultato[df_risultato["docente"].str.contains(docente_scelto, na=False)].copy()
            
            if df_docente.empty:
                st.warning(f"Nessuna lezione trovata per il docente **{docente_scelto}**.")
            else:
                df_docente["lezione"] = df_docente["materia"] + "\n[" + df_docente["classe"] + "]"

                pivot_docente = df_docente.pivot_table(
                    index="ora", 
                    columns="giorno", 
                    values="lezione", 
                    aggfunc=lambda x: ' / '.join(x)
                )

                giorni_presenti_doc = [g for g in ordine_giorni if g in pivot_docente.columns]
                pivot_docente = pivot_docente[giorni_presenti_doc] if giorni_presenti_doc else pivot_docente

                st.markdown(f"### Orario Settimanale Docente: **{docente_scelto}**")
                st.dataframe(pivot_docente, use_container_width=True)

        with tab_sinottico:
            st.markdown("### 📊 Quadro Sinottico Generale dei Docenti")
            st.write("Vista d'insieme di tutti i docenti disposti sulla griglia settimanale.")
            
            try:
                conn_sin = sqlite3.connect("orario_scolastico.db")
                df_res_sin = pd.read_sql_query("SELECT * FROM orario_risultato WHERE progetto = ?", conn_sin, params=(progetto_corrente,))
                
                try:
                    df_fall_sin = pd.read_sql_query("SELECT * FROM orario_fallimenti", conn_sin)
                except Exception:
                    df_fall_sin = pd.DataFrame()
                
                conn_sin.close()

                if not df_res_sin.empty:
                    ordine_giorni_map = {"Lunedì": 1, "Martedì": 2, "Mercoledì": 3, "Giovedì": 4, "Venerdì": 5, "Sabato": 6}
                    df_res_sin['giorno_num'] = df_res_sin['giorno'].map(ordine_giorni_map).fillna(99)
                    df_res_sin = df_res_sin.sort_values(by=['docente', 'giorno_num', 'ora'])
                    
                    df_res_sin['slot'] = df_res_sin['giorno'] + " (" + df_res_sin['ora'].astype(str) + "ª)"

                    # Generiamo la lista degli slot ordinati cronologicamente
                    slots_ordinati = []
                    for g in ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"]:
                        max_o = df_res_sin[df_res_sin['giorno'] == g]['ora'].max()
                        if pd.notna(max_o):
                            for o in range(1, int(max_o) + 1):
                                s_name = f"{g} ({o}ª)"
                                if s_name in df_res_sin['slot'].values:
                                    slots_ordinati.append(s_name)

                    sinottico = df_res_sin.pivot_table(
                        index="docente", 
                        columns="slot", 
                        values="classe", 
                        aggfunc=lambda x: " + ".join(str(v) for v in x)
                    ).fillna("")

                    # Riordiniamo le colonne del dataframe in base alla sequenza temporale corretta
                    colonne_esistenti = [s for s in slots_ordinati if s in sinottico.columns]
                    sinottico = sinottico[colonne_esistenti]

                    st.dataframe(sinottico, use_container_width=True)

                    if not df_fall_sin.empty:
                        st.markdown("---")
                        st.markdown("### ⚠️ Blocchi Residui Non Collocati")
                        st.write("I seguenti blocchi non hanno trovato posto nella griglia:")
                        
                        cols_da_prendere = ["classe", "materia", "docente"]
                        if "giorno" in df_fall_sin.columns:
                            cols_da_prendere.append("giorno")
                        if "ora" in df_fall_sin.columns:
                            cols_da_prendere.append("ora")
                        if "motivo" in df_fall_sin.columns:
                            cols_da_prendere.append("motivo")
                            
                        df_fall_mostra = df_fall_sin[cols_da_prendere].copy()
                        
                        rename_map = {
                            "classe": "Classe", 
                            "materia": "Materia", 
                            "docente": "Docente", 
                            "giorno": "Giorno Critico", 
                            "ora": "Ora",
                            "motivo": "Motivo del Blocco"
                        }
                        df_fall_mostra = df_fall_mostra.rename(columns=rename_map)
                        st.dataframe(df_fall_mostra, use_container_width=True)
                else:
                    st.info("Nessun orario generato trovato per questo progetto.")
            except Exception as e:
                st.warning(f"Impossibile generare il quadro sinottico: {e}")

        with tab_fissa:
            st.markdown("### 📌 Fissaggio Manuale e Gestione Rapida Orario")
            st.write("Gestisci l'orario bloccando i blocchi definitivi o modificando al volo qualsiasi casella.")

            # --- PULSANTI GLOBALI DI CONTROLLO ---
            col_glob1, col_glob2 = st.columns(2)
            
            with col_glob1:
                if st.button("🔒 Blocca Intero Orario Generato (Tutte le classi)", type="primary", use_container_width=True):
                    conn_g = sqlite3.connect("orario_scolastico.db")
                    cursor_g = conn_g.cursor()
                    cursor_g.execute("""
                        CREATE TABLE IF NOT EXISTS orario_fissati (
                            classe TEXT,
                            giorno TEXT,
                            ora INTEGER,
                            materia TEXT,
                            docente TEXT
                        )
                    """)
                    cursor_g.execute("DELETE FROM orario_fissati")
                    cursor_g.execute("""
                        INSERT INTO orario_fissati (classe, giorno, ora, materia, docente)
                        SELECT classe, giorno, ora, materia, docente 
                        FROM orario_risultato WHERE progetto = ?
                    """, (progetto_corrente,))
                    conn_g.commit()
                    conn_g.close()
                    st.success("🔒 L'intero orario del progetto è stato bloccato come fisso!")
                    st.rerun()

            with col_glob2:
                if st.button("🗑️ Svuota Tutti i Blocchi Fissati", type="secondary", use_container_width=True):
                    conn_sg = sqlite3.connect("orario_scolastico.db")
                    cursor_sg = conn_sg.cursor()
                    cursor_sg.execute("DELETE FROM orario_fissati")
                    conn_sg.commit()
                    conn_sg.close()
                    st.warning("🗑️ Tutti i blocchi fissati sono stati rimossi.")
                    st.rerun()

            st.divider()

            # Selezione classe
            classi_disponibili_fissa = sorted(df_risultato["classe"].unique()) if not df_risultato.empty else []
            if not classi_disponibili_fissa:
                conn_c = sqlite3.connect("orario_scolastico.db")
                df_c = pd.read_sql("SELECT nome FROM classi WHERE progetto = ?", conn_c, params=(progetto_corrente,))
                conn_c.close()
                classi_disponibili_fissa = df_c["nome"].tolist() if not df_c.empty else []

            if not classi_disponibili_fissa:
                st.warning("Nessuna classe trovata nel database per questo progetto.")
            else:
                classe_fissa = st.selectbox("Seleziona la classe da rifinire", options=classi_disponibili_fissa, key="sel_classe_fissa")

                # Carichiamo configurazione e dati fissati
                conn_f = sqlite3.connect("orario_scolastico.db")
                cursor_f = conn_f.cursor()
                cursor_f.execute("SELECT giorni, orario_ore FROM classi WHERE nome = ? AND progetto = ?", (classe_fissa, progetto_corrente))
                row_cls_cfg = cursor_f.fetchone()
                
                giorni_classe = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
                ore_per_giorno = {}
                if row_cls_cfg:
                    giorni_classe = json.loads(row_cls_cfg[0])
                    ore_per_giorno = json.loads(row_cls_cfg[1])
                
                cursor_f.execute("""
                    CREATE TABLE IF NOT EXISTS orario_fissati (
                        classe TEXT,
                        giorno TEXT,
                        ora INTEGER,
                        materia TEXT,
                        docente TEXT
                    )
                """)
                conn_f.commit()

                df_ass_classe = pd.read_sql("SELECT materia, docente FROM assegnazioni WHERE classe = ? AND progetto = ? ORDER BY materia ASC", conn_f, params=(classe_fissa, progetto_corrente))
                df_res_cls = pd.read_sql("SELECT giorno, ora, materia, docente FROM orario_risultato WHERE classe = ? AND progetto = ?", conn_f, params=(classe_fissa, progetto_corrente))
                df_fix_cls = pd.read_sql("SELECT rowid as id, giorno, ora, materia, docente FROM orario_fissati WHERE classe = ?", conn_f, params=(classe_fissa,))
                conn_f.close()

                mappa_orario = {}
                fissati_set = set()
                for _, r in df_res_cls.iterrows():
                    mappa_orario[(r["giorno"], int(r["ora"]))] = (r['materia'], r['docente'])
                
                for _, r in df_fix_cls.iterrows():
                    mappa_orario[(r["giorno"], int(r["ora"]))] = (r['materia'], r['docente'])
                    fissati_set.add((r["giorno"], int(r["ora"])))

                if "slot_selezionato" not in st.session_state:
                    st.session_state["slot_selezionato"] = (giorni_classe[0], 1)

                st.markdown(f"#### 🛠️ Clicca su uno slot della griglia per selezionarlo e modificarlo:")
                
                cols_giorni = st.columns(len(giorni_classe))
                for idx, g in enumerate(giorni_classe):
                    with cols_giorni[idx]:
                        st.markdown(f"**{g}**")
                        max_o = ore_per_giorno.get(g, 6)
                        for o in range(1, max_o + 1):
                            if (g, o) in fissati_set:
                                mat, doc = mappa_orario[(g, o)]
                                etichetta_btn = f"🔒 {o}ª: {mat}"
                            elif (g, o) in mappa_orario:
                                mat, doc = mappa_orario[(g, o)]
                                etichetta_btn = f"{o}ª: {mat}"
                            else:
                                etichetta_btn = f"{o}ª: [Libero]"
                            
                            is_selected = (st.session_state["slot_selezionato"] == (g, o))
                            tipo_btn = "primary" if is_selected else "secondary"

                            if st.button(etichetta_btn, key=f"btn_slot_{g}_{o}", type=tipo_btn, use_container_width=True):
                                st.session_state["slot_selezionato"] = (g, o)
                                st.rerun()

                st.markdown("---")

                g_sel, o_sel = st.session_state["slot_selezionato"]
                st.markdown(f"##### 🎯 Slot attualmente in modifica: **{g_sel} - {o_sel}ª ora**")

                valore_attuale = mappa_orario.get((g_sel, o_sel), None)
                if valore_attuale:
                    st.info(f"Attuale: **{valore_attuale[0]}** ({valore_attuale[1]})")
                else:
                    st.info("Attuale: **Libero / Vuoto**")

                opzioni_assegnazioni_raw = [("--- Rimuovi / Lascia Libero ---", "")]
                df_ass_classe_ordinato = df_ass_classe.sort_values(by="materia", ascending=True)
                for _, row in df_ass_classe_ordinato.iterrows():
                    opzioni_assegnazioni_raw.append((f"{row['materia']} ({row['docente']})", (row['materia'], row['docente'])))

                indice_predefinito = 0
                if valore_attuale:
                    materia_attuale = valore_attuale[0].strip().lower()
                    docente_attuale = valore_attuale[1].strip().lower()
                    
                    for idx, (etichetta, dati) in enumerate(opzioni_assegnazioni_raw):
                        if dati != "":
                            mat_opt = dati[0].strip().lower()
                            doc_opt = dati[1].strip().lower()
                            if mat_opt == materia_attuale and doc_opt == docente_attuale:
                                indice_predefinito = idx
                                break
                    
                    if indice_predefinito == 0:
                        for idx, (etichetta, dati) in enumerate(opzioni_assegnazioni_raw):
                            if dati != "" and dati[0].strip().lower() == materia_attuale:
                                indice_predefinito = idx
                                break

                chiave_selectbox = f"mod_materia_doc_{classe_fissa}_{g_sel}_{o_sel}"

                scelta_materia_docente = st.selectbox(
                    "Scegli nuova Materia/Docente per questo slot:", 
                    options=[opt[0] for opt in opzioni_assegnazioni_raw],
                    index=indice_predefinito,
                    key=chiave_selectbox
                )

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("🔒 Fissa / Salva Modifica su questo Slot", type="primary", use_container_width=True):
                        dati_sel = next(opt[1] for opt in opzioni_assegnazioni_raw if opt[0] == scelta_materia_docente)
                        if dati_sel == "":
                            conn_ins = sqlite3.connect("orario_scolastico.db")
                            cursor_ins = conn_ins.cursor()
                            cursor_ins.execute("DELETE FROM orario_fissati WHERE classe = ? AND giorno = ? AND ora = ?", 
                                               (classe_fissa, g_sel, o_sel))
                            cursor_ins.execute("DELETE FROM orario_risultato WHERE classe = ? AND giorno = ? AND ora = ? AND progetto = ?", 
                                               (classe_fissa, g_sel, o_sel, progetto_corrente))
                            conn_ins.commit()
                            conn_ins.close()
                            st.success(f"🗑️ Slot {g_sel} {o_sel}ª ora liberato!")
                            st.rerun()
                        else:
                            mat_s, doc_s = dati_sel
                            conn_ins = sqlite3.connect("orario_scolastico.db")
                            cursor_ins = conn_ins.cursor()
                            cursor_ins.execute("DELETE FROM orario_fissati WHERE classe = ? AND giorno = ? AND ora = ?", 
                                               (classe_fissa, g_sel, o_sel))
                            cursor_ins.execute("INSERT INTO orario_fissati (classe, giorno, ora, materia, docente) VALUES (?, ?, ?, ?, ?)",
                                               (classe_fissa, g_sel, o_sel, mat_s, doc_s))
                            conn_ins.commit()
                            conn_ins.close()
                            st.success(f"✅ Slot {g_sel} {o_sel}ª ora aggiornato e fissato!")
                            st.rerun()

                with col_b2:
                    if st.button("🔓 Sblocca Slot (Rendi Dinamico)", type="secondary", use_container_width=True):
                        conn_un = sqlite3.connect("orario_scolastico.db")
                        cursor_un = conn_un.cursor()
                        cursor_un.execute("DELETE FROM orario_fissati WHERE classe = ? AND giorno = ? AND ora = ?", 
                                           (classe_fissa, g_sel, o_sel))
                        conn_un.commit()
                        conn_un.close()
                        st.info(f"🔓 Slot {g_sel} {o_sel}ª ora sbloccato.")
                        st.rerun()