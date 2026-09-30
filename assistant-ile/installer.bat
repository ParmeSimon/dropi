@echo off
cd /d "%~dp0"
echo Installation des dependances...
python -m pip install -r requirements.txt
echo Creation du logo et du raccourci "Assistant" sur le Bureau...
python logo.py --raccourci
echo Telechargement du modele IA (quelques Go, patience)...
ollama pull qwen3:8b
echo.
echo Termine ! Lance l assistant avec lancer.bat
pause
