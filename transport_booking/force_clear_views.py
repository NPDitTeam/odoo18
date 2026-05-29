#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run this script in Odoo shell to force clear view cache:

python odoo-bin shell -d Npd_Transport -c odoo.conf
>>> exec(open('custom-addons/transport_booking/force_clear_views.py').read())
"""

print("="*60)
print("Force Clear Views Cache")
print("="*60)

try:
    # Get environment
    if 'env' not in globals():
        print("❌ Error: Must run in Odoo shell")
        print("Run: python odoo-bin shell -d Npd_Transport -c odoo.conf")
        exit(1)
    
    # Find tracking_map_template view
    print("\n[1] Finding tracking_map_template view...")
    views = env['ir.ui.view'].sudo().search([
        ('name', 'ilike', 'tracking_map'),
    ])
    
    print(f"Found {len(views)} views:")
    for view in views:
        print(f"  - ID: {view.id}, Name: {view.name}, XML ID: {view.xml_id}")
    
    # Clear view cache
    print("\n[2] Clearing view cache...")
    env['ir.ui.view'].sudo().clear_caches()
    print("✅ View cache cleared")
    
    # Clear QWeb cache
    print("\n[3] Clearing QWeb template cache...")
    env['ir.qweb'].sudo().clear_caches()
    print("✅ QWeb cache cleared")
    
    # Clear config parameter cache
    print("\n[4] Clearing config parameter cache...")
    env['ir.config_parameter'].sudo().clear_caches()
    
    # Check Google Maps API key
    print("\n[5] Checking Google Maps API key...")
    api_keys = env['ir.config_parameter'].sudo().search([
        ('key', 'ilike', 'google')
    ])
    for key in api_keys:
        print(f"  - {key.key}: {key.value[:30]}..." if len(key.value) > 30 else f"  - {key.key}: {key.value}")
    
    # Commit changes
    print("\n[6] Committing changes...")
    env.cr.commit()
    print("✅ Changes committed")
    
    print("\n" + "="*60)
    print("✅ All caches cleared successfully!")
    print("="*60)
    print("\nNext steps:")
    print("1. Restart Odoo service")
    print("2. Clear browser cache")
    print("3. Test tracking map")
    print("="*60)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
