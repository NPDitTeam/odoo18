# Vehicle Tracking Module for Odoo 18

## Description
This module provides real-time GPS tracking for vehicles using DistarGPS API.

## Features
- Real-time vehicle tracking
- Interactive map view with Google Maps integration
- Automatic data refresh every 5 minutes
- Vehicle status monitoring (Moving/Idle/Stopped)
- Engine status tracking
- Battery and signal monitoring
- Detailed vehicle information display

## Installation
1. Copy the module to your Odoo addons directory:
   `C:\Program Files\Odoo 18.0.20251009\server\custom-addons\vehicle_tracking`

2. Restart Odoo server

3. Go to Apps menu, update apps list

4. Search for "Vehicle Tracking" and install

## Configuration
The module is pre-configured with DistarGPS API credentials:
- API Endpoint: https://api.distargps.com/gps/realtime2
- Headers are set in the code (key, sign, x-key)

To change API credentials, edit the file:
`models/vehicle_tracking.py` in the `fetch_vehicle_data` method

## Usage
1. Open the "Vehicle Tracking" app from the main menu
2. Click "Refresh Data" to fetch current vehicle data
3. Click on any vehicle to view details
4. Use "View on Google Maps" button to see location
5. The system auto-refreshes data every 5 minutes

## Icon
Please add an icon file (PNG, 128x128) to:
`static/description/icon.png`

You can use any vehicle or GPS tracking icon.

## Requirements
- Odoo 18.0
- Python requests library (usually pre-installed)
- Internet connection for API access

## Support
For issues or questions, contact your system administrator.
