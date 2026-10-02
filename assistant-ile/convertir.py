"""Convertir un fichier déposé sur Dropi : images (PNG, JPG, WebP, PDF, réduire), PDF vers images ou texte,
et « en PDF » pour les textes (txt, md, csv, json, html, code…) et les documents Office (si Office est installé).

Tout se fait sur le PC, sans IA : le fichier converti est créé à côté de l'original, qui n'est jamais touché.
"""
import re
import subprocess
import unicodedata
from pathlib import Path

IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
TEXTES = {".txt", ".md", ".log", ".csv", ".json", ".xml", ".html", ".htm", ".py", ".js", ".yaml", ".yml", ".ini"}
OFFICE = {".docx": "word", ".doc": "word", ".odt": "word", ".rtf": "word",
          ".xlsx": "excel", ".xls": "excel", ".pptx": "powerpoint", ".ppt": "powerpoint"}
CODE = {".csv", ".json", ".xml", ".py", ".js", ".yaml", ".yml", ".ini", ".log"}      # affichés en police fixe

LIBELLES = {"png": "PNG", "jpg": "JPG", "webp": "WebP", "pdf": "PDF", "reduire": "Image réduite (1280 px)",
            "pdf_unique": "Un seul PDF", "images": "Images (une par page)", "texte": "Texte (.txt)"}
GROUPES = {"pdf_unique"}                 # un seul résultat pour plusieurs fichiers
SORTIE_IMAGE = {"png": ".png", "jpg": ".jpg", "webp": ".webp", "reduire": ".jpg"}
PAGES_MAX = 60                           # PDF vers images : au-delà, on s'arrête (des centaines de PNG, ce n'est pas voulu)
DELAI_OFFICE = 180


def type_de(chemin):
    ext = Path(chemin).suffix.lower()
    if ext in IMAGES:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in OFFICE:
        return "office"
    if ext in TEXTES:
        return "texte"
    return None


def formats_possibles(chemins):
    """Les conversions proposées pour ces fichiers : [(clé, libellé)]. Seulement celles qui valent pour TOUS."""
    types = {type_de(c) for c in chemins}
    if not chemins or None in types or len(types) > 1:
        return []
    genre = types.pop()
    if genre == "image":
        exts = {Path(c).suffix.lower() for c in chemins}
        cles = [c for c in ("png", "jpg", "webp") if not (len(exts) == 1 and exts <= {SORTIE_IMAGE[c]} | ({".jpeg"} if c == "jpg" else set()))]
        cles += ["pdf", "reduire"]
        if len(chemins) > 1:
            cles.insert(len(cles) - 1, "pdf_unique")
    elif genre == "pdf":
        cles = ["images", "texte"]
    else:
        cles = ["pdf"]
    return [(c, LIBELLES[c]) for c in cles]


def _simple(texte):
    t = unicodedata.normalize("NFD", texte.lower().replace("’", "'"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def cle_depuis_texte(texte, chemins):
    """« convertis en jpg », « mets ça en pdf », « réduis l'image »… -> clé de conversion, ou None."""
    t = _simple(texte)
    dispo = {c for c, _ in formats_possibles(chemins)}
    if not dispo or not re.search(r"convert|transform|mets?|passe|exporte|enregistre|sauvegarde|reduis|compresse|extrais|en (?:png|jpe?g|webp|pdf|texte|txt|images?)", t):
        return None
    if re.search(r"reduis|compresse|plus petit|allege|redimensionne", t) and "reduire" in dispo:
        return "reduire"
    if re.search(r"(?:en|vers) (?:un seul |un |1 )?pdf", t):
        return "pdf_unique" if "pdf_unique" in dispo and re.search(r"seul|un pdf|1 pdf|ensemble|tout", t) else ("pdf" if "pdf" in dispo else None)
    if "images" in dispo and re.search(r"en images?|en png|en jpe?g|page par page|chaque page", t):
        return "images"
    if "texte" in dispo and re.search(r"en texte|en txt|extrais.*texte|le texte", t):
        return "texte"
    for cle, motif in (("png", r"png"), ("jpg", r"jpe?g"), ("webp", r"webp")):
        if cle in dispo and re.search(rf"en {motif}\b", t):
            return cle
    return None


def _libre(dossier, nom, ext):
    """Un nom de fichier qui n'existe pas encore : « photo.jpg », « photo (2).jpg »…"""
    candidat = dossier / f"{nom}{ext}"
    n = 2
    while candidat.exists():
        candidat = dossier / f"{nom} ({n}){ext}"
        n += 1
    return candidat


def _image_rgb(im):
    """Une image sans transparence (JPG et PDF n'en ont pas) : sur fond blanc."""
    from PIL import Image
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        fond = Image.new("RGB", im.size, (255, 255, 255))
        fond.paste(im, mask=im.split()[-1])
        return fond
    return im.convert("RGB")


def _ouvrir_image(chemin):
    from PIL import Image, ImageOps
    im = Image.open(chemin)
    im.load()
    return ImageOps.exif_transpose(im)         # une photo de téléphone reste dans le bon sens


def _image_vers(chemin, cle):
    p = Path(chemin)
    im = _ouvrir_image(p)
    if cle == "reduire":
        im.thumbnail((1280, 1280))
        sortie = _libre(p.parent, p.stem + " (réduit)", ".jpg")
        _image_rgb(im).save(sortie, "JPEG", quality=85, optimize=True)
    elif cle == "pdf":
        sortie = _libre(p.parent, p.stem, ".pdf")
        _image_rgb(im).save(sortie, "PDF", resolution=100.0)
    else:
        sortie = _libre(p.parent, p.stem, SORTIE_IMAGE[cle])
        if cle == "jpg":
            _image_rgb(im).save(sortie, "JPEG", quality=92, optimize=True)
        elif cle == "webp":
            im.save(sortie, "WEBP", quality=90)
        else:
            im.save(sortie, "PNG")
    return sortie


def _images_vers_un_pdf(chemins):
    premiere = Path(chemins[0])
    pages = [_image_rgb(_ouvrir_image(c)) for c in chemins]
    sortie = _libre(premiere.parent, premiere.stem + f" (+{len(chemins) - 1})", ".pdf")
    pages[0].save(sortie, "PDF", resolution=100.0, save_all=True, append_images=pages[1:])
    return sortie


def _pdf_vers_images(chemin):
    import pypdfium2
    p = Path(chemin)
    pdf = pypdfium2.PdfDocument(str(p))
    total = len(pdf)
    dossier = _libre(p.parent, p.stem + " (images)", "")
    dossier.mkdir()
    n = min(total, PAGES_MAX)
    for i in range(n):
        pdf[i].render(scale=2).to_pil().convert("RGB").save(dossier / f"page {i + 1:03d}.png")
    pdf.close()
    return dossier, n, total


def _pdf_vers_texte(chemin):
    from pypdf import PdfReader
    p = Path(chemin)
    lecteur = PdfReader(str(p))
    if lecteur.is_encrypted:
        lecteur.decrypt("")
    morceaux = [(page.extract_text() or "").strip() for page in lecteur.pages]
    texte = "\n\n".join(m for m in morceaux if m)
    if not texte:
        raise ValueError("Aucun texte dans ce PDF (un scan ? Je ne lis pas les images).")
    sortie = _libre(p.parent, p.stem, ".txt")
    sortie.write_text(texte, "utf-8")
    return sortie


def _texte_vers_pdf(chemin):
    """Un fichier texte, Markdown ou HTML en PDF, avec Qt (déjà là, rien à installer)."""
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QTextDocument, QPdfWriter, QPageSize, QPageLayout, QFont
    p = Path(chemin)
    brut = p.read_bytes()[:5_000_000]
    texte = brut.decode("utf-8", errors="replace") if b"\x00" not in brut[:2000] else None
    if texte is None:
        raise ValueError("C'est un fichier binaire, je ne peux pas le mettre en PDF.")
    sortie = _libre(p.parent, p.stem, ".pdf")
    ecrivain = QPdfWriter(str(sortie))
    ecrivain.setPageSize(QPageSize(QPageSize.A4))
    ecrivain.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Millimeter)
    doc = QTextDocument()
    ext = p.suffix.lower()
    if ext in (".html", ".htm"):
        doc.setHtml(texte)
    elif ext == ".md":
        doc.setMarkdown(texte)
    else:
        police = QFont("Consolas" if ext in CODE else "Segoe UI", 9 if ext in CODE else 10)
        doc.setDefaultFont(police)
        doc.setPlainText(texte)
    doc.print_(ecrivain)
    return sortie


def _office_vers_pdf(chemin):
    p = Path(chemin)
    sortie = _libre(p.parent, p.stem, ".pdf")
    appli = OFFICE[p.suffix.lower()]
    entree, cible = str(p).replace("'", "''"), str(sortie).replace("'", "''")
    scripts = {
        "word": "$a = New-Object -ComObject Word.Application; $a.Visible = $false; $a.DisplayAlerts = 0; "
                f"$d = $a.Documents.Open('{entree}', $false, $true); $d.SaveAs2('{cible}', 17); $d.Close(0); $a.Quit()",
        "excel": "$a = New-Object -ComObject Excel.Application; $a.Visible = $false; $a.DisplayAlerts = $false; "
                 f"$d = $a.Workbooks.Open('{entree}', 0, $true); $d.ExportAsFixedFormat(0, '{cible}'); $d.Close($false); $a.Quit()",
        "powerpoint": "$a = New-Object -ComObject PowerPoint.Application; "
                      f"$d = $a.Presentations.Open('{entree}', -1, 0, 0); $d.SaveAs('{cible}', 32); $d.Close(); $a.Quit()",
    }
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", scripts[appli]], capture_output=True,
                       timeout=DELAI_OFFICE, creationflags=0x08000000)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if sortie.exists() and sortie.stat().st_size > 0:
        return sortie
    sortie.unlink(missing_ok=True)
    if p.suffix.lower() == ".docx":                 # pas de Word : on garde au moins le texte
        import tools
        texte, _ = tools.texte_document(str(p), 400_000)
        brouillon = _libre(p.parent, p.stem + " (brouillon)", ".txt")
        brouillon.write_text(texte, "utf-8")
        try:
            pdf = _texte_vers_pdf(brouillon)
            final = _libre(p.parent, p.stem, ".pdf")
            pdf.rename(final)
            return final, "mise en forme simplifiée, Word n'est pas installé"
        finally:
            brouillon.unlink(missing_ok=True)
    nom = {"word": "Word", "excel": "Excel", "powerpoint": "PowerPoint"}[appli]
    raise ValueError(f"Pour convertir ça en PDF, il faut {nom} d'installé sur ce PC.")


def convertir(chemin, cle):
    """Convertit un fichier. Renvoie une phrase pour l'utilisateur. Lève ValueError avec une explication."""
    p = Path(chemin)
    if not p.is_file():
        raise ValueError(f"Introuvable : {p}")
    genre = type_de(p)
    if genre is None or cle not in {c for c, _ in formats_possibles([chemin])}:
        raise ValueError(f"Je ne sais pas convertir {p.name} en {LIBELLES.get(cle, cle)}.")
    try:
        if genre == "image":
            sortie = _image_vers(p, cle)
        elif genre == "pdf" and cle == "images":
            dossier, n, total = _pdf_vers_images(p)
            reste = f" (les {PAGES_MAX} premières pages sur {total})" if n < total else ""
            return f"{n} image{'s' if n > 1 else ''} dans « {dossier.name} »{reste}."
        elif genre == "pdf":
            sortie = _pdf_vers_texte(p)
        elif genre == "office":
            sortie = _office_vers_pdf(p)
        else:
            sortie = _texte_vers_pdf(p)
    except ValueError:
        raise
    except Exception as ex:
        raise ValueError(f"Conversion impossible ({type(ex).__name__} : {str(ex)[:120]}).")
    note = ""
    if isinstance(sortie, tuple):
        sortie, note = sortie
        note = f" ({note})"
    return f"{sortie.name} créé{note}."


def convertir_groupe(chemins, cle):
    """Plusieurs images dans un seul PDF."""
    if cle != "pdf_unique" or cle not in {c for c, _ in formats_possibles(chemins)}:
        raise ValueError("Je ne sais pas faire cette conversion avec ces fichiers.")
    try:
        sortie = _images_vers_un_pdf(chemins)
    except Exception as ex:
        raise ValueError(f"Conversion impossible ({type(ex).__name__} : {str(ex)[:120]}).")
    return f"{sortie.name} créé ({len(chemins)} images)."
