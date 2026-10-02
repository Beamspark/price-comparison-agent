import json
from pathlib import Path

VIGILANCIA_FILE = Path("catalogo_vigilancia.json")

if not VIGILANCIA_FILE.exists():
    print("Error: No se encuentra catalogo_vigilancia.json")
    exit()

with open(VIGILANCIA_FILE, "r", encoding="utf-8") as f:
    catalogo = json.load(f)

# Definimos los cruces manuales exactos protegidos
CRUCES_PROTEGIDOS = {
    "10965262": {
        "url_leroy": "https://www.leroymerlin.es/productos/generador-gasolina-genergy-creta-sol-7500w-con-arranque-automatico-82354367.html", # o la URL de 629€ de Leroy
        "titulo_leroy": "GENERADOR GASOLINA GENERGY 7000W EQUIVALENTE",
        "precio_referencia_lm": 629.0
    },
    "10965241": {
        "url_leroy": "https://www.leroymerlin.es/productos/generador-profesional-gasolina-genergy-jaca-3300w-de-potencia-maxima-arranque-electrico-sistema-de-regulacion-electronica-82354365.html",
        "titulo_leroy": "GENERADOR GASOLINA GENERGY 3300W EQUIVALENTE",
        "precio_referencia_lm": 299.0
    }
}

modificados = 0
for item in catalogo:
    ref = str(item.get("obramat", {}).get("id_obramat") or item.get("id_cruce") or "").strip()
    
    # Si es uno de los que blindamos a mano
    if ref in CRUCES_PROTEGIDOS:
        item["bloqueado"] = True
        item["veredicto_homologacion"] = "HOMOLOGADO_MANUAL_PROTEGIDO"
        if "leroy_merlin" not in item:
            item["leroy_merlin"] = {}
        
        # Mantenemos las claves de URL consistentes
        item["leroy_merlin"]["url"] = CRUCES_PROTEGIDOS[ref]["url_leroy"]
        item["leroy_merlin"]["url_candidata"] = CRUCES_PROTEGIDOS[ref]["url_leroy"]
        item["leroy_merlin"]["vendedor"] = "LEROY MERLIN"
        modificados += 1
        print(f"[Protegido con éxito]: {ref} marcado como 'bloqueado: True'")

    # Aseguramos que los de Bauhaus no se pierdan
    if ref in ["10806222", "25105536"]:
        item["bloqueado"] = True
        print(f"[Protegido con éxito]: {ref} (Bauhaus) marcado como 'bloqueado: True'")

with open(VIGILANCIA_FILE, "w", encoding="utf-8") as f:
    json.dump(catalogo, f, ensure_ascii=False, indent=2)

print(f"\nCatálogo actualizado con éxito. {modificados} productos blindados contra sobrescritura del auditor.")