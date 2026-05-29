#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to set Google Maps API Key in Odoo System Parameters
Run this from Odoo shell:
    python odoo-bin shell -d Npd_Transport -c odoo.conf --addons-path=addons,custom-addons
    >>> exec(open('custom-addons/transport_booking/set_google_api_key.py').read())
"""

import logging

_logger = logging.getLogger(__name__)

def set_google_maps_api_key():
    """Set Google Maps API Key in Odoo System Parameters"""
    try:
        # API Key สำหรับ Odoo18
        api_key = 'AIzaSyAorvWR_BL6tgkNgkkRO4NIb8ZTKq92S3U'
        
        # ค้นหา config parameter ที่มีอยู่
        IrConfigParameter = env['ir.config_parameter'].sudo()
        
        # ลบ config เก่าถ้ามี
        existing = IrConfigParameter.search([('key', '=', 'google_maps_api_key')])
        if existing:
            existing.unlink()
            _logger.info("🗑️  Deleted existing google_maps_api_key")
        
        # สร้างใหม่
        IrConfigParameter.create({
            'key': 'google_maps_api_key',
            'value': api_key
        })
        
        print("✅ Google Maps API Key has been set successfully!")
        print(f"   Key: google_maps_api_key")
        print(f"   Value: {api_key}")
        
        # Verify
        saved_key = IrConfigParameter.get_param('google_maps_api_key')
        if saved_key == api_key:
            print("✅ Verification successful!")
        else:
            print("❌ Verification failed!")
        
        env.cr.commit()
        print("💾 Changes committed to database")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

# Run the function
if __name__ == '__main__' or 'env' in globals():
    set_google_maps_api_key()
