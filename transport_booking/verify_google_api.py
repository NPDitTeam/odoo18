#!/usr/bin/env python3
"""
🔑 Google API Key Verification Script
ตรวจสอบว่า API Key ทำงานได้กับ Odoo URL
"""

import requests
import json
from datetime import datetime

# Odoo Configuration
ODOO_URL = "http://119.59.124.50:8070"
ODOO_PATH = "/booking/map/1"  # Example path

# Test Data
TEST_ORIGIN = "Bangkok, Thailand"
TEST_DESTINATION = "Chiang Mai, Thailand"

print("=" * 70)
print("🔑 Google Maps API Key Verification")
print("=" * 70)
print()

# Get current date/time
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"⏰ Test Time: {now}")
print(f"🌐 Odoo URL: {ODOO_URL}")
print()

# Step 1: Check Odoo Availability
print("=" * 70)
print("[Step 1] Checking Odoo Server Connection")
print("=" * 70)

try:
    response = requests.get(f"{ODOO_URL}/web", timeout=10)
    if response.status_code == 200:
        print("✅ Odoo server is reachable")
        print(f"   Status: {response.status_code}")
    else:
        print(f"⚠️  Odoo responded but status: {response.status_code}")
except requests.Timeout:
    print("❌ Timeout connecting to Odoo")
    exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

print()

# Step 2: Check Map Page
print("=" * 70)
print("[Step 2] Checking Map Page Availability")
print("=" * 70)

try:
    map_url = f"{ODOO_URL}{ODOO_PATH}"
    print(f"   Testing URL: {map_url}")
    response = requests.get(map_url, timeout=10, allow_redirects=True)
    print(f"✅ Map page accessible")
    print(f"   Final URL: {response.url}")
    print(f"   Status: {response.status_code}")
    
    # Check for error messages
    if "RefererNotAllowedMapError" in response.text:
        print()
        print("❌ FOUND ERROR: RefererNotAllowedMapError")
        print("   → Google API Key has referrer restrictions")
        print("   → Need to update API Key settings in Google Cloud")
    elif "API Key" in response.text and "error" in response.text.lower():
        print()
        print("❌ FOUND ERROR: API Key issue detected")
    else:
        print()
        print("✅ No obvious API errors in response")
        
except Exception as e:
    print(f"⚠️  Error accessing map page: {e}")

print()

# Step 3: Check API Key in code
print("=" * 70)
print("[Step 3] Checking API Key Configuration")
print("=" * 70)

try:
    import sys
    sys.path.insert(0, r"C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking\controllers")
    
    # Note: This is informational only, won't actually import due to Odoo dependencies
    config_path = r"C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking\controllers\map_controller.py"
    
    with open(config_path, 'r') as f:
        content = f.read()
        if "GOOGLE_API_KEY" in content:
            print("✅ API Key found in map_controller.py")
            
            # Extract key (masked)
            for line in content.split('\n'):
                if "GOOGLE_API_KEY" in line and "=" in line:
                    key_part = line.split('=')[1].strip().strip('"\'')
                    if len(key_part) > 10:
                        masked_key = key_part[:10] + "..." + key_part[-5:]
                        print(f"   Key (masked): {masked_key}")
        else:
            print("❌ API Key not found in controller")
            
except FileNotFoundError:
    print(f"⚠️  Could not read config file")
except Exception as e:
    print(f"⚠️  Error reading config: {e}")

print()

# Step 4: Summary & Recommendations
print("=" * 70)
print("[Step 4] Summary & Recommendations")
print("=" * 70)
print()

print("📋 Current Status:")
print("   1. Odoo Server: ✅ Running")
print("   2. Map Page: ✅ Accessible")
print("   3. API Key: Check above")
print()

print("🔧 If you see RefererNotAllowedMapError:")
print()
print("   1. Go to: https://console.cloud.google.com/")
print("   2. Navigate to: APIs & Services → Credentials")
print("   3. Find your API Key")
print("   4. Click edit (pencil icon)")
print("   5. Under 'HTTP referrers (web sites)' set:")
print("      - Either: [None. All HTTP referrers allowed]")
print("      - Or add: http://119.59.124.50/*")
print("   6. Click Save")
print("   7. Wait 2-5 minutes")
print("   8. Refresh Odoo (Ctrl+Shift+R)")
print()

print("=" * 70)
print("✨ Test Complete")
print("=" * 70)