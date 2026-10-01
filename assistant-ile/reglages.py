"""Les réglages du PC : volume, luminosité, verrouillage, écran, pages des Paramètres de Windows.

Le Wi-Fi, le Bluetooth ou « ne pas déranger » ne se commandent pas proprement depuis un programme
sans droits administrateur : pour eux, on ouvre la bonne page des Paramètres.
"""
import os
import re
import ctypes
import subprocess

# ce que l'utilisateur dit -> (page « ms-settings: », nom affiché)
PAGES = {
    "wifi": ("network-wifi", "Wi-Fi"), "wi-fi": ("network-wifi", "Wi-Fi"), "wi fi": ("network-wifi", "Wi-Fi"),
    "reseau": ("network-status", "réseau"), "internet": ("network-status", "réseau"),
    "bluetooth": ("bluetooth", "Bluetooth"),
    "son": ("sound", "son"), "audio": ("sound", "son"), "micro": ("sound", "son"),
    "affichage": ("display", "affichage"), "ecran": ("display", "affichage"),
    "eclairage nocturne": ("nightlight", "éclairage nocturne"), "mode nuit": ("nightlight", "éclairage nocturne"),
    "notifications": ("notifications", "notifications"),
    "ne pas deranger": ("notifications", "notifications (Ne pas déranger)"),
    "batterie": ("batterysaver", "batterie"), "alimentation": ("powersleep", "alimentation"),
    "mises a jour": ("windowsupdate", "mises à jour"), "mise a jour": ("windowsupdate", "mises à jour"),
    "stockage": ("storagesense", "stockage"), "applications": ("appsfeatures", "applications"),
    "imprimantes": ("printers", "imprimantes"), "imprimante": ("printers", "imprimantes"),
    "souris": ("mousetouchpad", "souris"), "clavier": ("typing", "clavier"),
    "fond d'ecran": ("personalization-background", "fond d'écran"),
    "parametres": ("", "Paramètres"), "reglages": ("", "Paramètres"),
}


def _nombre(valeur, actuel):
    """« 30 » → 30, « +10 » → actuel + 10, « -10 » → actuel - 10 (borné entre 0 et 100)."""
    trouve = re.search(r"([+-]?)\s*(\d{1,3})", str(valeur))
    if not trouve:
        return None
    n = int(trouve.group(2))
    if trouve.group(1):
        n = actuel + n if trouve.group(1) == "+" else actuel - n
    return max(0, min(100, n))


def _sortie_son():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try:
        comtypes.CoInitialize()          # on est appelé depuis un fil de fond
    except OSError:
        pass
    return AudioUtilities.GetSpeakers().EndpointVolume


def volume(valeur):
    sortie = _sortie_son()
    actuel = round(sortie.GetMasterVolumeLevelScalar() * 100)
    mot = str(valeur).strip().lower()
    if mot in ("muet", "couper", "coupe", "mute"):
        sortie.SetMute(1, None)
        return "Son coupé."
    if mot in ("son", "retablir", "remettre", "unmute"):
        sortie.SetMute(0, None)
        return f"Son rétabli ({actuel} %)."
    if not mot:
        return f"Le volume est à {actuel} %" + (" (son coupé)." if sortie.GetMute() else ".")
    voulu = _nombre(mot, actuel)
    if voulu is None:
        return f"Erreur : je n'ai pas compris le volume « {valeur} »."
    sortie.SetMasterVolumeLevelScalar(voulu / 100, None)
    if voulu > 0:
        sortie.SetMute(0, None)
    return f"Volume à {voulu} %."


def _powershell(script):
    return subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                          timeout=20, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()


def luminosite(valeur):
    lu = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
                     "-ErrorAction SilentlyContinue | Select-Object -First 1).CurrentBrightness")
    if not lu.isdigit():
        return "Erreur : cet écran ne laisse pas Windows régler sa luminosité (écran externe ?)."
    actuel = int(lu)
    if not str(valeur).strip():
        return f"La luminosité est à {actuel} %."
    voulu = _nombre(valeur, actuel)
    if voulu is None:
        return f"Erreur : je n'ai pas compris la luminosité « {valeur} »."
    _powershell("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=[uint32]1; Brightness=[byte]{voulu}}}")
    return f"Luminosité à {voulu} %."


def verrouiller():
    return "PC verrouillé." if ctypes.windll.user32.LockWorkStation() else "Erreur : Windows a refusé de verrouiller."


def eteindre_ecran():
    # WM_SYSCOMMAND / SC_MONITORPOWER, 2 = éteint ; il se rallume dès qu'on touche la souris ou le clavier
    ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)
    return "Écran éteint."


def page_parametres(nom):
    from ordres import simplifier
    cle = simplifier(nom)
    trouve = PAGES.get(cle) or next((p for mot, p in PAGES.items() if mot in cle), None)
    if not trouve:
        return f"Erreur : je ne connais pas de page de réglages « {nom} »."
    os.startfile("ms-settings:" + trouve[0])
    return f"J'ouvre les réglages {trouve[1]}." if trouve[0] else "J'ouvre les Paramètres."


def regler(reglage, valeur=""):
    """Le point d'entrée unique (pour l'IA et pour les ordres directs)."""
    reglage = str(reglage).strip().lower()
    if reglage == "volume":
        return volume(valeur)
    if reglage in ("luminosite", "luminosité"):
        return luminosite(valeur)
    if reglage == "verrouiller":
        return verrouiller()
    if reglage == "ecran":
        return eteindre_ecran()
    if reglage == "parametres":
        return page_parametres(valeur)
    return f"Erreur : réglage « {reglage} » inconnu."
