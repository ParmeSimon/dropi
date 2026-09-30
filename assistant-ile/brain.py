"""Le cerveau : discute avec le modèle local et exécute les outils qu'il demande."""
import re
import ollama

import tools
import memoire
import classement

SYSTEME = """Tu es l'assistant personnel de l'utilisateur, intégré à son PC Windows sous forme de "Dynamic Island".
- Réponds toujours en français et tutoie l'utilisateur.
- Dès qu'une action est demandée, utilise les outils au lieu d'expliquer comment faire,
  puis confirme en quelques mots seulement (ex : « Rangé dans Factures. », « Discord est lancé. »).
- Ne fais de vraies phrases que si l'utilisateur te pose une question (2 à 4 phrases maximum).
- Quand on te donne des fichiers avec une consigne, applique la consigne à chacun (chemins complets fournis).
- Le rangement est méthodique : ranger_fichier met chaque fichier dans le dossier de son TYPE
  (PDF, Word, Bloc-notes, Images…) puis de sa SOURCE (le site ou l'appli d'où il vient, ex : PDF › Gmail).
  Il choisit le dossier tout seul : n'invente pas de catégorie. Pour le Bureau ou un dossier entier : ranger_dossier.
- Tu gardes la trace de tout ce que tu déplaces. Si un fichier n'est plus à son ancien chemin, c'est sûrement
  toi qui l'as rangé : utilise son nouveau chemin (liste plus bas) ou chercher_fichier.
- Ne supprime un fichier que si l'utilisateur le demande clairement.
- Pour faire de la place sur le disque, utilise analyser_espace : l'interface affiche une carte où
  l'utilisateur choisit quoi supprimer. Ne supprime jamais rien toi-même pour faire de la place.
- Quand tu utilises lister_jeux, l'interface affiche déjà les jeux avec leurs jaquettes :
  ne recopie pas la liste, réponds juste une phrase courte (ex : « Voilà tes jeux ! »).
- Si on te pose une question sur un sujet que tu ne connais pas bien ou récent (jeu, film, produit,
  actualité, personne, logiciel), utilise se_renseigner AVANT de répondre, puis réponds avec ce que tu as trouvé.
  Ne réponds jamais « je ne sais pas » sans avoir cherché.
- Quand l'utilisateur te donne une préférence, une info sur lui ou te corrige, utilise memoriser.
- Tes souvenirs (plus bas) viennent de vos échanges passés : sers-t'en, ils sont fiables.
- Pour les mails, fais un résumé clair : qui, quoi, et ce qui semble important ou urgent.
- Les dossiers de l'utilisateur : ~/Desktop (Bureau), ~/Downloads (Téléchargements), ~/Documents, ~/Pictures, ~/Videos."""


class Cerveau:
    def __init__(self, config):
        self.client = ollama.Client(host=config.get("ollama_url", "http://localhost:11434"))
        self.modele = config.get("modele", "qwen3:8b")
        self.historique = []

    def demander(self, texte, sur_action=None, sur_resultat=None):
        self.historique.append({"role": "user", "content": texte})
        self.historique = self.historique[-30:]

        systeme = SYSTEME + memoire.contexte(texte) + classement.contexte()
        renseigne = False
        for _ in range(8):  # jusqu'à 8 allers-retours outils par demande
            rep = self.client.chat(
                model=self.modele,
                messages=[{"role": "system", "content": systeme}] + self.historique,
                tools=tools.schemas(),
            )
            msg = rep.message
            self.historique.append(msg)

            if not msg.tool_calls:
                reponse = re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.S).strip() or "C'est fait."
                if renseigne:          # ce qu'il a trouvé sur internet, il le retient pour la prochaine fois
                    memoire.retenir(f"{texte[:200]} → {reponse}", genre="appris")
                return reponse

            for appel in msg.tool_calls:
                nom = appel.function.name
                args = dict(appel.function.arguments or {})
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
                self.historique.append({"role": "tool", "content": str(resultat), "tool_name": nom})

        return "J'ai fait le maximum, dis-moi si quelque chose manque."

    def noter(self, demande, resultat):
        """Garde la trace d'une action faite sans l'IA, pour qu'elle puisse en reparler ensuite."""
        self.historique += [{"role": "user", "content": demande},
                            {"role": "assistant", "content": resultat}]

    def oublier(self):
        self.historique = []
