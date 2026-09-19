import sqlite3
import json
import ast
import re
import time
from collections import Counter, defaultdict
from ortools.sat.python import cp_model

class MotoreOrario:
    """
    Motore di generazione dell'orario scolastico basato su OR-Tools CP-SAT.
    PRINCIPALI CARATTERISTICHE
    --------------------------
    HARD CONSTRAINTS:
        - una sola lezione per classe/slot
        - un docente non può essere in due classi contemporaneamente
        - disponibilità docente
        - giorni liberi docente
        - ore richieste per ogni assegnazione
        - rispetto del calendario della classe
        - docenti compresenti
        - eventuale monte ore settimanale docente
        - ore fissate (lucchetti)
    SOFT CONSTRAINTS:
        - minimizzazione delle buche
        - minimizzazione delle ore indesiderate
        - rispetto delle preferenze sui blocchi
        - distribuzione equilibrata delle lezioni
        - minimizzazione dei giorni lavorativi
    Il database viene utilizzato senza distruggere i risultati
    degli altri progetti.
    """
    # ------------------------------------------------------------------
    # CONFIGURAZIONE PESI
    # ------------------------------------------------------------------
    PESO_BUCHE = 2000
    PESO_ORE_INDESIDERATE = 1000
    PESO_BLOCCO = 1500
    PESO_GIORNI_LAVORATIVI = 500
    
    # Se True, il campo ore_settimanali del docente viene imposto come vincolo HARD.
    USA_MONTE_ORE_DOCENTE = True
    
    # Se True, min_ore_giorno e max_ore_giorno sono considerati preferenze HARD/SOFT.
    MIN_GIORNALIERO_HARD = False
    MAX_GIORNALIERO_HARD = True

    def __init__(
        self,
        db_path="orario_scolastico.db",
        progetto=None
    ):
        self.db_path = db_path
        self.progetto = progetto
        self.classi = {}
        self.docenti = {}
        self.assegnazioni = []
        self.orario_fissati = []  # <--- AGGIUNTO PER I LUCCHETTI
        self.model = None
        self.solver = None
        self.x = {}
        self.assegnazione_vars = []
        self.penalita = []
        self.diagnostica = []
        self.max_ore_giornaliere = 0

    # ==================================================================
    # UTILITY
    # ==================================================================
    @staticmethod
    def norm(value):
        if value is None:
            return ""
        value = str(value).strip().lower()
        replacements = {
            "à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u",
        }
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value

    @staticmethod
    def parse_json_or_python(value, default=None):
        if default is None:
            default = {}
        if value is None:
            return default
        if isinstance(value, (dict, list, tuple)):
            return value
        if not isinstance(value, str):
            return default
        value = value.strip()
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return default

    @staticmethod
    def lista_ore(value):
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            result = []
            for x in value:
                try:
                    result.append(int(x))
                except (ValueError, TypeError):
                    pass
            return result
        if isinstance(value, str):
            parsed = MotoreOrario.parse_json_or_python(value, None)
            if isinstance(parsed, (list, tuple)):
                return MotoreOrario.lista_ore(parsed)
            tokens = re.split(r"[,; ]+", value.strip())
            result = []
            for token in tokens:
                if token:
                    try:
                        result.append(int(token))
                    except ValueError:
                        pass
            return result
        return []

    @staticmethod
    def lista_giorni(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            parsed = MotoreOrario.parse_json_or_python(value, None)
            if isinstance(parsed, (list, tuple)):
                return list(parsed)
            return [x.strip() for x in value.split(",") if x.strip()]
        return []

    # ==================================================================
    # PARSING BLOCCHI
    # ==================================================================
    @staticmethod
    def parse_blocchi(preferenza, ore_totali):
        try:
            ore_totali = int(ore_totali)
        except (ValueError, TypeError):
            return []
        if ore_totali <= 0:
            return []
        if not preferenza:
            return [1] * ore_totali
        testo = str(preferenza).strip().lower()
        if not testo:
            return [1] * ore_totali
        if "+" in testo:
            try:
                parti = [int(x.strip()) for x in testo.split("+") if x.strip()]
                if parti and all(x > 0 for x in parti) and sum(parti) == ore_totali:
                    return parti
            except ValueError:
                pass
        if testo == "2":
            result = [2] * (ore_totali // 2)
            if ore_totali % 2:
                result.append(1)
            return result
        if testo == "1":
            return [1] * ore_totali
        return [1] * ore_totali

    # ==================================================================
    # CARICAMENTO DATABASE
    # ==================================================================
    def _carica_dati(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            if not self.progetto:
                cursor.execute("SELECT nome FROM progetti LIMIT 1")
                row = cursor.fetchone()
                self.progetto = row["nome"] if row else "Principale"
            
            print(f"📁 Caricamento progetto: '{self.progetto}'")

            # 1. CLASSI
            cursor.execute("SELECT nome, giorni, orario_ore, note FROM classi WHERE progetto = ?", (self.progetto,))
            for row in cursor.fetchall():
                nome = str(row["nome"]).strip()
                giorni = self.parse_json_or_python(row["giorni"], [])
                ore = self.parse_json_or_python(row["orario_ore"], {})
                if not isinstance(giorni, list): giorni = []
                if not isinstance(ore, dict): ore = {}
                giorni = [str(g).strip() for g in giorni if str(g).strip()]
                
                ore_normalizzate = {}
                for giorno, numero in ore.items():
                    try:
                        ore_normalizzate[str(giorno).strip()] = int(numero)
                    except (ValueError, TypeError):
                        raise ValueError(f"Numero ore non valido: {nome} / {giorno}")
                
                self.classi[nome] = {
                    "giorni": giorni,
                    "ore": ore_normalizzate,
                    "note": row["note"],
                }

            # 2. DOCENTI
            cursor.execute("SELECT nome, ore_settimanali, vincoli FROM docenti WHERE progetto = ?", (self.progetto,))
            for row in cursor.fetchall():
                nome = str(row["nome"]).strip()
                vincoli = self.parse_json_or_python(row["vincoli"], {})
                if not isinstance(vincoli, dict): vincoli = {}
                try:
                    ore_settimanali = int(row["ore_settimanali"])
                except (ValueError, TypeError):
                    ore_settimanali = 0
                self.docenti[nome] = {
                    "ore_settimanali": ore_settimanali,
                    "vincoli": vincoli,
                }

            # 3. ASSEGNAZIONI
            cursor.execute("""
                SELECT id, classe, materia, docente, docente_2, ore, preferenza_blocchi 
                FROM assegnazioni WHERE progetto = ?
            """, (self.progetto,))
            for row in cursor.fetchall():
                ass = dict(row)
                ass["classe"] = str(ass.get("classe", "")).strip()
                ass["materia"] = str(ass.get("materia", "")).strip()
                d1 = str(ass.get("docente") or "").strip()
                d2 = str(ass.get("docente_2") or "").strip()
                ass["docenti"] = [x for x in [d1, d2] if x]
                try:
                    ass["ore"] = int(ass["ore"])
                except (ValueError, TypeError):
                    ass["ore"] = 0
                ass["preferenza_blocchi"] = ass.get("preferenza_blocchi") or ""
                self.assegnazioni.append(ass)

            # 4. ORARIO FISSATI (Lucchetti) <--- AGGIUNTO
            cursor.execute("""
                SELECT classe, giorno, ora, materia, docente 
                FROM orario_fissati WHERE progetto = ?
            """, (self.progetto,))
            for row in cursor.fetchall():
                self.orario_fissati.append(dict(row))

        finally:
            conn.close()

    # ==================================================================
    # VALIDAZIONE
    # ==================================================================
    def _valida_dati(self):
        errori = []
        if not self.classi: errori.append("Nessuna classe configurata.")
        if not self.docenti: errori.append("Nessun docente configurato.")
        if not self.assegnazioni: errori.append("Nessuna assegnazione configurata.")
        return errori

    # ==================================================================
    # SLOT DELLE CLASSI
    # ==================================================================
    def _crea_slot_classi(self):
        slots_classe = {}
        for classe, dati in self.classi.items():
            slots = []
            for giorno in dati["giorni"]:
                numero_ore = dati["ore"].get(giorno)
                if numero_ore is None: continue
                for ora in range(1, numero_ore + 1):
                    slots.append((giorno, ora))
            slots_classe[classe] = slots
        self.max_ore_giornaliere = max(
            (max(dati["ore"].values(), default=0) for dati in self.classi.values()),
            default=0
        )
        return slots_classe

    # ==================================================================
    # VINCOLI DOCENTE
    # ==================================================================
    def _docente_disponibile(self, docente, giorno, ora):
        if docente not in self.docenti: return False
        vincoli = self.docenti[docente].get("vincoli", {})
        giorno_norm = self.norm(giorno)

        giorni_liberi = self.lista_giorni(vincoli.get("giorni_liberi", []))
        for giorno_libero in giorni_liberi:
            if self.norm(giorno_libero)[:3] == giorno_norm[:3]:
                return False

        disponibilita = vincoli.get("disponibili") or vincoli.get("disponibilita")
        disponibilita = self.parse_json_or_python(disponibilita, {})
        if disponibilita:
            trovato = False
            ore_disponibili = []
            for g, ore in disponibilita.items():
                if self.norm(g)[:3] == giorno_norm[:3]:
                    trovato = True
                    ore_disponibili = self.lista_ore(ore)
                    break
            if not trovato or ora not in ore_disponibili:
                return False

        non_disponibili = self.parse_json_or_python(vincoli.get("non_disponibili", {}), {})
        for g, ore in non_disponibili.items():
            if self.norm(g)[:3] == giorno_norm[:3]:
                if ora in self.lista_ore(ore):
                    return False
        return True

    # ==================================================================
    # MODELLO E VINCOLI HARD (Inclusi i Lucchetti)
    # ==================================================================
    def _crea_modello(self, slots_classe):
        self.model = cp_model.CpModel()
        self.x = {}
        self.assegnazione_vars = []
        self.penalita = []

        # 1. Variabili di Assegnazione
        for idx, ass in enumerate(self.assegnazioni):
            classe = ass["classe"]
            docenti = ass["docenti"]
            ore_richieste = ass["ore"]
            if classe not in slots_classe: continue

            slot_validi = []
            for giorno, ora in slots_classe[classe]:
                valido = True
                for docente in docenti:
                    if not self._docente_disponibile(docente, giorno, ora):
                        valido = False
                        break
                if valido:
                    slot_validi.append((giorno, ora))

            if len(slot_validi) < ore_richieste:
                self.diagnostica.append({
                    "classe": classe, "materia": ass["materia"], "docente": ", ".join(docenti),
                    "motivo": f"Servono {ore_richieste} ore ma esistono solo {len(slot_validi)} slot validi."
                })
                continue

            vars_assegnazione = []
            for giorno, ora in slot_validi:
                nome = f"x_{idx}_{self.norm(classe)}_{self.norm(giorno)}_{ora}"
                var = self.model.NewBoolVar(nome)
                self.x[(classe, giorno, ora, idx)] = var
                vars_assegnazione.append(var)

            self.model.Add(sum(vars_assegnazione) == ore_richieste)
            self.assegnazione_vars.append((idx, classe, docenti, vars_assegnazione))

        # 2. Vincolo: Max 1 lezione per slot classe
        for classe, slots in slots_classe.items():
            for giorno, ora in slots:
                vars_slot = []
                for idx, classe_ass, _, _ in self.assegnazione_vars:
                    if classe_ass != classe: continue
                    key = (classe, giorno, ora, idx)
                    if key in self.x:
                        vars_slot.append(self.x[key])
                if vars_slot:
                    self.model.Add(sum(vars_slot) <= 1)

        # 3. Vincoli Docenti e Soft Constraints
        self._aggiungi_vincoli_docenti()
        self._aggiungi_vincoli_blocchi()
        
        # 4. Applicazione dei Lucchetti (Orari Fissati) <--- INTEGRATO QUI
        self._aggiungi_vincoli_fissati()

    def _aggiungi_vincoli_fissati(self):
        """
        Forza i vincoli Hard (lucchetti) per le ore fissate dall'utente.
        """
        for fissato in self.orario_fissati:
            c_fissata = str(fissato.get("classe", "")).strip()
            g_fissato = str(fissato.get("giorno", "")).strip()
            ora_fissata = int(fissato.get("ora", 0))
            materia_fissata = str(fissato.get("materia", "")).strip()
            docente_fissato = str(fissato.get("docente", "")).strip()

            trovato = False
            for idx, ass in enumerate(self.assegnazioni):
                if ass["classe"] == c_fissata and ass["materia"] == materia_fissata:
                    docenti_ass = [self.norm(d) for d in ass["docenti"]]
                    if self.norm(docente_fissato) in docenti_ass or not docente_fissato:
                        key = (c_fissata, g_fissato, ora_fissata, idx)
                        if key in self.x:
                            self.model.Add(self.x[key] == 1)
                            trovato = True
                            break
            
            if not trovato:
                self.diagnostica.append({
                    "classe": c_fissata, "materia": materia_fissata, "docente": docente_fissato,
                    "giorno": g_fissato, "ora": ora_fissata,
                    "motivo": "Ora fissata (lucchetto) non compatibile con le assegnazioni o slot inesistente."
                })

    # ==================================================================
    # VINCOLI DOCENTI (Supporto Soft/Hard)
    # ==================================================================
    def _aggiungi_vincoli_docenti(self):
        giorni = sorted(set(giorno for dati in self.classi.values() for giorno in dati["giorni"]))
        for docente, dati_docente in self.docenti.items():
            vincoli = dati_docente.get("vincoli", {})
            try: min_ore = int(vincoli.get("min_ore_giorno", 2))
            except (ValueError, TypeError): min_ore = 2
            try: max_ore = int(vincoli.get("max_ore_giorno", 5))
            except (ValueError, TypeError): max_ore = 5

            indesiderate = self.parse_json_or_python(vincoli.get("indesiderate", {}), {})
            for giorno in giorni:
                giorno_norm = self.norm(giorno)
                ore_indesiderate = []
                for g, ore in indesiderate.items():
                    if self.norm(g)[:3] == giorno_norm[:3]:
                        ore_indesiderate = self.lista_ore(ore)
                        break

                lavora_ora = {}
                for ora in range(1, self.max_ore_giornaliere + 1):
                    vars_ora = []
                    for idx, classe, docenti, _ in self.assegnazione_vars:
                        if docente not in docenti: continue
                        key = (classe, giorno, ora, idx)
                        if key in self.x:
                            vars_ora.append(self.x[key])

                    lavora = self.model.NewBoolVar(f"lavora_{self.norm(docente)}_{self.norm(giorno)}_{ora}")
                    if vars_ora:
                        self.model.Add(sum(vars_ora) <= 1)
                        self.model.Add(sum(vars_ora) == 1).OnlyEnforceIf(lavora)
                        self.model.Add(sum(vars_ora) == 0).OnlyEnforceIf(lavora.Not())
                        if ora in ore_indesiderate:
                            self.penalita.append(lavora * self.PESO_ORE_INDESIDERATE)
                    else:
                        self.model.Add(lavora == 0)
                    lavora_ora[ora] = lavora

                tot_ore = self.model.NewIntVar(0, self.max_ore_giornaliere, f"tot_{self.norm(docente)}_{self.norm(giorno)}")
                self.model.Add(tot_ore == sum(lavora_ora.values()))
                lavora_giorno = self.model.NewBoolVar(f"giorno_{self.norm(docente)}_{self.norm(giorno)}")
                self.model.Add(tot_ore >= 1).OnlyEnforceIf(lavora_giorno)
                self.model.Add(tot_ore == 0).OnlyEnforceIf(lavora_giorno.Not())

                if self.MAX_GIORNALIERO_HARD:
                    self.model.Add(tot_ore <= max_ore)
                
                if self.MIN_GIORNALIERO_HARD:
                    self.model.Add(tot_ore >= min_ore).OnlyEnforceIf(lavora_giorno)

                self._aggiungi_penalita_buche(docente, giorno, lavora_ora, lavora_giorno)
                self.penalita.append(lavora_giorno * self.PESO_GIORNI_LAVORATIVI)

    # ==================================================================
    # BUCHE E BLOCCHI
    # ==================================================================
    def _aggiungi_penalita_buche(self, docente, giorno, lavora_ora, lavora_giorno):
        max_ore = self.max_ore_giornaliere
        if max_ore <= 2: return
        prima, dopo = {}, {}
        prima[1] = lavora_ora[1]
        for ora in range(2, max_ore + 1):
            p = self.model.NewBoolVar(f"prima_{self.norm(docente)}_{self.norm(giorno)}_{ora}")
            self.model.AddMaxEquality(p, [prima[ora - 1], lavora_ora[ora]])
            prima[ora] = p

        dopo[max_ore] = lavora_ora[max_ore]
        for ora in range(max_ore - 1, 0, -1):
            d = self.model.NewBoolVar(f"dopo_{self.norm(docente)}_{self.norm(giorno)}_{ora}")
            self.model.AddMaxEquality(d, [dopo[ora + 1], lavora_ora[ora]])
            dopo[ora] = d

        for ora in range(2, max_ore):
            buca = self.model.NewBoolVar(f"buca_{self.norm(docente)}_{self.norm(giorno)}_{ora}")
            self.model.Add(buca <= prima[ora - 1])
            self.model.Add(buca <= lavora_ora[ora].Not())
            self.model.Add(buca <= dopo[ora + 1])
            self.model.Add(buca >= prima[ora - 1] + lavora_ora[ora].Not() + dopo[ora + 1] - 2)
            self.penalita.append(buca * self.PESO_BUCHE)

    def _aggiungi_vincoli_blocchi(self):
        for idx, ass in enumerate(self.assegnazioni):
            classe = ass["classe"]
            ore_totali = ass["ore"]
            if ore_totali <= 0: continue
            pattern = self.parse_blocchi(ass.get("preferenza_blocchi", ""), ore_totali)
            if pattern == [1] * ore_totali: continue

            giorni = self.classi[classe]["giorni"]
            for giorno in giorni:
                numero_ore = self.classi[classe]["ore"].get(giorno, 0)
                inizio_blocco = {}
                for ora in range(1, numero_ore + 1):
                    key = (classe, giorno, ora, idx)
                    if key not in self.x: continue
                    current = self.x[key]
                    start = self.model.NewBoolVar(f"start_blocco_{idx}_{self.norm(giorno)}_{ora}")
                    if ora == 1:
                        self.model.Add(start == current)
                    else:
                        previous_key = (classe, giorno, ora - 1, idx)
                        if previous_key in self.x:
                            previous = self.x[previous_key]
                            self.model.Add(start >= current - previous)
                            self.model.Add(start <= current)
                            self.model.Add(start <= 1 - previous)
                        else:
                            self.model.Add(start == current)
                    inizio_blocco[giorno, ora] = start

                if not inizio_blocco: continue
                numero_start = sum(inizio_blocco[giorno, ora] for ora in range(1, numero_ore + 1) if (giorno, ora) in inizio_blocco)
                target_blocchi = len(pattern)
                scarto = self.model.NewIntVar(0, numero_ore + 1, f"scarto_blocchi_{idx}_{self.norm(giorno)}")
                diff = self.model.NewIntVar(-numero_ore - 1, numero_ore + 1, f"diff_blocchi_{idx}_{self.norm(giorno)}")
                self.model.Add(diff == numero_start - target_blocchi)
                self.model.AddAbsEquality(scarto, diff)
                self.penalita.append(scarto * self.PESO_BLOCCO)

    # ==================================================================
    # SALVATAGGIO RISULTATI E DIAGNOSTICA
    # ==================================================================
    def _salva_risultato(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orario_risultato (
                    progetto TEXT, classe TEXT, giorno TEXT, ora INTEGER, materia TEXT, docente TEXT
                )
            """)
            cursor.execute("DELETE FROM orario_risultato WHERE progetto = ?", (self.progetto,))
            
            for (c, giorno, ora, idx), var in self.x.items():
                if self.solver.Value(var) != 1: continue
                ass = self.assegnazioni[idx]
                docente = " + ".join(ass["docenti"])
                cursor.execute("""
                    INSERT INTO orario_risultato (progetto, classe, giorno, ora, materia, docente)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (self.progetto, c, giorno, ora, ass["materia"], docente))
            conn.commit()
        finally:
            conn.close()

    def _salva_diagnostica(self):
        if not self.diagnostica: return
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orario_fallimenti (
                    progetto TEXT, classe TEXT, materia TEXT, docente TEXT, giorno TEXT, ora INTEGER, motivo TEXT
                )
            """)
            cursor.execute("DELETE FROM orario_fallimenti WHERE progetto = ?", (self.progetto,))
            for item in self.diagnostica:
                cursor.execute("""
                    INSERT INTO orario_fallimenti (progetto, classe, materia, docente, giorno, ora, motivo)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.progetto, item.get("classe", ""), item.get("materia", ""),
                    item.get("docente", ""), item.get("giorno", ""), item.get("ora", None), item.get("motivo", "")
                ))
            conn.commit()
        finally:
            conn.close()

    # ==================================================================
    # GENERAZIONE PRINCIPALE
    # ==================================================================
    def genera(self, timeout_secondi=60, log_search_progress=False):
        start_time = time.time()
        self.diagnostica = []
        
        print("\n============================================")
        print(" Avvio caricamento dati nel motore...")
        self._carica_dati()
        
        errori = self._valida_dati()
        if errori:
            print("❌ Errore di validazione dati:")
            for err in errori: print(f" - {err}")
            return False, errori

        slots_classe = self._crea_slot_classi()
        print("⚙️ Creazione modello di ottimizzazione CP-SAT...")
        self._crea_modello(slots_classe)
        
        if self.penalita:
            self.model.Minimize(sum(self.penalita))

        print(f"🚀 Avvio Solver (Timeout: {timeout_secondi}s)...")
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = float(timeout_secondi)
        if log_search_progress:
            self.solver.parameters.log_search_progress = True

        status = self.solver.Solve(self.model)
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"✅ Soluzione trovata in {time.time() - start_time:.2f} secondi!")
            self._salva_risultato()
            self._salva_diagnostica()
            return True, "Orario generato con successo."
        else:
            print("❌ Nessuna soluzione trovata (Incompatibilità tra i vincoli o lucchetti in conflitto).")
            self._salva_diagnostica()
            return False, "Impossibile trovare una soluzione con i vincoli attuali."