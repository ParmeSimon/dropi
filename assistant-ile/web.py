"""Se renseigner sur internet : l'IA locale ne connaît que ce qu'elle a appris avant sa sortie.

Pour une question sur un sujet récent ou inconnu (un jeu, un film, une actu…), l'assistant cherche
sur DuckDuckGo et Wikipédia (sans compte ni clé), lit le début du meilleur résultat, puis répond.
Seule ta question part sur internet, rien d'autre.
"""
import re
import json
import html
import urllib.parse
import urllib.request
from html.parser import HTMLParser

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AssistantIsland/1.0"
DELAI = 8


def _telecharger(url, donnees=None):
    requete = urllib.request.Request(url, data=donnees, headers={"User-Agent": AGENT, "Accept-Language": "fr,en;q=0.8"})
    with urllib.request.urlopen(requete, timeout=DELAI) as r:
        return r.read(600_000).decode(r.headers.get_content_charset() or "utf-8", errors="ignore")


def _propre(texte):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", texte)).split())


def duckduckgo(question, n=5):
    page = _telecharger("https://html.duckduckgo.com/html/",
                        urllib.parse.urlencode({"q": question, "kl": "fr-fr"}).encode())
    resultats = []
    for bloc in page.split('result__body')[1:]:
        titre = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', bloc, re.S)
        extrait = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', bloc, re.S)
        if not titre:
            continue
        url = titre.group(1)
        if "uddg=" in url:
            url = urllib.parse.unquote(re.search(r"uddg=([^&]+)", url).group(1))
        if "duckduckgo.com/y.js" in url:          # publicité
            continue
        resultats.append({"titre": _propre(titre.group(2)), "url": url,
                          "extrait": _propre(extrait.group(1)) if extrait else ""})
        if len(resultats) >= n:
            break
    return resultats


def wikipedia(question):
    """Le résumé de l'article Wikipédia le plus proche (français, sinon anglais)."""
    for langue in ("fr", "en"):
        base = f"https://{langue}.wikipedia.org"
        r = json.loads(_telecharger(f"{base}/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": question, "format": "json", "srlimit": 1})))
        trouves = r.get("query", {}).get("search", [])
        if not trouves:
            continue
        titre = trouves[0]["title"]
        mots_titre = {m.lower() for m in re.findall(r"\w{3,}", titre)}
        if not mots_titre & {m.lower() for m in re.findall(r"\w{3,}", question)}:
            continue                                # article hors sujet
        resume = json.loads(_telecharger(f"{base}/api/rest_v1/page/summary/" + urllib.parse.quote(titre)))
        if resume.get("extract"):
            return {"titre": titre, "texte": resume["extract"], "url": f"{base}/wiki/" + urllib.parse.quote(titre)}
    return None


class _Paragraphes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.textes, self._dans, self._ignore = [], False, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "header", "footer"):
            self._ignore += 1
        elif tag in ("p", "li", "h1", "h2"):
            self._dans = True
            self.textes.append("")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "header", "footer"):
            self._ignore = max(0, self._ignore - 1)
        elif tag in ("p", "li", "h1", "h2"):
            self._dans = False

    def handle_data(self, data):
        if self._dans and not self._ignore and self.textes:
            self.textes[-1] += data


def texte_de_la_page(url, limite=1800):
    lecteur = _Paragraphes()
    lecteur.feed(_telecharger(url))
    morceaux = [" ".join(t.split()) for t in lecteur.textes]
    return " ".join(m for m in morceaux if len(m) > 60)[:limite]


def se_renseigner(question):
    """Ce que l'IA reçoit : résultats de recherche + résumé Wikipédia + début de la meilleure page."""
    parties, sources = [], []
    try:
        resultats = duckduckgo(question)
    except OSError:
        resultats = []
    try:
        wiki = wikipedia(question)
    except (OSError, ValueError):
        wiki = None
    if wiki:
        parties.append(f"Wikipédia – {wiki['titre']} : {wiki['texte']}")
        sources.append(wiki["url"])
    for r in resultats:
        parties.append(f"- {r['titre']} : {r['extrait']}")
        sources.append(r["url"])
    for r in resultats[:2]:
        if "wikipedia.org" in r["url"]:
            continue
        try:
            texte = texte_de_la_page(r["url"])
        except (OSError, ValueError):
            continue
        if texte:
            parties.append(f"Extrait de {r['titre']} : {texte}")
            break
    if not parties:
        return "Pas de connexion internet ou aucun résultat : je ne peux pas me renseigner."
    return ("Résultats trouvés sur internet :\n" + "\n".join(parties))[:4500] + \
        "\nSources : " + ", ".join(sources[:4])
