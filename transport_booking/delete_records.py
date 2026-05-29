#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delete Invalid Records from vehicle_tracking
"""

import sys

def main():
    print()
    print("=" * 60)
    print("Deleting Invalid Records from vehicle_tracking")
    print("=" * 60)
    print()
    
    try:
        import psycopg2
        print("✓ psycopg2 loaded successfully")
    except ImportError:
        print("Installing psycopg2-binary...")
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'psycopg2-binary'], 
                       capture_output=True)
        import psycopg2
        print("✓ psycopg2 installed")
    
    print()
    print("Connecting to database...")
    
    try:
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='Npd_Transport',
            user='odoo18',
            password='odoo18'
        )
        cursor = conn.cursor()
        
        print("✓ Connected successfully!")
        print()
        print("Deleting invalid records...")
        print()
        
        # Delete query
        sql = """DELETE FROM vehicle_tracking 
                 WHERE driver_id IS NOT NULL 
                 AND driver_id NOT IN (SELECT id FROM vehicle_driver)"""
        
        cursor.execute(sql)
        deleted = cursor.rowcount
        conn.commit()
        
        print(f"  Deleted: {deleted} invalid records")
        print()
        
        # Check remaining
        print("Checking remaining records...")
        cursor.execute("SELECT COUNT(*) FROM vehicle_tracking")
        remaining = cursor.fetchone()[0]
        print(f"  Total records: {remaining}")
        
        cursor.close()
        conn.close()
        
        print()
        print("=" * 60)
        print("✓ Done! Ready to restart Odoo")
        print("=" * 60)
        print()
        print("Next command:")
        print("  cd C:\\Program Files\\Odoo 18.0.20251009\\server")
        print("  python odoo-bin")
        print()
        
        return True
        
    except Exception as e:
        print()
        print("=" * 60)
        print("✗ Error occurred:")
        print("=" * 60)
        print(f"{e}")
        print()
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    input("Press Enter to exit...")
    sys.exit(0 if success else 1)
