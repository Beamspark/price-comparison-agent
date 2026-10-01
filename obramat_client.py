import json
import re
import urllib.parse
from curl_cffi import requests

class ObramatClient:
    def __init__(self, store_config: dict):
        self.store = store_config
        self.session = requests.Session(impersonate="firefox")
        self.headers = self._construir_headers()

    def _construir_headers(self) -> dict:
        # Construye el contexto y lo codifica exactamente en URL (%XX)
        contexto_dict = {
            "auto_context": "false",
            "nearby_stores": "",
            "city": self.store["ciudad"],
            "latitude": self.store["lat"],
            "main_store": str(self.store["id"]),
            "postcode": self.store["cp"],
            "stores_name": [{
                "name": self.store["nombre"].replace(" ", "+"),
                "id": str(self.store["id"])
            }],
            "white_zone": "true",
            "longitude": self.store["lon"]
        }
        
        contexto_json = json.dumps(contexto_dict, separators=(',', ':'))
        contexto_encoded = urllib.parse.quote(contexto_json)
        
        cookie_header = (
            f"customer_context={contexto_encoded}; "
            f"cctx=%7B%22cctxId%22%3A%2267747b27-8386-409a-8f6f-b0d8b5a3cc1f%22%7D"
        )

        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Cookie": cookie_header
        }

    def obtener_precio(self, url: str) -> float | None:
        if not url:
            return None
        try:
            r = self.session.get(url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                return None

            # Extracción por bloque visual con IVA
            match_iva = re.findall(r'(\d+(?:[.,]\d+)?)\s*€?\s*IVA', r.text, re.IGNORECASE)
            if match_iva:
                return float(match_iva[0].replace(".", "").replace(",", "."))

        except Exception as e:
            print(f"[ObramatClient Error] {url[:50]}: {e}")
        return None