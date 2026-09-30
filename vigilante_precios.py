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
    Actúa como un perito técnico y auditor de compras de ferretería industrial para Obramat Churra.
    Audita si los competidores ofrecen EXACTAMENTE el mismo producto o si se trata de un falso positivo.

    PRODUCTO NUESTRO (Obramat Churra):
    - Título: {nuestro['titulo']}
    - Precio: {nuestro['precio_actual']} €

    COMPETIDORES A COMPARAR:
    {json.dumps(competidores, indent=2, ensure_ascii=False)}

    REGLAS ESTRICTAS DE HOMOLOGACIÓN:
    1. SEGMENTACIÓN DE GAMA (VITAL): 
       - NO compares herramientas profesionales con gamas de bricolaje doméstico.
       - En Bosch: 'GWS', 'GSR', 'GBH' o 'Bosch Professional' (gama azul) NUNCA es equivalente a 'UniversalGrind', 'EasyGrind', 'Advanced', 'PWS' o gamas verdes de bricolaje doméstico.
       - En DeWalt / Stanley / Black&Decker: no mezclar gamas de uso profesional continuo con gamas de bricolaje ocasional.
    2. POTENCIA Y CARACTERÍSTICAS TÉCNICAS:
       - No homologues potencias diferentes (ej. 700W no es 750W).
       - No homologues diámetros de disco o voltajes diferentes.
    3. DOTACIÓN Y ACCESORIOS:
       - Máquina con 2 baterías + maletín NO equivale a máquina sola (cuerpo sin batería).

    Devuelve OBLIGATORIAMENTE un JSON con esta estructura exacta y nada más:
    {{
      "es_mismo_producto": true,
      "alerta_competencia_mas_barata": false,
      "competidor_lider": "Nombre del competidor más barato idéntico (o 'Ninguno')",
      "tienda_competidor": "Ubicación del competidor",
      "precio_competidor_minimo": 0.0,
      "nuestro_precio_churra": {nuestro['precio_actual']},
      "diferencia_desfavorable_eur": 0.0,
      "porcentaje_descuento_competidor": 0.0,
      "precio_recomendado_contraataque": 0.0,
      "resumen_tecnico": "Explicación detallada del descarte o de la coincidencia"
    }}

    CONDICIÓN OBLIGATORIA:
    - Si el producto de la competencia es gama verde/bricolaje y el nuestro es profesional (azul), o difieren en potencia o dotación:
      * 'es_mismo_producto' DEBE SER false.
      * 'alerta_competencia_mas_barata' DEBE SER false.
      * 'competidor_lider' DEBE SER 'Ninguno'.
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
        print(f"OK [Sin Alerta]: {item['nombre_interno']} -> {resultado['resumen_tecnico']}")

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