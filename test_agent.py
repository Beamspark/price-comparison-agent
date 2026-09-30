import os
import json
import requests
from dotenv import load_dotenv

# Cargar configuración desde .env
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
modelo = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not api_key:
    print("Error: No se encontró GEMINI_API_KEY en el archivo .env")
    exit()

print(f"-> Conectando con Gemini ({modelo})...")

url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"

producto_a = {
    "tienda": "Obramat Murcia",
    "titulo": "Amoladora angular BOSCH GWS 750-115 750W disco 115mm",
    "precio": 54.90,
    "descripcion": "Amoladora con motor de 750W. Diámetro de disco 115mm. Incluye empuñadura auxiliar y llave. No incluye maletín."
}

producto_b = {
    "tienda": "Leroy Merlin Murcia",
    "titulo": "Miniamoladora con cable Bosch Professional GWS 750 de 750 W y disco de 115 mm",
    "precio": 59.00,
    "descripcion": "Herramienta con potencia de 750W, protector contra rearranque, disco de 115 mm. Se entrega en caja de cartón sin maletín."
}

prompt = f"""
Actúa como un experto en retail y herramientas de bricolaje/construcción.
Analiza si estos dos artículos corresponden al MISMO producto exacto y evalúa la diferencia de precio.

Artículo 1:
{producto_a}

Artículo 2:
{producto_b}

Devuelve OBLIGATORIAMENTE un JSON con esta estructura exacta y nada más:
{{
  "es_mismo_producto": true,
  "justificacion_tecnica": "breve explicacion sobre modelo, potencia y dotacion",
  "tienda_mas_barata": "nombre de la tienda",
  "precio_mas_barato": 0.0,
  "tienda_mas_cara": "nombre de la tienda",
  "precio_mas_caro": 0.0,
  "diferencia_eur": 0.0,
  "diferencia_porcentaje": 0.0,
  "alerta_obramat_mas_caro": false,
  "precio_objetivo_recomendado": 0.0
}}
"""

payload = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {
        "responseMimeType": "application/json",
        "temperature": 0.1
    }
}

headers = {"Content-Type": "application/json"}

try:
    print("Enviando consulta de análisis...")
    response = requests.post(url, json=payload, headers=headers, timeout=20)
    
    if response.status_code == 200:
        data = response.json()
        raw_json = data["candidates"][0]["content"]["parts"][0]["text"]
        resultado = json.loads(raw_json)
        print("\n--- RESPUESTA JSON ESTRUCTURADA ---")
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        print(f"Error {response.status_code}: {response.text}")

except requests.exceptions.Timeout:
    print("Error: Tiempo de espera agotado.")
except Exception as e:
    print(f"Error: {e}")