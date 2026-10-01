import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.obramat.es/",
    "Upgrade-Insecure-Requests": "1"
}

# Tienda 42: Obramat Murcia Norte (Churra)
COOKIES = {
    "customer_context": '{"main_store":"42","city":"Murcia","postcode":"30003","stores_name":[{"name":"Obramat Murcia Norte (Churra)","id":"42"}]}'
}

# Familias canónicas completas de herramientas y maquinaria
FAMILIAS_OBJETIVO = [
    # Herramientas electroportátiles
    {"categoria": "Electroportátil - Taladros y Atornilladores", "url": "https://www.obramat.es/herramientas/herramientas-electricas-portatiles/taladros-percutores/"},
    {"categoria": "Electroportátil - Amoladoras", "url": "https://www.obramat.es/herramientas/herramientas-electricas-portatiles/amoladoras/"},
    {"categoria": "Electroportátil - Martillos", "url": "https://www.obramat.es/herramientas/herramientas-electricas-portatiles/martillos-perforadores-demoledores/"},
    {"categoria": "Electroportátil - Sierras e Ingletadoras", "url": "https://www.obramat.es/herramientas/herramientas-electricas-portatiles/sierras-circulares-ingletadoras/"},
    {"categoria": "Electroportátil - Batidores y Mezcladores", "url": "https://www.obramat.es/search?q=mezclador+mortero+batidor"},
    
    # Corte cerámico y alicatado (Cortag, Rubi, Bellota)
    {"categoria": "Corte Cerámico - Cortadoras Manuales", "url": "https://www.obramat.es/search?q=cortadora+manual+ceramica"},
    {"categoria": "Corte Cerámico - Mesas y Cortadoras Eléctricas", "url": "https://www.obramat.es/search?q=mesa+corte+electrica+agua"},
    
    # Maquinaria de obra, taller y neumática
    {"categoria": "Maquinaria - Compresores de Aire", "url": "https://www.obramat.es/search?q=compresor+aire"},
    {"categoria": "Maquinaria - Generadores Eléctricos", "url": "https://www.obramat.es/search?q=generador+electrico"},
    {"categoria": "Maquinaria - Soldadura Inverter", "url": "https://www.obramat.es/search?q=soldador+inverter+grupo"},
    {"categoria": "Maquinaria - Hormigoneras", "url": "https://www.obramat.es/search?q=hormigonera"},
    
    # Medición y nivelación técnica
    {"categoria": "Medición - Niveles Láser", "url": "https://www.obramat.es/search?q=nivel+laser+autonivelante"}
]

# Extracción de marcas conocidas y códigos técnicos
MARCAS_DETECCION = [
    "CORTAG", "RUBI", "BOSCH", "DEWALT", "MAKITA", "BELLOTA", "STAYER", 
    "CEVIK", "AYERBE", "MICHELIN", "PRAMAC", "STANLEY", "MILWAUKEE", "KOMA TOOLS"
]

PATRONES_CODIGO = [
    # Cortag (ej. Master, Top, Mega, Zapp, Flex)
    r"\b(MASTER\-[0-9]{2,3})\b",
    r"\b(TOP\-[0-9]{2,3})\b",
    r"\b(MEGA\-[0-9]{2,4})\b",
    r"\b(HD\-[0-9]{2,4})\b",
    
    # Rubi (Speed, Fast, Star, TZ, TX, HIT, TS)
    r"\b(SPEED\-[0-9]{2,3}(?:\s*MAGNET)?)\b",
    r"\b(FAST\-[0-9]{2,3})\b",
    r"\b(STAR\-[0-9]{2,3}(?:\s*PLATINUM)?)\b",
    r"\b(HIT\-[0-9]{3,4}(?:\s*N|\s*PLUS)?)\b",
    r"\b(TZ\-[0-9]{3,4})\b",
    r"\b(TX\-[0-9]{3,4}\s*MAX)\b",
    r"\b(TS\-[0-9]{2,3}\s*MAX)\b",
    
    # DeWalt
    r"\b(DCK[0-9A-Z\-]+)\b",
    r"\b(DCD[0-9A-Z\-]+)\b",
    r"\b(DCF[0-9A-Z\-]+)\b",
    r"\b(DCG[0-9A-Z\-]+)\b",
    r"\b(DCH[0-9A-Z\-]+)\b",
    r"\b(DCS[0-9A-Z\-]+)\b",
    
    # Bosch Professional
    r"\b(GSB\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    r"\b(GSR\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    r"\b(GWS\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    r"\b(GBH\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    
    # Makita
    r"\b(DHP[0-9A-Z\-]+)\b",
    r"\b(DDF[0-9A-Z\-]+)\b",
    r"\b(DF[0-9A-Z\-]+)\b",
    r"\b(DGA[0-9A-Z\-]+)\b",
    r"\b(DHR[0-9A-Z\-]+)\b",
    r"\b(HR[0-9]{4}[A-Z\-]*)\b",
    r"\b(GA[0-9]{4}[A-Z\-]*)\b",
    
    # Generadores / Compresores (Ayerbe, Cevik)
    r"\b(AY\-[0-9]{3,4}[A-Z\-]*)\b",
    r"\b(PRO\s*[0-9]+)\b"
]

def extraer_marca(titulo):
    titulo_up = titulo.upper()
    for m in MARCAS_DETECCION:
        if m in titulo_up:
            return m
    return "OTRA / MARCA BLANCA"

def extraer_codigo(titulo):
    for pat in PATRONES_CODIGO:
        m = re.search(pat, titulo.upper())
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None

def extraer_pagina(url):
    try:
        r = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=20)
        if r.status_code != 200:
            return [], False
    except Exception:
        return [], False

    soup = BeautifulSoup(r.text, "html.parser")
    articulos = soup.find_all("article")
    if not articulos:
        enlaces_directos = soup.find_all("a", href=re.compile(r"/productos/.*-\d+\.html"))
        articulos = [a.find_parent("div") for a in enlaces_directos if a.find_parent("div")]

    productos = []
    for art in articulos:
        enlace = art.find("a", href=re.compile(r"/productos/.*-\d+\.html"))
        if not enlace:
            continue

        href = enlace.get("href", "")
        match_id = re.search(r"-(\d+)\.html", href)
        if not match_id:
            continue
        ref_id = match_id.group(1)

        texto_card = art.get_text(separator=" ", strip=True)
        match_precio = re.search(r"(\d+[.,]?\d*)\s*[€]", texto_card)
        if not match_precio:
            continue

        try:
            precio = float(match_precio.group(1).replace(".", "").replace(",", "."))
        except:
            continue

        titulo = enlace.get_text(strip=True)
        if len(titulo) < 6:
            h_tag = art.find(["h2", "h3", "h4"])
            titulo = h_tag.get_text(strip=True) if h_tag else ""

        if not titulo or len(titulo) < 6:
            continue

        url_completa = href if href.startswith("http") else f"https://www.obramat.es{href}"

        productos.append({
            "referencia_local": ref_id,
            "marca": extraer_marca(titulo),
            "codigo_fabricante": extraer_codigo(titulo),
            "titulo": titulo,
            "precio_churra": precio,
            "url": url_completa
        })

    # Si hay enlace "next" o encontramos productos en esta página, permitimos seguir
    hay_mas = bool(soup.find("a", class_=re.compile(r"next|pagination__next"))) or len(productos) > 0
    return productos, hay_mas

def ejecutar_barrido_completo():
    print("=" * 70)
    print("BARRIDO EXHAUSTIVO DE MAQUINARIA Y CORTE - OBRAMAT CHURRA")
    print("=" * 70)

    censo_maestro = {}

    for fam in FAMILIAS_OBJETIVO:
        print(f"\n[Procesando Familia] {fam['categoria']}")
        pagina = 1
        
        while True:
            sep = "&" if "?" in fam["url"] else "?"
            url_pag = f"{fam['url']}{sep}p={pagina}" if pagina > 1 else fam["url"]
            
            prods, hay_mas = extraer_pagina(url_pag)
            
            # Si no devolvió productos nuevos, terminamos esta familia
            nuevos_en_pagina = 0
            for p in prods:
                ref = p["referencia_local"]
                if ref not in censo_maestro:
                    p["subfamilia"] = fam["categoria"]
                    censo_maestro[ref] = p
                    nuevos_en_pagina += 1
            
            print(f"  Pág {pagina}: {len(prods)} detectados ({nuevos_en_pagina} nuevos incorporados)")

            if len(prods) == 0 or nuevos_en_pagina == 0 or not hay_mas:
                break
                
            pagina += 1
            time.sleep(1.2)

    catalogo = list(censo_maestro.values())
    catalogo.sort(key=lambda x: x["precio_churra"], reverse=True)

    with open("catalogo_maestro_obramat.json", "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)

    con_codigo = sum(1 for x in catalogo if x["codigo_fabricante"])
    marcas_resumen = {}
    for x in catalogo:
        marcas_resumen[x["marca"]] = marcas_resumen.get(x["marca"], 0) + 1

    print("\n" + "=" * 70)
    print(f"CENSO TOTAL CONSOLIDADO: {len(catalogo)} referencias maestras en Churra.")
    print(f"Listas con código técnico unívoco: {con_codigo} ({round(con_codigo/len(catalogo)*100, 1)}%)")
    print("\nDistribución por fabricante en inventario:")
    for marca, cant in sorted(marcas_resumen.items(), key=lambda item: item[1], reverse=True):
        print(f"  - {marca}: {cant} referencias")
    print("=" * 70)

if __name__ == "__main__":
    ejecutar_barrido_completo()