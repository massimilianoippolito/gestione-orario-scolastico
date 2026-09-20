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
                            docente TEXT,
                            progetto TEXT
                        )
                    """)
                    cursor_g.execute("DELETE FROM orario_fissati WHERE progetto = ?", (progetto_corrente,))
                    cursor_g.execute("""
                        INSERT INTO orario_fissati (classe, giorno, ora, materia, docente, progetto)
                        SELECT classe, giorno, ora, materia, docente, progetto 
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
                    cursor_sg.execute("DELETE FROM orario_fissati WHERE progetto = ?", (progetto_corrente,))
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
                    try:
                        giorni_classe = json.loads(row_cls_cfg[0])
                    except Exception:
                        pass
                    
                    raw_ore = row_cls_cfg[1]
                    if raw_ore is not None:
                        try:
                            parsed_ore = json.loads(str(raw_ore))
                            if isinstance(parsed_ore, dict):
                                ore_per_giorno = parsed_ore
                            elif isinstance(parsed_ore, int):
                                ore_per_giorno = {g: parsed_ore for g in giorni_classe}
                        except Exception:
                            try:
                                val_int = int(raw_ore)
                                ore_per_giorno = {g: val_int for g in giorni_classe}
                            except Exception:
                                ore_per_giorno = {}

                if not ore_per_giorno:
                    ore_per_giorno = {g: 6 for g in giorni_classe}
                
                cursor_f.execute("""
                    CREATE TABLE IF NOT EXISTS orario_fissati (
                        classe TEXT,
                        giorno TEXT,
                        ora INTEGER,
                        materia TEXT,
                        docente TEXT,
                        progetto TEXT
                    )
                """)
                conn_f.commit()

                df_ass_classe = pd.read_sql("SELECT materia, docente FROM assegnazioni WHERE classe = ? AND progetto = ? ORDER BY materia ASC", conn_f, params=(classe_fissa, progetto_corrente))
                df_res_cls = pd.read_sql("SELECT giorno, ora, materia, docente FROM orario_risultato WHERE classe = ? AND progetto = ?", conn_f, params=(classe_fissa, progetto_corrente))
                df_fix_cls = pd.read_sql("SELECT rowid as id, giorno, ora, materia, docente FROM orario_fissati WHERE classe = ? AND progetto = ?", conn_f, params=(classe_fissa, progetto_corrente))
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

                st.markdown(f"#### 🛠️ Clicca su uno slot della griglia (per Classe) per selezionarlo e modificarlo:")
                
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
                st.markdown(f"##### 🎯 Slot Classe attualmente in modifica: **{g_sel} - {o_sel}ª ora**")

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
                    "Scegli nuova Materia/Docente per questo slot (Classe):", 
                    options=[opt[0] for opt in opzioni_assegnazioni_raw],
                    index=indice_predefinito,
                    key=chiave_selectbox
                )

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("🔒 Fissa / Salva Modifica su questo Slot (Classe)", type="primary", use_container_width=True):
                        dati_sel = next(opt[1] for opt in opzioni_assegnazioni_raw if opt[0] == scelta_materia_docente)
                        conn_ins = sqlite3.connect("orario_scolastico.db")
                        cursor_ins = conn_ins.cursor()
                        
                        cursor_ins.execute("DELETE FROM orario_fissati WHERE classe = ? AND giorno = ? AND ora = ? AND progetto = ?", 
                                           (classe_fissa, g_sel, o_sel, progetto_corrente))
                        cursor_ins.execute("DELETE FROM orario_risultato WHERE classe = ? AND giorno = ? AND ora = ? AND progetto = ?", 
                                           (classe_fissa, g_sel, o_sel, progetto_corrente))

                        if dati_sel == "":
                            conn_ins.commit()
                            conn_ins.close()
                            st.success(f"🗑️ Slot {g_sel} {o_sel}ª ora liberato!")
                            st.rerun()
                        else:
                            mat_s, doc_s = dati_sel
                            cursor_ins.execute("""
                                INSERT INTO orario_fissati (classe, giorno, ora, materia, docente, progetto) 
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (classe_fissa, g_sel, o_sel, mat_s, doc_s, progetto_corrente))
                            
                            cursor_ins.execute("""
                                INSERT INTO orario_risultato (classe, giorno, ora, materia, docente, progetto) 
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (classe_fissa, g_sel, o_sel, mat_s, doc_s, progetto_corrente))
                            
                            conn_ins.commit()
                            conn_ins.close()
                            st.success(f"✅ Slot {g_sel} {o_sel}ª ora aggiornato, fissato e salvato!")
                            st.rerun()

                with col_b2:
                    if st.button("🔓 Sblocca Slot (Rendi Dinamico - Classe)", type="secondary", use_container_width=True):
                        conn_un = sqlite3.connect("orario_scolastico.db")
                        cursor_un = conn_un.cursor()
                        cursor_un.execute("DELETE FROM orario_fissati WHERE classe = ? AND giorno = ? AND ora = ? AND progetto = ?", 
                                           (classe_fissa, g_sel, o_sel, progetto_corrente))
                        cursor_un.execute("DELETE FROM orario_risultato WHERE classe = ? AND giorno = ? AND ora = ? AND progetto = ?", 
                                           (classe_fissa, g_sel, o_sel, progetto_corrente))
                        conn_un.commit()
                        conn_un.close()
                        st.info(f"🔓 Slot {g_sel} {o_sel}ª ora sbloccato e reso dinamico.")
                        st.rerun()

            # ==========================================
            # SEZIONE AGGIUNTIVA: FISSAGGIO / SBLOCCO PER DOCENTE
            # ==========================================
            st.markdown("---")
            st.markdown("### 👨‍🏫 Fissaggio / Sblocco per Docente")

            def docente_contiene(docente_valore, docente_riferimento):
                if pd.isna(docente_valore):
                    return False
                return any(part.strip() == docente_riferimento for part in str(docente_valore).split("+"))

            conn_doc_list = sqlite3.connect("orario_scolastico.db")
            try:
                df_doc_list = pd.read_sql("SELECT DISTINCT docente FROM orario_risultato WHERE progetto = ?", conn_doc_list, params=(progetto_corrente,))
            except Exception:
                df_doc_list = pd.DataFrame()
            conn_doc_list.close()

            docenti_fissabili = []
            if not df_doc_list.empty:
                for doc_str in df_doc_list["docente"].dropna():
                    for singolo in str(doc_str).split("+"):
                        singolo = singolo.strip()
                        if singolo:
                            docenti_fissabili.append(singolo)
            else:
                conn_doc_as = sqlite3.connect("orario_scolastico.db")
                try:
                    df_doc_as = pd.read_sql("SELECT DISTINCT docente FROM assegnazioni WHERE progetto = ?", conn_doc_as, params=(progetto_corrente,))
                except Exception:
                    df_doc_as = pd.DataFrame()
                conn_doc_as.close()

                if not df_doc_as.empty:
                    for doc_str in df_doc_as["docente"].dropna():
                        for singolo in str(doc_str).split("+"):
                            singolo = singolo.strip()
                            if singolo:
                                docenti_fissabili.append(singolo)

            docenti_fissabili = sorted(set(docenti_fissabili))

            if not docenti_fissabili:
                st.warning("Nessun docente trovato nel database per questo progetto.")
            else:
                docente_fissa = st.selectbox("Seleziona il docente da rifinire", options=docenti_fissabili, key="sel_docente_fissa")

                # --- CARICHIAMO I VINCOLI DEL DOCENTE DALLA TABELLA DOCENTI ---
                conn_vincoli = sqlite3.connect("orario_scolastico.db")
                cur_v = conn_vincoli.cursor()
                cur_v.execute("SELECT vincoli FROM docenti WHERE nome = ? AND progetto = ?", (docente_fissa, progetto_corrente))
                row_vincoli = cur_v.fetchone()
                conn_vincoli.close()

                vincoli_docente = {}
                if row_vincoli and row_vincoli[0]:
                    try:
                        parsed_v = json.loads(row_vincoli[0])
                        if isinstance(parsed_v, dict):
                            vincoli_docente = parsed_v
                    except:
                        pass

                non_disponibili_doc = vincoli_docente.get("non_disponibili", {})
                indesiderate_doc = vincoli_docente.get("indesiderate", {})
                giorni_liberi_doc = vincoli_docente.get("giorni_liberi", [])

                # --- PULSANTI BLOCCO / SBLOCCO MASSIVO DOCENTE ---
                col_doc_glob1, col_doc_glob2 = st.columns(2)
                with col_doc_glob1:
                    if st.button(f"🔒 Blocca Tutte le Ore di {docente_fissa}", type="primary", use_container_width=True):
                        conn_dg = sqlite3.connect("orario_scolastico.db")
                        cursor_dg = conn_dg.cursor()
                        cursor_dg.execute("""
                            CREATE TABLE IF NOT EXISTS orario_fissati (
                                classe TEXT,
                                giorno TEXT,
                                ora INTEGER,
                                materia TEXT,
                                docente TEXT,
                                progetto TEXT
                            )
                        """)
                        df_to_fix = pd.read_sql("SELECT classe, giorno, ora, materia, docente FROM orario_risultato WHERE progetto = ?", conn_dg, params=(progetto_corrente,))
                        
                        for _, r in df_to_fix.iterrows():
                            if docente_contiene(r["docente"], docente_fissa):
                                cursor_dg.execute("""
                                    SELECT 1 FROM orario_fissati 
                                    WHERE classe = ? AND giorno = ? AND ora = ? AND docente = ? AND progetto = ?
                                """, (r["classe"], r["giorno"], r["ora"], r["docente"], progetto_corrente))
                                if not cursor_dg.fetchone():
                                    cursor_dg.execute("""
                                        INSERT INTO orario_fissati (classe, giorno, ora, materia, docente, progetto)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                    """, (r["classe"], r["giorno"], r["ora"], r["materia"], r["docente"], progetto_corrente))
                        
                        conn_dg.commit()
                        conn_dg.close()
                        st.success(f"🔒 Tutte le ore del docente {docente_fissa} sono state bloccate!")
                        st.rerun()

                with col_doc_glob2:
                    if st.button(f"🗑️ Sblocca Tutte le Ore di {docente_fissa}", type="secondary", use_container_width=True):
                        conn_dun = sqlite3.connect("orario_scolastico.db")
                        cursor_dun = conn_dun.cursor()
                        
                        df_fix_all = pd.read_sql("SELECT rowid as id, docente FROM orario_fissati WHERE progetto = ?", conn_dun, params=(progetto_corrente,))
                        for _, r in df_fix_all.iterrows():
                            if docente_contiene(r["docente"], docente_fissa):
                                cursor_dun.execute("DELETE FROM orario_fissati WHERE rowid = ?", (r["id"],))
                                
                        conn_dun.commit()
                        conn_dun.close()
                        st.warning(f"🔓 Tutti i blocchi fissati per il docente {docente_fissa} sono stati rimossi.")
                        st.rerun()

                st.markdown("---")

                conn_doc = sqlite3.connect("orario_scolastico.db")
                cursor_doc = conn_doc.cursor()
                cursor_doc.execute("""
                    CREATE TABLE IF NOT EXISTS orario_fissati (
                        classe TEXT,
                        giorno TEXT,
                        ora INTEGER,
                        materia TEXT,
                        docente TEXT,
                        progetto TEXT
                    )
                """)
                conn_doc.commit()

                df_res_doc = pd.read_sql("SELECT giorno, ora, classe, materia, docente FROM orario_risultato WHERE progetto = ?", conn_doc, params=(progetto_corrente,))
                df_fix_doc = pd.read_sql("SELECT rowid as id, giorno, ora, classe, materia, docente FROM orario_fissati WHERE progetto = ?", conn_doc, params=(progetto_corrente,))
                conn_doc.close()

                df_docente_slots = df_res_doc[df_res_doc["docente"].apply(lambda d: docente_contiene(d, docente_fissa))].copy()
                mappa_doc = {}
                fissati_doc = set()

                for _, r in df_docente_slots.iterrows():
                    mappa_doc[(r["giorno"], int(r["ora"]))] = (r["classe"], r["materia"], r["docente"])

                for _, r in df_fix_doc.iterrows():
                    if docente_contiene(r["docente"], docente_fissa):
                        mappa_doc[(r["giorno"], int(r["ora"]))] = (r["classe"], r["materia"], r["docente"])
                        fissati_doc.add((r["giorno"], int(r["ora"])))

                # Leggiamo le ore standard impostate nei parametri dell'istituto per garantire la visibilità di tutte le ore
                ore_standard_istituto = st.session_state.config_default.get("ore_standard", 6)
                giorni_doc = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
                ore_doc = {g: ore_standard_istituto for g in giorni_doc}

                if "slot_doc_selezionato" not in st.session_state:
                    st.session_state["slot_doc_selezionato"] = (giorni_doc[0], 1)

                st.markdown(f"#### 🛠️ Clicca su uno slot della griglia (per Docente) per selezionarlo e modificarlo:")  
                st.markdown(
                    "<span style='color:grey; font-size:12px;'>Legenda: 🔒 Fissato/Bloccato | 🔴 Indisponibile | 🟡 Ora Indesiderata | [Libero] Vuoto</span>", 
                    unsafe_allow_html=True
                )

                cols_doc = st.columns(len(giorni_doc))
                for idx, g in enumerate(giorni_doc):
                    with cols_doc[idx]:
                        st.markdown(f"**{g}**")
                        max_o = ore_doc.get(g, 6)
                        for o in range(1, max_o + 1):
                            
                            # Controllo vincoli in base alla struttura effettiva del dizionario del docente
                            prefisso_vincolo = ""
                            ore_nd_giorno = non_disponibili_doc.get(g, [])
                            ore_ind_giorno = indesiderate_doc.get(g, [])
                            
                            if g in giorni_liberi_doc or o in ore_nd_giorno:
                                prefisso_vincolo = "🔴 "
                            elif o in ore_ind_giorno:
                                prefisso_vincolo = "🟡 "

                            if (g, o) in fissati_doc:
                                classe_val, mat_val, doc_val = mappa_doc[(g, o)]
                                etichetta_btn = f"{prefisso_vincolo}🔒 {o}ª: {classe_val} - {mat_val}"
                            elif (g, o) in mappa_doc:
                                classe_val, mat_val, doc_val = mappa_doc[(g, o)]
                                etichetta_btn = f"{prefisso_vincolo}{o}ª: {classe_val} - {mat_val}"
                            else:
                                etichetta_btn = f"{prefisso_vincolo}{o}ª: [Libero]"

                            is_selected = (st.session_state["slot_doc_selezionato"] == (g, o))
                            tipo_btn = "primary" if is_selected else "secondary"

                            if st.button(etichetta_btn, key=f"btn_slot_doc_{docente_fissa}_{g}_{o}", type=tipo_btn, use_container_width=True):
                                st.session_state["slot_doc_selezionato"] = (g, o)
                                st.rerun()

                st.markdown("---")

                g_sel, o_sel = st.session_state["slot_doc_selezionato"]
                st.markdown(f"##### 🎯 Slot Docente attualmente in modifica: **{g_sel} - {o_sel}ª ora**")

                valore_attuale = mappa_doc.get((g_sel, o_sel), None)
                if valore_attuale:
                    st.info(f"Attuale: **{valore_attuale[1]}** ({valore_attuale[0]})")
                else:
                    st.info("Attuale: **Libero / Vuoto**")

                # --- FILTRAGGIO OPZIONI: Escludiamo classe/materia già usate negli altri slot fissati ---
                slot_gia_usati = set()
                for (g_tup, o_tup), (cls_tup, mat_tup, doc_tup) in mappa_doc.items():
                    if (g_tup, o_tup) != (g_sel, o_sel) and (g_tup, o_tup) in fissati_doc:
                        slot_gia_usati.add((str(cls_tup).strip().lower(), str(mat_tup).strip().lower()))

                opzioni_doc_raw = [("--- Rimuovi / Lascia Libero ---", "")]
                for _, row in df_docente_slots.sort_values(by=["classe", "materia"], ascending=True).drop_duplicates().iterrows():
                    cls_item = str(row['classe']).strip()
                    mat_item = str(row['materia']).strip()
                    
                    if (cls_item.lower(), mat_item.lower()) in slot_gia_usati:
                        continue
                        
                    opzioni_doc_raw.append((f"{cls_item} - {mat_item}", (row['classe'], row['materia'], row['docente'])))

                indice_predefinito = 0
                if valore_attuale:
                    classe_attuale = str(valore_attuale[0]).strip().lower()
                    materia_attuale = str(valore_attuale[1]).strip().lower()
                    
                    trovata_in_lista = any(dati != "" and str(dati[0]).strip().lower() == classe_attuale and str(dati[1]).strip().lower() == materia_attuale for _, dati in opzioni_doc_raw)
                    if not trovata_in_lista and valore_attuale:
                        opzioni_doc_raw.append((f"{valore_attuale[0]} - {valore_attuale[1]} (Attuale)", (valore_attuale[0], valore_attuale[1], docente_fissa)))

                    for idx, (etichetta, dati) in enumerate(opzioni_doc_raw):
                        if dati != "":
                            cls_opt = str(dati[0]).strip().lower()
                            mat_opt = str(dati[1]).strip().lower()
                            if cls_opt == classe_attuale and mat_opt == materia_attuale:
                                indice_predefinito = idx
                                break

                chiave_selectbox = f"mod_docente_slot_{docente_fissa}_{g_sel}_{o_sel}"

                scelta_docente_slot = st.selectbox(
                    "Scegli nuova classe/materia per questo slot (Docente):",
                    options=[opt[0] for opt in opzioni_doc_raw],
                    index=indice_predefinito,
                    key=chiave_selectbox
                )

                col_db1, col_db2 = st.columns(2)
                with col_db1:
                    if st.button("🔒 Fissa / Salva Modifica per questo Slot Docente", type="primary", use_container_width=True):
                        dati_sel = next(opt[1] for opt in opzioni_doc_raw if opt[0] == scelta_docente_slot)

                        conn_ins = sqlite3.connect("orario_scolastico.db")
                        cursor_ins = conn_ins.cursor()

                        df_fix_da_canc = pd.read_sql("SELECT rowid as id, classe, giorno, ora, materia, docente FROM orario_fissati WHERE progetto = ?", conn_ins, params=(progetto_corrente,))
                        for _, r in df_fix_da_canc.iterrows():
                            if docente_contiene(r["docente"], docente_fissa) and r["giorno"] == g_sel and int(r["ora"]) == o_sel:
                                cursor_ins.execute("DELETE FROM orario_fissati WHERE rowid = ?", (r["id"],))

                        df_res_da_canc = pd.read_sql("SELECT rowid as id, classe, giorno, ora, materia, docente FROM orario_risultato WHERE progetto = ?", conn_ins, params=(progetto_corrente,))
                        for _, r in df_res_da_canc.iterrows():
                            if docente_contiene(r["docente"], docente_fissa) and r["giorno"] == g_sel and int(r["ora"]) == o_sel:
                                cursor_ins.execute("DELETE FROM orario_risultato WHERE rowid = ?", (r["id"],))

                        if dati_sel == "":
                            conn_ins.commit()
                            conn_ins.close()
                            st.success(f"🗑️ Slot docente {docente_fissa} {g_sel} {o_sel}ª ora liberato!")
                            st.rerun()
                        else:
                            classe_sel, materia_sel, docente_sel = dati_sel
                            cursor_ins.execute("""
                                INSERT INTO orario_fissati (classe, giorno, ora, materia, docente, progetto)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (classe_sel, g_sel, o_sel, materia_sel, docente_sel, progetto_corrente))

                            cursor_ins.execute("""
                                INSERT INTO orario_risultato (classe, giorno, ora, materia, docente, progetto)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (classe_sel, g_sel, o_sel, materia_sel, docente_sel, progetto_corrente))

                            conn_ins.commit()
                            conn_ins.close()
                            st.success(f"✅ Slot docente {docente_fissa} {g_sel} {o_sel}ª ora aggiornato, fissato e salvato!")
                            st.rerun()

                with col_db2:
                    if st.button("🔓 Sblocca Slot Docente (Rendi Dinamico)", type="secondary", use_container_width=True):
                        conn_un = sqlite3.connect("orario_scolastico.db")
                        cursor_un = conn_un.cursor()

                        df_fix_un = pd.read_sql("SELECT rowid as id, classe, giorno, ora, materia, docente FROM orario_fissati WHERE progetto = ?", conn_un, params=(progetto_corrente,))
                        for _, r in df_fix_un.iterrows():
                            if docente_contiene(r["docente"], docente_fissa) and r["giorno"] == g_sel and int(r["ora"]) == o_sel:
                                cursor_un.execute("DELETE FROM orario_fissati WHERE rowid = ?", (r["id"],))

                        df_res_un = pd.read_sql("SELECT rowid as id, classe, giorno, ora, materia, docente FROM orario_risultato WHERE progetto = ?", conn_un, params=(progetto_corrente,))
                        for _, r in df_res_un.iterrows():
                            if docente_contiene(r["docente"], docente_fissa) and r["giorno"] == g_sel and int(r["ora"]) == o_sel:
                                cursor_un.execute("DELETE FROM orario_risultato WHERE rowid = ?", (r["id"],))

                        conn_un.commit()
                        conn_un.close()
                        st.info(f"🔓 Slot docente {docente_fissa} {g_sel} {o_sel}ª ora sbloccato e reso dinamico.")
                        st.rerun()