import os
import json
import re
import time
import random
import logging
import warnings
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("No se encontró GEMINI_API_KEY en el archivo .env")

client = genai.Client(api_key=API_KEY)

MODELOS_PRIORITARIOS = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]

def sanitizar_guiones(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", texto)

def obtener_datos_leroy_cdp(page, url: str):
    """Navega a la ficha de Leroy Merlin a través de Chrome en puerto 9222 con filtro estricto anti-Marketplace."""
    try:
        time.sleep(random.uniform(1.2, 2.0))
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        try:
            page.wait_for_selector("h1", timeout=5000)
        except Exception:
            pass

        html = page.content()
        html_limpio = sanitizar_guiones(html)
        soup = BeautifulSoup(html_limpio, "html.parser")

        # 1. Título
        h1 = soup.find("h1")
        titulo = h1.get_text(strip=True) if h1 else ""

        # 2. VALIDACIÓN QUIRÚRGICA DEL VENDEDOR (Caja de compra principal)
        nodo_vendedor = soup.find(string=re.compile(r"Vendido\s+(?:y\s+enviado\s+)?por", re.IGNORECASE))
        
        es_venta_directa_leroy = False
        nombre_vendedor_detectado = "DESCONOCIDO"

        if nodo_vendedor:
            contenedor_vendedor = nodo_vendedor.find_parent()
            texto_linea_vendedor = contenedor_vendedor.get_text(separator=" ", strip=True).upper() if contenedor_vendedor else ""
            texto_linea_vendedor = re.sub(r"\s+", " ", texto_linea_vendedor)
            
            match = re.search(r"POR\s+([A-Z0-9\s\.\-_]{3,40})", texto_linea_vendedor)
            if match:
                nombre_vendedor_detectado = match.group(1).strip()
            
            if "LEROY MERLIN" in texto_linea_vendedor:
                es_venta_directa_leroy = True
            else:
                print(f"      [Descartado]: Vendedor Marketplace exclusivo ({nombre_vendedor_detectado})")
                return None
        else:
            bloque_compra = soup.select_one("[data-qa='buybox'], .buybox, .pdp-buybox")
            if bloque_compra and "MARKETPLACE" in bloque_compra.get_text().upper():
                print("      [Descartado]: Detectado Marketplace en bloque de compra")
                return None
            es_venta_directa_leroy = True

        if not es_venta_directa_leroy:
            return None

        # 3. EXTRACCIÓN DE PRECIO (Oferta principal directa de Leroy Merlin)
        precio = None
        bloque_precio = soup.select_one(".price-tag, [data-qa='price'], .product-price, .m-price__integer, .price")
        if bloque_precio:
            m = re.search(r"(\d+[\.,]?\d*)", bloque_precio.get_text())
            if m:
                precio = float(m.group(1).replace(",", "."))

        if not precio:
            meta_precio = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
            if meta_precio and meta_precio.get("content"):
                try:
                    precio = float(meta_precio["content"].replace(",", "."))
                except Exception:
                    pass

        if not titulo or not precio:
            return None

        # 4. Bloque técnico
        specs = []
        for elem in soup.select("table tr, dl > div, .ui-spec-list li"):
            specs.append(elem.get_text(separator=" ", strip=True))
        
        bloque_tecnico = sanitizar_guiones(f"{titulo} | " + " | ".join(specs))[:1500]

        return {
            "titulo": sanitizar_guiones(titulo),
            "precio": precio,
            "descripcion": bloque_tecnico,
            "vendedor": "LEROY MERLIN"
        }
    except Exception as e:
        print(f"      [Error leyendo ficha en CDP]: {e}")
        return None

def auditar_con_gemini(candidato: dict, item_leroy: dict) -> dict:
    tipo_cruce = candidato.get("tipo_cruce", "HOMOLOGADO_DIRECTO")
    info_obramat = candidato.get("obramat", {})

    if tipo_cruce == "HOMOLOGADO_DIRECTO":
        criterio_instruccion = """
NIVEL DE EVALUACIÓN: HOMOLOGACIÓN DIRECTA (MISMA MARCA Y MODELO).
1. Comprueba si es el mismo modelo base exacto de máquina o accesorio.
2. Comprueba la dotación o equipamiento (mangueras, prolongadores, baterías, maletín).
3. Si es idéntico en modelo y dotación, emite 'HOMOLOGADO_DIRECTO'. Si difiere la dotación accesoria, emite 'HOMOLOGADO_CON_DIFERENCIAS'. Si es un modelo o accesorio distinto, 'NO_EQUIVALENTE'.
"""
    else:
        especificaciones = candidato.get("especificaciones_exactas", "")
        criterio_instruccion = f"""
NIVEL DE EVALUACIÓN: EQUIVALENTE TÉCNICO EN MAQUINARIA.
Parámetros requeridos: {especificaciones}
1. Evalúa si el producto de Leroy Merlin cumple las mismas prestaciones de trabajo.
2. Si las especificaciones de servicio son equivalentes para el profesional, emite 'HOMOLOGADO_DIRECTO' o 'HOMOLOGADO_CON_DIFERENCIAS'.
3. Si difieren significativamente en potencia o tecnología, emite 'NO_EQUIVALENTE'.
"""

    prompt = f"""Actúa como un perito técnico de maquinaria profesional y analista de precios.
Compara estos dos productos para validar si su comparación comercial es rigurosa:

PRODUCTO DE REFERENCIA OBRAMAT:
- Título: {info_obramat.get('titulo', '')}
- Ref Fabricante: {info_obramat.get('ref_fabricante', 'N/D')}

PRODUCTO CANDIDATO LEROY MERLIN:
- Título: {item_leroy['titulo']}
- Ficha técnica: {item_leroy.get('descripcion', '')}

{criterio_instruccion}

Responde ÚNICAMENTE un objeto JSON válido:
{{
  "veredicto": "HOMOLOGADO_DIRECTO" | "HOMOLOGADO_CON_DIFERENCIAS" | "NO_EQUIVALENTE",
  "confianza": 0-100,
  "justificacion": "Explicación técnica concisa en una frase",
  "diferencia_dotacion": "Ninguna o resumen de la discrepancia de dotación"
}}
"""

    for mod in MODELOS_PRIORITARIOS:
        for intento in range(3):
            try:
                response = client.models.generate_content(
                    model=mod,
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
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    espera = 2 * (intento + 1)
                    print(f"      [Aviso 503 en {mod}]: Servidor saturado. Reintentando en {espera}s ({intento+1}/3)...")
                    time.sleep(espera)
                else:
                    break

    return {
        "veredicto": "ERROR_API",
        "confianza": 0,
        "justificacion": "Servidores de Gemini saturados momentáneamente tras reintentos.",
        "diferencia_dotacion": "Desconocida"
    }

def ejecutar_auditoria():
    print("=" * 75)
    print("AUDITORÍA INTELIGENTE: HOMOLOGACIÓN CON GEMINI VÍA CHROME CDP (9222)")
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

    with open(archivo_candidatos, "r", encoding="utf-8") as f:
        candidatos = json.load(f)

    print(f"Productos en vigilancia activa: {len(vigilancia_existente)}")
    print(f"Total parejas candidatas a procesar: {len(candidatos)}\n")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.new_page()
            print("Conectado con éxito a Chrome en localhost:9222 para auditoría.")
        except Exception as e:
            print(f"[Error crítico]: No se pudo conectar a Chrome en localhost:9222: {e}")
            return

        nuevos_homologados = 0

        for c in candidatos:
            info_obramat = c.get("obramat", {})
            id_cruce = str(c.get("id_cruce"))
            tipo_cruce = c.get("tipo_cruce", "HOMOLOGADO_DIRECTO")
            titulo_obramat = info_obramat.get("titulo", "Sin título")

            # --- PUNTO 3: BLINDAJE ANTI-SOBRESCRITURA DE CRUCES MANUALES Y HOMOLOGADOS ---
            if id_cruce in vigilancia_existente:
                item_existente = vigilancia_existente[id_cruce]
                # Si está bloqueado manualmente o ya fue homologado válidamente, se salta sin tocarlo
                if item_existente.get("bloqueado") is True:
                    print(f"-> [Protegido/Bloqueado]: {titulo_obramat[:55]} ya fijado manualmente. Saltando.")
                    continue
                if "HOMOLOGADO" in item_existente.get("veredicto_homologacion", ""):
                    continue

            url_lm = c.get("leroy_merlin", {}).get("url_candidata")
            if not url_lm:
                continue

            print(f"-> Evaluando [{tipo_cruce}]: {titulo_obramat[:55]}...")
            print(f"   URL Leroy: {url_lm[:70]}...")

            datos_lm = obtener_datos_leroy_cdp(page, url_lm)
            if not datos_lm or not datos_lm.get("titulo"):
                print("   [Saltado]: Ficha descartada (Marketplace o sin datos).\n")
                continue

            precio_lm = datos_lm["precio"]
            print(f"   Leroy (Venta Directa): '{datos_lm['titulo'][:50]}...' a {precio_lm} €")

            print("   Consultando a Gemini...")
            analisis = auditar_con_gemini(c, datos_lm)
            veredicto = analisis.get("veredicto", "NO_EQUIVALENTE")
            print(f"   Veredicto: {veredicto} ({analisis.get('confianza')}%) | {analisis.get('justificacion')}\n")

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
                        "ref_fabricante": info_obramat.get("ref_fabricante", ""),
                        "url": info_obramat.get("url")
                    },
                    "leroy_merlin": {
                        "titulo": datos_lm["titulo"],
                        "url": url_lm,
                        "vendedor": "LEROY MERLIN"
                    }
                }
                vigilancia_existente[id_cruce] = registro
                nuevos_homologados += 1

                with open(archivo_vigilancia, "w", encoding="utf-8") as f:
                    json.dump(list(vigilancia_existente.values()), f, ensure_ascii=False, indent=2)

        try:
            page.close()
        except Exception:
            pass

    print("=" * 75)
    print("AUDITORÍA CONCLUIDA:")
    print(f" - Nuevos productos incorporados: {nuevos_homologados}")
    print(f" - Catálogo total en vigilancia activa: {len(vigilancia_existente)} productos")
    print("=" * 75)

if __name__ == "__main__":
    ejecutar_auditoria()