@echo off
REM Login to Odoo database and delete invalid records
setlocal enabledelayedexpansion

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo =========================================================
echo Deleting Invalid Records
echo =========================================================
echo.

python -c "
import os
os.environ['PGPASSWORD'] = 'odoo'

import subprocess
sql = 'DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN (SELECT id FROM vehicle_driver);'

print('Attempting to connect and delete...')
print()

result = subprocess.run([
    'psql',
    '-h', 'localhost',
    '-U', 'odoo',
    '-d', 'Npd_Transport',
    '-c', sql
], capture_output=True, text=True)

if result.returncode == 0:
    print('Success!')
    print(result.stdout)
else:
    if 'not found' in result.stderr or 'not recognized' in result.stderr:
        print('psql not found - installing psycopg2...')
        print()
        subprocess.run(['pip', 'install', 'psycopg2-binary'], capture_output=True)
        print('Please run this script again')
    else:
        print('Error:', result.stderr)
"

echo.
pause
