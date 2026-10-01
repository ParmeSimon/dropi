"""Le coffre : tes mots de passe, rangés dans le Gestionnaire d'identifiants de Windows.

Rien n'est écrit dans un fichier de l'assistant : Windows chiffre chaque entrée avec ta session
(tu peux les voir et les supprimer dans Panneau de configuration › Gestionnaire d'identifiants ›
Informations d'identification Windows, elles commencent par « Dropi/ »).
Les mots de passe ne passent jamais par l'IA ni par la mémoire de l'assistant.
"""
import string
import secrets
import ctypes
from ctypes import wintypes

PREFIXE = "Dropi/"
SYMBOLES = "!@#$%*-_=+?"
_GENERIQUE, _CE_PC = 1, 2          # CRED_TYPE_GENERIC, CRED_PERSIST_LOCAL_MACHINE


class _Identifiant(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


_PIdentifiant = ctypes.POINTER(_Identifiant)
_adv = ctypes.WinDLL("advapi32", use_last_error=True)
_adv.CredWriteW.argtypes = [_PIdentifiant, wintypes.DWORD]
_adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_PIdentifiant)]
_adv.CredEnumerateW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                ctypes.POINTER(ctypes.POINTER(_PIdentifiant))]
_adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_adv.CredFree.argtypes = [ctypes.c_void_p]
for _f in (_adv.CredWriteW, _adv.CredReadW, _adv.CredEnumerateW, _adv.CredDeleteW):
    _f.restype = wintypes.BOOL


def generer(longueur=20):
    """Un mot de passe robuste : tiré au sort par Windows, avec minuscule, majuscule, chiffre et symbole."""
    longueur = max(8, int(longueur))
    alphabet = string.ascii_letters + string.digits + SYMBOLES
    while True:
        mdp = "".join(secrets.choice(alphabet) for _ in range(longueur))
        if (any(c.islower() for c in mdp) and any(c.isupper() for c in mdp)
                and any(c.isdigit() for c in mdp) and any(c in SYMBOLES for c in mdp)):
            return mdp


def _cible(hote, login):
    return f"{PREFIXE}{hote}/{login}"


def enregistrer(hote, login, mdp):
    secret = mdp.encode("utf-16-le")
    tampon = (ctypes.c_ubyte * len(secret)).from_buffer_copy(secret)
    fiche = _Identifiant(Type=_GENERIQUE, TargetName=_cible(hote, login), Comment="Enregistré par l'assistant",
                         CredentialBlobSize=len(secret), CredentialBlob=tampon, Persist=_CE_PC,
                         UserName=login or hote)
    if not _adv.CredWriteW(ctypes.byref(fiche), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def lire(hote, login):
    """Le mot de passe enregistré pour ce compte, ou None."""
    p = _PIdentifiant()
    if not _adv.CredReadW(_cible(hote, login), _GENERIQUE, 0, ctypes.byref(p)):
        return None
    try:
        return ctypes.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize).decode("utf-16-le")
    finally:
        _adv.CredFree(p)


def tous():
    """[(hôte, identifiant)] de tout le coffre, le plus récemment enregistré en premier."""
    nombre, fiches = wintypes.DWORD(), ctypes.POINTER(_PIdentifiant)()
    if not _adv.CredEnumerateW(PREFIXE + "*", 0, ctypes.byref(nombre), ctypes.byref(fiches)):
        return []                    # coffre vide
    try:
        trouves = []
        for i in range(nombre.value):
            f = fiches[i].contents
            hote, _, login = f.TargetName[len(PREFIXE):].partition("/")
            trouves.append(((f.LastWritten.dwHighDateTime << 32) | f.LastWritten.dwLowDateTime, hote, login))
        return [(hote, login) for _, hote, login in sorted(trouves, reverse=True)]
    finally:
        _adv.CredFree(fiches)


def comptes(hote):
    """Les identifiants enregistrés pour ce site (exactement ce site : c'est la protection anti-hameçonnage)."""
    return [login for h, login in tous() if h == hote]


def supprimer(hote, login):
    return bool(_adv.CredDeleteW(_cible(hote, login), _GENERIQUE, 0))
