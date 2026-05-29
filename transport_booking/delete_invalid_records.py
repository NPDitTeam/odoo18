import sys
import psycopg2

print()
print("=" * 60)
print("Deleting Invalid Records from vehicle_tracking")
print("=" * 60)
print()

try:
    print("Connecting to database...")
    
    conn = psycopg2.connect(
        host='localhost',
        port=5434,
        database='Npd_Transport',
        user='odoo18',
        password='odoo18'
    )
    cursor = conn.cursor()
    
    print("Connected successfully!")
    print()
    print("Deleting invalid records...")
    print()
    
    sql = "DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN (SELECT id FROM vehicle_driver)"
    
    cursor.execute(sql)
    deleted = cursor.rowcount
    conn.commit()
    
    print("  Deleted: {} records".format(deleted))
    print()
    print("Checking remaining records...")
    
    cursor.execute("SELECT COUNT(*) FROM vehicle_tracking")
    remaining = cursor.fetchone()[0]
    print("  Total records: {}".format(remaining))
    
    cursor.close()
    conn.close()
    
    print()
    print("=" * 60)
    print("Done! Ready to restart Odoo")
    print("=" * 60)
    print()
    
except Exception as e:
    print("Error: {}".format(e))
    import traceback
    traceback.print_exc()

input("Press Enter to exit...")
