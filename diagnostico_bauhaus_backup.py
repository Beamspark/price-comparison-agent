import json
from pathlib import Path

BACKUP_FILE = Path("catalogo_vigilancia_backup.json")
with open(BACKUP_FILE, "r", encoding="utf-8") as f:
    datos = json.load(f)

print(f"=== ANÁLISIS DE ITEMS CON BAUHAUS EN BACKUP ({len(datos)} totales) ===")
for i, item in enumerate(datos):
    bh = item.get("bauhaus")
    if not bh or not bh.get("url"):
        continue
    
    ref = item.get("id_cruce")
    ob = item.get("obramat", {})
    titulo_ob = ob.get("titulo") if isinstance(ob, dict) else item.get("titulo")
    url_ob = ob.get("url") if isinstance(ob, dict) else item.get("url_obramat")
    
    url_bh = bh.get("url", "")
    slug_bh = url_bh.split("/p/")[0].split("/")[-1] if "/p/" in url_bh else url_bh[-40:]

    print(f"[{i}] Ref Obramat: {ref} | Titulo Ob: {titulo_ob}")
    print(f"     URL Obramat: {url_ob}")
    print(f"     Bauhaus Slug: {slug_bh}")
    print("-" * 70)