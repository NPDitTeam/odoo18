#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
🔍 Rating Link Diagnostic Script
Checks all rating records to identify why links are showing as expired
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'odoo.settings')
sys.path.insert(0, r'C:\Program Files\Odoo 18.0.20251009\server')

# Connect to Odoo
import odoo
from odoo import api, _
from odoo.tools import config

# Configuration
config.set_xmlrpc_port(8069)
config['db_name'] = 'odoo18'  # Change to your database name

def diagnose_rating_links():
    """Check all rating records and identify issues"""
    print("\n" + "="*80)
    print("🔍 RATING LINK DIAGNOSTIC TOOL")
    print("="*80 + "\n")
    
    with api.Environment.manage():
        # Get environment
        env = api.Environment(odoo.sql_db.db_connect('odoo18').cursor(), 2, {})
        
        # Get all ratings
        ratings = env['delivery.rating'].search([])
        
        print(f"📊 Total rating records: {len(ratings)}\n")
        
        # Count by state
        pending = ratings.filtered(lambda r: r.state == 'pending')
        done = ratings.filtered(lambda r: r.state == 'done')
        expired = ratings.filtered(lambda r: r.state == 'expired')
        
        print(f"📈 Statistics:")
        print(f"   ✓ Pending (can be rated): {len(pending)}")
        print(f"   ✓ Done (already rated): {len(done)}")
        print(f"   ✗ Expired (expired): {len(expired)}")
        
        print("\n" + "-"*80)
        print("🔗 RATING LINKS DETAIL")
        print("-"*80 + "\n")
        
        for rating in ratings[:20]:  # Show first 20
            status = "✓ OK" if rating.state != 'expired' else "✗ EXPIRED"
            print(f"{status} | Booking: {rating.booking_id.name}")
            print(f"       Token: {rating.rating_token}")
            print(f"       State: {rating.state}")
            print(f"       Link: /rating/{rating.rating_token}")
            print(f"       Driver: {rating.driver_name}")
            print()
        
        print("\n" + "-"*80)
        print("⚠️  COMMON ISSUES & SOLUTIONS")
        print("-"*80 + "\n")
        
        if len(expired) > 0:
            print(f"1. ❌ {len(expired)} rating(s) marked as EXPIRED")
            print("   → Solution: Reset them to pending using the action button\n")
        
        # Check for duplicate tokens
        token_counts = {}
        for rating in ratings:
            token_counts[rating.rating_token] = token_counts.get(rating.rating_token, 0) + 1
        
        duplicates = {k: v for k, v in token_counts.items() if v > 1}
        if duplicates:
            print(f"2. ❌ {len(duplicates)} duplicate token(s) found")
            print("   → Solution: Check database for token conflicts\n")
        
        # Check for missing booking_id
        missing_booking = ratings.filtered(lambda r: not r.booking_id)
        if missing_booking:
            print(f"3. ❌ {len(missing_booking)} rating(s) with missing booking")
            print("   → Solution: Delete these orphaned records\n")
        
        print("-"*80)
        print("✅ NEXT STEPS")
        print("-"*80)
        print("""
1. In Odoo, go to: Transport Booking > Ratings
2. For each EXPIRED link:
   - Click the record
   - Change state back to "pending"
   - Save
3. Test the link again
4. Restart Odoo server after making changes

Command: restart the server
- Windows: Press Ctrl+C in terminal, then run: start_odoo.bat
- Linux: sudo systemctl restart odoo18
        """)

if __name__ == '__main__':
    try:
        diagnose_rating_links()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nNote: Make sure Odoo is running and database name is correct")
