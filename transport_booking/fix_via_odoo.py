#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix Invalid Records using Odoo ORM
"""

import os
import sys
import subprocess

# Odoo path
ODOO_PATH = r"C:\Program Files\Odoo 18.0.20251009\server"

def main():
    print()
    print("=" * 60)
    print("Fixing Invalid Records - Using Odoo ORM")
    print("=" * 60)
    print()
    
    # Python code ที่จะรัน
    cleanup_code = """
import os
os.environ['PGPASSWORD'] = 'odoo'
import subprocess
import sys

# Delete invalid records using SQL via command line
print('Deleting invalid records...')

sql_queries = [
    'DELETE FROM vehicle_tracking WHERE driver_id NOT IN (SELECT id FROM vehicle_driver WHERE id IS NOT NULL) AND driver_id IS NOT NULL;',
    'SELECT COUNT(*) FROM vehicle_tracking;'
]

for query in sql_queries:
    result = subprocess.run([
        'psql',
        '-h', 'localhost',
        '-U', 'odoo',
        '-d', 'Npd_Transport',
        '-c', query
    ], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print('Error:', result.stderr)
"""
    
    # Try direct SQL approach
    print("Step 1: Attempting to delete invalid records...")
    print()
    
    # Using environment variable for password
    env = os.environ.copy()
    env['PGPASSWORD'] = 'odoo'
    
    # Step 1: Delete invalid records
    try:
        result = subprocess.run([
            'psql',
            '-h', 'localhost',
            '-U', 'odoo',
            '-d', 'Npd_Transport',
            '-c', 'DELETE FROM vehicle_tracking WHERE driver_id NOT IN (SELECT id FROM vehicle_driver WHERE id IS NOT NULL) AND driver_id IS NOT NULL;'
        ], env=env, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("Deleted records successfully")
            print(result.stdout)
        else:
            print("Error deleting records:")
            print(result.stderr)
            
    except FileNotFoundError:
        print("psql not found - using alternate method...")
        print()
        print("Please use pgAdmin to run this SQL:")
        print()
        print("DELETE FROM vehicle_tracking WHERE driver_id NOT IN (SELECT id FROM vehicle_driver WHERE id IS NOT NULL) AND driver_id IS NOT NULL;")
        print()
        return False
    
    # Step 2: Check results
    print()
    print("Step 2: Checking results...")
    print()
    
    try:
        result = subprocess.run([
            'psql',
            '-h', 'localhost',
            '-U', 'odoo',
            '-d', 'Npd_Transport',
            '-c', 'SELECT COUNT(*) FROM vehicle_tracking;'
        ], env=env, capture_output=True, text=True, timeout=10)
        
        print("Total tracking records:")
        print(result.stdout)
        
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    print()
    print("=" * 60)
    print("Done! Ready to restart Odoo")
    print("=" * 60)
    return True

if __name__ == '__main__':
    try:
        success = main()
    except Exception as e:
        print(f"Error: {e}")
        success = False
    
    input("\nPress Enter to exit...")
    sys.exit(0 if success else 1)
