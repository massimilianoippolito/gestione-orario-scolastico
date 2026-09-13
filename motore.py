import sqlite3
import json
import time
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
            classi[row["nome"]] = {
                "giorni": json.loads(row["giorni"]),
                "ore": json.loads(row["orario_ore"]),
                "note": row["note"]
            }
        
        cursor.execute("SELECT nome, ore_settimanali, vincoli FROM docenti WHERE progetto = ?", (self.progetto,))
        docenti = {}
        for row in cursor.fetchall():
            nome_doc = row["nome"]
            vincoli_raw = row["vincoli"]
            try:
                vincoli_parsed = json.loads(vincoli_raw) if isinstance(vincoli_raw, str) else vincoli_raw
            except:
                vincoli_parsed = {}
                
            docenti[nome_doc] = {
                "ore_settimanali": row["ore_settimanali"],
                "vincoli": vincoli_parsed if vincoli_parsed else {}
            }
            
            # --- STAMPA DI CONTROLLO MIRATA PER BUONOPANE ---
            if nome_doc == "Buonopane":
                print(f"🎯 [DEBUG VINCOLI] Docente: Buonopane -> Grezzo nel DB: {vincoli_raw} | Parsed: {vincoli_parsed}", flush=True)
        
        cursor.execute("SELECT id, classe, materia, docente, docente_2, ore, preferenza_blocchi FROM assegnazioni WHERE progetto = ?", (self.progetto,))
        assegnazioni = []
        for row in cursor.fetchall():
            d = dict(row)
            d1 = d.get("docente", "")
            d2 = d.get("docente_2", "")
            if d2 and "+" not in d1:
                d["docente"] = f"{d1} + {d2}"
            assegnazioni.append(d)
            
        conn.close()
        return classi, docenti, assegnazioni

    def genera(self, timeout_secondi=60):
        print(f"🔄 Avvio motore CP-SAT Google OR-Tools (Ottimizzazione con eliminazione buchi)...")
        classi, docenti, assegnazioni = self._carica_dati()
        
        if not classi or not docenti or not assegnazioni:
            return False, "Dati insufficienti nel database."

        model = cp_model.CpModel()
        
        def norm(s):
            return s.lower().strip().replace('à', 'a').replace('è', 'e').replace('é', 'e').replace('ì', 'i').replace('ò', 'o').replace('ù', 'u')

        x = {}
        slots_classe = {c: [] for c in classi}
        for c, dati_c in classi.items():
            for giorno in dati_c["giorni"]:
                num_ore = dati_c["ore"].get(giorno, 6)
                for ora in range(1, num_ore + 1):
                    slots_classe[c].append((giorno, ora))

        assegnazione_vars = []
        
        for idx_ass, ass in enumerate(assegnazioni):
            c = ass["classe"]
            m = ass["materia"]
            d = ass["docente"]
            ore_tot = ass["ore"]
            
            if c not in classi: 
                continue
                
            singoli_docenti = [t.strip() for t in d.split("+")] if d else []
            slot_validi_per_questa_assegnazione = []
            
            for giorno, ora in slots_classe[c]:
                giorno_norm = norm(giorno)
                docenti_ok = True
                
                for singolo in singoli_docenti:
                    if singolo in docenti:
                        v_doc = docenti[singolo]["vincoli"]
                        
                        g_liberi = [norm(g) for g in v_doc.get("giorni_liberi", [])]
                        if giorno_norm in g_liberi:
                            docenti_ok = False
                            break
                        
                        non_disp = v_doc.get("non_disponibili", {})
                        ore_vietate = []
                        for k_g, v_ore in non_disp.items():
                            if norm(k_g) == giorno_norm or norm(k_g)[:3] == giorno_norm[:3]:
                                ore_vietate = [int(o) for o in v_ore]
                                break
                                
                        if ora in ore_vietate:
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
                return False, f"Impossibile piazzare {m} in {c}: i docenti ({d}) hanno troppe indisponibilità e nessun slot libero comune!"

            assegnazione_vars.append((idx_ass, c, singoli_docenti, vars_cattedra))

        # Vincolo 1: In ogni slot di una classe max 1 lezione
        for c, slots in slots_classe.items():
            for giorno, ora in slots:
                vars_nello_slot = [
                    x[(c, giorno, ora, idx_ass)] 
                    for idx_ass, cl, _, _ in assegnazione_vars 
                    if cl == c and (c, giorno, ora, idx_ass) in x
                ]
                if vars_nello_slot:
                    model.Add(sum(vars_nello_slot) <= 1)

        # Vincolo 2: Un docente non in due classi contemporaneamente
        tutti_i_docenti_unici = list(docenti.keys())
        giorni_scuola = sorted(list(set(g for dati in classi.values() for g in dati["giorni"])))
        
        penalita_compattamento = []
        penalita_indesiderate = []

        for docente in tutti_i_docenti_unici:
            dati_doc = docenti[docente]
            v_doc = dati_doc.get("vincoli", {})
            indesiderate = v_doc.get("indesiderate", {})

            for giorno in giorni_scuola:
                giorno_norm = norm(giorno)
                ore_indesiderate_oggi = []
                for k_g, v_ore in indesiderate.items():
                    if norm(k_g) == giorno_norm or norm(k_g)[:3] == giorno_norm[:3]:
                        ore_indesiderate_oggi = [int(o) for o in v_ore]
                        break

                vars_docente_giorno = {} 
                for ora in range(1, 9):
                    vars_docente_ora = []
                    for idx_ass, c, sing_l, _ in assegnazione_vars:
                        if docente in sing_l:
                            if (c, giorno, ora, idx_ass) in x:
                                var_catt = x[(c, giorno, ora, idx_ass)]
                                vars_docente_ora.append(var_catt)
                                
                                # Penalizziamo se questa ora è indesiderata
                                if ora in ore_indesiderate_oggi:
                                    usa_indes = model.NewBoolVar(f"indes_{docente}_{giorno}_{ora}_{idx_ass}")
                                    model.Add(usa_indes == var_catt)
                                    penalita_indesiderate.append(usa_indes * 1000)
                    
                    if vars_docente_ora:
                        model.Add(sum(vars_docente_ora) <= 1)
                        
                        lavora_ora = model.NewBoolVar(f"lav_{docente}_{giorno}_{ora}")
                        model.Add(sum(vars_docente_ora) >= 1).OnlyEnforceIf(lavora_ora)
                        model.Add(sum(vars_docente_ora) == 0).OnlyEnforceIf(lavora_ora.Not())
                        vars_docente_giorno[ora] = lavora_ora

                if vars_docente_giorno:
                    ore_presenti = sorted(vars_docente_giorno.keys())
                    min_ora = ore_presenti[0]
                    max_ora = ore_presenti[-1]
                    
                    primissima = model.NewIntVar(min_ora, max_ora, f"first_{docente}_{giorno}")
                    ultimissima = model.NewIntVar(min_ora, max_ora, f"last_{docente}_{giorno}")
                    
                    for o in ore_presenti:
                        model.Add(primissima <= o).OnlyEnforceIf(vars_docente_giorno[o])
                        model.Add(ultimissima >= o).OnlyEnforceIf(vars_docente_giorno[o])
                    
                    span_giornaliero = model.NewIntVar(0, 8, f"span_{docente}_{giorno}")
                    model.Add(span_giornaliero == ultimissima - primissima)
                    penalita_compattamento.append(span_giornaliero)

        # Funzione Obiettivo Totale: Compattamento + Evitare ore indesiderate
        tutte_le_penalita = penalita_compattamento + penalita_indesiderate
        if tutte_le_penalita:
            model.Minimize(sum(tutte_le_penalita))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(timeout_secondi)
        
        print("⚙️ Esecuzione ottimizzazione avanzata OR-Tools in corso (compattamento + indesiderate)...")
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