@echo off
echo ======================================
echo  Check Vehicle Tracking Module Status
echo ======================================
echo.

SET /P DB_NAME="Enter your database name: "

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

python odoo-bin shell -c odoo.conf -d %DB_NAME% << EOF
import sys
try:
    module = env['ir.module.module'].search([('name', '=', 'vehicle_tracking')])
    if module:
        print(f"\nModule Found!")
        print(f"Name: {module.name}")
        print(f"State: {module.state}")
        print(f"Summary: {module.summary}")
    else:
        print("\nModule NOT found in database!")
except Exception as e:
    print(f"\nError: {str(e)}")
sys.exit(0)
EOF

echo.
pause
