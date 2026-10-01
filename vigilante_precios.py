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
    Audita qué competidores venden el producto equivalente o sustitutivo directo a efectos de mercado.

    PRODUCTO NUESTRO (Obramat Churra):
    {json.dumps(nuestro, indent=2, ensure_ascii=False)}

    COMPETIDORES CANDIDATOS:
    {json.dumps(competidores, indent=2, ensure_ascii=False)}

    CRITERIOS DE HOMOLOGACIÓN Y EQUIVALENCIA COMERCIAL:
    1. SEGMENTO DE GAMA (FILTRO ESTRICTO):
       - PROHIBIDO equiparar herramientas de bricolaje doméstico con gamas profesionales.
       - En Bosch: Gama Profesional/Azul (GWS, GSR, GBH) NUNCA equivale a Bricolaje/Verde (UniversalGrind, Easy, PWS).
       - En DeWalt/Stanley: No mezclar líneas de uso industrial continuo con bricolaje ocasional.

    2. TOLERANCIA TÉCNICA DE SUSTITUCIÓN (REGLA DE MERCADO):
       - Dentro de la MISMA gama profesional (ej. Bosch Professional azul de 115mm):
         * Se consideran productos competidores directos y sustitutivos los modelos con variaciones menores de potencia de actualización de catálogo (por ejemplo, GWS 700W y GWS 750W con disco de 115mm son directamente comparables en precio de mostrador).
         * NO homologar saltos de potencia grandes (ej. 700W vs 1000W o más) ni cambios de diámetro de disco (115mm vs 125mm).
         * NO homologar herramientas con cable frente a herramientas a batería.

    3. DOTACIÓN Y ACCESORIOS:
       - Máquina básica en caja de cartón solo compite contra máquina básica.
       - No comparar una máquina sola frente a un set con maletín y accesorios de alto valor a menos que aún con maletín sea más barata.

    Devuelve ÚNICAMENTE un JSON con esta estructura exacta y nada más:
    {{
      "alerta_competencia_mas_barata": false,
      "competidor_lider": "Nombre del competidor idéntico o sustitutivo directo más barato (o 'Ninguno')",
      "tienda_competidor": "Ubicación o canal del competidor",
      "precio_competidor_minimo": 0.0,
      "nuestro_precio_churra": {nuestro['precio_actual']},
      "diferencia_desfavorable_eur": 0.0,
      "porcentaje_descuento_competidor": 0.0,
      "precio_recomendado_contraataque": 0.0,
      "resumen_tecnico": "Explica la validación: descarta bricolaje, reconoce sustitutos válidos de potencia (ej. 700W-750W) y analiza el precio."
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