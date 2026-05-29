#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clear Odoo View Cache and Force Update
"""
import os
import sys
import subprocess

# Odoo configuration
ODOO_PATH = r"C:\Program Files\Odoo 18.0.20251009\server"
DATABASE = "Npd_Transport"
MODULE = "transport_booking"

def run_command(cmd):
    """Run shell command"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    return result.returncode == 0

def main():
    print("="*60)
    print("Odoo Cache Clear and Module Update Script")
    print("="*60)
    
    # Step 1: Stop Odoo
    print("\n[1/6] Stopping Odoo service...")
    run_command('net stop "odoo-server-18.0"')
    
    # Step 2: Delete Python cache
    print("\n[2/6] Clearing Python cache...")
    transport_path = os.path.join(ODOO_PATH, "custom-addons", MODULE)
    for root, dirs, files in os.walk(transport_path):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            print(f"  Deleting: {pycache_path}")
            try:
                import shutil
                shutil.rmtree(pycache_path)
            except Exception as e:
                print(f"  Warning: {e}")
    
    # Step 3: Start Odoo
    print("\n[3/6] Starting Odoo service...")
    run_command('net start "odoo-server-18.0"')
    
    # Step 4: Wait
    print("\n[4/6] Waiting for Odoo to be ready...")
    import time
    time.sleep(10)
    
    # Step 5: Update module
    print("\n[5/6] Updating module...")
    os.chdir(ODOO_PATH)
    update_cmd = f'python odoo-bin -u {MODULE} -d {DATABASE} --stop-after-init'
    run_command(update_cmd)
    
    # Step 6: Final restart
    print("\n[6/6] Final restart...")
    run_command('net stop "odoo-server-18.0"')
    time.sleep(3)
    run_command('net start "odoo-server-18.0"')
    
    print("\n" + "="*60)
    print("✅ Done!")
    print("="*60)
    print("\nIMPORTANT NEXT STEPS:")
    print("1. Close ALL browser windows")
    print("2. Open Incognito/Private window")
    print("3. Go to: http://127.0.0.1:8069")
    print("4. Check tracking map")
    print("="*60)

if __name__ == '__main__':
    main()
