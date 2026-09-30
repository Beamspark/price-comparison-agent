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
    Actúa como auditor de precios para Obramat Churra (Murcia Norte).
    Compara nuestro producto contra la lista de competidores (Leroy Merlin, Brico Depôt, Bauhaus).
    
    Nuestro artículo:
    - Tienda: Obramat Churra
    - Título: {nuestro['titulo']}
    - Precio: {nuestro['precio_actual']} €

    Competidores a auditar:
    {json.dumps(competidores, indent=2, ensure_ascii=False)}

    Objetivo:
    1. Verifica si los artículos de los competidores corresponden al mismo producto exacto.
    2. Identifica cuál es el competidor con el precio MÍNIMO verificado.
    3. Determina si ese competidor más barato supera a Obramat Churra (es decir, si vende más barato que nosotros).

    Devuelve OBLIGATORIAMENTE un JSON con esta estructura exacta y nada más:
    {{
      "alerta_competencia_mas_barata": true,
      "competidor_lider": "Nombre de la empresa más barata (o 'Ninguno')",
      "tienda_competidor": "Ubicación o canal del competidor líder",
      "precio_competidor_minimo": 0.0,
      "nuestro_precio_churra": {nuestro['precio_actual']},
      "diferencia_desfavorable_eur": 0.0,
      "porcentaje_descuento_competidor": 0.0,
      "precio_recomendado_contraataque": 0.0,
      "resumen_tecnico": "breve explicación técnica"
    }}
    NOTA: 'alerta_competencia_mas_barata' SOLO debe ser true si el precio del competidor líder es INFERIOR a {nuestro['precio_actual']}.
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    try:
        res = requests.post(URL_API, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
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

print(f"Iniciando auditoría de {len(catalogo)} productos frente a Leroy Merlin, Brico Depôt y Bauhaus...")
alertas = []

for item in catalogo:
    resultado = evaluar_mercado_producto(item)
    if resultado and resultado.get("alerta_competencia_mas_barata"):
        alertas.append({
            "id": item["id_referencia"],
            "producto": item["nombre_interno"],
            "analisis": resultado
        })

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
        print(f"Precio recomendado para recuperar el liderazgo: {res['precio_recomendado_contraataque']} €")
        print(f"Detalle: {res['resumen_tecnico']}")
else:
    print("\nTodo en orden: Obramat Churra mantiene el precio más bajo en todas las referencias auditadas.")