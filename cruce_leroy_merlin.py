import os
import json
import re
import requests
import xml.etree.ElementTree as ET
import gzip
from pathlib import Path

BASE_DIR = Path(r"C:\Users\Beamspark\Desktop\Proyecto Comparador\price-comparison-agent")
CACHE_SITEMAP_FILE = BASE_DIR / "sitemap_urls_lm.json"
CATALOGO_OBRAMAT_FILE = BASE_DIR / "catalogo_maestro_obramat.json"
OUTPUT_CANDIDATOS_FILE = BASE_DIR / "candidatos_homologacion.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def sanitizar_guiones(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", texto)

def generar_subidentificador(titulo: str, marca: str) -> str:
    t = sanitizar_guiones(titulo).upper()
    
    tipo = None
    if "HORMIGONERA" in t: tipo = "HORMIGONERA"
    elif "COMPRESOR" in t: tipo = "COMPRESOR"
    elif "GENERADOR" in t: tipo = "GENERADOR"
    elif "TALADRO" in t or "PERCUTOR" in t: tipo = "TALADRO"
    elif "AMOLADORA" in t: tipo = "AMOLADORA"
    elif "MARTILLO" in t: tipo = "MARTILLO"
    elif "CORTADORA" in t or "CORTADOR" in t: tipo = "CORTADORA"
    elif "INVERSOR" in t: tipo = "INVERSOR"
    elif "INGLETADORA" in t: tipo = "INGLETADORA"
    elif "SIERRA" in t: tipo = "SIERRA"
    elif "LIJADORA" in t: tipo = "LIJADORA"

    if not tipo:
        return None

    cap_l = re.search(r"\b(\d+)\s*L\b", t)
    pot_w = re.search(r"\b(\d+)\s*(?:W|KW)\b", t)
    pot_cv = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:CV|HP)\b", t)
    volt = re.search(r"\b(\d+)\s*V\b", t)
    corte_mm = re.search(r"\b(\d{2,4})\s*MM\b", t)
    
    atributos = [tipo]
    if marca and "MARCA BLANCA" not in marca.upper():
        atributos.append(marca.upper().strip())
    if cap_l: atributos.append(f"{cap_l.group(1)}L")
    if pot_cv: atributos.append(f"{pot_cv.group(1).replace(',', '.')}CV")
    if pot_w: atributos.append(f"{pot_w.group(1)}W")
    if volt: atributos.append(f"{volt.group(1)}V")
    if corte_mm: atributos.append(f"{corte_mm.group(1)}MM")
    
    # Exigir al menos Tipo + Atributo técnico
    return "-".join(atributos) if len(atributos) >= 2 else None

def obtener_sitemaps_productos():
    url_robots = "https://www.leroymerlin.es/robots.txt"
    try:
        r = requests.get(url_robots, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            sitemaps = re.findall(r"Sitemap:\s*(https?://[^\s]+)", r.text, re.IGNORECASE)
            sitemaps_prod = [s for s in sitemaps if "producto" in s.lower() or "product" in s.lower()]
            if sitemaps_prod:
                return sitemaps_prod
    except Exception as e:
        print(f"Error accediendo a robots.txt: {e}")
    
    return [f"https://www.leroymerlin.es/sitemap-productos{i}.xml" for i in range(1, 12)]

def extraer_urls_de_sitemap(sitemap_url: str):
    print(f"   -> Descargando: {sitemap_url} ...")
    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        
        contenido = r.content
        if sitemap_url.endswith(".gz") or r.headers.get("Content-Type") == "application/x-gzip":
            try:
                contenido = gzip.decompress(contenido)
            except Exception:
                pass
                
        root = ET.fromstring(contenido)
        urls = []
        for elem in root.iter():
            if elem.tag.endswith("loc") and not elem.tag.startswith("{http://www.google.com/schemas/sitemap-image"):
                url = elem.text.strip() if elem.text else ""
                if "leroymerlin.es/productos/" in url and url.endswith(".html"):
                    urls.append(url)
        print(f"      Fichas válidas halladas: {len(urls)}")
        return urls
    except Exception as e:
        print(f"      [Fallo en sitemap]: {e}")
        return []

def cargar_pool_urls_leroy():
    if CACHE_SITEMAP_FILE.exists():
        print(f"Cargando pool de URLs desde caché local: {CACHE_SITEMAP_FILE}")
        with open(CACHE_SITEMAP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("No existe caché local. Descargando sitemaps de Leroy Merlin...")
    sitemaps = obtener_sitemaps_productos()
    pool_urls = []
    
    for s_url in sitemaps[:10]:
        urls = extraer_urls_de_sitemap(s_url)
        pool_urls.extend(urls)

    pool_urls = list(dict.fromkeys(pool_urls))
    print(f"\nTotal fichas únicas indexadas: {len(pool_urls)}")
    
    with open(CACHE_SITEMAP_FILE, "w", encoding="utf-8") as f:
        json.dump(pool_urls, f)
    print(f"Índice cacheado en: {CACHE_SITEMAP_FILE}")
    
    return pool_urls

ALIAS_FILE = BASE_DIR / "alias_maquinaria.json"
LISTA_NEGRA_FILE = BASE_DIR / "lista_negra.json"

def cargar_alias():
    if ALIAS_FILE.exists():
        try:
            with open(ALIAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

TABLA_ALIAS = cargar_alias()

def generar_variantes_codigo(codigo: str, marca: str = ""):
    c = sanitizar_guiones(codigo).lower().strip()
    variantes = set()

    slug_guiones = re.sub(r"[^a-z0-9]", "-", c).strip("-")
    slug_compacto = re.sub(r"[^a-z0-9]", "", c)
    variantes.add(slug_guiones)
    variantes.add(slug_compacto)

    # Comprobar alias configurados (ej. GWS 700 -> GWS 750)
    marca_up = marca.upper().strip()
    if marca_up in TABLA_ALIAS:
        for modelo_base, lista_alias in TABLA_ALIAS[marca_up].items():
            if modelo_base.lower() in c or c in modelo_base.lower():
                for al in lista_alias:
                    al_slug = re.sub(r"[^a-z0-9]", "-", al.lower()).strip("-")
                    variantes.add(al_slug)
                    variantes.add(re.sub(r"[^a-z0-9]", "", al.lower()))

    base = re.sub(r"-(?:qs|qw|dsae|xj|eu|jh|re|e)$", "", slug_guiones)
    if base != slug_guiones and len(base) >= 4:
        variantes.add(base)
        variantes.add(re.sub(r"[^a-z0-9]", "", base))

    return [v for v in variantes if len(v) >= 3]

def ejecutar_cruce():
    print("=" * 70)
    print("CRUCE INTEGRAL OPTIMIZADO: HERRAMIENTAS OBRAMAT vs LEROY MERLIN")
    print("=" * 70)

    if not CATALOGO_OBRAMAT_FILE.exists():
        print(f"Error: No existe el catálogo maestro en {CATALOGO_OBRAMAT_FILE}")
        return

    with open(CATALOGO_OBRAMAT_FILE, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    maquinas_a_buscar = []
    con_codigo = 0
    con_subid = 0

    for item in catalogo:
        cod = item.get("codigo_fabricante")
        if cod and len(cod.strip()) >= 3:
            item["id_cruce"] = cod.strip()
            item["tipo_cruce"] = "CODIGO_FABRICANTE"
            con_codigo += 1
            maquinas_a_buscar.append(item)
        else:
            subid = generar_subidentificador(item["titulo"], item.get("marca"))
            if subid:
                item["id_cruce"] = subid
                item["tipo_cruce"] = "SUBIDENTIFICADOR_TECNICO"
                con_subid += 1
                maquinas_a_buscar.append(item)

    print(f"Total referencias Obramat Churra: {len(catalogo)}")
    print(f" - Herramientas con Código Fabricante: {con_codigo}")
    print(f" - Herramientas con Subidentificador Técnico: {con_subid}")
    print(f"Total herramientas listas para emparejar: {len(maquinas_a_buscar)}\n")

    pool_urls = cargar_pool_urls_leroy()

    emparejados = []
    
    for item in maquinas_a_buscar:
        clave = item["id_cruce"]
        tipo = item["tipo_cruce"]
        candidatas = []

        if tipo == "CODIGO_FABRICANTE":
            variantes = generar_variantes_codigo(clave, item.get("marca", ""))
            patrones = [re.compile(rf"(?:-|^){re.escape(var)}(?:-|\.html)", re.IGNORECASE) for var in variantes]
            
            for u in pool_urls:
                if any(p.search(u) for p in patrones):
                    candidatas.append(u)
                    if len(candidatas) >= 3:  # Hasta 3 URLs para tener alternativas a marketplace
                        break
        else:
            # Subidentificador: requiere coincidencia de al menos 2 tokens técnicos
            tokens = [t.lower() for t in clave.split("-") if len(t) > 1 and t not in ["herramienta", "otra", "marca", "blanca"]]
            if len(tokens) >= 2:
                for u in pool_urls:
                    u_lower = u.lower()
                    if all(tok in u_lower for tok in tokens):
                        candidatas.append(u)
                        if len(candidatas) >= 2:
                            break

        if candidatas:
            for match_url in candidatas:
                emparejados.append({
                    "id_cruce": item["id_cruce"],
                    "tipo_cruce": item["tipo_cruce"],
                    "marca": item.get("marca", "GENÉRICO"),
                    "obramat": {
                        "referencia_local": item.get("referencia_local") or item.get("id_obramat"),
                        "titulo": item["titulo"],
                        "precio_churra": item.get("precio_churra") or item.get("precio"),
                        "ref_fabricante": item.get("codigo_fabricante", ""),
                        "url": item.get("url", "")
                    },
                    "leroy_merlin": {
                        "url_candidata": match_url
                    }
                })
            print(f" [MATCH] [{tipo}] {clave} -> {len(candidatas)} candidata(s) encontrada(s)")

    print("\n" + "=" * 70)
    print(f"CRUCE CONCLUIDO:")
    print(f" - Parejas candidatas generadas: {len(emparejados)} (para {len(maquinas_a_buscar)} herramientas)")
    print("=" * 70)

    with open(OUTPUT_CANDIDATOS_FILE, "w", encoding="utf-8") as f:
        json.dump(emparejados, f, ensure_ascii=False, indent=2)

    print(f"Archivo exportado para auditoría: {OUTPUT_CANDIDATOS_FILE}")

if __name__ == "__main__":
    ejecutar_cruce()