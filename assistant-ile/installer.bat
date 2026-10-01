@echo off
cd /d "%~dp0"
echo Installation des dependances...
python -m pip install -r requirements.txt
echo Creation du logo et du raccourci "Assistant" sur le Bureau...
python logo.py --raccourci
echo Le moteur IA et le modele (5 Go) se telechargent tout seuls au premier lancement.
echo.
echo Termine ! Lance l assistant avec lancer.bat
pause
