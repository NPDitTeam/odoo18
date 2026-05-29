#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delete Invalid Records from vehicle_tracking
"""

import subprocess
import sys

def main():
    print()
    print("=" * 60)
    print("Deleting Invalid Records from vehicle_tracking")
    print("=" * 60)
    print()
    
    # Set password environment variable
    import os
    os.environ['PGPASSWORD'] = 'odoo'
    
    sql_query = """DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN (SELECT id FROM vehicle_driver);"""
    
    try:
        print("Connecting to database...")
        print()
        
        # Run the delete query
        result = subprocess.run([
            'psql',
            '-h', 'localhost',
            '-U', 'odoo',
            '-d', 'Npd_Transport',
            '-c', sql_query
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Successfully deleted invalid records!")
            print()
            print(result.stdout)
        else:
            print("Error:")
            print(result.stderr)
            return False
            
    except FileNotFoundError:
        print("Error: psql not found")
        print()
        print("Install PostgreSQL client tools first")
        print()
        print("Or use pgAdmin GUI:")
        print("1. Open https://localhost/pgadmin")
        print("2. Click SQL tab")
        print("3. Paste: DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN (SELECT id FROM vehicle_driver);")
        print("4. Click Execute")
        return False
    
    # Check result
    print()
    print("Checking results...")
    print()
    
    try:
        result = subprocess.run([
            'psql',
            '-h', 'localhost',
            '-U', 'odoo',
            '-d', 'Npd_Transport',
            '-c', 'SELECT COUNT(*) as total_records FROM vehicle_tracking;'
        ], capture_output=True, text=True)
        
        print(result.stdout)
        
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    print()
    print("=" * 60)
    print("Done! Ready to restart Odoo")
    print("=" * 60)
    print()
    print("Next step:")
    print("python odoo-bin")
    print()
    
    return True

if __name__ == '__main__':
    try:
        success = main()
    except Exception as e:
        print(f"Error: {e}")
        success = False
    
    input("Press Enter to exit...")
    sys.exit(0 if success else 1)
