#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix Countdown Timer - แก้ไขปัญหา tracking_interval ไม่แปลงหน่วยนาทีเป็น milliseconds
"""

import os
import sys

# Path to the file
FILE_PATH = r"C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking\views\tracking_map_food_delivery.xml"

print("=" * 60)
print(" FIX COUNTDOWN TIMER")
print("=" * 60)
print()

# Check if file exists
if not os.path.exists(FILE_PATH):
    print(f"❌ Error: File not found: {FILE_PATH}")
    sys.exit(1)

print(f"📄 Reading file: {FILE_PATH}")

# Read the file
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

original_content = content

# Apply fixes
replacements = [
    # Fix 1: บรรทัด 776 - เพิ่ม * 60
    (
        "updateInterval = (userSettings.tracking_interval || 5) * 1000;",
        "// ✅ FIX: tracking_interval เป็นหน่วยนาที ต้องแปลงเป็น milliseconds ด้วย * 60 * 1000\n                                updateInterval = (userSettings.tracking_interval || 5) * 60 * 1000;"
    ),
    
    # Fix 2: บรรทัด 779 - เพิ่ม minutes ใน console.log
    (
        "console.log(`⏱️  Update interval: ${updateInterval}ms`);",
        "console.log(`⏱️  Update interval: ${updateInterval}ms (${userSettings.tracking_interval} minutes)`);"
    ),
    
    # Fix 3: บรรทัด 782 - เปลี่ยนจาก s เป็น นาที
    (
        "`⏱️ อัพเดททุก ${userSettings.tracking_interval}s`;",
        "`⏱️ อัพเดททุก ${userSettings.tracking_interval} นาที`;"
    ),
    
    # Fix 4: บรรทัด 793 - เปลี่ยนจาก 5s เป็น 5 นาที (else block)
    (
        "`⏱️ อัพเดททุก 5s (ค่าเริ่มต้น)`;",
        "`⏱️ อัพเดททุก 5 นาที (ค่าเริ่มต้น)`;"
    ),
]

# Apply all replacements
changes_made = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)  # Replace only first occurrence
        changes_made += 1
        print(f"✅ Fixed: {old[:50]}...")
    else:
        print(f"⚠️  Not found (might be already fixed): {old[:50]}...")

print()
print(f"📊 Changes made: {changes_made}/{len(replacements)}")

if content != original_content:
    print()
    print("💾 Writing changes to file...")
    
    # Create backup
    backup_path = FILE_PATH + ".backup"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(original_content)
    print(f"✅ Backup created: {backup_path}")
    
    # Write modified content
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ File updated: {FILE_PATH}")
    
    print()
    print("=" * 60)
    print(" SUCCESS!")
    print("=" * 60)
    print()
    print("🎉 Countdown timer fixed successfully!")
    print()
    print("Next steps:")
    print("1. Run 'FIX_COUNTDOWN_TIMER.bat' to restart Odoo")
    print("2. Refresh the tracking map page in your browser")
    print("3. The countdown should now show correct minutes")
    print()
else:
    print()
    print("=" * 60)
    print(" NO CHANGES NEEDED")
    print("=" * 60)
    print()
    print("The file appears to be already fixed or no changes were found.")
    print()

input("Press Enter to exit...")
