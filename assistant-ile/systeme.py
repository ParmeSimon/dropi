"""Ce que Dropi demande à Windows pour remplacer le bureau et la barre des tâches.

- la liste des fenêtres ouvertes (celles que la barre des tâches montrerait), les mettre devant, les réduire, les fermer ;
- la barre des tâches de Windows : la passer en masquage automatique (et la remettre comme avant en quittant) ;
- un raccourci clavier global pour afficher le tableau de bord.

Rien n'est installé ni modifié durablement : si Dropi se ferme, la barre des tâches retrouve son réglage.
"""
import ctypes
import os
import sys
from ctypes import wintypes

WINDOWS = sys.platform == "win32"
if WINDOWS:
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
    u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.GetWindow.restype = wintypes.HWND
    u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u32.GetForegroundWindow.restype = wintypes.HWND
    u32.IsWindowVisible.argtypes = [wintypes.HWND]
    u32.IsIconic.argtypes = [wintypes.HWND]
    u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u32.GetWindowThreadProcessId.restype = wintypes.DWORD
    u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

GWL_EXSTYLE, GW_OWNER = -20, 4
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = 0x80, 0x40000, 0x08000000
DWMWA_CLOAKED = 14
SW_MINIMIZE, SW_RESTORE, SW_SHOW = 6, 9, 5
WM_CLOSE = 0x0010
CLASSES_IGNOREES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow",
                    "XamlExplorerHostIslandWindow", "TopLevelWindowForOverflowXamlIsland"}


def chemin_processus(pid):
    """Le chemin de l'exe d'un processus ("" si Windows ne veut pas le dire)."""
    poignee = k32.OpenProcess(0x1000, False, pid)             # PROCESS_QUERY_LIMITED_INFORMATION
    if not poignee:
        return ""
    try:
        tampon, taille = ctypes.create_unicode_buffer(520), wintypes.DWORD(520)
        return tampon.value if k32.QueryFullProcessImageNameW(poignee, 0, tampon, ctypes.byref(taille)) else ""
    finally:
        k32.CloseHandle(poignee)


def _pid(hwnd):
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def est_a_nous(hwnd):
    """Cette fenêtre appartient-elle à Dropi (la goutte, le tableau de bord, le dock) ?"""
    return bool(hwnd) and _pid(hwnd) == os.getpid()


def fenetres():
    """Les fenêtres que la barre des tâches montrerait : [{"hwnd", "titre", "exe", "pid", "reduite", "active"}],
    de la plus récemment utilisée à la plus ancienne. Sans celles de Dropi."""
    if not WINDOWS:
        return []
    trouvees = []
    devant = u32.GetForegroundWindow()
    moi = os.getpid()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def rappel(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        style = u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        possedee = bool(u32.GetWindow(hwnd, GW_OWNER))
        if (style & WS_EX_TOOLWINDOW or style & WS_EX_NOACTIVATE or possedee) and not style & WS_EX_APPWINDOW:
            return True
        longueur = u32.GetWindowTextLengthW(hwnd)
        if not longueur:
            return True
        masquee = wintypes.DWORD()
        dwm.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(masquee), ctypes.sizeof(masquee))
        if masquee.value:                                      # fenêtre d'un autre bureau virtuel, ou appli suspendue
            return True
        classe = ctypes.create_unicode_buffer(128)
        u32.GetClassNameW(hwnd, classe, 128)
        if classe.value in CLASSES_IGNOREES:
            return True
        pid = _pid(hwnd)
        if pid == moi:
            return True
        titre = ctypes.create_unicode_buffer(longueur + 1)
        u32.GetWindowTextW(hwnd, titre, longueur + 1)
        trouvees.append({"hwnd": int(hwnd), "titre": titre.value, "pid": pid, "exe": chemin_processus(pid),
                         "reduite": bool(u32.IsIconic(hwnd)), "active": hwnd == devant})
        return True

    u32.EnumWindows(rappel, 0)
    return trouvees


def activer(hwnd):
    """Met une fenêtre devant (la restaure si elle était réduite). Windows le refuse souvent à un programme qui n'a pas
    le clavier : on s'attache un instant au fil de la fenêtre du premier plan."""
    if not WINDOWS:
        return
    hwnd = wintypes.HWND(hwnd)
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_RESTORE)
    devant = u32.GetForegroundWindow()
    moi = k32.GetCurrentThreadId()
    autre = u32.GetWindowThreadProcessId(devant, None) if devant else 0
    if autre and autre != moi:
        u32.AttachThreadInput(moi, autre, True)
    try:
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
    finally:
        if autre and autre != moi:
            u32.AttachThreadInput(moi, autre, False)


def reduire(hwnd):
    if WINDOWS:
        u32.ShowWindow(wintypes.HWND(hwnd), SW_MINIMIZE)


def fermer(hwnd):
    """Demande poliment à la fenêtre de se fermer (elle peut proposer d'enregistrer)."""
    if WINDOWS:
        u32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0)


# ---------------------------------------------------------------- la barre des tâches de Windows
ABM_GETSTATE, ABM_SETSTATE = 4, 10
ABS_AUTOHIDE, ABS_ALWAYSONTOP = 1, 2


class _DonneesBarre(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


def barre_windows_masquee():
    """La barre des tâches de Windows est-elle en masquage automatique ?"""
    if not WINDOWS:
        return False
    donnees = _DonneesBarre()
    donnees.cbSize = ctypes.sizeof(donnees)
    shell32.SHAppBarMessage.restype = ctypes.c_size_t
    return bool(shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(donnees)) & ABS_AUTOHIDE)


def masquer_barre_windows(masquer):
    """Passe la barre des tâches en masquage automatique (elle revient si on pousse la souris en bas), ou la remet."""
    if not WINDOWS:
        return
    u32.FindWindowW.restype = wintypes.HWND
    donnees = _DonneesBarre()
    donnees.cbSize = ctypes.sizeof(donnees)
    donnees.hWnd = u32.FindWindowW("Shell_TrayWnd", None)
    donnees.lParam = ABS_AUTOHIDE if masquer else ABS_ALWAYSONTOP
    shell32.SHAppBarMessage.restype = ctypes.c_size_t
    shell32.SHAppBarMessage(ABM_SETSTATE, ctypes.byref(donnees))


# ---------------------------------------------------------------- raccourci clavier global
MODIFICATEURS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "maj": 0x4, "shift": 0x4, "win": 0x8}
TOUCHES = {"espace": 0x20, "space": 0x20, "tab": 0x09, "entree": 0x0D, "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
           "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B}
WM_HOTKEY = 0x0312


def analyser_raccourci(texte):
    """« ctrl+alt+d » -> (modificateurs, code de touche), ou None si on ne comprend pas."""
    mods, touche = 0, None
    for morceau in str(texte).lower().replace(" ", "").split("+"):
        if morceau in MODIFICATEURS:
            mods |= MODIFICATEURS[morceau]
        elif morceau in TOUCHES:
            touche = TOUCHES[morceau]
        elif len(morceau) == 1 and morceau.isalnum():
            touche = ord(morceau.upper())
        else:
            return None
    return (mods | 0x4000, touche) if mods and touche else None          # 0x4000 : pas de répétition


def enregistrer_raccourci(identifiant, texte):
    """Réserve un raccourci global pour ce programme. Faux s'il est déjà pris par une autre appli ou invalide."""
    combinaison = analyser_raccourci(texte)
    if not WINDOWS or not combinaison:
        return False
    return bool(u32.RegisterHotKey(None, identifiant, combinaison[0], combinaison[1]))


def liberer_raccourci(identifiant):
    if WINDOWS:
        u32.UnregisterHotKey(None, identifiant)
