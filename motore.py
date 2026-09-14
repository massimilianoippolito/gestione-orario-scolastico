import sqlite3
import json
import ast
import time
from collections import Counter
from ortools.sat.python import cp_model

class MotoreOrario:
    def __init__(self, db_path="orario_scolastico.db", progetto=None):
        self.db_path = db_path
        self.progetto = progetto

    def _carica_dati(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if not self.progetto:
            cursor.execute("SELECT nome FROM progetti LIMIT 1")
            row_p = cursor.fetchone()
            self.progetto = row_p["nome"] if row_p else "Principale"

        print(f"📁 [MOTORE] Caricamento dati per il progetto attivo: '{self.progetto}'")

        cursor.execute("SELECT nome, giorni, orario_ore, note FROM classi WHERE progetto = ?", (self.progetto,))
        classi = {}
        for row in cursor.fetchall():
            nome_c = str(row["nome"]).strip()
            classi[nome_c] = {
                "giorni": json.loads(row["giorni"]),
                "ore": json.loads(row["orario_ore"]),
                "note": row["note"]
            }
        
        cursor.execute("SELECT nome, ore_settimanali, vincoli FROM docenti WHERE progetto = ?", (self.progetto,))
        docenti = {}
        for row in cursor.fetchall():
            nome_doc = str(row["nome"]).strip()
            vincoli_raw = row["vincoli"]
            vincoli_parsed = {}
            
            if vincoli_raw:
                if isinstance(vincoli_raw, str):
                    try:
                        vincoli_parsed = json.loads(vincoli_raw)
                    except:
                        try:
                            vincoli_parsed = ast.literal_eval(vincoli_raw)
                        except Exception as e:
                            print(f"⚠️ Errore critico parsing vincoli {nome_doc}: {e}")
                elif isinstance(vincoli_raw, dict):
                    vincoli_parsed = vincoli_raw

            # DIFESA ANTI-DUPLICATI: Sovrascrivi solo se i nuovi vincoli sono pieni
            if nome_doc not in docenti or (vincoli_parsed and not docenti[nome_doc]["vincoli"]):
                docenti[nome_doc] = {
                    "ore_settimanali": row["ore_settimanali"],
                    "vincoli": vincoli_parsed
                }
        
        cursor.execute("SELECT id, classe, materia, docente, docente_2, ore, preferenza_blocchi FROM assegnazioni WHERE progetto = ?", (self.progetto,))
        assegnazioni = []
        for row in cursor.fetchall():
            d = dict(row)
            d1 = str(d.get("docente", "")).strip()
            d2 = str(d.get("docente_2", "")).strip()
            if d2 and "+" not in d1:
                d["docente"] = f"{d1} + {d2}"
            else:
                d["docente"] = d1
            assegnazioni.append(d)
            
        conn.close()
        return classi, docenti, assegnazioni

    def genera(self, timeout_secondi=60):
        print(f"🔄 Avvio motore CP-SAT Google OR-Tools (Protezione Massima DB)...")
        classi, docenti, assegnazioni = self._carica_dati()
        
        if not classi or not docenti or not assegnazioni:
            return False, "Dati insufficienti nel database."

        model = cp_model.CpModel()
        
        def norm(s):
            return str(s).lower().strip().replace('à', 'a').replace('è', 'e').replace('é', 'e').replace('ì', 'i').replace('ò', 'o').replace('ù', 'u')

        def safe_dict(val):
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                try:
                    res = ast.literal_eval(val)
                    if isinstance(res, dict): return res
                except: pass
            return {}
            
        def parse_blocchi(testo_pref, ore_totali):
            if not testo_pref: 
                return [1] * ore_totali
            testo_norm = str(testo_pref).lower().strip()
            if "+" in testo_norm:
                try:
                    parts = [int(p.strip()) for p in testo_norm.split("+")]
                    if sum(parts) == ore_totali: return parts
                except: pass
            if "2" in testo_norm:
                blocchi = [2] * (ore_totali // 2)
                if ore_totali % 2 != 0: blocchi.append(1)
                return blocchi
            return [1] * ore_totali

        x = {}
        slots_classe = {c: [] for c in classi}
        for c, dati_c in classi.items():
            for giorno in dati_c["giorni"]:
                num_ore = dati_c["ore"].get(giorno, 6)
                for ora in range(1, num_ore + 1):
                    slots_classe[c].append((str(giorno).strip(), ora))

        assegnazione_vars = []
        penalita_violazione_blocchi = []
        
        for idx_ass, ass in enumerate(assegnazioni):
            c = str(ass["classe"]).strip()
            m = ass["materia"]
            d = ass["docente"]
            ore_tot = int(ass["ore"])
            pref_blocchi = ass.get("preferenza_blocchi", "")
            
            if c not in classi: continue
                
            singoli_docenti = [t.strip() for t in d.split("+")] if d else []
            slot_validi_per_questa_assegnazione = []
            
            # --- FILTRAGGIO RIGIDO HARD CONSTRAINT (Bollini) ---
            for giorno, ora in slots_classe[c]:
                giorno_norm = norm(giorno)
                docenti_ok = True
                
                for singolo in singoli_docenti:
                    if singolo in docenti:
                        v_doc = docenti[singolo]["vincoli"]
                        
                        # 1. Giorni Liberi
                        g_liberi = v_doc.get("giorni_liberi", [])
                        if isinstance(g_liberi, str):
                            try: g_liberi = ast.literal_eval(g_liberi)
                            except: g_liberi = []
                        if isinstance(g_liberi, list):
                            if any(giorno_norm[:3] == norm(g)[:3] for g in g_liberi if g):
                                docenti_ok = False
                                break
                        
                        # 2. Disponibilità (Verdi)
                        disp = safe_dict(v_doc.get("disponibili") or v_doc.get("disponibilita"))
                        if disp:
                            giorno_trovato = False
                            ore_verdi = []
                            for k_g, v_ore in disp.items():
                                if norm(k_g)[:3] == giorno_norm[:3]:
                                    giorno_trovato = True
                                    if isinstance(v_ore, str):
                                        try: v_ore = ast.literal_eval(v_ore)
                                        except: pass
                                    if isinstance(v_ore, (list, tuple)):
                                        ore_verdi = [int(o) for o in v_ore if str(o).isdigit()]
                                    break
                            if not giorno_trovato or int(ora) not in ore_verdi:
                                docenti_ok = False
                                break

                        # 3. Indisponibilità (Rossi)
                        non_disp = safe_dict(v_doc.get("non_disponibili"))
                        if non_disp:
                            ore_rossi = []
                            for k_g, v_ore in non_disp.items():
                                if norm(k_g)[:3] == giorno_norm[:3]:
                                    if isinstance(v_ore, str):
                                        try: v_ore = ast.literal_eval(v_ore)
                                        except: pass
                                    if isinstance(v_ore, (list, tuple)):
                                        ore_rossi = [int(o) for o in v_ore if str(o).isdigit()]
                                    break
                            
                            if int(ora) in ore_rossi:
                                docenti_ok = False
                                break
                
                if docenti_ok:
                    slot_validi_per_questa_assegnazione.append((giorno, ora))

            vars_cattedra = []
            for giorno, ora in slot_validi_per_questa_assegnazione:
                var_name = f"c_{idx_ass}_{c}_{giorno}_{ora}"
                v_bool = model.NewBoolVar(var_name)
                x[(c, giorno, ora, idx_ass)] = v_bool
                vars_cattedra.append(v_bool)

            if vars_cattedra:
                model.Add(sum(vars_cattedra) == ore_tot)
            else:
                return False, f"Impossibile piazzare {m} in {c}: i docenti ({d}) non hanno slot validi o disponibili (Conflitto bollini)!"

            assegnazione_vars.append((idx_ass, c, singoli_docenti, vars_cattedra))

            # --- LOGICA DEI BLOCCHI ---
            pattern_target = parse_blocchi(pref_blocchi, ore_tot)
            target_counts = Counter(pattern_target)
            
            ore_giornaliere_vars = []
            for giorno in classi[c]["giorni"]:
                giorno = str(giorno).strip()
                num_ore_giorno = classi[c]["ore"].get(giorno, 6)
                ore_oggi = []
                start_oggi = []
                
                for ora in range(1, num_ore_giorno + 1):
                    if (c, giorno, ora, idx_ass) in x:
                        v_h = x[(c, giorno, ora, idx_ass)]
                        ore_oggi.append(v_h)
                        is_start = model.NewBoolVar(f"start_{idx_ass}_{giorno}_{ora}")
                        if ora == 1 or (c, giorno, ora - 1, idx_ass) not in x:
                            model.Add(is_start == v_h)
                        else:
                            v_prev = x[(c, giorno, ora - 1, idx_ass)]
                            model.Add(is_start >= v_h - v_prev)
                            model.Add(is_start <= v_h)
                            model.Add(is_start <= 1 - v_prev)
                        start_oggi.append(is_start)
                        
                if ore_oggi:
                    sum_ore_oggi = model.NewIntVar(0, num_ore_giorno, f"sum_ore_{idx_ass}_{giorno}")
                    model.Add(sum_ore_oggi == sum(ore_oggi))
                    ore_giornaliere_vars.append(sum_ore_oggi)
                    
                    sum_starts_oggi = model.NewIntVar(0, num_ore_giorno, f"sum_starts_{idx_ass}_{giorno}")
                    model.Add(sum_starts_oggi == sum(start_oggi))
                    
                    is_active_day = model.NewBoolVar(f"active_{idx_ass}_{giorno}")
                    model.Add(sum_ore_oggi >= 1).OnlyEnforceIf(is_active_day)
                    model.Add(sum_ore_oggi == 0).OnlyEnforceIf(is_active_day.Not())
                    
                    extra_starts = model.NewIntVar(0, num_ore_giorno, f"extra_starts_{idx_ass}_{giorno}")
                    model.Add(extra_starts == sum_starts_oggi - is_active_day)
                    penalita_violazione_blocchi.append(extra_starts * 5000) 
                    
            for k in range(1, ore_tot + 1):
                target_k = target_counts.get(k, 0)
                days_with_k_vars = []
                for d_idx, sum_var in enumerate(ore_giornaliere_vars):
                    is_k = model.NewBoolVar(f"is_{k}_{idx_ass}_{d_idx}")
                    is_less = model.NewBoolVar(f"less_{k}_{idx_ass}_{d_idx}")
                    is_greater = model.NewBoolVar(f"great_{k}_{idx_ass}_{d_idx}")
                    
                    model.AddExactlyOne([is_k, is_less, is_greater])
                    model.Add(sum_var == k).OnlyEnforceIf(is_k)
                    model.Add(sum_var < k).OnlyEnforceIf(is_less)
                    model.Add(sum_var > k).OnlyEnforceIf(is_greater)
                    days_with_k_vars.append(is_k)
                    
                tot_days_with_k = model.NewIntVar(0, len(ore_giornaliere_vars), f"tot_days_{k}_{idx_ass}")
                model.Add(tot_days_with_k == sum(days_with_k_vars))
                scarto_k = model.NewIntVar(0, len(ore_giornaliere_vars), f"scarto_{k}_{idx_ass}")
                model.AddAbsEquality(scarto_k, tot_days_with_k - target_k)
                penalita_violazione_blocchi.append(scarto_k * 1000)

        # Vincolo 1: Max 1 lezione per slot classe
        for c, slots in slots_classe.items():
            for giorno, ora in slots:
                vars_nello_slot = [
                    x[(c, giorno, ora, idx_ass)] 
                    for idx_ass, cl, _, _ in assegnazione_vars 
                    if cl == c and (c, giorno, ora, idx_ass) in x
                ]
                if vars_nello_slot:
                    model.Add(sum(vars_nello_slot) <= 1)

        # Vincolo 2: Docenti (No sovrapposizioni, Min/Max ore, Buche)
        tutti_i_docenti_unici = list(docenti.keys())
        giorni_scuola = sorted(list(set(str(g).strip() for dati in classi.values() for g in dati["giorni"])))
        penalita_docenti = []

        for docente in tutti_i_docenti_unici:
            dati_doc = docenti[docente]
            v_doc = dati_doc.get("vincoli", {})
            indesiderate = safe_dict(v_doc.get("indesiderate"))
            
            try: min_ore_gg = int(v_doc.get("min_ore_giorno", 2))
            except: min_ore_gg = 2
            try: max_ore_gg = int(v_doc.get("max_ore_giorno", 5))
            except: max_ore_gg = 5

            for giorno in giorni_scuola:
                giorno_norm = norm(giorno)
                ore_indesiderate_oggi = []
                for k_g, v_ore in indesiderate.items():
                    if norm(k_g)[:3] == giorno_norm[:3]:
                        if isinstance(v_ore, str):
                            try: v_ore = ast.literal_eval(v_ore)
                            except: pass
                        if isinstance(v_ore, (list, tuple)):
                            ore_indesiderate_oggi = [int(o) for o in v_ore if str(o).isdigit()]
                        break

                vars_docente_giorno = {} 
                for ora in range(1, 9):
                    vars_docente_ora = []
                    for idx_ass, c, sing_l, _ in assegnazione_vars:
                        if docente in sing_l:
                            if (c, giorno, ora, idx_ass) in x:
                                var_catt = x[(c, giorno, ora, idx_ass)]
                                vars_docente_ora.append(var_catt)
                                
                                if ora in ore_indesiderate_oggi:
                                    usa_indes = model.NewBoolVar(f"indes_{docente}_{giorno}_{ora}_{idx_ass}")
                                    model.Add(usa_indes == var_catt)
                                    penalita_docenti.append(usa_indes * 1000)
                    
                    lavora_ora = model.NewBoolVar(f"lav_{docente}_{giorno}_{ora}")
                    if vars_docente_ora:
                        model.Add(sum(vars_docente_ora) <= 1)
                        model.Add(sum(vars_docente_ora) == 1).OnlyEnforceIf(lavora_ora)
                        model.Add(sum(vars_docente_ora) == 0).OnlyEnforceIf(lavora_ora.Not())
                    else:
                        model.Add(lavora_ora == 0)
                    vars_docente_giorno[ora] = lavora_ora

                tot_ore_oggi = model.NewIntVar(0, 8, f"tot_ore_{docente}_{giorno}")
                model.Add(tot_ore_oggi == sum(vars_docente_giorno.values()))
                
                lavora_oggi = model.NewBoolVar(f"lavora_{docente}_{giorno}")
                model.Add(tot_ore_oggi >= 1).OnlyEnforceIf(lavora_oggi)
                model.Add(tot_ore_oggi == 0).OnlyEnforceIf(lavora_oggi.Not())
                
                # --- CALCOLO BUCHE ---
                ore_presenti = sorted(vars_docente_giorno.keys())
                primissima = model.NewIntVar(1, 8, f"first_{docente}_{giorno}")
                ultimissima = model.NewIntVar(1, 8, f"last_{docente}_{giorno}")
                
                for o in ore_presenti:
                    model.Add(primissima <= o).OnlyEnforceIf(vars_docente_giorno[o])
                    model.Add(ultimissima >= o).OnlyEnforceIf(vars_docente_giorno[o])
                
                span = model.NewIntVar(0, 8, f"span_{docente}_{giorno}")
                model.Add(span == ultimissima - primissima).OnlyEnforceIf(lavora_oggi)
                model.Add(span == 0).OnlyEnforceIf(lavora_oggi.Not())
                
                buche_oggi = model.NewIntVar(0, 8, f"buche_{docente}_{giorno}")
                model.Add(buche_oggi == span - tot_ore_oggi + 1).OnlyEnforceIf(lavora_oggi)
                model.Add(buche_oggi == 0).OnlyEnforceIf(lavora_oggi.Not())
                penalita_docenti.append(buche_oggi * 2000)

                # --- MIN/MAX ORE ---
                sotto_minimo = model.NewBoolVar(f"sotto_min_{docente}_{giorno}")
                model.Add(tot_ore_oggi < min_ore_gg).OnlyEnforceIf([lavora_oggi, sotto_minimo])
                model.Add(tot_ore_oggi >= min_ore_gg).OnlyEnforceIf([lavora_oggi, sotto_minimo.Not()])
                model.Add(sotto_minimo == 0).OnlyEnforceIf(lavora_oggi.Not())
                penalita_docenti.append(sotto_minimo * 8000)

                sopra_massimo = model.NewBoolVar(f"sopra_max_{docente}_{giorno}")
                model.Add(tot_ore_oggi > max_ore_gg).OnlyEnforceIf(sopra_massimo)
                model.Add(tot_ore_oggi <= max_ore_gg).OnlyEnforceIf(sopra_massimo.Not())
                penalita_docenti.append(sopra_massimo * 8000)

        tutte_le_penalita = penalita_docenti + penalita_violazione_blocchi
        if tutte_le_penalita:
            model.Minimize(sum(tutte_le_penalita))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(timeout_secondi)
        
        print("⚙️ Esecuzione ottimizzazione avanzata OR-Tools in corso...")
        status = solver.Solve(model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print("🎉 Soluzione ottimizzata trovata con successo!")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DROP TABLE IF EXISTS orario_risultato")
            cursor.execute("""
                CREATE TABLE orario_risultato (
                    progetto TEXT,
                    classe TEXT, 
                    giorno TEXT, 
                    ora INTEGER, 
                    materia TEXT, 
                    docente TEXT
                )
            """)
            
            for (c, giorno, ora, idx_ass), var in x.items():
                if solver.Value(var) == 1:
                    ass = assegnazioni[idx_ass]
                    mat = ass["materia"]
                    doc = ass["docente"]
                    cursor.execute(
                        "INSERT INTO orario_risultato (progetto, classe, giorno, ora, materia, docente) VALUES (?, ?, ?, ?, ?, ?)",
                        (self.progetto, c, giorno, ora, mat, doc)
                    )
            
            cursor.execute("DROP TABLE IF EXISTS orario_fallimenti")
            cursor.execute("CREATE TABLE orario_fallimenti (classe TEXT, materia TEXT, docente TEXT, giorno TEXT, ora INTEGER, motivo TEXT)")
            conn.commit()
            conn.close()
            
            return True, "Orario generato e ottimizzato con successo!"
        else:
            return False, "Il solver OR-Tools non ha trovato una soluzione: i vincoli attuali sono troppo restrittivi."