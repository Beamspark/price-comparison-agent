import os
import json
import csv
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi import requests
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

# Configuración leída desde config.json
cfg_obramat = CONFIG.get("obramat", {})
cfg_leroy = CONFIG.get("leroy_merlin", {})
cfg_bauhaus = CONFIG.get("bauhaus", {})

# Completar valores que espera ObramatClient usando datos locales y alias
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
session_lm = requests.Session(impersonate="firefox")


def normalizar_precio(val):
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace("€", "").replace("\xa0", "").strip()
        s = s.replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return None


def get_leroy_headers(store_id: str, store_name: str) -> dict:
    cookie_str = (
        f'store=store={store_id}|dateContext=20261001; store_id={store_id}; lmes_store_id={store_id}; '
        f'customer_context={{"auto_context":"false","city":"Murcia","latitude":"37.9861",'
        f'"main_store":"{store_id}","postcode":"30003","stores_name":[{{"name":"{store_name}","id":"{store_id}"}}],"longitude":"-1.1213"}}'
    )
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
        "Cookie": cookie_str
    }


def extraer_precio_leroy(url: str, headers_tienda: dict):
    if not url:
        return None
    try:
        r = session_lm.get(url, headers=headers_tienda, timeout=15)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
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

        meta = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
        if meta and meta.get("content"):
            return float(meta["content"].replace(",", "."))
    except Exception as e:
        print(f"[Leroy Error] {url[:50]}: {e}")
    return None


def ejecutar_tracking():
    if not VIGILANCIA_FILE.exists():
        print(f"[Error]: No existe el archivo {VIGILANCIA_FILE}")
        return

    with open(VIGILANCIA_FILE, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    # Cargar catálogo maestro de Obramat para precios de respaldo
    precios_maestro_ob = {}
    urls_maestro_ob = {}
    if MAESTRO_FILE.exists():
        try:
            with open(MAESTRO_FILE, "r", encoding="utf-8") as f:
                maestro_data = json.load(f)
                for m in maestro_data:
                    mid = str(m.get("id") or m.get("id_obramat") or "").strip()
                    p = m.get("precio") or m.get("precio_iva")
                    u = m.get("url")
                    if mid and p:
                        precios_maestro_ob[mid] = p
                    if mid and u:
                        urls_maestro_ob[mid] = u
        except Exception:
            pass

    tienda_activa = cfg_obramat.get("nombre", "Obramat Churra")
    print("=" * 90)
    print(f"TRACKING PRECIOS LOCAL: {tienda_activa} vs COMPETENCIA ({len(catalogo)} items)")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    resultados = []

    tiendas_leroy = []
    if cfg_leroy.get("tienda_principal"):
        tiendas_leroy.append({"id": cfg_leroy["tienda_principal"], "nombre": cfg_leroy.get("nombre", "Murcia Sur")})
    if cfg_leroy.get("tienda_cercana"):
        tiendas_leroy.append({"id": cfg_leroy["tienda_cercana"], "nombre": "Tienda Cercana"})

    for item in catalogo:
        es_homologado_lm = "HOMOLOGADO" in item.get("veredicto_homologacion", "")
        tiene_bauhaus = "bauhaus" in item

        if not es_homologado_lm and not tiene_bauhaus:
            continue

        ob_data = item.get("obramat", {})
        lm_data = item.get("leroy_merlin", {})
        bh_data = item.get("bauhaus", {})

        ref_om = str(ob_data.get("id_obramat") or item.get("id_obramat") or item.get("id") or "").strip()
        marca = item.get("marca") or ob_data.get("marca", "GENÉRICO")
        titulo = (ob_data.get("titulo") or item.get("titulo_obramat") or item.get("titulo") or "Sin título")[:42]
        url_ob = ob_data.get("url") or urls_maestro_ob.get(ref_om)
        url_lm = lm_data.get("url") or lm_data.get("url_candidata")
        url_bh = bh_data.get("url")

        # 1. Consulta Obramat
        precio_ob = None
        if url_ob:
            precio_ob = obramat.obtener_precio(url_ob)
        if not precio_ob:
            p_fallback = (
                ob_data.get("precio_churra") 
                or ob_data.get("precio") 
                or item.get("precio_obramat") 
                or precios_maestro_ob.get(ref_om)
            )
            precio_ob = p_fallback

        # 2. Consulta Leroy Merlin
        precio_lm_min = None
        if url_lm:
            precios_lm = []
            for t in tiendas_leroy:
                headers_t = get_leroy_headers(t["id"], t["nombre"])
                p = extraer_precio_leroy(url_lm, headers_t)
                if p is not None:
                    precios_lm.append(p)
            precio_lm_min = min(precios_lm) if precios_lm else None
            if not precio_lm_min and lm_data.get("precio"):
                precio_lm_min = lm_data.get("precio")

        # 3. Consulta Bauhaus Alfafar (con fallback directo al precio homologado)
        precio_bh = bh_data.get("precio") or item.get("precio_bauhaus")
        if url_bh:
            try:
                for metodo in ["obtener_precio", "extraer_producto", "consultar_precio", "scrape_product"]:
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

        # 4. Normalización y cálculo
        precio_ob = normalizar_precio(precio_ob)
        precio_lm_min = normalizar_precio(precio_lm_min)
        precio_bh = normalizar_precio(precio_bh)

        competidores_precios = [p for p in [precio_lm_min, precio_bh] if p is not None]
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
        p_lm_str = f"{precio_lm_min:.2f} €" if precio_lm_min else "---"
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
            "precio_leroy": precio_lm_min,
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