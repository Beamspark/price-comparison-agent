import json
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

class BauhausClient:
    def __init__(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            self.config = json.load(f).get("bauhaus", {})
            
        self.store_id = self.config.get("store_id", "352")
        self.cookie_store = self.config.get("cookie_selected_store", "")
        self.session = requests.Session(impersonate="chrome124")
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cookie": f"selectedStore={self.cookie_store}"
        }

    def obtener_precio(self, url: str) -> dict:
        """
        Extrae el precio actual y el nombre del producto en Bauhaus Alfafar (352).
        Retorna: {'precio': float, 'titulo': str, 'status': str}
        """
        try:
            resp = self.session.get(url, headers=self.headers, timeout=20)
            if resp.status_code != 200:
                return {"precio": None, "titulo": None, "status": f"HTTP_{resp.status_code}"}

            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 1. Extracción por Schema.org JSON-LD
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "")
                    if isinstance(data, dict) and data.get("@type") == "Product":
                        offers = data.get("offers", {})
                        p_val = offers.get("price") if isinstance(offers, dict) else (offers[0].get("price") if isinstance(offers, list) else None)
                        titulo = data.get("name")
                        if p_val is not None:
                            return {
                                "precio": float(p_val),
                                "titulo": titulo,
                                "status": "OK"
                            }
                except Exception:
                    continue

            # 2. Respaldo por meta tags
            meta_price = soup.find("meta", property="product:price:amount")
            meta_title = soup.find("meta", property="og:title")
            if meta_price and meta_price.get("content"):
                return {
                    "precio": float(meta_price.get("content")),
                    "titulo": meta_title.get("content") if meta_title else None,
                    "status": "OK"
                }

            return {"precio": None, "titulo": None, "status": "PRECIO_NO_ENCONTRADO"}

        except Exception as e:
            return {"precio": None, "titulo": None, "status": f"ERROR: {str(e)}"}