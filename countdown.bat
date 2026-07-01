@echo off
rem Wrapper para poder escribir "countdown" en vez de "python countdown.py"
rem Debe estar en la MISMA carpeta que countdown.py

python "%~dp0countdown.py" %*
