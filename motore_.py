import sqlite3
import json
import time
from ortools.sat.python import cp_model

class MotoreOrario:
    def __init__(self, db_path="orario_scolastico.db"):
        self.db_path = db_path

    def _carica_dati(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT nome, giorni, orario_ore, note FROM classi")
        classi = {
            row["nome"]: {
                "giorni": json.loads(row["giorni"]),
                "ore": json.loads(row["orario_ore"]),
                "note": row["note"]
            }
            for row in cursor.fetchall()
        }
        
        cursor.execute("SELECT nome, ore_settimanali, vincoli FROM docenti")
        docenti = {
            row["nome"]: {
                "ore_settimanali": row["ore_settimanali"],
                "vincoli": json.loads(row["vincoli"]) if row["vincoli"] else {}
            }
            for row in cursor.fetchall()
        }
        
        cursor.execute("SELECT id, classe, materia, docente, docente_2, ore, preferenza_blocchi FROM assegnazioni")
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
        print(f"🔄 Avvio motore CP-SAT Google OR-Tools (Ottimizzazione)...")
        
        # Svuotiamo subito il DB per non vedere vecchi orari fantasma
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS orario_risultato")
        cursor.execute("CREATE TABLE orario_risultato (classe TEXT, giorno TEXT, ora INTEGER, materia TEXT, docente TEXT)")
        conn.commit()
        conn.close()
        
        classi, docenti, assegnazioni = self._carica_dati()
        if not classi or not docenti or not assegnazioni:
            return False, "Dati insufficienti nel database."

        # --- DEBUG MIRATO: Stampiamo i vincoli letti per Buonopane ---
        if "Buonopane" in docenti:
            print(f"🔍 [DEBUG MOTORE] Vincoli letti per Buonopane: {docenti['Buonopane']['vincoli']}")
        else:
            print("⚠️ [DEBUG MOTORE] Docente Buonopane non trovato nel dizionario docenti!")

        inizio_tempo = time.time()
        model = cp_model.CpModel()
        
        x = {}
        presenza_docente = {}

        for ass in assegnazioni:
            c, d, m = ass["classe"], ass["docente"], ass["materia"]
            if c not in classi: continue
            if not d: d = "Nessuno"
            singoli_docenti = [t.strip() for t in d.split("+")]
            
            for giorno in classi[c]["giorni"]:
                num_ore = classi[c]["ore"].get(giorno, 6)
                for ora in range(1, num_ore + 1):
                    var_name = f"x_{c}_{d}_{m}_{giorno}_{ora}"
                    x[(c, d, m, giorno, ora)] = model.NewBoolVar(var_name)
                    for singolo in singoli_docenti:
                        if singolo != "Nessuno":
                            if (singolo, giorno, ora) not in presenza_docente:
                                presenza_docente[(singolo, giorno, ora)] = []
                            presenza_docente[(singolo, giorno, ora)].append(x[(c, d, m, giorno, ora)])

        # 1. VINCOLI BASE
        for ass in assegnazioni:
            c, d, m, ore_tot = ass["classe"], ass["docente"], ass["materia"], ass["ore"]
            if not d: d = "Nessuno"
            if c in classi:
                model.Add(sum(x[(c, d, m, giorno, ora)] for giorno in classi[c]["giorni"] for ora in range(1, classi[c]["ore"].get(giorno, 6) + 1) if (c, d, m, giorno, ora) in x) == ore_tot)

        for c in classi:
            for giorno in classi[c]["giorni"]:
                num_ore = classi[c]["ore"].get(giorno, 6)
                for ora in range(1, num_ore + 1):
                    lezioni_classe_ora = [x[k] for k in x if k[0] == c and k[3] == giorno and k[4] == ora]
                    if lezioni_classe_ora:
                        model.AddAtMostOne(lezioni_classe_ora)

        for (singolo, giorno, ora), lista_impegni in presenza_docente.items():
            model.AddAtMostOne(lista_impegni)
            
        # Max 2 ore per materia al giorno nella stessa classe
        for ass in assegnazioni:
            c, d, m = ass["classe"], ass["docente"], ass["materia"]
            if not d: d = "Nessuno"
            if c in classi:
                for giorno in classi[c]["giorni"]:
                    ore_materia_oggi = [x[(c, d, m, giorno, ora)] for ora in range(1, classi[c]["ore"].get(giorno, 6) + 1) if (c, d, m, giorno, ora) in x]
                    if ore_materia_oggi:
                        model.Add(sum(ore_materia_oggi) <= 2)

        penalita_totali = []

        # 2. GESTIONE DOCENTI E BUCHE
        for singolo, dati_doc in docenti.items():
            vincoli_ui = dati_doc.get("vincoli", {})
            giorni_liberi = vincoli_ui.get("giorni_liberi", [])
            non_disp = vincoli_ui.get("non_disponibili", {})
            max_ore_giorno = int(vincoli_ui.get("max_ore_giorno", 5))
            max_buche = int(vincoli_ui.get("max_buche_giorno", 1))

            tutti_giorni = set()
            for c in classi.values(): tutti_giorni.update(c["giorni"])

            for giorno in tutti_giorni:
                lavora_oggi = model.NewBoolVar(f"lavora_{singolo}_{giorno}")
                ore_lavorate_oggi = []
                
                giorno_norm = giorno.lower().replace('à', 'a').replace('è', 'e').replace('é', 'e').replace('ì', 'i').replace('ò', 'o').replace('ù', 'u')
                
                ore_non_disp_giorno = []
                for k, v in non_disp.items():
                    k_norm = k.lower().replace('à', 'a').replace('è', 'e').replace('é', 'e').replace('ì', 'i').replace('ò', 'o').replace('ù', 'u')
                    if k_norm == giorno_norm:
                        ore_non_disp_giorno = [int(o) for o in v]
                        break

                giorni_liberi_norm = [g.lower().replace('à', 'a').replace('è', 'e').replace('é', 'e').replace('ì', 'i').replace('ò', 'o').replace('ù', 'u') for g in giorni_liberi]
                is_giorno_libero = giorno_norm in giorni_liberi_norm

                # Spegnimento ore non disponibili o giorni liberi
                for (c_chiave, d_chiave, m_chiave, g_chiave, ora_chiave), var_x in x.items():
                    singoli_nella_cella = [t.strip() for t in d_chiave.split("+")]
                    if singolo in singoli_nella_cella and g_chiave == giorno:
                        if is_giorno_libero or ora_chiave in ore_non_disp_giorno:
                            model.Add(var_x == 0)

                for ora in range(1, 10):
                    if (singolo, giorno, ora) in presenza_docente:
                        if not (is_giorno_libero or ora in ore_non_disp_giorno):
                            ore_lavorate_oggi.append(sum(presenza_docente[(singolo, giorno, ora)]))
                
                if not ore_lavorate_oggi:
                    continue
                
                somma_ore_oggi = sum(ore_lavorate_oggi)
                model.Add(somma_ore_oggi <= max_ore_giorno)
                
                model.Add(somma_ore_oggi > 0).OnlyEnforceIf(lavora_oggi)
                model.Add(somma_ore_oggi == 0).OnlyEnforceIf(lavora_oggi.Not())

                prima_ora = model.NewIntVar(1, 10, f"inizio_{singolo}_{giorno}")
                ultima_ora = model.NewIntVar(1, 10, f"fine_{singolo}_{giorno}")
                
                for ora in range(1, 10):
                    if (singolo, giorno, ora) in presenza_docente:
                        is_presente_var = model.NewBoolVar(f"pres_{singolo}_{giorno}_{ora}")
                        model.Add(is_presente_var == sum(presenza_docente[(singolo, giorno, ora)]))
                        model.Add(prima_ora <= ora).OnlyEnforceIf(is_presente_var)
                        model.Add(ultima_ora >= ora).OnlyEnforceIf(is_presente_var)
                
                model.Add(prima_ora == 1).OnlyEnforceIf(lavora_oggi.Not())
                model.Add(ultima_ora == 1).OnlyEnforceIf(lavora_oggi.Not())

                span = model.NewIntVar(0, 10, f"span_{singolo}_{giorno}")
                model.Add(span == (ultima_ora - prima_ora + 1)).OnlyEnforceIf(lavora_oggi)
                model.Add(span == 0).OnlyEnforceIf(lavora_oggi.Not())
                
                buche_effettive = model.NewIntVar(0, 10, f"buche_{singolo}_{giorno}")
                model.Add(buche_effettive == (span - somma_ore_oggi))
                
                penalita_totali.append(buche_effettive * 10)
                
                diff_buche = model.NewIntVar(-10, 10, f"diff_{singolo}_{giorno}")
                eccesso_buche = model.NewIntVar(0, 10, f"eccesso_{singolo}_{giorno}")
                model.Add(diff_buche == buche_effettive - max_buche)
                model.AddMaxEquality(eccesso_buche, [0, diff_buche])
                penalita_totali.append(eccesso_buche * 500)

        if penalita_totali:
            model.Minimize(sum(penalita_totali))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = timeout_secondi
        
        status = solver.Solve(model)
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            for (c, d, m, giorno, ora), var in x.items():
                if solver.Value(var) == 1:
                    cursor.execute("INSERT INTO orario_risultato (classe, giorno, ora, materia, docente) VALUES (?, ?, ?, ?, ?)", (c, giorno, ora, m, d))
            
            cursor.execute("DROP TABLE IF EXISTS orario_fallimenti")
            cursor.execute("CREATE TABLE orario_fallimenti (classe TEXT, materia TEXT, docente TEXT, giorno TEXT, ora INTEGER, motivo TEXT)")
            conn.commit()
            conn.close()
            
            tempo_impiegato = round(time.time() - inizio_tempo, 1)
            qualita = "OTTIMO" if status == cp_model.OPTIMAL else "FATTIBILE (ha fatto del suo meglio)"
            return True, f"Orario generato con successo! Stato: {qualita} in {tempo_impiegato}s."
        else:
            return False, "L'algoritmo si è arreso. Troppi vincoli stretti o ore eccessive per i giorni a disposizione."