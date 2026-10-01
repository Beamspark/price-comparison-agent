import os
import json
import re
import time
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi import requests

BASE_DIR = Path(__file__).resolve().parent

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

# Familias canónicas ampliadas: Electroportátil, Corte, Taller, Energía y Limpieza
FAMILIAS_OBJETIVO = [
    # 1. Electroportátil básico
    {"categoria": "Electroportátil - Taladros y Atornilladores", "url": "https://www.obramat.es/herramientas/herramientas-electricas-portatiles/taladros-percutores/"},
    {"categoria": "Electroportátil - Amoladoras", "url": "https://www.obramat.es/herramientas/herramientas-electricas-portatiles/amoladoras/"},
    {"categoria": "Electroportátil - Martillos", "url": "https://www.obramat.es/herramientas/herramientas-electricas-portatiles/martillos-perforadores-demoledores/"},
    {"categoria": "Electroportátil - Batidores y Mezcladores", "url": "https://www.obramat.es/search?q=mezclador+mortero+batidor"},

    # 2. Madera, Metal y Corte Estacionario
    {"categoria": "Corte - Ingletadoras y Tronzadoras", "url": "https://www.obramat.es/search?q=ingletadora+tronzadora"},
    {"categoria": "Corte - Sierras de Mesa y Circulares", "url": "https://www.obramat.es/search?q=sierra+mesa+circular"},
    {"categoria": "Corte - Sierras de Sable y Caladoras", "url": "https://www.obramat.es/search?q=sierra+sable+caladora"},

    # 3. Cerámica y Alicatado Profesional
    {"categoria": "Corte Cerámico - Cortadoras Manuales", "url": "https://www.obramat.es/search?q=cortadora+manual+ceramica"},
    {"categoria": "Corte Cerámico - Mesas y Cortadoras Eléctricas", "url": "https://www.obramat.es/search?q=mesa+corte+electrica+agua"},

    # 4. Maquinaria Pesada, Neumática y Energía
    {"categoria": "Maquinaria - Compresores de Aire", "url": "https://www.obramat.es/search?q=compresor+aire"},
    {"categoria": "Maquinaria - Generadores Eléctricos", "url": "https://www.obramat.es/search?q=generador+electrico"},
    {"categoria": "Maquinaria - Soldadura Inverter", "url": "https://www.obramat.es/search?q=soldador+inverter+grupo"},
    {"categoria": "Maquinaria - Hormigoneras", "url": "https://www.obramat.es/search?q=hormigonera"},

    # 5. Limpieza Industrial y Medición
    {"categoria": "Limpieza - Hidrolimpiadoras y LAP", "url": "https://www.obramat.es/search?q=hidrolimpiadora+alta+presion"},
    {"categoria": "Limpieza - Aspiradores Industriales", "url": "https://www.obramat.es/search?q=aspirador+seco+humedo+industrial"},
    {"categoria": "Medición - Niveles Láser", "url": "https://www.obramat.es/search?q=nivel+laser+autonivelante"}
]

MARCAS_DETECCION = [
    "CORTAG", "RUBI", "BOSCH", "DEWALT", "MAKITA", "BELLOTA", "STAYER", 
    "CEVIK", "AYERBE", "MICHELIN", "PRAMAC", "GENERGY", "STANLEY", 
    "MILWAUKEE", "KOMA TOOLS", "KARCHER", "NILFISK", "EINHELL", "BLACK+DECKER"
]

PATRONES_CODIGO = [
    # Cortag
    r"\b(MASTER\-[0-9]{2,3})\b",
    r"\b(TOP\-[0-9]{2,3})\b",
    r"\b(MEGA\-[0-9]{2,4})\b",
    r"\b(HD\-[0-9]{2,4})\b",
    
    # Rubi
    r"\b(SPEED\-[0-9]{2,3}(?:\s*MAGNET)?)\b",
    r"\b(FAST\-[0-9]{2,3})\b",
    r"\b(STAR\-[0-9]{2,3}(?:\s*PLATINUM)?)\b",
    r"\b(HIT\-[0-9]{3,4}(?:\s*N|\s*PLUS)?)\b",
    r"\b(TZ\-[0-9]{3,4})\b",
    r"\b(TX\-[0-9]{3,4}\s*MAX)\b",
    r"\b(TS\-[0-9]{2,3}\s*MAX)\b",
    
    # DeWalt (Taladros, amoladoras, ingletadoras DWS/DWE, sables DCS)
    r"\b(DCK[0-9A-Z\-]+)\b",
    r"\b(DCD[0-9A-Z\-]+)\b",
    r"\b(DCF[0-9A-Z\-]+)\b",
    r"\b(DCG[0-9A-Z\-]+)\b",
    r"\b(DCH[0-9A-Z\-]+)\b",
    r"\b(DCS[0-9A-Z\-]+)\b",
    r"\b(DWS[0-9A-Z\-]+)\b",
    r"\b(DWE[0-9A-Z\-]+)\b",
    
    # Bosch Professional (GSB, GSR, GWS, GBH, GCM ingletadoras, GTS sierras mesa, GSA sable)
    r"\b(GSB\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    r"\b(GSR\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    r"\b(GWS\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    r"\b(GBH\s*[0-9]+[A-Z\-0-9]*(?:\s*[A-Z]{1,3})?)\b",
    r"\b(GCM\s*[0-9]+[A-Z\-0-9]*)\b",
    r"\b(GTS\s*[0-9]+[A-Z\-0-9]*)\b",
    r"\b(GSA\s*[0-9]+[A-Z\-0-9]*)\b",
    
    # Makita (DHP, DDF, DGA, DHR, HR, GA, LS ingletadoras, JR sable, MLT mesa)
    r"\b(DHP[0-9A-Z\-]+)\b",
    r"\b(DDF[0-9A-Z\-]+)\b",
    r"\b(DF[0-9A-Z\-]+)\b",
    r"\b(DGA[0-9A-Z\-]+)\b",
    r"\b(DHR[0-9A-Z\-]+)\b",
    r"\b(HR[0-9]{4}[A-Z\-]*)\b",
    r"\b(GA[0-9]{4}[A-Z\-]*)\b",
    r"\b(LS[0-9]{4}[A-Z\-]*)\b",
    r"\b(JR[0-9]{4}[A-Z\-]*)\b",
    r"\b(MLT[0-9]{3}[A-Z\-]*)\b",
    
    # Hidrolimpiadoras Kärcher y Nilfisk (K2, K3, K4, K5, K7, Core, Premium)
    r"\b(K\s*[2-7](?:\s*POWER\s*CONTROL|\s*SMART\s*CONTROL|\s*PREMIUM)?)\b",
    r"\b(CORE\s*[0-9]{2,3})\b",

    # Generadores y Compresores (Ayerbe, Cevik, Genergy)
    r"\b(AY\-[0-9]{3,4}[A-Z\-]*)\b",
    r"\b(PRO\s*[0-9]+[A-Z\-]*)\b",
    r"\b(CA\-[0-9A-Z\-]+)\b"
]

session = requests.Session(impersonate="firefox")

def extraer_marca(titulo):
    titulo_up = titulo.upper()
    for m in MARCAS_DETECCION:
        if re.search(rf"\b{re.escape(m)}\b", titulo_up):
            return m
    return "OTRA"

def extraer_codigo(titulo):
    for pat in PATRONES_CODIGO:
        m = re.search(pat, titulo.upper())
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None

def extraer_pagina(url):
    try:
        r = session.get(url, headers=HEADERS, cookies=COOKIES, timeout=25)
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
        match_id = re.search(r"-(\d{8})\.html", href)
        if not match_id:
            # Fallback para IDs numéricos de longitud variable
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
        except Exception:
            continue

        titulo = enlace.get_text(strip=True)
        if len(titulo) < 6:
            h_tag = art.find(["h2", "h3", "h4"])
            titulo = h_tag.get_text(strip=True) if h_tag else ""

        if not titulo or len(titulo) < 6:
            continue

        url_completa = href if href.startswith("http") else f"https://www.obramat.es{href}"

        productos.append({
            "id_obramat": ref_id,
            "referencia_local": ref_id,
            "marca": extraer_marca(titulo),
            "codigo_fabricante": extraer_codigo(titulo),
            "titulo": titulo,
            "precio_churra": precio,
            "url": url_completa
        })

    # Paginación activa: existe botón siguiente o se han devuelto artículos
    hay_mas = bool(soup.find("a", class_=re.compile(r"next|pagination__next"))) or len(productos) >= 12
    return productos, hay_mas

def ejecutar_barrido_completo():
    print("=" * 75)
    print("BARRIDO MAESTRO: ELECTROPORTÁTIL, CORTE, TALLER Y LIMPIEZA (CHURRA)")
    print("=" * 75)

    censo_maestro = {}

    for fam in FAMILIAS_OBJETIVO:
        print(f"\n[Familia] {fam['categoria']}")
        pagina = 1
        paginas_vacias_consecutivas = 0
        
        while pagina <= 6:  # Tope de seguridad: 6 páginas por familia
            sep = "&" if "?" in fam["url"] else "?"
            url_pag = f"{fam['url']}{sep}p={pagina}" if pagina > 1 else fam["url"]
            
            prods, hay_mas = extraer_pagina(url_pag)
            
            nuevos = 0
            for p in prods:
                ref = p["id_obramat"]
                if ref not in censo_maestro:
                    p["subfamilia"] = fam["categoria"]
                    censo_maestro[ref] = p
                    nuevos += 1
            
            print(f"   Pág {pagina}: {len(prods)} detectados (+{nuevos} nuevos)")

            if len(prods) == 0:
                paginas_vacias_consecutivas += 1
                if paginas_vacias_consecutivas >= 2 or not hay_mas:
                    break
            else:
                paginas_vacias_consecutivas = 0

            if not hay_mas:
                break

            pagina += 1
            time.sleep(1.2)

    catalogo = list(censo_maestro.values())
    catalogo.sort(key=lambda x: x["precio_churra"], reverse=True)

    ruta_salida = BASE_DIR / "catalogo_maestro_obramat.json"
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)

    con_codigo = sum(1 for x in catalogo if x.get("codigo_fabricante"))
    marcas_resumen = {}
    for x in catalogo:
        m = x.get("marca", "OTRA")
        marcas_resumen[m] = marcas_resumen.get(m, 0) + 1

    print("\n" + "=" * 75)
    print(f"CENSO TOTAL MAESTRO: {len(catalogo)} productos en Obramat Churra.")
    print(f"Con código técnico identificativo: {con_codigo} ({round((con_codigo/len(catalogo))*100, 1)}%)")
    print("\nDistribución por fabricante:")
    for marca, cant in sorted(marcas_resumen.items(), key=lambda item: item[1], reverse=True):
        print(f"   - {marca}: {cant}")
    print("=" * 75)

if __name__ == "__main__":
    ejecutar_barrido_completo()