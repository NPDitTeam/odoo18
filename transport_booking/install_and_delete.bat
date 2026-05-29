@echo off
REM Install psycopg2 and delete invalid records

setlocal enabledelayedexpansion

echo.
echo =========================================================
echo Installing psycopg2...
echo =========================================================
echo.

pip install psycopg2-binary

if errorlevel 1 (
    echo Error installing psycopg2
    pause
    exit /b 1
)

echo.
echo =========================================================
echo Connecting to database and deleting records...
echo =========================================================
echo.

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

python -c "
import psycopg2

print('Connecting to Npd_Transport database...')
try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='Npd_Transport',
        user='odoo',
        password='odoo'
    )
    cursor = conn.cursor()
    
    print('Connected successfully!')
    print()
    print('Deleting invalid records...')
    
    sql = 'DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN (SELECT id FROM vehicle_driver);'
    
    cursor.execute(sql)
    deleted = cursor.rowcount
    conn.commit()
    
    print(f'Deleted {deleted} invalid records')
    print()
    print('Checking remaining records...')
    
    cursor.execute('SELECT COUNT(*) FROM vehicle_tracking;')
    remaining = cursor.fetchone()[0]
    print(f'Total records remaining: {remaining}')
    
    cursor.close()
    conn.close()
    
    print()
    print('Done!')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
"

echo.
pause
