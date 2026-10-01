import json
import re
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from bauhaus_client import BauhausClient

BASE_DIR = Path(__file__).resolve().parent
MAESTRO_PATH = BASE_DIR / "catalogo_maestro_obramat.json"

bh = BauhausClient()

with open(MAESTRO_PATH, "r", encoding="utf-8") as f:
    productos_ob = json.load(f)

print("Iniciando cruce automatico contra Bauhaus (Store 352 - Alfafar)...")
print(f"Total productos en maestro Obramat: {len(productos_ob)}\n")

candidatos_bauhaus = []

STOP_WORDS = {
    "TALADRO", "PERCUTOR", "BATERIA", "BATERÍA", "AMOLADORA", "ANGULAR", 
    "GENERADOR", "ELECTRICO", "ELÉCTRICO", "GASOLINA", "INVERTER", 
    "SOLDADOR", "CORTADOR", "AZULEJOS", "MANUAL", "SIERRA", "SABLE", 
    "BRUSHLESS", "PACK", "MOTOR", "CON", "DE", "Y", "+", "DEWALT", "BOSCH", "MAKITA", "STAYER", "RUBI"
}

def extraer_modelo(titulo, marca):
    tokens = [t for t in re.split(r'[\s/]+', titulo.upper()) if t not in STOP_WORDS]
    # Buscar tokens con letras y numeros (modelos tecnicos tipo GSB, DCD, GA9020)
    modelos = [t for t in tokens if re.search(r'\d', t)]
    if modelos:
        return f"{marca} {modelos[0]}"
    return f"{marca} {tokens[0]}" if tokens else marca

for i, prod in enumerate(productos_ob, 1):
    marca = prod.get("marca") or prod.get("brand", "")
    titulo = prod.get("titulo") or prod.get("name", "")
    id_ob = prod.get("id_obramat") or prod.get("id", "")

    if not marca or marca.upper() == "SIN MARCA":
        continue

    termino = extraer_modelo(titulo, marca)
    query_enc = urllib.parse.quote(termino)
    url_search = f"https://www.bauhaus.es/search?q={query_enc}&availability=352"

    try:
        resp = bh.session.get(url_search, headers=bh.headers, timeout=15)
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Buscar enlaces que lleven a ficha de producto (/p/NUMERO)
        links = soup.find_all("a", href=re.compile(r"/p/\d+"))
        if not links:
            continue

        hrefs_vistos = set()
        primer_link = None
        for a in links:
            href = a.get("href", "")
            if "/p/" in href and href not in hrefs_vistos:
                primer_link = f"https://www.bauhaus.es{href}" if href.startswith("/") else href
                break

        if primer_link:
            datos_precio = bh.obtener_precio(primer_link)
            if datos_precio.get("precio"):
                print(f"[{i}/{len(productos_ob)}] MATCH ENCONTRADO")
                print(f"  Obramat: {titulo} ({marca})")
                print(f"  Bauhaus: {datos_precio.get('titulo')} -> {datos_precio.get('precio')} €")
                print(f"  URL:     {primer_link}\n")

                candidatos_bauhaus.append({
                    "id_obramat": id_ob,
                    "titulo_obramat": titulo,
                    "marca": marca,
                    "bauhaus": {
                        "titulo": datos_precio.get("titulo"),
                        "precio": datos_precio.get("precio"),
                        "url": primer_link
                    }
                })

    except Exception:
        continue

output_path = BASE_DIR / "candidatos_bauhaus.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(candidatos_bauhaus, f, indent=2, ensure_ascii=False)

print(f"\nProceso finalizado. Se han encontrado {len(candidatos_bauhaus)} coincidencias.")
print(f"Guardados en: {output_path.name}")