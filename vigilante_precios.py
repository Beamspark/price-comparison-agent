import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
modelo = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not api_key:
    print("Error: No se encontró GEMINI_API_KEY.")
    exit()

URL_API = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"

def evaluar_mercado_producto(item):
    nuestro = item["obramat"]
    competidores = item["competidores"]

    prompt = f"""
    Actúa como perito técnico de compras industriales para Obramat Churra.
    Audita qué competidores venden EXACTAMENTE el mismo producto técnico.

    PRODUCTO NUESTRO (Obramat Churra):
    {json.dumps(nuestro, indent=2, ensure_ascii=False)}

    COMPETIDORES CANDIDATOS:
    {json.dumps(competidores, indent=2, ensure_ascii=False)}

    REGLAS DE ORO OBLIGATORIAS:
    1. PROHIBIDO comparar herramientas de gama doméstica/bricolaje con herramientas de gama profesional.
       - Si nuestro producto es Bosch Azul (Professional / GWS / GSR / GBH) y el competidor es Bosch Verde (UniversalGrind / EasyGrind / AdvancedGrind / PWS), DEBES DESCARTARLO INMEDIATAMENTE como producto distinto.
    2. POTENCIA Y MODELO:
       - Si la potencia en vatios o el modelo no coincide exactamente (ej. 700W frente a 750W), NO es el mismo producto.
    3. Para cada competidor:
       - Solo compite si es 100% idéntico técnica y comercialmente.
       - Si ninguno de los competidores más baratos es idéntico, NO se emite alerta.

    Devuelve ÚNICAMENTE un JSON con esta estructura exacta y nada más:
    {{
      "alerta_competencia_mas_barata": false,
      "competidor_lider": "Nombre del competidor idéntico más barato (o 'Ninguno')",
      "tienda_competidor": "Ubicación o 'Ninguna'",
      "precio_competidor_minimo": 0.0,
      "nuestro_precio_churra": {nuestro['precio_actual']},
      "diferencia_desfavorable_eur": 0.0,
      "porcentaje_descuento_competidor": 0.0,
      "precio_recomendado_contraataque": 0.0,
      "resumen_tecnico": "Explica con precisión qué productos fueron descartados por gama/potencia y si alguno idéntico supera el precio."
    }}
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0
        }
    }

    try:
        res = requests.post(URL_API, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
        if res.status_code == 200:
            raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw)
        else:
            print(f"Error API ({res.status_code}): {res.text}")
            return None
    except Exception as e:
        print(f"Error analizando {item['id_referencia']}: {e}")
        return None

# Cargar catálogo de vigilancia
with open("catalogo_vigilancia.json", "r", encoding="utf-8") as f:
    catalogo = json.load(f)

print(f"Iniciando auditoría de {len(catalogo)} productos frente a competidores...")
alertas = []

for item in catalogo:
    resultado = evaluar_mercado_producto(item)
    if resultado and resultado.get("alerta_competencia_mas_barata"):
        alertas.append({
            "id": item["id_referencia"],
            "producto": item["nombre_interno"],
            "analisis": resultado
        })
    elif resultado:
        print(f"\nOK [Sin Alerta]: {item['nombre_interno']}")
        print(f"Análisis: {resultado['resumen_tecnico']}")

print("\n" + "="*60)
print(f"INFORME FINAL: Se detectaron {len(alertas)} alertas de precios desfavorables.")
print("="*60)

if alertas:
    for a in alertas:
        res = a["analisis"]
        print(f"\n[ALERTA DE PRECIO - ACCIÓN REQUERIDA]")
        print(f"Producto: {a['id']} - {a['producto']}")
        print(f"Obramat Churra: {res['nuestro_precio_churra']} €")
        print(f"Rival más barato: {res['competidor_lider']} ({res['tienda_competidor']}) a {res['precio_competidor_minimo']} €")
        print(f"Brecha desfavorable: -{res['diferencia_desfavorable_eur']} € ({res['porcentaje_descuento_competidor']}%)")
        print(f"Precio sugerido para recuperar el liderazgo: {res['precio_recomendado_contraataque']} €")
        print(f"Detalle: {res['resumen_tecnico']}")
else:
    print("\nNingún competidor supera a Obramat Churra en producto idéntico verificado.")