import os
import json
import re
import time
import random
import logging
import warnings
from bs4 import BeautifulSoup
from curl_cffi import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
LEROY_COOKIE = os.getenv("LEROY_COOKIE")

if not API_KEY:
    raise ValueError("No se encontró GEMINI_API_KEY en el archivo .env")

client = genai.Client(api_key=API_KEY)
# Lista de modelos en cascada (primero el recomendado por el API de Google)
MODELOS_DISPONIBLES = [
    "gemini-3.8-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

session = requests.Session(impersonate="firefox")

HEADERS_FIREFOX = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.leroymerlin.es/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Priority": "u=0, i",
    "TE": "trailers"
}

if LEROY_COOKIE:
    HEADERS_FIREFOX["Cookie"] = LEROY_COOKIE

def sanitizar_guiones(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", texto)

def obtener_datos_leroy(url: str):
    try:
        time.sleep(random.uniform(1.0, 1.8))
        r = session.get(url, headers=HEADERS_FIREFOX, timeout=20)
        
        if r.status_code != 200:
            print(f"      [Aviso HTTP {r.status_code} al acceder a la ficha]")
            return None

        html_limpio = sanitizar_guiones(r.text)
        soup = BeautifulSoup(html_limpio, "html.parser")

        titulo = None
        precio = None
        descripcion = ""
        vendedor_detectado = None

        # 1. Extracción primaria y vendedor mediante JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        titulo = item.get("name")
                        descripcion = item.get("description", "")
                        offers = item.get("offers", {})
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict):
                            p = offers.get("price")
                            if p:
                                precio = float(str(p).replace(",", "."))
                            seller = offers.get("seller", {})
                            if isinstance(seller, dict):
                                vendedor_detectado = seller.get("name", "").strip().upper()
                        break
            except Exception:
                continue

        # 2. Extracción de Título si falta en JSON-LD
        if not titulo:
            h1 = soup.find("h1")
            titulo = h1.get_text(strip=True) if h1 else ""

        # 3. Extracción de Precio si falta en JSON-LD
        if not precio:
            meta_precio = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
            if meta_precio and meta_precio.get("content"):
                try:
                    precio = float(meta_precio["content"].replace(",", "."))
                except Exception:
                    pass

        # 4. FILTRADO ESTRICTO DE MARKETPLACE
        if not vendedor_detectado:
            caja = soup.select_one(".product-buy-box, [data-qa='buy-box'], #seller-info, .seller-info, main")
            texto_caja = caja.get_text().upper() if caja else ""
            
            if "VENDIDO POR LEROY MERLIN" in texto_caja or "VENDIDO Y ENVIADO POR LEROY MERLIN" in texto_caja:
                vendedor_detectado = "LEROY MERLIN"
            else:
                match_tercero = re.search(r"VENDIDO POR\s*:?\s*([A-Z0-9\s\.\-_]{3,40})", texto_caja)
                if match_tercero:
                    candidato_vend = match_tercero.group(1).strip()
                    if "LEROY MERLIN" in candidato_vend:
                        vendedor_detectado = "LEROY MERLIN"
                    else:
                        vendedor_detectado = candidato_vend

        if not vendedor_detectado:
            vendedor_detectado = "LEROY MERLIN"

        if "LEROY MERLIN" not in vendedor_detectado:
            print(f"      [Descartado]: Vendedor externo Marketplace ({vendedor_detectado.splitlines()[0][:30]})")
            return None

        if not titulo or not precio:
            return None

        # 5. Atributos técnicos y dotación
        specs = []
        for elem in soup.select("table tr, dl > div, .ui-spec-list li"):
            specs.append(elem.get_text(separator=" ", strip=True))
        
        bloque_tecnico = sanitizar_guiones(f"{descripcion} | " + " | ".join(specs))[:1500]

        return {
            "titulo": sanitizar_guiones(titulo),
            "precio": precio,
            "descripcion": bloque_tecnico,
            "vendedor": "LEROY MERLIN"
        }
    except Exception as e:
        print(f"      [Error en lectura]: {e}")
        return None

# Modelos oficiales vigentes y soportados por el SDK google-genai
MODELOS_CANDIDATOS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite"
]

def auditar_con_gemini(candidato: dict, item_leroy: dict) -> dict:
    tipo_cruce = candidato.get("tipo_cruce", "HOMOLOGADO_DIRECTO")
    info_obramat = candidato.get("obramat", {})

    if tipo_cruce == "HOMOLOGADO_DIRECTO":
        criterio_instruccion = """
NIVEL DE EVALUACIÓN: HOMOLOGACIÓN DIRECTA (MISMA MARCA Y MODELO).
1. Comprueba si es el mismo modelo base exacto de máquina.
2. Comprueba la dotación: número de baterías, amperaje (Ah), cargador y maletín.
3. Si es la misma máquina y dotación, emite 'HOMOLOGADO_DIRECTO'. Si difiere la dotación, 'HOMOLOGADO_CON_DIFERENCIAS'. Si no es el modelo, 'NO_EQUIVALENTE'.
"""
    else:
        especificaciones = candidato.get("especificaciones_exactas", "")
        criterio_instruccion = f"""
NIVEL DE EVALUACIÓN: EQUIVALENTE TÉCNICO EN MAQUINARIA (COMPRESORES, GENERADORES O SOLDADURA).
Parámetros obligatorios requeridos: {especificaciones}
1. Las marcas PUEDEN ser diferentes. Evalúa si el producto de Leroy Merlin cumple ESTRICTAMENTE las mismas especificaciones (ej. mismos litros y potencia en compresores, mismos vatios y tecnología inverter/AVR en generadores, o mismos amperios y proceso en soldadura).
2. Si las especificaciones de servicio son equivalentes para el profesional, emite 'HOMOLOGADO_DIRECTO'.
3. Si difieren significativamente en potencia, calderín, amperios o tecnología, emite 'NO_EQUIVALENTE'.
"""

    prompt = f"""Actúa como un perito técnico de maquinaria profesional y analista de precios.
Compara estos dos productos para validar si su comparación comercial es rigurosa:

PRODUCTO DE REFERENCIA OBRAMAT:
- Título: {info_obramat.get('titulo', '')}
- Ref Fabricante: {info_obramat.get('ref_fabricante', 'N/D')}
- Precio Almacén Churra: {info_obramat.get('precio_churra', 'N/D')} €

PRODUCTO CANDIDATO LEROY MERLIN:
- Título: {item_leroy['titulo']}
- Precio Web Directo: {item_leroy.get('precio')} €
- Ficha técnica: {item_leroy.get('descripcion', '')}

{criterio_instruccion}

Responde ÚNICAMENTE un objeto JSON válido con este formato:
{{
  "veredicto": "HOMOLOGADO_DIRECTO" | "HOMOLOGADO_CON_DIFERENCIAS" | "NO_EQUIVALENTE",
  "confianza": 0-100,
  "justificacion": "Explicación técnica concisa en una frase",
  "diferencia_dotacion": "Ninguna o resumen de la discrepancia técnica/accesorios"
}}
"""

    ultimo_error = ""
    for modelo in MODELOS_CANDIDATOS:
        try:
            # Usar generate_content nativo del SDK google-genai
            response = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            texto_resp = response.text.strip()
            texto_resp = re.sub(r"^```(?:json)?\s*", "", texto_resp)
            texto_resp = re.sub(r"\s*```$", "", texto_resp)
            return json.loads(texto_resp)
        except Exception as e:
            ultimo_error = str(e)
            continue

    print(f"      [Error persistente en Gemini]: {ultimo_error}")
    return {
        "veredicto": "ERROR_API",
        "confianza": 0,
        "justificacion": ultimo_error,
        "diferencia_dotacion": "Desconocida"
    }

def ejecutar_auditoria():
    print("=" * 75)
    print("AUDITORÍA INTELIGENTE: HOMOLOGACIÓN DIRECTA Y EQUIVALENCIAS TÉCNICAS")
    print("=" * 75)

    archivo_candidatos = "candidatos_homologacion.json"
    archivo_vigilancia = "catalogo_vigilancia.json"

    if not os.path.exists(archivo_candidatos):
        print(f"[Error]: No se encuentra '{archivo_candidatos}'.")
        return

    vigilancia_existente = {}
    if os.path.exists(archivo_vigilancia):
        try:
            with open(archivo_vigilancia, "r", encoding="utf-8") as f:
                datos_previos = json.load(f)
                for item in datos_previos:
                    ref_key = item.get("id_cruce") or item.get("obramat", {}).get("id_obramat")
                    if ref_key:
                        vigilancia_existente[str(ref_key)] = item
        except Exception as e:
            print(f"[Aviso]: No se pudo leer vigilancia previa: {e}")

    print(f"Productos ya vigilados en catálogo: {len(vigilancia_existente)}")

    with open(archivo_candidatos, "r", encoding="utf-8") as f:
        candidatos = json.load(f)

    print(f"Total parejas candidatas a procesar: {len(candidatos)}\n")
    nuevos_homologados = 0

    for c in candidatos:
        info_obramat = c.get("obramat", {})
        id_cruce = str(c.get("id_cruce"))
        tipo_cruce = c.get("tipo_cruce", "HOMOLOGADO_DIRECTO")
        titulo_obramat = info_obramat.get("titulo", "Sin título")

        # Evitar reauditar si ya está consolidado
        if id_cruce in vigilancia_existente and "HOMOLOGADO" in vigilancia_existente[id_cruce].get("veredicto_homologacion", ""):
            continue

        url_lm = c.get("leroy_merlin", {}).get("url_candidata")
        if not url_lm:
            continue

        print(f"-> Evaluando [{tipo_cruce}]: {titulo_obramat[:55]}...")
        print(f"   URL Leroy: {url_lm[:70]}...")

        datos_lm = obtener_datos_leroy(url_lm)
        if not datos_lm or not datos_lm.get("titulo"):
            print("   [Saltado]: Ficha descartada (Marketplace o inaccesible).\n")
            continue

        precio_lm = datos_lm["precio"]
        print(f"   Leroy: '{datos_lm['titulo'][:50]}...' a {precio_lm} €")

        # FILTRO ANTI-BAJA CALIDAD (Solo aplica a Nivel 2)
        if tipo_cruce == "EQUIVALENTE_TECNICO":
            filtro = c.get("filtro_calidad", {})
            umbral_min = filtro.get("umbral_descarte_bricolaje_60pct", 0.0)
            if precio_lm < umbral_min:
                print(f"   [DESCARTADO POR CALIDAD]: Precio Leroy ({precio_lm} €) < Umbral mínimo ({umbral_min} €). No equiparable.\n")
                continue

        print("   Auditando con Gemini...")
        analisis = auditar_con_gemini(c, datos_lm)
        veredicto = analisis.get("veredicto", "NO_EQUIVALENTE")
        print(f"   Veredicto: {veredicto} ({analisis.get('confianza')}%) | Justificación: {analisis.get('justificacion')}\n")

        if "HOMOLOGADO" in veredicto:
            registro = {
                "id_cruce": id_cruce,
                "tipo_cruce": tipo_cruce,
                "nivel_prioridad": c.get("nivel_prioridad", 1),
                "marca": c.get("marca", info_obramat.get("marca", "GENÉRICO")),
                "veredicto_homologacion": veredicto,
                "detalles_homologacion": analisis,
                "obramat": {
                    "id_obramat": str(info_obramat.get("id_obramat") or info_obramat.get("referencia_local")),
                    "titulo": info_obramat.get("titulo"),
                    "precio": info_obramat.get("precio_churra"),
                    "ref_fabricante": info_obramat.get("ref_fabricante", ""),
                    "url": info_obramat.get("url")
                },
                "leroy_merlin": {
                    "titulo": datos_lm["titulo"],
                    "precio": precio_lm,
                    "url": url_lm,
                    "vendedor": "LEROY MERLIN"
                }
            }
            vigilancia_existente[id_cruce] = registro
            nuevos_homologados += 1

            # Guardado incremental inmediato
            with open(archivo_vigilancia, "w", encoding="utf-8") as f:
                json.dump(list(vigilancia_existente.values()), f, ensure_ascii=False, indent=2)

    print("=" * 75)
    print("AUDITORÍA CONCLUIDA:")
    print(f" - Nuevos productos incorporados: {nuevos_homologados}")
    print(f" - Catálogo total en vigilancia activa: {len(vigilancia_existente)} productos")
    print("=" * 75)

if __name__ == "__main__":
    ejecutar_auditoria()