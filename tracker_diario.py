import os
import json
import csv
import re
import time
import random
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import notificador_email
from obramat_client import ObramatClient
from bauhaus_client import BauhausClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CONFIG_FILE = BASE_DIR / "config.json"
VIGILANCIA_FILE = BASE_DIR / "catalogo_vigilancia.json"
HISTORICO_CSV = BASE_DIR / "historico_precios.csv"
MAESTRO_FILE = BASE_DIR / "catalogo_maestro_obramat.json"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

cfg_obramat = CONFIG.get("obramat", {})
cfg_leroy = CONFIG.get("leroy_merlin", {})
cfg_bauhaus = CONFIG.get("bauhaus", {})

defaults_obramat = {
    "id": cfg_obramat.get("almacen_id", "42"),
    "almacen_id": cfg_obramat.get("id", "42"),
    "ciudad": "Murcia",
    "lat": cfg_leroy.get("lat", "37.9861"),
    "lon": cfg_leroy.get("lon", "-1.1213"),
    "cp": cfg_leroy.get("cp", "30003"),
    "postal_code": cfg_leroy.get("cp", "30003")
}

for k, v in defaults_obramat.items():
    if k not in cfg_obramat:
        cfg_obramat[k] = v

obramat = ObramatClient(cfg_obramat)

try:
    bauhaus = BauhausClient(cfg_bauhaus)
except TypeError:
    bauhaus = BauhausClient()

def limpiar_precio_texto(texto: str):
    """Parsea importes respetando puntos de millar (ej. 1.290 €) y comas decimales."""
    if not texto:
        return None
    try:
        m = re.search(r"(\d+(?:[\.,]\d+)?)", str(texto))
        if not m:
            return None
        cadena = m.group(1).strip()
        # Caso millares con punto exacto: 1 a 3 dígitos, punto, y 3 dígitos (ej: 1.290 ó 1.495)
        if re.search(r"^\d{1,3}\.\d{3}$", cadena):
            cadena = cadena.replace(".", "")
        else:
            cadena = cadena.replace(",", ".")
        return float(cadena)
    except Exception:
        return None

def normalizar_precio(val):
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        return limpiar_precio_texto(str(val))
    except (ValueError, TypeError):
        return None

def extraer_precio_obramat_cdp(page, url: str):
    """Navega a Obramat en vivo a través de Chrome CDP y extrae el precio oficial con IVA de Murcia."""
    if not url:
        return None
    try:
        time.sleep(random.uniform(1.0, 1.4))
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        
        # Espera activa a que el componente de precio esté visible en pantalla
        try:
            page.wait_for_selector(".m-price, .kl-price, .m-price__line, [data-test='product-price']", timeout=6000)
        except Exception:
            pass
        page.wait_for_timeout(1400)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # 1. Selector prioritario: bloque principal con IVA (.m-price.-main o .kl-price p.-main)
        bloque_principal = soup.select_one("p.m-price.-main, .m-price.-main, .kl-price p.-main")
        if bloque_principal:
            texto = bloque_principal.get_text(separator=" ", strip=True)
            m = re.search(r"(\d+[\.,]?\d*)\s*(?:€|IVA)", texto)
            if m:
                p = limpiar_precio_texto(m.group(1))
                if p:
                    return p

        # 2. Selector alternativo de accesibilidad explícito
        for span_acc in soup.select(".kl-hidden-accessibility"):
            txt_acc = span_acc.get_text(separator=" ", strip=True)
            if "IVA" in txt_acc and "SIN IVA" not in txt_acc.upper():
                p = limpiar_precio_texto(txt_acc)
                if p:
                    return p

        # 3. Primera línea de precio en el contenedor general
        linea_precio = soup.select_one(".m-price__line")
        if linea_precio:
            txt_linea = linea_precio.get_text(strip=True)
            if "sin IVA" not in txt_linea:
                p = limpiar_precio_texto(txt_linea)
                if p:
                    return p

        # 4. Selectores visuales clásicos de respaldo
        elem_ob = soup.select_one(".price-final, [data-test='product-price'], .main-price, .text-price, .price")
        if elem_ob:
            p = limpiar_precio_texto(elem_ob.get_text())
            if p:
                return p

    except Exception as e:
        print(f"      [Error Obramat CDP]: {e}")
    return None

def extraer_precio_leroy_cdp(page, url: str):
    """Consulta la ficha de Leroy Merlin a través de Chrome en puerto 9222 con filtro anti-Marketplace."""
    if not url:
        return None
    try:
        time.sleep(random.uniform(1.0, 1.6))
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        try:
            page.wait_for_selector("h1", timeout=5000)
        except Exception:
            pass

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # 1. Filtro Buy-box: verificar si es Marketplace externo
        nodo_vendedor = soup.find(string=re.compile(r"Vendido\s+(?:y\s+enviado\s+)?por", re.IGNORECASE))
        if nodo_vendedor:
            contenedor = nodo_vendedor.parent
            for _ in range(3):
                if contenedor and contenedor.parent:
                    contenedor = contenedor.parent
            texto_vendedor = contenedor.get_text(separator=" ", strip=True).upper() if contenedor else ""
            if "POR" in texto_vendedor and "LEROY MERLIN" not in texto_vendedor:
                match_tercero = re.search(r"POR\s+([A-Z0-9\s\.\-_]{3,35})", texto_vendedor)
                if match_tercero:
                    return None
        else:
            bloque_compra = soup.select_one("[data-qa='buybox'], .buybox, .pdp-buybox")
            if bloque_compra and "MARKETPLACE" in bloque_compra.get_text().upper():
                return None

        # 2. Extracción de precio directo
        # ld+json oficial de la oferta
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        offers = item.get("offers", {})
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict) and offers.get("price"):
                            return float(str(offers["price"]).replace(",", "."))
            except Exception:
                continue

        # Selectores visuales
        elem_entero = soup.select_one(".m-price__integer, [data-qa='price-integer']")
        elem_decimal = soup.select_one(".m-price__decimal, [data-qa='price-decimal']")
        if elem_entero:
            entero = re.sub(r"[^\d]", "", elem_entero.get_text())
            decimal = re.sub(r"[^\d]", "", elem_decimal.get_text()) if elem_decimal else "00"
            if entero:
                return float(f"{entero}.{decimal}")

        bloque_precio = soup.select_one(".price-tag, [data-qa='price'], .product-price, .price")
        if bloque_precio:
            p = limpiar_precio_texto(bloque_precio.get_text())
            if p:
                return p

        meta = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
        if meta and meta.get("content"):
            return float(meta["content"].replace(",", "."))

    except Exception as e:
        print(f"      [Error Leroy CDP]: {e}")
    return None

def extraer_precio_bauhaus_cdp(page, url: str):
    """Navega a la ficha de Bauhaus a través de Chrome en puerto 9222 en vivo."""
    if not url:
        return None
    try:
        time.sleep(random.uniform(1.0, 1.5))
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        try:
            page.wait_for_selector(".price-box, [data-qa='price'], .product-price, .current-price", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(1000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # 1. Metadatos estructurados LD+JSON
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        offers = item.get("offers", {})
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict) and offers.get("price"):
                            return float(str(offers["price"]).replace(",", "."))
            except Exception:
                continue

        # 2. Selectores visuales DOM
        elem_precio = soup.select_one(".price-box .price, .product-price, .current-price, .product-price__price, .price")
        if elem_precio:
            p = limpiar_precio_texto(elem_precio.get_text())
            if p:
                return p

        meta = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
        if meta and meta.get("content"):
            return float(meta["content"].replace(",", "."))

    except Exception as e:
        print(f"      [Error Bauhaus CDP]: {e}")
    return None

def ejecutar_tracking():
    if not VIGILANCIA_FILE.exists():
        print(f"[Error]: No existe el archivo {VIGILANCIA_FILE}")
        return

    with open(VIGILANCIA_FILE, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    urls_maestro_ob = {}
    if MAESTRO_FILE.exists():
        try:
            with open(MAESTRO_FILE, "r", encoding="utf-8") as f:
                maestro_data = json.load(f)
                for m in maestro_data:
                    mid = str(m.get("id") or m.get("id_obramat") or "").strip()
                    u = m.get("url")
                    if mid and u:
                        urls_maestro_ob[mid] = u
        except Exception:
            pass

    tienda_activa = cfg_obramat.get("nombre", "Obramat Murcia Churra")
    print("=" * 90)
    print(f"TRACKING EN VIVO VÍA CHROME CDP: {tienda_activa} vs COMPETENCIA ({len(catalogo)} items)")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            # Reutiliza estrictamente la pestaña física activa existente en Chrome sin abrir pestañas extra
            page = context.pages[0] if context.pages else context.new_page()
            print("Conectado con éxito a Chrome en localhost:9222 para rastreo en tiempo real.\n")
        except Exception as e:
            print(f"[Error crítico]: No se pudo conectar a Chrome en localhost:9222: {e}")
            return

        resultados = []

        for item in catalogo:
            es_homologado_lm = "HOMOLOGADO" in item.get("veredicto_homologacion", "")
            tiene_bauhaus = "bauhaus" in item

            if not es_homologado_lm and not tiene_bauhaus:
                continue

            ob_data = item.get("obramat") or {}
            lm_data = item.get("leroy_merlin") or {}
            bh_data = item.get("bauhaus") or {}

            ref_om = str(ob_data.get("id_obramat") or item.get("id_cruce") or "").strip()
            marca = item.get("marca") or ob_data.get("marca", "GENÉRICO")
            titulo = (ob_data.get("titulo") or item.get("titulo") or "Sin título")[:42]
            
            url_ob = ob_data.get("url") or urls_maestro_ob.get(ref_om)
            url_lm = lm_data.get("url") or lm_data.get("url_candidata")
            url_bh = bh_data.get("url")

            # 1. Consulta en directo a Obramat vía Chrome CDP (esperando hidratación de Murcia)
            precio_ob = extraer_precio_obramat_cdp(page, url_ob)

            # 2. Consulta en directo a Leroy Merlin vía Chrome CDP (puerto 9222)
            precio_lm = extraer_precio_leroy_cdp(page, url_lm)

            # 3. Consulta en directo a Bauhaus vía Chrome CDP (con fallback a cliente/datos previos si red falla)
            precio_bh = None
            if url_bh:
                precio_bh = extraer_precio_bauhaus_cdp(page, url_bh)
                if not precio_bh:
                    try:
                        for metodo in ["obtener_precio", "extraer_producto", "consultar_precio"]:
                            if hasattr(bauhaus, metodo):
                                res = getattr(bauhaus, metodo)(url_bh)
                                if isinstance(res, dict) and res.get("precio"):
                                    precio_bh = res["precio"]
                                    break
                                elif isinstance(res, (int, float)) and res > 0:
                                    precio_bh = res
                                    break
                    except Exception:
                        pass
                if not precio_bh and bh_data.get("precio"):
                    precio_bh = bh_data.get("precio")

            precio_ob = normalizar_precio(precio_ob)
            precio_lm = normalizar_precio(precio_lm)
            precio_bh = normalizar_precio(precio_bh)

            competidores_precios = [p for p in [precio_lm, precio_bh] if p is not None]
            mejor_competencia = min(competidores_precios) if competidores_precios else None

            dif_eur = None
            dif_pct = None
            estado = "N/D"

            if precio_ob and mejor_competencia:
                dif_eur = round(mejor_competencia - precio_ob, 2)
                dif_pct = round(((mejor_competencia - precio_ob) / precio_ob) * 100, 2)

                if dif_eur > 0:
                    estado = "OBRAMAT MAS BARATO"
                elif dif_eur < 0:
                    quien = "BAUHAUS" if mejor_competencia == precio_bh else "LEROY"
                    estado = f"{quien} MAS BARATO"
                else:
                    estado = "PRECIO EMPATADO"

            p_ob_str = f"{precio_ob:.2f} €" if precio_ob else "N/D"
            p_lm_str = f"{precio_lm:.2f} €" if precio_lm else "---"
            p_bh_str = f"{precio_bh:.2f} €" if precio_bh else "---"
            dif_str = f"{dif_eur:+.2f} €" if dif_eur is not None else "---"

            print(f"[{ref_om}] {titulo}")
            print(f"   OB: {p_ob_str:<9} | LM: {p_lm_str:<9} | BH: {p_bh_str:<9} | Dif: {dif_str:<9} ({estado})")

            resultados.append({
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "id_obramat": ref_om,
                "marca": marca,
                "titulo": titulo,
                "precio_obramat": precio_ob,
                "precio_leroy": precio_lm,
                "precio_bauhaus": precio_bh,
                "mejor_competencia": mejor_competencia,
                "diferencia_eur": dif_eur,
                "diferencia_pct": dif_pct,
                "estado": estado,
                "url_obramat": url_ob,
                "url_leroy": url_lm,
                "url_bauhaus": url_bh
            })

    columnas_csv = [
        "fecha", "id_obramat", "marca", "titulo", "precio_obramat",
        "precio_leroy", "precio_bauhaus", "mejor_competencia",
        "diferencia_eur", "diferencia_pct", "estado",
        "url_obramat", "url_leroy", "url_bauhaus"
    ]
    es_nuevo = not HISTORICO_CSV.exists()
    with open(HISTORICO_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columnas_csv)
        if es_nuevo:
            writer.writeheader()
        for r in resultados:
            writer.writerow(r)

    print("\n" + "=" * 90)
    print(f"Tracking completado con éxito. {len(resultados)} productos procesados y guardados en CSV.")
    print("=" * 90)

    # Evaluación y envío de alertas por correo
    alertas_precio = [r for r in resultados if "MAS BARATO" in r["estado"] and "OBRAMAT" not in r["estado"]]
    debe_enviar = CONFIG.get("notificaciones", {}).get("enviar_si_hay_alertas", True)
    if alertas_precio and debe_enviar:
        print(f"\n[Alerta]: Se detectaron {len(alertas_precio)} alertas de precio con la competencia. Enviando correo...")
        notificador_email.enviar_email(
            alertas_precio=alertas_precio,
            candidatos_revision=[],
            productos_homologados=catalogo
        )

if __name__ == "__main__":
    ejecutar_tracking()