@echo off
title Gestion de Ordenes de Servicio
cd /d "%~dp0"
echo.
echo ================================================
echo       GESTION DE ORDENES DE SERVICIO
echo ================================================
echo.
echo Abriendo la aplicacion...
echo.
python -m streamlit run app.py
pause
