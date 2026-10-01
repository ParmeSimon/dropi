"""Le guetteur : repère le champ « mot de passe » où tu viens de cliquer dans ton navigateur, et le remplit.

Windows décrit à tout programme ce qui a le clavier (l'accessibilité, « UI Automation ») : on y lit
si c'est un champ mot de passe, l'adresse de la page, et le champ identifiant placé juste avant.
Le remplissage écrit directement dans ces deux champs (aucune frappe simulée : rien ne peut partir
dans une autre fenêtre), et seulement si la page est toujours celle du site attendu.
Un seul fil parle à Windows : il guette, et exécute les remplissages qu'on lui dépose.
"""
import os
import queue
import ctypes
import threading
from ctypes import wintypes
from urllib.parse import urlsplit

try:        # chargé ici, au lancement : dans le fil de fond, l'animation de l'île le ralentirait de 10 secondes
    import comtypes
    import comtypes.client
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as U
except (ImportError, OSError):
    U = None                    # pas sous Windows, ou comtypes pas installé : pas de guetteur

NAVIGATEURS = ("chrome", "brave", "msedge")
PAUSE = 0.4                    # secondes entre deux coups d'œil

_surveillant = None


def hote_de(url):
    """« https://www.Exemple.fr/connexion » → « exemple.fr » (vide si ce n'est pas une page web)."""
    u = urlsplit(url or "")
    if u.scheme not in ("http", "https") or not u.hostname:
        return ""
    hote = u.hostname.lower()
    return hote[4:] if hote.startswith("www.") else hote


def _nom_processus(pid):
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    poignee = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not poignee:
        return ""
    try:
        chemin, taille = ctypes.create_unicode_buffer(520), wintypes.DWORD(520)
        if not k32.QueryFullProcessImageNameW(wintypes.HANDLE(poignee), 0, chemin, ctypes.byref(taille)):
            return ""
        return os.path.splitext(os.path.basename(chemin.value))[0].lower()
    finally:
        k32.CloseHandle(wintypes.HANDLE(poignee))


class Surveillant:
    def __init__(self, sur_champ, sur_rempli, navigateurs=NAVIGATEURS):
        self.sur_champ = sur_champ          # dict (champ mot de passe sous le curseur) ou None ; depuis le fil de fond
        self.sur_rempli = sur_rempli        # (réussi ?, message)
        self.navigateurs = [n.lower() for n in navigateurs]
        self._demandes = queue.Queue()
        self._numero = 0
        self._champ = None                  # le champ en cours : éléments Windows + ce qu'on en a lu
        self._sur_ile = False
        self._noms = {}

    def demarrer(self):
        if U is not None:
            threading.Thread(target=self._fil, daemon=True).start()

    def remplir(self, numero, login, mdp):
        self._demandes.put((numero, login, mdp))

    # ---------------------------------------------------------------- le fil de fond
    def _preparer(self):
        try:
            comtypes.CoInitialize()
        except OSError:
            pass
        self.U = U
        self.uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        self._edits = self.uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId, U.UIA_EditControlTypeId)

    def _fil(self):
        self._preparer()
        while True:
            try:
                demande = self._demandes.get(timeout=PAUSE)
            except queue.Empty:
                demande = None
            try:
                if demande:
                    self.sur_rempli(*self._remplir(*demande))
                else:
                    self._regarder()
            except Exception:              # un élément qui disparaît pendant qu'on le lit (page fermée, rechargée…)
                if demande:
                    self.sur_rempli(False, "Je n'ai pas réussi à remplir ce champ.")
                self._oublier()

    def _est_navigateur(self, pid):
        if pid not in self._noms:
            if len(self._noms) > 200:
                self._noms.clear()
            self._noms[pid] = _nom_processus(pid)
        return self._noms[pid] in self.navigateurs

    def _regarder(self):
        el = self.uia.GetFocusedElement()
        if not el:
            return
        pid = el.CurrentProcessId
        if pid == os.getpid():
            self._sur_ile = True            # c'est l'île qui a le clavier (on vient de cliquer dessus) : on garde le champ
            return
        revenu, self._sur_ile = self._sur_ile, False
        if not (self._est_navigateur(pid) and el.CurrentIsPassword):
            self._oublier()
            return
        if self._champ and self.uia.CompareElements(el, self._champ["mdp"]):
            if revenu:                      # de retour dans le champ après un passage par l'île : on le repropose
                self.sur_champ(self._champ["vu"])
            return
        self._noter(el)

    def _noter(self, el):
        """Un nouveau champ mot de passe a le clavier : on lit sa page et son champ identifiant."""
        page = self._page(el)
        hote = hote_de(self._valeur(page)) if page else ""
        if not hote:
            self._oublier()
            return
        champ_login = self._champ_login(page, el)
        self._numero += 1
        vu = {"numero": self._numero, "hote": hote,
              "login": (self._valeur(champ_login) or "").strip() if champ_login else ""}
        self._champ = {"numero": self._numero, "hote": hote, "mdp": el, "page": page, "champ_login": champ_login,
                       "vu": vu}
        self.sur_champ(vu)

    def _oublier(self):
        if self._champ:
            self._champ = None
            self.sur_champ(None)

    def _motif(self, el):
        motif = el.GetCurrentPattern(self.U.UIA_ValuePatternId)
        return motif.QueryInterface(self.U.IUIAutomationValuePattern) if motif else None

    def _valeur(self, el):
        motif = self._motif(el)
        return motif.CurrentValue if motif else ""

    def _page(self, el):
        """La page web qui contient ce champ (la plus haute : celle dont l'adresse est dans la barre du navigateur)."""
        marcheur, page = self.uia.ControlViewWalker, None
        for _ in range(60):
            el = marcheur.GetParentElement(el)
            if not el:
                break
            if el.CurrentControlType == self.U.UIA_DocumentControlTypeId:
                page = el
        return page

    def _champ_login(self, page, mdp):
        """Le champ de saisie juste avant le mot de passe : presque toujours l'identifiant ou l'e-mail."""
        champs = page.FindAll(self.U.TreeScope_Descendants, self._edits)
        avant = None
        for i in range(min(champs.Length, 80)):
            c = champs.GetElement(i)
            if self.uia.CompareElements(c, mdp):
                return avant
            if not c.CurrentIsPassword and c.CurrentIsEnabled and c.CurrentIsKeyboardFocusable:
                avant = c
        return None

    def _remplir(self, numero, login, mdp):
        champ = self._champ
        if not champ or champ["numero"] != numero:
            return False, "Le champ a changé, reclique dedans."
        # la page a pu changer entre-temps : on relit son adresse juste avant d'écrire
        if hote_de(self._valeur(champ["page"])) != champ["hote"] or not champ["mdp"].CurrentIsPassword:
            self._oublier()
            return False, "La page a changé, je n'ai rien rempli."
        champ_login = champ["champ_login"]
        if login and champ_login and (self._valeur(champ_login) or "").strip() != login:
            motif = self._motif(champ_login)
            if motif and not motif.CurrentIsReadOnly:
                motif.SetValue(login)
        motif = self._motif(champ["mdp"])
        if not motif or motif.CurrentIsReadOnly:
            return False, "Ce champ refuse d'être rempli."
        motif.SetValue(mdp)
        self._rendre_clavier(champ["mdp"])
        return True, champ["hote"]

    @staticmethod
    def _rendre_clavier(el):
        el.SetFocus()                       # le clavier revient dans le champ : il ne reste qu'à valider


def demarrer(sur_champ, sur_rempli, navigateurs=NAVIGATEURS):
    global _surveillant
    _surveillant = Surveillant(sur_champ, sur_rempli, navigateurs)
    _surveillant.demarrer()


def remplir(numero, login, mdp):
    if _surveillant:
        _surveillant.remplir(numero, login, mdp)
