import os
import json
import re
import csv
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi import requests
from dotenv import load_dotenv

import notificador_email

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

VIGILANCIA_FILE = BASE_DIR / "catalogo_vigilancia.json"
HISTORICO_CSV = BASE_DIR / "historico_precios.csv"
LEROY_COOKIE = os.getenv("LEROY_COOKIE", "")

session = requests.Session(impersonate="firefox")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin"
}

if LEROY_COOKIE:
    HEADERS["Cookie"] = LEROY_COOKIE

def extraer_precio_leroy(url: str):
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Intentar por JSON-LD
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
                
        # 2. Fallback meta tag
        meta = soup.find("meta", property="product:price:amount") or soup.find("meta", itemprop="price")
        if meta and meta.get("content"):
            return float(meta["content"].replace(",", "."))
    except Exception as e:
        print(f"Error extrayendo precio Leroy ({url[:40]}...): {e}")
    return None

def extraer_precio_obramat(url: str):
    try:
        headers_obramat = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0",
            "Cookie": "customer_context=42" # Store 42: Murcia-Churra
        }
        r = session.get(url, headers=headers_obramat, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        
        meta = soup.find("meta", property="product:price:amount")
        if meta and meta.get("content"):
            return float(meta["content"].replace(",", "."))
            
        match = re.search(r'data-qa="product-price"[^>]*>([\d\.,]+)\s*€', r.text)
        if match:
            return float(match.group(1).replace(".", "").replace(",", "."))
    except Exception as e:
        print(f"Error extrayendo precio Obramat ({url[:40]}...): {e}")
    return None

def ejecutar_tracking():
    if not VIGILANCIA_FILE.exists():
        print(f"[Error]: No existe {VIGILANCIA_FILE}")
        return

    with open(VIGILANCIA_FILE, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    print("=" * 75)
    print(f"TRACKING DIARIO DE PRECIOS: OBRAMAT CHURRA vs LEROY MERLIN ({len(catalogo)} items)")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75)

    resultados = []
    
    for item in catalogo:
        veredicto = item.get("veredicto_homologacion", "")
        if "HOMOLOGADO" not in veredicto:
            continue

        ref_om = str(item.get("obramat", {}).get("referencia_local", "") or item.get("id_obramat", ""))
        marca = item.get("marca", "")
        titulo_obramat = item.get("obramat", {}).get("titulo", "")[:40]
        url_obramat = item.get("obramat", {}).get("url")
        url_leroy = item.get("leroy_merlin", {}).get("url")
        precio_obramat_previo = item.get("obramat", {}).get("precio_churra")
        
        precio_ob = extraer_precio_obramat(url_obramat) or precio_obramat_previo
        precio_lm = extraer_precio_leroy(url_leroy)

        dif_eur = None
        dif_pct = None
        estado = "N/D"

        if precio_ob and precio_lm:
            dif_eur = round(precio_lm - precio_ob, 2)
            dif_pct = round(((precio_lm - precio_ob) / precio_ob) * 100, 2)
            if dif_eur > 0:
                estado = "OBRAMAT MAS BARATO"
            elif dif_eur < 0:
                estado = "LEROY MAS BARATO"
            else:
                estado = "PRECIO EMPATADO"

        print(f"[{ref_om}] [{marca}] {titulo_obramat}...")
        print(f"   Obramat: {precio_ob} € | Leroy: {precio_lm} € | Dif: {dif_eur} € ({estado})")

        resultados.append({
            "fecha": datetime.now().strftime("%Y-%m-%d"),
            "id_obramat": ref_om,
            "marca": marca,
            "titulo": titulo_obramat,
            "precio_obramat": precio_ob,
            "precio_leroy": precio_lm,
            "diferencia_eur": dif_eur,
            "diferencia_pct": dif_pct,
            "estado": estado,
            "url_obramat": url_obramat,
            "url_leroy": url_leroy
        })

    # Guardar en histórico CSV con id_obramat
    es_nuevo = not HISTORICO_CSV.exists()
    with open(HISTORICO_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "fecha", "id_obramat", "marca", "titulo", "precio_obramat", "precio_leroy",
            "diferencia_eur", "diferencia_pct", "estado", "url_obramat", "url_leroy"
        ])
        if es_nuevo:
            writer.writeheader()
        for r in resultados:
            writer.writerow(r)

    print("\n" + "=" * 75)
    print(f"Tracking finalizado. Registros volcados en '{HISTORICO_CSV.name}'.")
    print("=" * 75)

    # -------------------------------------------------------------
    # EVALUACIÓN DE ALERTAS Y ENVÍO POR CORREO
    # -------------------------------------------------------------
    alertas_precio = []
    for r in resultados:
        if r["estado"] == "LEROY MAS BARATO":
            alertas_precio.append({
                "id_obramat": r["id_obramat"],
                "marca": r["marca"],
                "titulo": r["titulo"],
                "precio_obramat": r["precio_obramat"],
                "precio_competidor": r["precio_leroy"],
                "diferencia_eur": r["diferencia_eur"],
                "diferencia_pct": r["diferencia_pct"],
                "url_obramat": r["url_obramat"],
                "url_competidor": r["url_leroy"]
            })

    candidatos_revision = []
    candidatos_file = BASE_DIR / "candidatos_revision.json"
    if candidatos_file.exists():
        try:
            with open(candidatos_file, "r", encoding="utf-8") as f:
                candidatos_revision = json.load(f)
        except Exception:
            pass

    if alertas_precio or candidatos_revision:
        print(f"\n[Alerta]: Se detectaron {len(alertas_precio)} alertas y {len(candidatos_revision)} candidatos.")
        notificador_email.enviar_email(
            alertas_precio=alertas_precio,
            candidatos_revision=candidatos_revision,
            productos_homologados=catalogo
        )
    else:
        print("\n[OK]: Competitividad asegurada. Sin alertas de precio activas.")

if __name__ == "__main__":
    ejecutar_tracking()