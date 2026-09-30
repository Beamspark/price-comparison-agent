import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PENDIENTES_FILE = BASE_DIR / "candidatos_revision.json"
VIGILANCIA_FILE = BASE_DIR / "catalogo_vigilancia.json"
LISTA_NEGRA_FILE = BASE_DIR / "lista_negra.json"

def cargar_json(ruta: Path, default):
    if ruta.exists():
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def guardar_json(ruta: Path, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def listar():
    pendientes = cargar_json(PENDIENTES_FILE, [])
    if not pendientes:
        print("\nNo hay candidatos pendientes de revision.")
        return

    print("\n" + "=" * 80)
    print(f"CANDIDATOS PENDIENTES DE REVISION ({len(pendientes)})")
    print("=" * 80)
    for idx, c in enumerate(pendientes, 1):
        ref_ob = c.get("id_obramat", "S/REF")
        marca = c.get("marca", "")
        tit_ob = c.get("titulo_obramat", "")
        tit_lm = c.get("titulo_leroy", "")
        p_ob = c.get("precio_obramat", 0)
        p_lm = c.get("precio_leroy", 0)
        motivo = c.get("motivo_revision", "")

        print(f"[{idx}] Ref Obramat: {ref_ob} | {marca}")
        print(f"    Obramat: {tit_ob} ({p_ob} €)")
        print(f"    Leroy:   {tit_lm} ({p_lm} €)")
        print(f"    Motivo:  {motivo}")
        print("-" * 80)

def aprobar(id_obramat: str):
    pendientes = cargar_json(PENDIENTES_FILE, [])
    vigilancia = cargar_json(VIGILANCIA_FILE, [])

    candidato = next((c for c in pendientes if str(c.get("id_obramat")) == str(id_obramat)), None)
    if not candidato:
        print(f"No se encontro ningun candidato con Ref Obramat: {id_obramat}")
        return

    # Registrar en catálogo de vigilancia activo
    nuevo_vigilado = {
        "id_cruce": candidato.get("id_cruce", id_obramat),
        "tipo_cruce": "HOMOLOGADO_MANUAL",
        "marca": candidato.get("marca"),
        "veredicto_homologacion": "HOMOLOGADO_MANUAL",
        "detalles_homologacion": {
            "veredicto": "HOMOLOGADO_MANUAL",
            "confianza": 100,
            "justificacion": f"Aprobado manualmente. {candidato.get('motivo_revision', '')}"
        },
        "obramat": {
            "referencia_local": id_obramat,
            "titulo": candidato.get("titulo_obramat"),
            "precio_churra": candidato.get("precio_obramat"),
            "url": candidato.get("url_obramat")
        },
        "leroy_merlin": {
            "titulo": candidato.get("titulo_leroy"),
            "precio": candidato.get("precio_leroy"),
            "url": candidato.get("url_leroy"),
            "vendedor": "LEROY MERLIN"
        }
    }

    # Reemplazar o insertar en vigilancia
    vigilancia = [v for v in vigilancia if str(v.get("obramat", {}).get("referencia_local")) != str(id_obramat)]
    vigilancia.append(nuevo_vigilado)
    guardar_json(VIGILANCIA_FILE, vigilancia)

    # Quitar de pendientes
    pendientes = [c for c in pendientes if str(c.get("id_obramat")) != str(id_obramat)]
    guardar_json(PENDIENTES_FILE, pendientes)

    print(f"\n[Aprobado]: {id_obramat} anadido a catalogo_vigilancia.json.")

def rechazar(id_obramat: str):
    pendientes = cargar_json(PENDIENTES_FILE, [])
    lista_negra = cargar_json(LISTA_NEGRA_FILE, [])

    candidato = next((c for c in pendientes if str(c.get("id_obramat")) == str(id_obramat)), None)
    url_lm = candidato.get("url_leroy") if candidato else None

    # Guardar en lista negra para no volver a emparejarlos
    reg_bloqueo = {
        "id_obramat": str(id_obramat),
        "url_leroy": url_lm
    }
    if reg_bloqueo not in lista_negra:
        lista_negra.append(reg_bloqueo)
        guardar_json(LISTA_NEGRA_FILE, lista_negra)

    # Eliminar de pendientes
    pendientes = [c for c in pendientes if str(c.get("id_obramat")) != str(id_obramat)]
    guardar_json(PENDIENTES_FILE, pendientes)

    print(f"\n[Rechazado]: {id_obramat} descartado y agregado a lista_negra.json.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestion de Candidatos a Vigilancia")
    parser.add_argument("--listar", action="store_true", help="Listar candidatos pendientes")
    parser.add_argument("--aprobar", type=str, help="ID Obramat del candidato a aprobar")
    parser.add_argument("--rechazar", type=str, help="ID Obramat del candidato a rechazar")

    args = parser.parse_args()

    if args.listar:
        listar()
    elif args.aprobar:
        aprobar(args.aprobar)
    elif args.rechazar:
        rechazar(args.rechazar)
    else:
        parser.print_help()