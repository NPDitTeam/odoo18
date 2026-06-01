import logging
import requests
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

GOOGLE_API_KEY = "AIzaSyCHKkMOyDdI29v52SULcRx_OcB3i-MD7lw"
PLACES_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"


class NpdPlaceAutocompleteController(http.Controller):
    """ Proxy เรียก Google Places API (New) ผ่าน Odoo backend
        เพื่อเลี่ยงปัญหา CORS / เวอร์ชัน Google Maps JS ที่ชนกับโมดูลอื่น """

    @http.route("/npd/place_autocomplete", type="json", auth="user")
    def place_autocomplete(self, input=None, **kw):
        text = (input or "").strip()
        if len(text) < 2:
            return {"suggestions": []}
        try:
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_API_KEY,
            }
            body = {
                "input": text,
                "includedRegionCodes": ["th"],
                "languageCode": "th",
            }
            resp = requests.post(PLACES_AUTOCOMPLETE_URL, headers=headers, json=body, timeout=8)
            data = resp.json()
            suggestions = []
            for item in data.get("suggestions", []):
                pred = item.get("placePrediction") or {}
                full_text = (pred.get("text") or {}).get("text")
                if not full_text:
                    continue
                sf = pred.get("structuredFormat") or {}
                main = (sf.get("mainText") or {}).get("text") or full_text
                secondary = (sf.get("secondaryText") or {}).get("text") or ""
                suggestions.append({
                    "text": full_text,
                    "main": main,
                    "secondary": secondary,
                })
            return {"suggestions": suggestions}
        except Exception as e:
            _logger.error("Place Autocomplete proxy error: %s", e)
            return {"suggestions": [], "error": str(e)}
