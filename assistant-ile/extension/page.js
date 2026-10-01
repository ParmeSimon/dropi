// Dans chaque page : au moment où tu valides un formulaire de connexion, on relève l'identifiant
// et le mot de passe et on les confie à l'assistant du PC (par fond.js). Rien n'est gardé ici.
(() => {
  const TEXTE = ["text", "email", "tel"];
  const RESSEMBLE_LOGIN = /user|login|e-?mail|identifiant|account|compte|pseudo/i;
  const BOUTON_OEIL = /show|hide|afficher|masquer|montrer|cacher|voir|visib|reveal|toggle|eye|oeil|œil/i;
  let dernier = "";

  const visible = (el) => el.getClientRects().length > 0;
  const champs = (racine, types) =>
    [...racine.querySelectorAll("input")].filter((c) => types.includes(c.type) && c.value && visible(c));

  function envoyer(message) {
    try {
      if (chrome.runtime?.id) chrome.runtime.sendMessage(message).catch(() => {});
    } catch {
      // l'extension vient d'être rechargée : cette page ne peut plus lui parler avant d'être rafraîchie
    }
  }

  // Le mot de passe saisi : sur un formulaire d'inscription ou de changement, c'est celui qui est tapé deux fois.
  function motDePasse() {
    const saisis = champs(document, ["password"]);
    const double = saisis.find((c, i) => saisis.some((autre, j) => j > i && autre.value === c.value));
    return double || saisis[0];
  }

  // L'identifiant : le champ de texte rempli juste avant le mot de passe, dans le même formulaire.
  function identifiant(mdp) {
    const avant = champs(mdp.form || document, TEXTE).filter(
      (c) => c.compareDocumentPosition(mdp) & Node.DOCUMENT_POSITION_FOLLOWING);
    const champ = avant.reverse().find((c) => c.type === "email" || RESSEMBLE_LOGIN.test(c.autocomplete + c.name + c.id))
      || avant[0];
    return champ ? champ.value.trim() : "";
  }

  function relever() {
    const mdp = motDePasse();
    if (mdp) {
      const login = identifiant(mdp);
      const empreinte = login + "\n" + mdp.value;
      if (empreinte !== dernier) {
        dernier = empreinte;
        envoyer({ type: "connexion", login, mdp: mdp.value });
      }
      return;
    }
    // pas de mot de passe sur cette page : c'est peut-être l'étape « identifiant » d'une connexion en deux temps
    const seul = champs(document, TEXTE).find(
      (c) => c.type === "email" || RESSEMBLE_LOGIN.test(c.autocomplete + c.name + c.id));
    if (seul) envoyer({ type: "identifiant", valeur: seul.value.trim() });
  }

  document.addEventListener("submit", relever, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target instanceof HTMLInputElement) relever();
  }, true);
  document.addEventListener("click", (e) => {
    const bouton = e.target instanceof Element
      && e.target.closest("button, input[type=submit], input[type=button], [role=button]");
    if (!bouton) return;
    // le bouton « œil » qui montre le mot de passe n'est pas une validation
    if (BOUTON_OEIL.test((bouton.getAttribute("aria-label") || "") + bouton.title + bouton.className + bouton.id)) return;
    relever();
  }, true);
})();
