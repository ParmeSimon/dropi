// Le fond de l'extension : relaie ce que page.js a vu vers l'assistant du PC (hote.py), et rien d'autre.
const HOTE = "fr.dropi.assistant";

// Connexions en deux étapes (identifiant, puis mot de passe sur une autre page) :
// on garde l'identifiant de l'étape 1 le temps de la session, par onglet.
const cle = (onglet) => "identifiant_" + onglet;

chrome.runtime.onMessage.addListener((message, expediteur, repondre) => {
  if (expediteur.id !== chrome.runtime.id || !expediteur.tab) return;
  const onglet = expediteur.tab.id;

  if (message.type === "identifiant") {
    chrome.storage.session.set({ [cle(onglet)]: String(message.valeur || "") });
    return;
  }
  if (message.type !== "connexion") return;

  (async () => {
    let login = String(message.login || "");
    if (!login) login = (await chrome.storage.session.get(cle(onglet)))[cle(onglet)] || "";
    try {
      // l'adresse vient du navigateur (celle de l'onglet), pas de la page : elle ne peut pas mentir
      repondre(await chrome.runtime.sendNativeMessage(HOTE, {
        type: "connexion", url: expediteur.tab.url, login, mdp: String(message.mdp || ""),
      }));
    } catch (erreur) {
      repondre({ ok: false, erreur: String(erreur && erreur.message || erreur) });
    }
  })();
  return true;      // la réponse arrive plus tard
});

chrome.tabs.onRemoved.addListener((onglet) => chrome.storage.session.remove(cle(onglet)));
