"""Le cerveau : discute avec le modèle local et exécute les outils qu'il demande."""
import json
import re
import threading
import time

import moteur
import themes
import tools
import memoire
import classement

SYSTEME = """Tu es Dropi, l'assistant personnel de l'utilisateur, intégré à son PC Windows sous forme de "Dynamic Island".
- Réponds toujours en français et tutoie l'utilisateur.
- Dès qu'une action est demandée, utilise les outils au lieu d'expliquer comment faire,
  puis confirme en quelques mots seulement (ex : « Rangé dans Factures. », « Discord est lancé. »).
- Ne fais de vraies phrases que si l'utilisateur te pose une question (2 à 4 phrases maximum).
- Quand on te donne des fichiers avec une consigne, applique la consigne à chacun (chemins complets fournis).
- Le rangement est méthodique : ranger_fichier met chaque fichier dans le dossier de son TYPE
  (PDF, Word, Bloc-notes, Images…) puis de sa SOURCE (le site ou l'appli d'où il vient, ex : PDF › Gmail).
  Il choisit le dossier tout seul : n'invente pas de catégorie. Pour le Bureau ou un dossier entier : ranger_dossier.
- Tu gardes la trace de tout ce que tu déplaces. Si un fichier n'est plus à son ancien chemin, c'est sûrement
  toi qui l'as rangé : utilise son nouveau chemin (liste jointe à la demande) ou chercher_fichier.
- Si un outil répond qu'une application, un jeu ou un fichier est introuvable, ou renvoie une erreur,
  dis-le simplement. Ne lance jamais autre chose à la place, et ne dis jamais qu'une action est faite
  si l'outil ne l'a pas confirmée.
- Ne supprime un fichier que si l'utilisateur le demande clairement.
- Pour faire de la place sur le disque, utilise analyser_espace : l'interface affiche une carte où
  l'utilisateur choisit quoi supprimer. Ne supprime jamais rien toi-même pour faire de la place.
- Quand tu utilises lister_jeux, l'interface affiche déjà les jeux avec leurs jaquettes :
  ne recopie pas la liste, réponds juste une phrase courte (ex : « Voilà tes jeux ! »).
- Si on te pose une question sur un sujet que tu ne connais pas bien ou récent (jeu, film, produit,
  actualité, personne, logiciel), utilise se_renseigner AVANT de répondre, puis réponds avec ce que tu as trouvé.
  Ne réponds jamais « je ne sais pas » sans avoir cherché.
- Quand l'utilisateur te donne une préférence, une info sur lui ou te corrige, utilise memoriser.
- Tes souvenirs (joints à la demande, entre crochets) viennent de vos échanges passés : sers-t'en, ils sont fiables.
- Pour les mails, fais un résumé clair : qui, quoi, et ce qui semble important ou urgent.
- Tu sais jouer avec l'utilisateur (morpion, puissance 4, chifoumi, mémoire, devine le nombre, réflexe). S'il s'ennuie ou veut jouer,
  propose-lui de dire « on joue ? » (ça ouvre les jeux).
- Les dossiers de l'utilisateur : ~/Desktop (Bureau), ~/Downloads (Téléchargements), ~/Documents, ~/Pictures, ~/Videos."""


# Les outils qui font quelque chose et le disent en une phrase : leur résultat sert de réponse tel quel.
# (Les autres rapportent de l'information que le modèle doit lire avant de répondre.)
ACTIONS = {"ouvrir_stream_twitch", "ouvrir_site", "recherche_web", "lancer_jeu", "ouvrir_application",
           "ranger_fichier", "supprimer_fichier", "deplacer_fichier", "renommer_fichier", "afficher_dans_explorateur",
           "ranger_telechargements", "ranger_dossier", "ouvrir_fichier", "memoriser", "controler_musique",
           "annuler_rangement", "regler_pc", "creer_rappel", "supprimer_rappels"}


RESUME_MAX = 12000              # caractères lus pour un résumé (la mémoire du modèle : ~6000 mots)


class Arrete(Exception):
    """La demande en cours a été arrêtée par l'utilisateur (Cerveau.arreter)."""


class Cerveau:
    def __init__(self, config, sur_etat=None):
        self.moteur = moteur.Moteur(config, sur_etat)
        self.reflexion = config.get("reflexion")                  # None : le modèle décide
        self.historique = []
        self._arret = False
        self._connexion = None
        self._cle_base = None

    def arreter(self):
        """Coupe la demande en cours : on ferme la connexion, le moteur arrête aussitôt de calculer."""
        self._arret = True
        try:
            self._connexion.close()
        except Exception:
            pass

    def demander(self, texte, sur_action=None, sur_resultat=None, sur_texte=None):
        avant = list(self.historique)
        self._arret = False
        try:
            return self._demander(texte, sur_action, sur_resultat, sur_texte)
        except Exception:
            if not self._arret:
                raise
            self.historique = avant          # une demande arrêtée ne laisse pas de trace dans la conversation
            raise Arrete() from None

    def _messages(self, demande, contexte):
        """Ce qu'on envoie au modèle. Les consignes et les outils sont identiques d'une demande à l'autre :
        le modèle garde en mémoire ce début déjà lu et ne relit que la suite (sur un PC sans carte graphique,
        les relire prend des minutes). Ce qui change (souvenirs, derniers rangements) est donc joint à la
        demande en cours, pas aux consignes."""
        messages = [{"role": "system", "content": SYSTEME + tools.contexte_applis()}]
        for m in self.historique:
            if m is demande and contexte:
                m = {"role": "user", "content": f"{m['content']}\n\n[Pour t'aider à répondre, ne le répète pas]\n{contexte}"}
            messages.append(m)
        return messages

    def prechauffer(self):
        """Au lancement : charge le modèle et lui fait lire ses consignes une fois pour toutes (ou recharge cette
        lecture sauvegardée sur disque), pour que la première vraie demande n'ait pas à attendre."""
        try:
            systeme = SYSTEME + tools.contexte_applis()
            self._cle_base = systeme + json.dumps(tools.schemas(), sort_keys=True)
            restaure = self.moteur.restaurer_cache(self._cle_base)
            self._generer([{"role": "system", "content": systeme}, {"role": "user", "content": "Bonjour"}],
                          None, max_tokens=1)
            if not restaure:
                self.moteur.sauver_cache()
        except Exception:
            pass                         # moteur pas prêt, ou demande arrêtée : tant pis, ce n'était qu'une avance

    def _demander(self, texte, sur_action, sur_resultat, sur_texte=None):
        demande = {"role": "user", "content": texte}
        self.historique.append(demande)
        self.historique = self.historique[-30:]
        while self.historique and self.historique[0]["role"] != "user":      # jamais un résultat d'outil sans son appel
            self.historique.pop(0)
        contexte = (memoire.contexte(texte) + classement.contexte()).strip()
        une_seule_chose = not texte.startswith("Fichiers :") and not re.search(r"[,;]| (?:et|puis|ensuite|après) ", texte.lower())
        renseigne = False
        for _ in range(8):  # jusqu'à 8 allers-retours outils par demande
            if self._arret:
                raise Arrete()
            msg = self._generer(self._messages(demande, contexte), sur_texte)
            self.historique.append(msg)

            if not msg.get("tool_calls"):
                reponse = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip() or "C'est fait."
                if renseigne:          # ce qu'il a trouvé sur internet, il le retient pour la prochaine fois
                    memoire.retenir(f"{texte[:200]} → {reponse}", genre="appris")
                return reponse

            resultats = []
            for appel in msg["tool_calls"]:
                nom = appel["function"]["name"]
                try:
                    args = dict(json.loads(appel["function"]["arguments"] or "{}"))
                except ValueError:
                    args = {}
                if sur_action:
                    sur_action(nom, args)
                memoire.noter_usage(nom, args)
                renseigne = renseigne or nom == "se_renseigner"
                fonction = tools.FONCTIONS.get(nom)
                try:
                    resultat = fonction(**args) if fonction else f"Outil inconnu : {nom}"
                except Exception as e:
                    resultat = f"Erreur : {e}"
                if sur_resultat:
                    sur_resultat(nom, args, str(resultat))
                self.historique.append({"role": "tool", "tool_call_id": appel["id"], "content": str(resultat)})
                resultats.append((nom, str(resultat)))

            # Une simple action (« ouvre… », « range… ») : le résultat de l'outil EST la réponse.
            # On ne redemande pas au modèle de le reformuler : une génération de moins, deux fois plus rapide.
            if une_seule_chose and all(nom in ACTIONS for nom, _ in resultats):
                reponse = " ".join(dict.fromkeys(r for _, r in resultats))
                self.historique.append({"role": "assistant", "content": reponse})
                return reponse

        return "J'ai fait le maximum, dis-moi si quelque chose manque."

    def _generer(self, messages, sur_texte, max_tokens=None, outils=True, penser=None):
        """Une réponse du modèle, reçue au fil de l'eau : sur_texte(texte déjà écrit) permet de l'afficher en direct."""
        corps = {"messages": messages, "stream": True, "temperature": 0.7, "top_p": 0.8, "top_k": 20}
        if outils:
            corps["tools"] = tools.schemas()
        if max_tokens:
            corps["max_tokens"] = max_tokens
        penser = self.reflexion if penser is None else penser
        if penser is not None:
            corps["chat_template_kwargs"] = {"enable_thinking": bool(penser)}
        contenu, appels, dernier, connexion = "", {}, 0.0, None
        self.moteur.en_cours(True)
        try:
            connexion = self._connexion = self.moteur.connexion()
            connexion.request("POST", "/v1/chat/completions", json.dumps(corps), {"Content-Type": "application/json"})
            reponse = connexion.getresponse()
            if reponse.status != 200:
                raise RuntimeError(f"moteur IA : erreur {reponse.status} {reponse.read()[:200].decode('utf-8', 'replace')}")
            for ligne in reponse:
                if self._arret:
                    raise Arrete()
                ligne = ligne.strip()
                if not ligne.startswith(b"data:") or ligne.endswith(b"[DONE]"):
                    continue
                choix = json.loads(ligne[5:]).get("choices") or [{}]
                delta = choix[0].get("delta") or {}
                contenu += delta.get("content") or ""
                for appel in delta.get("tool_calls") or []:
                    a = appels.setdefault(appel.get("index", 0), {"id": "", "type": "function",
                                                                  "function": {"name": "", "arguments": ""}})
                    a["id"] = appel.get("id") or a["id"]
                    a["function"]["name"] += (appel.get("function") or {}).get("name") or ""
                    a["function"]["arguments"] += (appel.get("function") or {}).get("arguments") or ""
                if sur_texte and not appels and time.monotonic() - dernier > 0.12:
                    visible = re.sub(r"<think>.*?(</think>|$)", "", contenu, flags=re.S).strip()
                    if visible:
                        dernier = time.monotonic()
                        sur_texte(visible)
        finally:
            self._connexion = None
            if connexion is not None:
                connexion.close()
            self.moteur.en_cours(False)
        message = {"role": "assistant", "content": contenu}
        if appels:
            message["tool_calls"] = [dict(a, id=a["id"] or f"appel_{i}") for i, a in sorted(appels.items())]
        return message

    def resumer(self, chemin, sur_texte=None):
        """Résume un document (PDF, Word, texte) lu en local. Sans outils ni historique : la demande est courte,
        puis on remet en place la lecture des consignes (le moteur n'a qu'une mémoire de travail)."""
        nom = chemin.replace("\\", "/").rsplit("/", 1)[-1]
        texte, lu = tools.texte_document(chemin, RESUME_MAX)
        self._arret = False
        messages = [
            {"role": "system", "content": "Tu résumes des documents, en français. Commence par une phrase qui dit de quoi "
             "il s'agit, puis 3 à 6 puces avec ce qui compte (chiffres, dates, décisions, actions à faire). "
             "Pas d'introduction ni de conclusion, rien d'inventé."},
            {"role": "user", "content": f"Document « {nom} » :\n\n{texte}"}]
        try:
            reponse = self._generer(messages, sur_texte, outils=False, penser=False)["content"]
            reponse = re.sub(r"<think>.*?</think>", "", reponse, flags=re.S).strip() or "Je n'ai rien à en dire."
        except Exception:
            if not self._arret:
                raise
            raise Arrete() from None
        finally:
            if self._cle_base:
                threading.Thread(target=self.moteur.restaurer_cache, args=(self._cle_base,), daemon=True).start()
        if lu:
            reponse += f"\n\n({lu})"
        self.noter(f"Résume le document {chemin}", reponse)
        return reponse

    def classer_document(self, nom, extrait, categories):
        """Dans quelle catégorie ranger ce document ? Renvoie « 01 Études/Cours » (ou None). Une sortie contrainte :
        le modèle ne peut répondre que par l'une des catégories. Appelé en tâche de fond par classement.py."""
        while self.moteur._occupe:                       # quelqu'un discute avec Dropi : on lui laisse le moteur
            time.sleep(2)
        corps = {
            "messages": [
                {"role": "system", "content": "Tu ranges des documents personnels dans la catégorie qui leur correspond le mieux."},
                {"role": "user", "content": f"Catégories (avec ce qu'on y range) :\n{themes.legende()}\n\n"
                 f"Nom du fichier : {nom}\n\nDébut du contenu :\n{extrait[:1800]}\n\n"
                 "Dans quelle catégorie ranger ce document ? Choisis « 99 À trier » s'il n'a pas de sens ou si aucune catégorie ne convient vraiment."}],
            "temperature": 0.1, "max_tokens": 60, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "classement", "strict": True, "schema": {
                "type": "object", "properties": {
                    "categorie": {"type": "string", "enum": list(categories)},
                    "confiance": {"type": "string", "enum": ["sûr", "probable", "incertain"]}},
                "required": ["categorie", "confiance"], "additionalProperties": False}}}}
        self.moteur.en_cours(True)
        try:
            connexion = self.moteur.connexion()
            connexion.request("POST", "/v1/chat/completions", json.dumps(corps), {"Content-Type": "application/json"})
            reponse = connexion.getresponse()
            donnees = json.loads(reponse.read())
            contenu = donnees["choices"][0]["message"]["content"]
            reponse_json = json.loads(contenu)
            self.dernier_classement = reponse_json                   # pour les tests et le diagnostic
            categorie = reponse_json["categorie"] if reponse_json.get("confiance") != "incertain" else None
        except Exception:
            return None
        finally:
            self.moteur.en_cours(False)
            if self._cle_base:                           # la lecture des consignes du chat est remise en place
                threading.Thread(target=self.moteur.restaurer_cache, args=(self._cle_base,), daemon=True).start()
        return categorie if categorie in categories else None

    def noter(self, demande, resultat):
        """Garde la trace d'une action faite sans l'IA, pour qu'elle puisse en reparler ensuite."""
        self.historique += [{"role": "user", "content": demande},
                            {"role": "assistant", "content": resultat}]

    def oublier(self):
        self.historique = []
