import sqlite3
import json
import ast
import uuid
from collections import defaultdict, Counter

from ortools.sat.python import cp_model


class MotoreOrario:
    """
    Motore di generazione dell'orario scolastico basato su Google OR-Tools CP-SAT.

    V5 - versione ottimizzata:
      - pre-calcolo degli slot compatibili per assegnazione;
      - indice assegnazioni per docente, evitando scansioni ripetute;
      - vincoli hard separati dalle preferenze soft;
      - gestione robusta di JSON / repr Python provenienti dal DB;
      - diagnostica più dettagliata;
      - gestione corretta di prima/ultima ora e delle buche;
      - preferenza blocchi modellata senza enumerare tutte le lunghezze;
      - salvataggio non distruttivo del risultato del progetto corrente;
      - gestione dei lucchetti di orario_fissati come vincoli HARD assoluti.
    """

    def __init__(
        self,
        db_path="orario_scolastico.db",
        progetto=None,
        min_ore_giorno_hard=False,
        max_ore_giorno_hard=False,
        peso_ora_indesiderata=1000,
        peso_buca=2000,
        peso_giorno_lavorativo=300,
        peso_blocco=1500,
        peso_sotto_minimo=8000,
        peso_sopra_massimo=8000,
        log=True,
    ):
        self.db_path = db_path
        self.progetto = progetto
        self.min_ore_giorno_hard = min_ore_giorno_hard
        self.max_ore_giorno_hard = max_ore_giorno_hard
        self.log = log

        self.pesi = {
            "ora_indesiderata": int(peso_ora_indesiderata),
            "buca": int(peso_buca),
            "giorno_lavorativo": int(peso_giorno_lavorativo),
            "blocco": int(peso_blocco),
            "sotto_minimo": int(peso_sotto_minimo),
            "sopra_massimo": int(peso_sopra_massimo),
        }

        self.classi = {}
        self.docenti = {}
        self.assegnazioni = []

        # Ore fissate dall'interfaccia: sono VINCOLI HARD.
        # Chiavi: indice assegnazione -> insieme di (giorno, ora).
        self.orario_fissati = []
        self.fissati_per_assegnazione = defaultdict(set)

        self.model = None
        self.solver = None
        self.x = {}
        self.assegnazione_vars = []
        self.penalita = []
        self.diagnostica = []
        self.generation_id = None

        # Indici costruiti una sola volta.
        self.assegnazioni_per_docente = defaultdict(list)
        self.assegnazioni_per_classe = defaultdict(list)
        self.lavora_docente_ora = {}

    # ============================================================
    # UTILITY
    # ============================================================

    def _log(self, msg):
        if self.log:
            print(msg)

    @staticmethod
    def _norm(value):
        if value is None:
            return ""
        return (
            str(value)
            .strip()
            .lower()
            .replace("à", "a")
            .replace("è", "e")
            .replace("é", "e")
            .replace("ì", "i")
            .replace("ò", "o")
            .replace("ù", "u")
        )

    @classmethod
    def _giorno_equivalente(cls, g1, g2):
        return cls._norm(g1)[:3] == cls._norm(g2)[:3]

    @staticmethod
    def _parse_json(value, default=None):
        if value is None or value == "":
            return default if default is not None else {}

        if isinstance(value, (dict, list, tuple, set)):
            return value

        if not isinstance(value, str):
            return default if default is not None else {}

        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError, TypeError):
            return default if default is not None else {}

    @classmethod
    def _lista_ore(cls, value):
        if value is None:
            return []

        if isinstance(value, str):
            value = cls._parse_json(value, [])

        if not isinstance(value, (list, tuple, set)):
            return []

        risultato = []
        for item in value:
            try:
                risultato.append(int(item))
            except (ValueError, TypeError):
                continue
        return risultato

    @classmethod
    def _dict_giorno_ore(cls, value):
        """
        Normalizza strutture del tipo:
            {"Lun": [1,2,3]}
        anche quando le ore sono serializzate come stringa.
        """
        data = cls._parse_json(value, {})
        if not isinstance(data, dict):
            return {}

        result = {}
        for giorno, ore in data.items():
            result[str(giorno).strip()] = cls._lista_ore(ore)
        return result

    @staticmethod
    def _parse_blocchi(preferenza, ore_totali):
        """
        "":      [1, 1, 1, ...]
        "2":      [2, 2, ...] (+ eventuale 1)
        "2+2":    [2, 2]
        "2+1":    [2, 1]
        """
        if ore_totali <= 0:
            return []

        if preferenza is None:
            return [1] * ore_totali

        testo = str(preferenza).strip().lower()
        if testo in ("", "nessuna", "nessuno"):
            return [1] * ore_totali

        if "+" in testo:
            try:
                blocchi = [int(x.strip()) for x in testo.split("+")]
                if all(x > 0 for x in blocchi) and sum(blocchi) == ore_totali:
                    return blocchi
            except (ValueError, TypeError):
                pass

        try:
            valore = int(testo)
            if valore > 0:
                blocchi = []
                rimanenti = ore_totali
                while rimanenti >= valore:
                    blocchi.append(valore)
                    rimanenti -= valore
                if rimanenti:
                    blocchi.append(rimanenti)
                return blocchi
        except (ValueError, TypeError):
            pass

        return [1] * ore_totali

    @staticmethod
    def _safe_int(value, default=None):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    # ============================================================
    # DATABASE
    # ============================================================

    def _carica_dati(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            if not self.progetto:
                cursor.execute("SELECT nome FROM progetti ORDER BY nome LIMIT 1")
                row = cursor.fetchone()
                self.progetto = row["nome"] if row else "Principale"

            self._log(
                f"📁 [MOTORE V5] Progetto attivo: '{self.progetto}'"
            )

            # --------------------------------------------------------
            # CLASSI
            # --------------------------------------------------------

            cursor.execute(
                """
                SELECT nome, giorni, orario_ore, note
                FROM classi
                WHERE progetto = ?
                """,
                (self.progetto,),
            )

            self.classi = {}

            for row in cursor.fetchall():
                nome = str(row["nome"]).strip()
                giorni = self._parse_json(row["giorni"], [])
                orario_ore = self._parse_json(row["orario_ore"], {})

                if not isinstance(giorni, list):
                    raise ValueError(
                        f"Giorni non validi per la classe '{nome}'."
                    )

                if not isinstance(orario_ore, dict):
                    raise ValueError(
                        f"orario_ore non valido per la classe '{nome}'."
                    )

                ore = {}
                for giorno, numero in orario_ore.items():
                    valore = self._safe_int(numero)
                    if valore is None or valore <= 0:
                        raise ValueError(
                            f"Numero ore non valido: {nome} / {giorno} / {numero}"
                        )
                    ore[str(giorno).strip()] = valore

                giorni_norm = [str(g).strip() for g in giorni if str(g).strip()]

                self.classi[nome] = {
                    "giorni": giorni_norm,
                    "ore": ore,
                    "note": row["note"],
                }

            # --------------------------------------------------------
            # DOCENTI
            # --------------------------------------------------------

            cursor.execute(
                """
                SELECT nome, ore_settimanali, vincoli
                FROM docenti
                WHERE progetto = ?
                """,
                (self.progetto,),
            )

            self.docenti = {}

            for row in cursor.fetchall():
                nome = str(row["nome"]).strip()
                vincoli = self._parse_json(row["vincoli"], {})
                if not isinstance(vincoli, dict):
                    vincoli = {}

                ore_settimanali = self._safe_int(
                    row["ore_settimanali"], 0
                )

                if nome not in self.docenti:
                    self.docenti[nome] = {
                        "ore_settimanali": ore_settimanali or 0,
                        "vincoli": vincoli,
                    }
                else:
                    precedente = self.docenti[nome]
                    if vincoli and not precedente["vincoli"]:
                        precedente["vincoli"] = vincoli
                    if ore_settimanali is not None and ore_settimanali > 0:
                        precedente["ore_settimanali"] = ore_settimanali

            # --------------------------------------------------------
            # ASSEGNAZIONI
            # --------------------------------------------------------

            cursor.execute(
                """
                SELECT
                    id, classe, materia, docente, docente_2,
                    ore, preferenza_blocchi
                FROM assegnazioni
                WHERE progetto = ?
                """,
                (self.progetto,),
            )

            self.assegnazioni = []

            for row in cursor.fetchall():
                ass = dict(row)

                # Correzione del progetto inserita correttamente qui:
                ass["progetto"] = self.progetto

                ass["classe"] = str(ass.get("classe") or "").strip()
                ass["materia"] = str(ass.get("materia") or "").strip()

                d1 = str(ass.get("docente") or "").strip()
                d2 = str(ass.get("docente_2") or "").strip()

                docenti_ass = []

                if d1:
                    docenti_ass.extend(
                        x.strip() for x in d1.split("+") if x.strip()
                    )

                if d2 and d2 not in docenti_ass:
                    docenti_ass.append(d2)

                ass["docenti"] = docenti_ass
                ass["docente"] = " + ".join(docenti_ass)

                ore = self._safe_int(ass.get("ore"))
                ass["ore"] = ore if ore is not None else 0

                self.assegnazioni.append(ass)

            self._carica_orario_fissati(cursor)
            self._ricostruisci_indici()

        finally:
            conn.close()

    def _carica_orario_fissati(self, cursor):
        """
        Carica i lucchetti dell'interfaccia da orario_fissati.

        OGNI riga è un VINCOLO HARD:
            classe + giorno + ora + materia + docente

        Un lucchetto non è una preferenza. Se il resto dei vincoli rende
        impossibile rispettarlo, il modello deve risultare INFEASIBLE.
        Non è mai consentito ignorare o rilassare un lucchetto.
        """
        self.orario_fissati = []
        self.fissati_per_assegnazione = defaultdict(set)

        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'orario_fissati'
            """
        )
        if cursor.fetchone() is None:
            return

        cursor.execute(
            """
            SELECT classe, giorno, ora, materia, docente, progetto
            FROM orario_fissati
            WHERE progetto = ?
            ORDER BY classe, giorno, ora
            """,
            (self.progetto,),
        )

        for row in cursor.fetchall():
            self.orario_fissati.append(
                {
                    "classe": str(row["classe"] or "").strip(),
                    "giorno": str(row["giorno"] or "").strip(),
                    "ora": self._safe_int(row["ora"]),
                    "materia": str(row["materia"] or "").strip(),
                    "docente": str(row["docente"] or "").strip(),
                    "progetto": str(row["progetto"] or "").strip(),
                }
            )

        for fis in self.orario_fissati:
            classe = fis["classe"]
            giorno = fis["giorno"]
            ora = fis["ora"]
            materia = fis["materia"]
            docente = fis["docente"]

            # La classe deve esistere.
            if classe not in self.classi:
                raise ValueError(
                    f"Lucchetto riferito a classe inesistente: "
                    f"{classe} / {giorno} / {ora}."
                )

            # Trova il nome del giorno effettivamente usato dalla classe
            # (es. Lun/Lunedì, se il DB usa abbreviazioni).
            giorno_reale = None
            for g in self.classi[classe]["giorni"]:
                if self._giorno_equivalente(g, giorno):
                    giorno_reale = g
                    break

            if giorno_reale is None:
                raise ValueError(
                    f"Lucchetto fuori dai giorni della classe: "
                    f"{classe} / {giorno} / {ora}."
                )

            max_ore = self.classi[classe]["ore"].get(giorno_reale, 0)
            if ora is None or ora < 1 or ora > max_ore:
                raise ValueError(
                    f"Lucchetto fuori dall'orario della classe: "
                    f"{classe} / {giorno} / {ora} "
                    f"(massimo {max_ore})."
                )

            candidati = []
            for idx, ass in enumerate(self.assegnazioni):
                if ass["classe"] != classe:
                    continue
                if self._norm(ass["materia"]) != self._norm(materia):
                    continue
                if self._norm(ass.get("progetto", "")) != self._norm(
                    fis["progetto"]
                ):
                    continue
                if not any(
                    self._norm(d) == self._norm(docente)
                    for d in ass["docenti"]
                ):
                    continue
                candidati.append(idx)

            if not candidati:
                raise ValueError(
                    "Lucchetto senza assegnazione corrispondente: "
                    f"{classe} / {giorno_reale} / {ora} / "
                    f"{materia} / {docente}."
                )

            if len(candidati) > 1:
                dettagli = ", ".join(
                    f"id={self.assegnazioni[i]['id']}"
                    for i in candidati
                )
                raise ValueError(
                    "Lucchetto ambiguo: "
                    f"{classe} / {giorno_reale} / {ora} / "
                    f"{materia} / {docente}. "
                    f"Possibili assegnazioni: {dettagli}."
                )

            idx = candidati[0]
            slot = (giorno_reale, ora)
            # --- AGGIUNGI QUI IL CONTROLLO DIAGNOSTICO DEI LUCCHETTI ---
            docenti_assegnazione = self.assegnazioni[idx]["docenti"]
            for d_chk in docenti_assegnazione:
                if not self._docente_disponibile(d_chk, giorno_reale, ora):
                    print(f"🔥 [DEBUG LUCCHETTO] Il docente '{d_chk}' ha un lucchetto il {giorno_reale} alla {ora}ª ora nella classe {classe}, MA ha il pallino rosso (indisponibile)!")
            # -------------------------------------------------------------

            if slot in self.fissati_per_assegnazione[idx]:
                raise ValueError(
                    "Lucchetto duplicato per la stessa assegnazione: "
                    f"{classe} / {giorno_reale} / {ora} / "
                    f"{materia} / {docente}."
                )

            self.fissati_per_assegnazione[idx].add(slot)

    def _ricostruisci_indici(self):
        self.assegnazioni_per_docente = defaultdict(list)
        self.assegnazioni_per_classe = defaultdict(list)
        self.lavora_docente_ora = {}

        for idx, ass in enumerate(self.assegnazioni):
            self.assegnazioni_per_classe[ass["classe"]].append(idx)
            for docente in ass["docenti"]:
                self.assegnazioni_per_docente[docente].append(idx)

    # ============================================================
    # VALIDAZIONE
    # ============================================================

    def _valida_dati(self):
        errori = []

        if not self.classi:
            errori.append("Nessuna classe presente nel progetto.")

        if not self.docenti:
            errori.append("Nessun docente presente nel progetto.")

        if not self.assegnazioni:
            errori.append("Nessuna assegnazione presente nel progetto.")

        # Classi
        for classe, dati in self.classi.items():
            if not dati["giorni"]:
                errori.append(
                    f"La classe '{classe}' non ha giorni configurati."
                )

            for giorno in dati["giorni"]:
                if giorno not in dati["ore"]:
                    errori.append(
                        f"La classe '{classe}' ha il giorno '{giorno}' "
                        f"ma non il numero di ore."
                    )

        # Assegnazioni
        ore_per_classe = Counter()

        for ass in self.assegnazioni:
            classe = ass["classe"]
            docenti = ass["docenti"]
            ore = ass["ore"]

            if classe not in self.classi:
                errori.append(
                    f"Assegnazione {ass['id']}: classe '{classe}' inesistente."
                )

            if not docenti:
                errori.append(
                    f"Assegnazione {ass['id']}: nessun docente."
                )

            for docente in docenti:
                if docente not in self.docenti:
                    errori.append(
                        f"Assegnazione {ass['id']}: docente "
                        f"'{docente}' inesistente."
                    )

            if ore <= 0:
                errori.append(
                    f"Assegnazione {ass['id']}: numero ore non valido ({ore})."
                )

            ore_per_classe[classe] += max(0, ore)

        # Controllo preventivo molto utile:
        # il totale delle ore assegnate a una classe non può superare
        # il numero di slot disponibili della classe.
        for classe, ore_richieste in ore_per_classe.items():
            if classe in self.classi:
                slot = sum(
                    self.classi[classe]["ore"].get(g, 0)
                    for g in self.classi[classe]["giorni"]
                )
                if ore_richieste > slot:
                    errori.append(
                        f"Classe '{classe}': richieste {ore_richieste} ore "
                        f"ma la classe dispone soltanto di {slot} slot."
                    )

        # --------------------------------------------------------
        # ORE FISSATE
        # --------------------------------------------------------
        # Le ore fissate dall'interfaccia sono vincoli HARD. Qui
        # controlliamo preventivamente che siano compatibili con la
        # struttura della classe e che non eccedano le ore richieste
        # dall'assegnazione.

        fissati_per_slot_classe = defaultdict(list)
        fissati_per_slot_docente = defaultdict(list)

        for idx, slots in self.fissati_per_assegnazione.items():
            ass = self.assegnazioni[idx]

            if len(slots) > ass["ore"]:
                errori.append(
                    f"Assegnazione id={ass['id']} "
                    f"({ass['classe']} / {ass['materia']} / "
                    f"{ass['docente']}): fissate {len(slots)} ore "
                    f"ma ne sono richieste soltanto {ass['ore']}."
                )

            for giorno, ora in slots:
                if ass["classe"] not in self.classi:
                    continue

                dati_classe = self.classi[ass["classe"]]

                giorno_reale = None
                for g in dati_classe["giorni"]:
                    if self._giorno_equivalente(g, giorno):
                        giorno_reale = g
                        break

                if giorno_reale is None:
                    errori.append(
                        f"Ora fissata fuori dai giorni della classe "
                        f"'{ass['classe']}': {giorno} / {ora}."
                    )
                    continue

                max_ore = dati_classe["ore"].get(giorno_reale, 0)
                if ora is None or ora < 1 or ora > max_ore:
                    errori.append(
                        f"Ora fissata fuori dall'orario della classe "
                        f"'{ass['classe']}': {giorno} / {ora} "
                        f"(massimo {max_ore})."
                    )
                    continue

                fissati_per_slot_classe[
                    (ass["classe"], giorno_reale, ora)
                ].append(idx)

                for docente in ass["docenti"]:
                    fissati_per_slot_docente[
                        (docente, giorno_reale, ora)
                    ].append(idx)

        # Una classe non può avere due attività fissate nello stesso slot.
        for slot, indici in fissati_per_slot_classe.items():
            if len(indici) > 1:
                descrizione = "; ".join(
                    f"{self.assegnazioni[i]['materia']} "
                    f"({self.assegnazioni[i]['docente']})"
                    for i in indici
                )
                errori.append(
                    f"Conflitto tra ore fissate per la classe "
                    f"'{slot[0]}' il {slot[1]} ora {slot[2]}: "
                    f"{descrizione}."
                )

        # Un docente non può essere fissato contemporaneamente in due classi.
        for slot, indici in fissati_per_slot_docente.items():
            classi = {self.assegnazioni[i]["classe"] for i in indici}
            if len(classi) > 1:
                docente, giorno, ora = slot
                descrizione = "; ".join(
                    f"{self.assegnazioni[i]['classe']} / "
                    f"{self.assegnazioni[i]['materia']}"
                    for i in indici
                )
                errori.append(
                    f"Conflitto tra ore fissate per il docente "
                    f"'{docente}' il {giorno} ora {ora}: "
                    f"{descrizione}."
                )

        return errori if 'errors' in locals() else errori

    # ============================================================
    # SLOT CLASSE
    # ============================================================

    def _crea_slots_classi(self):
        slots_classe = {}

        for classe, dati in self.classi.items():
            slots = []
            for giorno in dati["giorni"]:
                num_ore = dati["ore"].get(giorno, 0)
                for ora in range(1, num_ore + 1):
                    slots.append((giorno, ora))
            slots_classe[classe] = slots

        return slots_classe

    # ============================================================
    # VINCOLI DOCENTE - PRE-CALCOLO
    # ============================================================

    def _vincoli_docente_normalizzati(self, docente):
        dati = self.docenti[docente]
        vincoli = dati.get("vincoli") or {}

        giorni_liberi_raw = vincoli.get("giorni_liberi", [])
        giorni_liberi = self._parse_json(giorni_liberi_raw, [])
        if isinstance(giorni_liberi, str):
            giorni_liberi = [giorni_liberi]

        disponibili = self._dict_giorno_ore(
            vincoli.get("disponibili") or vincoli.get("disponibilita")
        )

        non_disponibili = self._dict_giorno_ore(
            vincoli.get("non_disponibili")
        )

        indesiderate = self._dict_giorno_ore(
            vincoli.get("indesiderate")
        )

        return {
            "giorni_liberi": giorni_liberi
            if isinstance(giorni_liberi, (list, tuple, set))
            else [],
            "disponibili": disponibili,
            "non_disponibili": non_disponibili,
            "indesiderate": indesiderate,
        }

    def _docente_disponibile(self, docente, giorno, ora, vincoli=None):
        if vincoli is None:
            vincoli = self._vincoli_docente_normalizzati(docente)

        giorno_norm = self._norm(giorno)

        # Giorni liberi
        for giorno_libero in vincoli["giorni_liberi"]:
            if self._giorno_equivalente(giorno, giorno_libero):
                return False

        # Disponibilità esplicita: se presente, è una whitelist.
        disponibili = vincoli["disponibili"]
        if disponibili:
            ore_concesse = []
            trovato = False

            for g, ore in disponibili.items():
                if self._giorno_equivalente(g, giorno_norm):
                    trovato = True
                    ore_concesse = ore
                    break

            if not trovato or int(ora) not in ore_concesse:
                return False

        # Indisponibilità esplicita.
        non_disponibili = vincoli["non_disponibili"]
        for g, ore in non_disponibili.items():
            if self._giorno_equivalente(g, giorno_norm):
                if int(ora) in ore:
                    return False

        return True

    def _ore_indesiderate(self, docente, giorno, vincoli=None):
        if vincoli is None:
            vincoli = self._vincoli_docente_normalizzati(docente)

        for g, ore in vincoli["indesiderate"].items():
            if self._giorno_equivalente(g, giorno):
                return set(ore)

        return set()

    # ============================================================
    # VARIABILI ASSEGNAZIONI
    # ============================================================

    def _crea_variabili_assegnazioni(self, slots_classe):
        """
        Crea una variabile booleana per ogni assegnazione/slot.

        IMPORTANTE:
        non eliminiamo più a monte gli slot incompatibili con la
        disponibilità del docente. Li manteniamo nel modello e imponiamo
        x = 0 come vincolo hard.

        Questo è indispensabile per i LUCChetti:
        se l'interfaccia fissa A in X il mercoledì alla 1ª ora, quella
        variabile deve esistere per poter imporre x = 1. Se contemporaneamente
        A è indisponibile in quell'ora, il modello diventa correttamente
        infeasible invece di ignorare il lucchetto.
        """
        self.x = {}
        self.assegnazione_vars = []

        for idx, ass in enumerate(self.assegnazioni):
            classe = ass["classe"]
            docenti = ass["docenti"]
            ore_tot = ass["ore"]

            if classe not in slots_classe:
                continue

            vincoli_doc = {
                docente: self._vincoli_docente_normalizzati(docente)
                for docente in docenti
            }

            tutti_slots = list(slots_classe[classe])
            fissati = self.fissati_per_assegnazione.get(idx, set())

            # Un'assegnazione non può avere più ore fissate di quelle richieste.
            if len(fissati) > ore_tot:
                self.diagnostica.append(
                    {
                        "classe": classe,
                        "materia": ass["materia"],
                        "docente": ass["docente"],
                        "giorno": "",
                        "ora": 0,
                        "motivo": (
                            f"Fissate {len(fissati)} ore, ma "
                            f"l'assegnazione ne richiede {ore_tot}."
                        ),
                    }
                )
                continue

            vars_ass = []

            for giorno, ora in tutti_slots:
                nome = (
                    f"x_{idx}_{self._norm(classe)}_"
                    f"{self._norm(giorno)}_{ora}"
                )
                var = self.model.NewBoolVar(nome)
                key = (classe, giorno, ora, idx)
                self.x[key] = var
                vars_ass.append(var)

                # Disponibilità del docente = VINCOLO HARD.
                # Se il docente non è disponibile, x deve essere 0.
                compatibile = all(
                    self._docente_disponibile(
                        docente,
                        giorno,
                        ora,
                        vincoli_doc[docente],
                    )
                    for docente in docenti
                )

                if not compatibile:
                    self.model.Add(var == 0)

            # Esattamente N ore per assegnazione.
            self.model.Add(sum(vars_ass) == ore_tot)

            # ========================================================
            # LUCChetti dell'interfaccia = VINCOLI HARD ASSOLUTI
            # ========================================================
            for giorno_fissato, ora_fissata in fissati:
                var_fissata = None

                for giorno_reale, ora_reale in tutti_slots:
                    if (
                        self._giorno_equivalente(
                            giorno_reale, giorno_fissato
                        )
                        and ora_reale == ora_fissata
                    ):
                        var_fissata = self.x[
                            (classe, giorno_reale, ora_reale, idx)
                        ]
                        break

                if var_fissata is None:
                    self.diagnostica.append(
                        {
                            "classe": classe,
                            "materia": ass["materia"],
                            "docente": ass["docente"],
                            "giorno": giorno_fissato,
                            "ora": ora_fissata,
                            "motivo": (
                                "Lucchetto non presente tra gli slot "
                                "della classe."
                            ),
                        }
                    )
                else:
                    self.model.Add(var_fissata == 1)

            self.assegnazione_vars.append(
                {
                    "idx": idx,
                    "assegnazione": ass,
                    "vars": vars_ass,
                }
            )

    # ============================================================
    # VINCOLI CLASSE
    # ============================================================

    def _aggiungi_vincoli_classi(self, slots_classe):
        for classe, slots in slots_classe.items():
            for giorno, ora in slots:
                variabili = []

                for idx in self.assegnazioni_per_classe.get(classe, []):
                    key = (classe, giorno, ora, idx)
                    var = self.x.get(key)
                    if var is not None:
                        variabili.append(var)

                if variabili:
                    self.model.Add(sum(variabili) <= 1)

    # ============================================================
    # BLOCCHI
    # ============================================================

    def _aggiungi_preferenza_blocchi(self, ass_info):
        
        idx = ass_info["idx"]
        ass = self.assegnazioni[idx]
        classe = ass["classe"]
        ore_tot = ass["ore"]

        pattern = self._parse_blocchi(
            ass.get("preferenza_blocchi"),
            ore_tot,
        )

        if not pattern:
            return

        target = Counter(pattern)
        dati_classe = self.classi[classe]

        for giorno in dati_classe["giorni"]:
            num_ore = dati_classe["ore"].get(giorno, 0)
            if num_ore <= 0:
                continue

            presenti = []
            for ora in range(1, num_ore + 1):
                presenti.append(
                    self.x.get(
                        (classe, giorno, ora, idx),
                        self.model.NewConstant(0),
                    )
                )

            # Start del blocco.
            starts = []
            for pos, current in enumerate(presenti):
                start = self.model.NewBoolVar(
                    f"blk_start_{idx}_{self._norm(giorno)}_{pos+1}"
                )

                if pos == 0:
                    self.model.Add(start == current)
                else:
                    previous = presenti[pos - 1]
                    self.model.Add(start <= current)
                    self.model.Add(start <= 1 - previous)
                    self.model.Add(start >= current - previous)

                starts.append(start)

            total_starts = self.model.NewIntVar(
                0, num_ore, f"blk_total_{idx}_{self._norm(giorno)}"
            )
            self.model.Add(total_starts == sum(starts))

            ore_giorno = self.model.NewIntVar(
                0, num_ore, f"blk_hours_{idx}_{self._norm(giorno)}"
            )
            self.model.Add(ore_giorno == sum(presenti))

            active = self.model.NewBoolVar(
                f"blk_active_{idx}_{self._norm(giorno)}"
            )
            self.model.Add(ore_giorno >= 1).OnlyEnforceIf(active)
            self.model.Add(ore_giorno == 0).OnlyEnforceIf(active.Not())

            numero_blocchi_target = len(pattern)
            errore_num_blocchi = self.model.NewIntVar(
                0, num_ore + numero_blocchi_target,
                f"blk_count_error_{idx}_{self._norm(giorno)}"
            )
            self.model.AddAbsEquality(
                errore_num_blocchi,
                total_starts - (
                    numero_blocchi_target * active
                ),
            )
            self.penalita.append(
                errore_num_blocchi * self.pesi["blocco"]
            )

            for lunghezza in sorted(target):
                desiderati = target[lunghezza]
                candidati = []

                for start_pos in range(
                    0, num_ore - lunghezza + 1
                ):
                    fine = start_pos + lunghezza
                    start = starts[start_pos]

                    segmento = presenti[start_pos:fine]
                    candidato = self.model.NewBoolVar(
                        f"blk_{idx}_{self._norm(giorno)}_"
                        f"{start_pos+1}_len{lunghezza}"
                    )

                    self.model.Add(candidato <= start)

                    for v in segmento:
                        self.model.Add(candidato <= v)

                    self.model.Add(
                        candidato >= start + sum(segmento) - lunghezza
                    )

                    if fine < num_ore:
                        self.model.Add(
                            candidato <= 1 - presenti[fine]
                        )

                    candidati.append(candidato)

                if not candidati:
                    continue

                conteggio = self.model.NewIntVar(
                    0, len(candidati),
                    f"blk_count_{idx}_{self._norm(giorno)}_len{lunghezza}"
                )
                self.model.Add(conteggio == sum(candidati))

                errore = self.model.NewIntVar(
                    0, len(candidati) + desiderati,
                    f"blk_error_{idx}_{self._norm(giorno)}_len{lunghezza}"
                )
                self.model.AddAbsEquality(
                    errore,
                    conteggio - desiderati * active,
                )
                self.penalita.append(
                    errore * self.pesi["blocco"]
                )

    def _aggiungi_tutte_preferenze_blocchi(self):
        for ass_info in self.assegnazione_vars:
            ass = self.assegnazioni[ass_info["idx"]]
            if ass.get("preferenza_blocchi"):
                self._aggiungi_preferenza_blocchi(ass_info)

    # ============================================================
    # VINCOLI DOCENTI
    # ============================================================

    def _aggiungi_vincoli_docenti(self, slots_classe):
        giorni_scuola = sorted(
            {
                str(g).strip()
                for dati in self.classi.values()
                for g in dati["giorni"]
            }
        )

        max_ore_classe = 0
        for dati in self.classi.values():
            for ore in dati["ore"].values():
                max_ore_classe = max(max_ore_classe, int(ore))

        if max_ore_classe <= 0:
            return

        for docente, dati_doc in self.docenti.items():
            vincoli = self._vincoli_docente_normalizzati(docente)

            min_ore = self._safe_int(
                dati_doc.get("vincoli", {}).get("min_ore_giorno"),
                2,
            )
            max_ore_giorno = self._safe_int(
                dati_doc.get("vincoli", {}).get("max_ore_giorno"),
                max_ore_classe,
            )

            min_ore = max(0, min_ore)
            max_ore_giorno = max(0, max_ore_giorno)

            assegnazioni_doc = self.assegnazioni_per_docente.get(
                docente, []
            )

            for giorno in giorni_scuola:
                ore_massime_giorno = max_ore_classe
                lavoro_ora = {}

                for ora in range(1, ore_massime_giorno + 1):
                    vars_ora = []

                    for idx in assegnazioni_doc:
                        ass = self.assegnazioni[idx]
                        classe = ass["classe"]
                        key = (classe, giorno, ora, idx)

                        var = self.x.get(key)
                        if var is not None:
                            vars_ora.append(var)

                    lavora = self.model.NewBoolVar(
                        f"lavora_{self._norm(docente)}_"
                        f"{self._norm(giorno)}_{ora}"
                    )

                    if vars_ora:
                        self.model.Add(sum(vars_ora) <= 1)
                        self.model.Add(sum(vars_ora) == lavora)
                    else:
                        self.model.Add(lavora == 0)

                    lavoro_ora[ora] = lavora
                    self.lavora_docente_ora[
                        (docente, giorno, ora)
                    ] = lavora

                    if ora in self._ore_indesiderate(
                        docente, giorno, vincoli
                    ):
                        self.penalita.append(
                            lavora * self.pesi["ora_indesiderata"]
                        )

                totale_giorno = self.model.NewIntVar(
                    0,
                    ore_massime_giorno,
                    f"totale_{self._norm(docente)}_"
                    f"{self._norm(giorno)}",
                )
                self.model.Add(
                    totale_giorno == sum(lavoro_ora.values())
                )

                lavora_giorno = self.model.NewBoolVar(
                    f"giorno_attivo_{self._norm(docente)}_"
                    f"{self._norm(giorno)}"
                )
                self.model.Add(totale_giorno >= 1).OnlyEnforceIf(
                    lavora_giorno
                )
                self.model.Add(totale_giorno == 0).OnlyEnforceIf(
                    lavora_giorno.Not()
                )

                sotto_min = self.model.NewBoolVar(
                    f"sotto_min_{self._norm(docente)}_"
                    f"{self._norm(giorno)}"
                )

                if min_ore > 0:
                    self.model.Add(
                        totale_giorno < min_ore
                    ).OnlyEnforceIf([lavora_giorno, sotto_min])
                    self.model.Add(
                        totale_giorno >= min_ore
                    ).OnlyEnforceIf(
                        [lavora_giorno, sotto_min.Not()]
                    )
                else:
                    self.model.Add(sotto_min == 0)

                self.model.Add(sotto_min == 0).OnlyEnforceIf(
                    lavora_giorno.Not()
                )

                if self.min_ore_giorno_hard:
                    self.model.Add(sotto_min == 0)
                else:
                    self.penalita.append(
                        sotto_min * self.pesi["sotto_minimo"]
                    )

                sopra_max = self.model.NewBoolVar(
                    f"sopra_max_{self._norm(docente)}_"
                    f"{self._norm(giorno)}"
                )

                self.model.Add(
                    totale_giorno > max_ore_giorno
                ).OnlyEnforceIf(sopra_max)
                self.model.Add(
                    totale_giorno <= max_ore_giorno
                ).OnlyEnforceIf(sopra_max.Not())

                if self.max_ore_giorno_hard:
                    self.model.Add(sopra_max == 0)
                else:
                    self.penalita.append(
                        sopra_max * self.pesi["sopra_massimo"]
                    )

                prefix = {0: self.model.NewConstant(0)}
                for ora in range(1, ore_massime_giorno + 1):
                    p = self.model.NewBoolVar(
                        f"prefix_{self._norm(docente)}_"
                        f"{self._norm(giorno)}_{ora}"
                    )
                    self.model.AddMaxEquality(
                        p,
                        [prefix[ora - 1], lavoro_ora[ora]],
                    )
                    prefix[ora] = p

                suffix = {
                    ore_massime_giorno + 1: self.model.NewConstant(0)
                }
                for ora in range(
                    ore_massime_giorno, 0, -1
                ):
                    s = self.model.NewBoolVar(
                        f"suffix_{self._norm(docente)}_"
                        f"{self._norm(giorno)}_{ora}"
                    )
                    self.model.AddMaxEquality(
                        s,
                        [suffix[ora + 1], lavoro_ora[ora]],
                    )
                    suffix[ora] = s

                for ora in range(1, ore_massime_giorno + 1):
                    buca = self.model.NewBoolVar(
                        f"buca_{self._norm(docente)}_"
                        f"{self._norm(giorno)}_{ora}"
                    )

                    if ora == 1 or ora == ore_massime_giorno:
                        self.model.Add(buca == 0)
                        continue

                    self.model.Add(buca <= prefix[ora - 1])
                    self.model.Add(buca <= 1 - lavoro_ora[ora])
                    self.model.Add(buca <= suffix[ora + 1])
                    self.model.Add(
                        buca >=
                        prefix[ora - 1]
                        - lavoro_ora[ora]
                        + suffix[ora + 1]
                        - 1
                    )

                    self.penalita.append(
                        buca * self.pesi["buca"]
                    )

                self.penalita.append(
                    lavora_giorno * self.pesi["giorno_lavorativo"]
                )

    # ============================================================
    # COSTRUZIONE MODELLO
    # ============================================================

    def _costruisci_modello(self):
        self.model = cp_model.CpModel()
        self.penalita = []
        self.diagnostica = []
        self.lavora_docente_ora = {}

        slots_classe = self._crea_slots_classi()

        self._crea_variabili_assegnazioni(slots_classe)

        if self.diagnostica:
            return False

        self._aggiungi_vincoli_classi(slots_classe)
        self._aggiungi_vincoli_docenti(slots_classe)
        self._aggiungi_tutte_preferenze_blocchi()

        if self.penalita:
            self.model.Minimize(sum(self.penalita))

        return True

    # ============================================================
    # SALVATAGGIO
    # ============================================================

    def _crea_tabelle_risultato(self, cursor):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orario_risultato (
                progetto TEXT,
                classe TEXT,
                giorno TEXT,
                ora INTEGER,
                materia TEXT,
                docente TEXT,
                generation_id TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orario_fallimenti (
                progetto TEXT,
                generation_id TEXT,
                classe TEXT,
                materia TEXT,
                docente TEXT,
                giorno TEXT,
                ora INTEGER,
                motivo TEXT
            )
            """
        )

        for tabella in ("orario_risultato", "orario_fallimenti"):
            cursor.execute(f"PRAGMA table_info({tabella})")
            colonne = {riga[1] for riga in cursor.fetchall()}

            if "generation_id" not in colonne:
                cursor.execute(
                    f"ALTER TABLE {tabella} ADD COLUMN generation_id TEXT"
                )

    def _salva_risultato(self):
        conn = sqlite3.connect(self.db_path)

        try:
            cursor = conn.cursor()
            self._crea_tabelle_risultato(cursor)

            cursor.execute(
                "DELETE FROM orario_risultato WHERE progetto = ?",
                (self.progetto,),
            )

            for key, var in self.x.items():
                if self.solver.Value(var) != 1:
                    continue

                classe, giorno, ora, idx = key
                ass = self.assegnazioni[idx]

                cursor.execute(
                    """
                    INSERT INTO orario_risultato
                    (progetto, classe, giorno, ora, materia, docente, generation_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.progetto,
                        classe,
                        giorno,
                        ora,
                        ass["materia"],
                        ass["docente"],
                        self.generation_id,
                    ),
                )

            conn.commit()

        finally:
            conn.close()

    def _salva_diagnostica(self):
        if not self.diagnostica:
            return

        conn = sqlite3.connect(self.db_path)

        try:
            cursor = conn.cursor()
            self._crea_tabelle_risultato(cursor)

            cursor.execute(
                "DELETE FROM orario_fallimenti WHERE progetto = ?",
                (self.progetto,),
            )

            for errore in self.diagnostica:
                cursor.execute(
                    """
                    INSERT INTO orario_fallimenti
                    (progetto, generation_id, classe, materia, docente,
                     giorno, ora, motivo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.progetto,
                        self.generation_id,
                        errore.get("classe", ""),
                        errore.get("materia", ""),
                        errore.get("docente", ""),
                        errore.get("giorno", ""),
                        errore.get("ora", 0),
                        errore.get("motivo", ""),
                    ),
                )

            conn.commit()

        finally:
            conn.close()

    # ============================================================
    # GENERAZIONE
    # ============================================================

    def genera(self, timeout_secondi=60):
        self.generation_id = str(uuid.uuid4())

        self._log(
            "🔄 Avvio MotoreOrario V3 "
            "CP-SAT / OR-Tools..."
        )

        try:
            self._carica_dati()
        except Exception as exc:
            return False, f"Errore caricamento database: {exc}"

        errori = self._valida_dati()

        if errori:
            self.diagnostica = [
                {"motivo": errore}
                for errore in errori
            ]
            self._salva_diagnostica()

            return (
                False,
                "Dati non validi:\n- "
                + "\n- ".join(errori),
            )

        try:
            if not self._costruisci_modello():
                self._salva_diagnostica()

                dettagli = "\n- ".join(
                    x.get("motivo", "Errore sconosciuto")
                    for x in self.diagnostica
                )

                return (
                    False,
                    "Impossibile costruire una soluzione:\n- "
                    + dettagli,
                )
        except Exception as exc:
            return False, f"Errore costruzione modello CP-SAT: {exc}"

        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = float(
            timeout_secondi
        )
        self.solver.parameters.num_search_workers = 8
        self.solver.parameters.log_search_progress = False

        self._log(
            "⚙️ Esecuzione ottimizzazione CP-SAT..."
        )

        try:
            status = self.solver.Solve(self.model)
        except Exception as exc:
            return False, f"Errore durante il solver OR-Tools: {exc}"

        if status in (
            cp_model.OPTIMAL,
            cp_model.FEASIBLE,
        ):
            self._log(
                "🎉 Soluzione trovata: "
                f"{self.solver.StatusName(status)}"
            )

            self._salva_risultato()

            valore_obiettivo = self.solver.ObjectiveValue()
            bound = self.solver.BestObjectiveBound()

            if status == cp_model.OPTIMAL:
                messaggio = (
                    "Orario generato e ottimizzato con successo "
                    "(soluzione ottima)."
                )
            else:
                messaggio = (
                    "Orario generato: soluzione ammissibile "
                    "trovata entro il tempo disponibile."
                )

            self._log(
                f"📊 Obiettivo: {valore_obiettivo:.0f} "
                f"| Best bound: {bound:.0f}"
            )

            return True, messaggio

        if status == cp_model.INFEASIBLE:
            # --- AGGIUNGI QUI LA STAMPA DELLA DIAGNOSTICA ---
            print("\n🚨 --- DIAGNOSTICA FALLIMENTI (INFEASIBLE) ---")
            if self.diagnostica:
                for item in self.diagnostica:
                    print(f"❌ Classe: {item.get('classe')} | Materia: {item.get('materia')} | Docente: {item.get('docente')} -> Motivo: {item.get('motivo')}")
            else:
                print("Nessun errore esplicito registrato nella lista diagnostica. Il conflitto è nei vincoli globali o in un lucchetto incrociato.")
            print("-----------------------------------------------\n")
            # -----------------------------------------------
            return (
                False,
                "Il solver ha dimostrato che i vincoli HARD "
                "sono incompatibili. Controllare disponibilità, "
                "giorni liberi, monte ore e assegnazioni.",
            )

        if status == cp_model.MODEL_INVALID:
            return (
                False,
                "Il modello CP-SAT non è valido. "
                "Controllare i dati e i vincoli configurati.",
            )

        return (
            False,
            "Il solver non ha trovato una soluzione entro il "
            f"tempo disponibile ({timeout_secondi} secondi).",
        )