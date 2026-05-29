@echo off
echo Stopping Odoo...
net stop odoo-server-18.0
timeout /t 2 >nul
echo Starting Odoo...
net start odoo-server-18.0
echo Done!
pause
