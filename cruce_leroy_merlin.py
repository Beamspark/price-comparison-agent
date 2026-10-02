import os
import json
import re
import requests
import xml.etree.ElementTree as ET
import gzip
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_SITEMAP_FILE = BASE_DIR / "sitemap_urls_lm.json"
CATALOGO_OBRAMAT_FILE = BASE_DIR / "catalogo_maestro_obramat.json"
OUTPUT_CANDIDATOS_FILE = BASE_DIR / "candidatos_homologacion.json"
ALIAS_FILE = BASE_DIR / "alias_maquinaria.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

TOLERANCIA_PRECIO_MAXIMA = 0.35  # ±35% para evitar mezclar bricolaje con industrial

def sanitizar_guiones(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", texto)

def cargar_alias():
    if ALIAS_FILE.exists():
        try:
            with open(ALIAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

TABLA_ALIAS = cargar_alias()

# -------------------------------------------------------------------------
# EXTRACCIÓN DE PARÁMETROS CRÍTICOS (NIVEL 2: TOLERANCIA CERO)
# -------------------------------------------------------------------------
def extraer_perfil_tecnico(titulo: str, subfamilia: str = "", marca: str = ""):
    t = sanitizar_guiones(titulo).upper()
    sub_up = subfamilia.upper()
    marca_up = marca.upper().strip()

    # COMPRESORES
    if "COMPRESOR" in t or "COMPRESOR" in sub_up:
        m_l = re.search(r"\b(\d+)\s*L(?:ITROS)?\b", t)
        m_cv = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:CV|HP)\b", t)
        if m_l and m_cv:
            litros = m_l.group(1)
            potencia = m_cv.group(1).replace(",", ".")
            tipo_const = "CORREAS" if "CORREA" in t else ("SILENCIOSO" if "SILENCI" in t or "OIL-FREE" in t else "DIRECTO")
            id_tecnico = f"COMPRESOR_{litros}L_{potencia}CV_{tipo_const}"
            tokens = [f"{litros}l", f"{potencia}cv" if "." not in potencia else f"{potencia}hp", "compresor"]
            return {"familia": "COMPRESOR", "id_tecnico": id_tecnico, "tokens": tokens, "marca": marca_up}

    # GENERADORES
    if "GENERADOR" in t or "GRUPO ELECTROGENO" in t or "GENERADOR" in sub_up:
        m_w = re.search(r"\b(\d{3,5})\s*W\b", t)
        if m_w:
            watts = m_w.group(1)
            tec = "INVERTER" if "INVERTER" in t else "AVR"
            id_tecnico = f"GENERADOR_{watts}W_{tec}"
            tokens = [f"{watts}w", "inverter" if tec == "INVERTER" else "generador"]
            # Si tiene marca reconocida (ej: GENERGY), el token de marca es obligatorio
            if marca_up and marca_up not in ["OTRA", "MARCA BLANCA"]:
                tokens.append(re.sub(r"[^a-z0-9]", "", marca_up.lower()))
            return {"familia": "GENERADOR", "id_tecnico": id_tecnico, "tokens": tokens, "marca": marca_up}

    # SOLDADURA
    if "SOLDADOR" in t or "SOLDADURA" in t or "INVERTER" in t or "SOLDADURA" in sub_up:
        m_a = re.search(r"\b(\d{2,3})\s*A\b", t)
        if m_a:
            amperios = m_a.group(1)
            proceso = "MIG" if ("MIG" in t or "HILO" in t) else ("TIG" if "TIG" in t else "MMA")
            id_tecnico = f"SOLDADOR_{proceso}_{amperios}A"
            tokens = [f"{amperios}a", "soldador" if proceso == "MMA" else proceso.lower()]
            return {"familia": "SOLDADOR", "id_tecnico": id_tecnico, "tokens": tokens, "marca": marca_up}

    return None

# -------------------------------------------------------------------------
# CARGA Y INDEXACIÓN DE SITEMAPS LEROY MERLIN
# -------------------------------------------------------------------------
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
    print(f"   -> Descargando sitemap: {sitemap_url} ...")
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
        return urls
    except Exception as e:
        print(f"   [Fallo en sitemap]: {e}")
        return []

def cargar_pool_urls_leroy():
    if CACHE_SITEMAP_FILE.exists():
        print(f"Cargando pool de URLs desde cache local: {CACHE_SITEMAP_FILE.name}")
        with open(CACHE_SITEMAP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("Descargando sitemaps de Leroy Merlin...")
    sitemaps = obtener_sitemaps_productos()
    pool_urls = []
    for s_url in sitemaps[:10]:
        urls = extraer_urls_de_sitemap(s_url)
        pool_urls.extend(urls)

    pool_urls = list(dict.fromkeys(pool_urls))
    with open(CACHE_SITEMAP_FILE, "w", encoding="utf-8") as f:
        json.dump(pool_urls, f)
    print(f"Indexadas {len(pool_urls)} fichas de Leroy Merlin.")
    return pool_urls

def generar_variantes_codigo(codigo: str, marca: str = ""):
    c = sanitizar_guiones(codigo).lower().strip()
    variantes = set()
    slug_guiones = re.sub(r"[^a-z0-9]", "-", c).strip("-")
    slug_compacto = re.sub(r"[^a-z0-9]", "", c)
    variantes.add(slug_guiones)
    variantes.add(slug_compacto)

    marca_up = marca.upper().strip()
    if marca_up in TABLA_ALIAS:
        for modelo_base, lista_alias in TABLA_ALIAS[marca_up].items():
            mod_limpio = sanitizar_guiones(modelo_base).lower().strip()
            # Cruce bidireccional entre código y alias
            if mod_limpio in c or c in mod_limpio:
                for al in lista_alias:
                    variantes.add(re.sub(r"[^a-z0-9]", "-", al.lower()).strip("-"))
                    variantes.add(re.sub(r"[^a-z0-9]", "", al.lower()))

    base = re.sub(r"-(?:qs|qw|dsae|xj|eu|jh|re|e)$", "", slug_guiones)
    if base != slug_guiones and len(base) >= 4:
        variantes.add(base)
        variantes.add(re.sub(r"[^a-z0-9]", "", base))

    return [v for v in variantes if len(v) >= 3]

# -------------------------------------------------------------------------
# EJECUCIÓN DEL CRUCE JERÁRQUICO
# -------------------------------------------------------------------------
def ejecutar_cruce():
    print("=" * 75)
    print("SISTEMA DE CRUCE JERÁRQUICO: OBRAMAT vs LEROY MERLIN")
    print("Nivel 1: Homologación Directa (Marca + Modelo + Alias)")
    print("Nivel 2: Equivalente Técnico + Filtro Precio Suelo y Banda ±35%")
    print("=" * 75)

    if not CATALOGO_OBRAMAT_FILE.exists():
        print(f"Error: No existe el catálogo maestro en {CATALOGO_OBRAMAT_FILE}")
        return

    with open(CATALOGO_OBRAMAT_FILE, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    pool_urls = cargar_pool_urls_leroy()
    candidatos_finales = []
    procesados_nivel_1 = set()

    # ---------------------------------------------------------------------
    # NIVEL 1: MATCH DIRECTO POR CÓDIGO TÉCNICO Y MARCA (INCLUYE ALIAS)
    # ---------------------------------------------------------------------
    print("\n[NIVEL 1] Ejecutando búsqueda de referencias directas e integradas por alias...")
    matches_directos = 0

    for item in catalogo:
        ref_om = str(item.get("id_obramat") or item.get("referencia_local"))
        cod_fab = item.get("codigo_fabricante")
        marca = item.get("marca", "").upper()

        if cod_fab and len(cod_fab.strip()) >= 3 and marca not in ["OTRA", "MARCA BLANCA"]:
            variantes = generar_variantes_codigo(cod_fab, marca)
            patrones = [re.compile(rf"(?:-|^){re.escape(var)}(?:-|\.html)", re.IGNORECASE) for var in variantes]
            marca_slug = re.sub(r"[^a-z0-9]", "", marca.lower())

            encontradas = []
            for u in pool_urls:
                u_lower = u.lower()
                if any(p.search(u) for p in patrones) and marca_slug in u_lower:
                    encontradas.append(u)
                    if len(encontradas) >= 2:
                        break

            if encontradas:
                procesados_nivel_1.add(ref_om)
                matches_directos += 1
                for match_url in encontradas:
                    candidatos_finales.append({
                        "id_cruce": cod_fab.strip(),
                        "tipo_cruce": "HOMOLOGADO_DIRECTO",
                        "nivel_prioridad": 1,
                        "marca": marca,
                        "obramat": {
                            "id_obramat": ref_om,
                            "titulo": item["titulo"],
                            "precio_churra": item.get("precio_churra") or item.get("precio"),
                            "ref_fabricante": cod_fab,
                            "url": item.get("url", "")
                        },
                        "leroy_merlin": {
                            "url_candidata": match_url
                        }
                    })

    print(f" -> Nivel 1 completado: {matches_directos} productos de Obramat tienen match idéntico o vía alias.")

    # ---------------------------------------------------------------------
    # NIVEL 2: EQUIVALENTE TÉCNICO (Solo huérfanos de Nivel 1 en familias clave)
    # ---------------------------------------------------------------------
    print("\n[NIVEL 2] Evaluando equivalencias técnicas con regla de precio suelo y banda ±35%...")
    
    # 1. Agrupar productos huérfanos de Obramat por ficha técnica exacta
    grupos_tecnicos = {}
    for item in catalogo:
        ref_om = str(item.get("id_obramat") or item.get("referencia_local"))
        if ref_om in procesados_nivel_1:
            continue

        marca = item.get("marca", "")
        perfil = extraer_perfil_tecnico(item["titulo"], item.get("subfamilia", ""), marca)
        if perfil:
            id_tec = perfil["id_tecnico"]
            precio = float(item.get("precio_churra") or item.get("precio") or 0.0)
            if precio <= 0:
                continue

            if id_tec not in grupos_tecnicos:
                grupos_tecnicos[id_tec] = {
                    "perfil": perfil,
                    "items": []
                }
            grupos_tecnicos[id_tec]["items"].append(item)

    matches_tecnicos = 0
    # 2. Para cada escalón técnico, fijar el precio suelo y buscar alternativa equiparable
    for id_tec, grupo in grupos_tecnicos.items():
        items_grupo = grupo["items"]
        
        # Principio de precio suelo: ordenar de menor a mayor precio dentro de Obramat
        items_ordenados = sorted(items_grupo, key=lambda x: float(x.get("precio_churra") or x.get("precio") or 999999))
        producto_suelo = items_ordenados[0]
        precio_suelo = float(producto_suelo.get("precio_churra") or producto_suelo.get("precio"))

        tokens = grupo["perfil"]["tokens"]
        candidatas_url = []
        for u in pool_urls:
            u_lower = u.lower()
            if all(tok in u_lower for tok in tokens):
                candidatas_url.append(u)
                if len(candidatas_url) >= 2:
                    break

        if candidatas_url:
            matches_tecnicos += 1
            for match_url in candidatas_url:
                candidatos_finales.append({
                    "id_cruce": id_tec,
                    "tipo_cruce": "EQUIVALENTE_TECNICO",
                    "nivel_prioridad": 2,
                    "especificaciones_exactas": id_tec,
                    "filtro_calidad": {
                        "precio_suelo_obramat": precio_suelo,
                        "banda_min_precio": round(precio_suelo * (1 - TOLERANCIA_PRECIO_MAXIMA), 2),
                        "banda_max_precio": round(precio_suelo * (1 + TOLERANCIA_PRECIO_MAXIMA), 2)
                    },
                    "obramat": {
                        "id_obramat": str(producto_suelo.get("id_obramat") or producto_suelo.get("referencia_local")),
                        "titulo": producto_suelo["titulo"],
                        "precio_churra": precio_suelo,
                        "ref_fabricante": producto_suelo.get("codigo_fabricante", ""),
                        "url": producto_suelo.get("url", ""),
                        "total_modelos_en_gama": len(items_grupo)
                    },
                    "leroy_merlin": {
                        "url_candidata": match_url
                    }
                })

    print(f" -> Nivel 2 completado: {matches_tecnicos} escalones técnicos emparejados.")

    # ---------------------------------------------------------------------
    # CONSOLIDACIÓN Y EXPORTACIÓN
    # ---------------------------------------------------------------------
    print("\n" + "=" * 75)
    print(f"TOTAL CANDIDATOS GENERADOS: {len(candidatos_finales)}")
    print(f" - Matches Directos (Nivel 1): {sum(1 for c in candidatos_finales if c['tipo_cruce'] == 'HOMOLOGADO_DIRECTO')}")
    print(f" - Equivalentes Técnicos (Nivel 2): {sum(1 for c in candidatos_finales if c['tipo_cruce'] == 'EQUIVALENTE_TECNICO')}")
    print("=" * 75)

    with open(OUTPUT_CANDIDATOS_FILE, "w", encoding="utf-8") as f:
        json.dump(candidatos_finales, f, ensure_ascii=False, indent=2)

    print(f"Base de candidatos guardada en: {OUTPUT_CANDIDATOS_FILE.name}")

if __name__ == "__main__":
    ejecutar_cruce()