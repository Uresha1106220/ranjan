@echo off
title VNF Mahila Adhiveshan 2026 — Registration Server
color 5F
echo.
echo  ==========================================
echo   VNF Mahila Adhiveshan 2026
echo   Registration Form Server
echo  ==========================================
echo.
echo  Installing/checking dependencies...
pip install Flask --quiet
echo.
echo  Starting server...
echo  Open your browser at: http://localhost:5000
echo  Admin panel at:       http://localhost:5000/admin
echo.
echo  Press Ctrl+C to stop the server.
echo  ==========================================
echo.
python app.py
pause
