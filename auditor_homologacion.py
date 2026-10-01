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

# 1. Silenciar logging y warnings de AFC del SDK google-genai
warnings.filterwarnings("ignore")
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
LEROY_COOKIE = os.getenv("LEROY_COOKIE")

if not API_KEY:
    raise ValueError("No se encontró GEMINI_API_KEY en el archivo .env")

# Cliente oficial de Google GenAI
client = genai.Client(api_key=API_KEY)
MODEL_ID = "gemini-3.5-flash-lite"

# Sesión persistente emulando Firefox
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
    """Convierte guiones tipográficos a ASCII estándar -"""
    if not texto:
        return ""
    return re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", texto)

def obtener_datos_leroy(url: str):
    try:
        time.sleep(random.uniform(1.0, 2.0))
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

        # 4. FILTRADO ESTRICTO DE MARKETPLACE (Blindado contra falsos positivos)
        if not vendedor_detectado:
            # Buscar en caja de compra o metadatos de oferta
            caja = soup.select_one(".product-buy-box, [data-qa='buy-box'], #seller-info, .seller-info, main")
            texto_caja = caja.get_text().upper() if caja else ""
            
            # Comprobar primero si indica venta directa de Leroy Merlin
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

        # Si tras evaluar sigue sin detectarse tercero, pero es producto de catálogo físico Leroy
        if not vendedor_detectado:
            # Por defecto en la web de LM, si no hay caja de seller externo es venta directa
            vendedor_detectado = "LEROY MERLIN"

        # Aplicar el filtro de exclusión:
        if "LEROY MERLIN" not in vendedor_detectado:
            print(f"      [Descartado]: Marketplace ({vendedor_detectado.splitlines()[0][:30]})")
            return None

        if not titulo:
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

def auditar_con_gemini(item_obramat: dict, item_leroy: dict) -> dict:
    prompt = f"""Actúa como un analista experto en maquinaria, herramientas profesionales y suministros de construcción.
Compara estos dos productos para determinar si son exactamente equiparables en una comparativa de precios profesional:

PRODUCTO OBRAMAT (Murcia Norte - Churra):
- Título: {item_obramat.get('titulo', item_obramat.get('nombre', ''))}
- Ref Fabricante / Código: {item_obramat.get('ref_fabricante', '')}
- Precio: {item_obramat.get('precio_churra', item_obramat.get('precio', 'N/D'))} €

PRODUCTO LEROY MERLIN:
- Título: {item_leroy['titulo']}
- Precio detectado: {item_leroy.get('precio', 'No detectado')} €
- Ficha técnica y dotación: {item_leroy.get('descripcion', '')}

Reglas de evaluación técnica:
1. Comprueba si es el mismo modelo base (código de fabricante coincidente o especificación equivalente).
2. Comprueba la dotación: número de baterías, amperaje (Ah), cargador y maletín. Si uno incluye batería y el otro viene solo el cuerpo, indícalo.

Responde ÚNICAMENTE un objeto JSON válido con esta estructura:
{{
  "veredicto": "HOMOLOGADO_DIRECTO" | "HOMOLOGADO_CON_DIFERENCIAS" | "NO_EQUIVALENTE",
  "confianza": 0-100,
  "justificacion": "Explicación técnica concisa en una frase",
  "diferencia_dotacion": "Ninguna o resumen de la discrepancia de accesorios"
}}
"""
    try:
        # Usar la interfaz oficial de Chat recomendada por el SDK para silenciar el aviso de AFC
        chat_session = client.chats.create(
            model=MODEL_ID,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        response = chat_session.send_message(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"      [Error en llamada a Gemini]: {e}")
        return {
            "veredicto": "ERROR_API",
            "confianza": 0,
            "justificacion": str(e),
            "diferencia_dotacion": "Desconocida"
        }

def ejecutar_auditoria():
    print("=" * 70)
    print("AUDITORÍA Y HOMOLOGACIÓN TÉCNICA (INCREMENTAL - FILTRO LEROY DIRECTO)")
    print("=" * 70)

    archivo_candidatos = "candidatos_homologacion.json"
    archivo_vigilancia = "catalogo_vigilancia.json"

    if not os.path.exists(archivo_candidatos):
        print(f"[Error]: No se encuentra '{archivo_candidatos}'.")
        return

    # Cargar vigilancia previa para no perder productos ya validados
    vigilancia_existente = {}
    if os.path.exists(archivo_vigilancia):
        try:
            with open(archivo_vigilancia, "r", encoding="utf-8") as f:
                datos_previos = json.load(f)
                for item in datos_previos:
                    # Indexar por referencia local de Obramat para unicidad
                    ref_key = item.get("obramat", {}).get("referencia_local") or item.get("id_cruce")
                    if ref_key:
                        vigilancia_existente[ref_key] = item
        except Exception as e:
            print(f"[Aviso]: No se pudo leer histórico previo: {e}")

    print(f"Productos ya homologados en catálogo de vigilancia: {len(vigilancia_existente)}")

    with open(archivo_candidatos, "r", encoding="utf-8") as f:
        candidatos = json.load(f)

    print(f"Total parejas candidatas en cola: {len(candidatos)}\n")

    nuevos_homologados = 0

    for c in candidatos:
        info_obramat = c.get("obramat", {})
        ref_obramat = info_obramat.get("referencia_local") or c.get("id_cruce")

        # Si ya lo tenemos homologado con éxito, no gastamos tiempo ni tokens
        if ref_obramat in vigilancia_existente and "HOMOLOGADO" in vigilancia_existente[ref_obramat].get("veredicto_homologacion", ""):
            continue

        url_lm = c.get("leroy_merlin", {}).get("url_candidata") or c.get("leroy_url")
        marca = c.get("marca", info_obramat.get("fabricante", "GENÉRICO"))
        titulo_obramat = info_obramat.get("titulo") or info_obramat.get("nombre", "Sin título")

        print(f"-> Analizando: [{marca}] {titulo_obramat[:50]}...")
        print(f"   URL Leroy: {url_lm[:70]}...")

        datos_lm = obtener_datos_leroy(url_lm)
        if not datos_lm or not datos_lm["titulo"]:
            print("   [Saltado]: Ficha no accesible o descartada por filtro de vendedor.\n")
            continue

        print(f"   Leroy Título: {datos_lm['titulo'][:55]}... | Precio: {datos_lm['precio']} €")
        print("   Auditando equivalencia con Gemini 3.5 Flash Lite...")

        analisis = auditar_con_gemini(info_obramat, datos_lm)
        veredicto = analisis.get("veredicto", "NO_EQUIVALENTE")
        print(f"   Veredicto: {veredicto} (Confianza: {analisis.get('confianza')}%)")
        print(f"   Detalle: {analisis.get('justificacion')}\n")

        if "HOMOLOGADO" in veredicto:
            registro = {
                "id_cruce": c.get("id_cruce", info_obramat.get("id_obramat")),
                "tipo_cruce": c.get("tipo_cruce", "FABRICANTE_O_SUBID"),
                "marca": marca,
                "veredicto_homologacion": veredicto,
                "detalles_homologacion": analisis,
                "obramat": info_obramat,
                "leroy_merlin": {
                    "titulo": datos_lm["titulo"],
                    "precio": datos_lm["precio"],
                    "url": url_lm,
                    "vendedor": "LEROY MERLIN"
                }
            }
            vigilancia_existente[ref_obramat] = registro
            nuevos_homologados += 1

            # Guardado incremental inmediato en disco para proteger el progreso
            with open(archivo_vigilancia, "w", encoding="utf-8") as f:
                json.dump(list(vigilancia_existente.values()), f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("AUDITORÍA FINALIZADA:")
    print(f" - Nuevos productos homologados en esta sesión: {nuevos_homologados}")
    print(f" - TOTAL acumulado en 'catalogo_vigilancia.json': {len(vigilancia_existente)}")
    print("=" * 70)

if __name__ == "__main__":
    ejecutar_auditoria()