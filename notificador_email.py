import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")  # Contraseña de aplicación
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO", "")

def generar_html_reporte(alertas_precio: list, candidatos_revision: list = None, productos_homologados: list = None) -> str:
    fecha_str = datetime.now().strftime("%d/%m/%Y - %H:%M")
    
    # 1. Extracción de listas de códigos OM (8 dígitos)
    codigos_homologados = []
    if productos_homologados:
        for p in productos_homologados:
            ref = str(p.get("obramat", {}).get("referencia_local", "") or p.get("id_obramat", ""))
            if ref and ref != "None" and ref not in codigos_homologados:
                codigos_homologados.append(ref)

    codigos_revision = []
    if candidatos_revision:
        for c in candidatos_revision:
            ref = str(c.get("id_obramat", "") or c.get("obramat", {}).get("referencia_local", ""))
            if ref and ref != "None" and ref not in codigos_revision:
                codigos_revision.append(ref)

    str_codigos_homologados = ", ".join(codigos_homologados) if codigos_homologados else "Ninguno registrado"
    str_codigos_revision = ", ".join(codigos_revision) if codigos_revision else "Ninguno pendiente"

    # 2. Filas de Alertas de Precio (Leroy más barato)
    filas_alertas = ""
    if alertas_precio:
        for item in alertas_precio:
            ref_om = item.get("id_obramat", "S/REF")
            filas_alertas += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px; font-family: monospace; font-weight: bold; color: #0284c7;">{ref_om}</td>
                <td style="padding: 10px; font-weight: bold; color: #1e293b;">{item.get('marca', '')}</td>
                <td style="padding: 10px; color: #334155;">{item.get('titulo', '')}</td>
                <td style="padding: 10px; text-align: center; font-weight: bold;">{item.get('precio_obramat')} €</td>
                <td style="padding: 10px; text-align: center; color: #b91c1c; font-weight: bold;">{item.get('precio_competidor')} €</td>
                <td style="padding: 10px; text-align: center; background-color: #fee2e2; color: #991b1b; font-weight: bold;">
                    {item.get('diferencia_eur')} € ({item.get('diferencia_pct')}%)
                </td>
                <td style="padding: 10px; text-align: center; white-space: nowrap;">
                    <a href="{item.get('url_obramat')}" target="_blank" style="background-color: #ea580c; color: white; padding: 6px 10px; text-decoration: none; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 4px; display: inline-block;">Obramat</a>
                    <a href="{item.get('url_competidor')}" target="_blank" style="background-color: #15803d; color: white; padding: 6px 10px; text-decoration: none; border-radius: 4px; font-size: 11px; font-weight: bold; display: inline-block;">Leroy</a>
                </td>
            </tr>
            """
    else:
        filas_alertas = """
        <tr>
            <td colspan="7" style="padding: 16px; text-align: center; color: #166534; background-color: #f0fdf4;">
                No se detectaron pérdidas de competitividad en la jornada de hoy. Obramat mantiene el mejor precio.
            </td>
        </tr>
        """

    # 3. Filas de Candidatos a Revisión
    seccion_revision = ""
    if candidatos_revision:
        filas_rev = ""
        for c in candidatos_revision:
            ref_om = c.get("id_obramat", "S/REF")
            filas_rev += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12px;">
                <td style="padding: 8px; font-family: monospace; font-weight: bold; color: #d97706;">{ref_om}</td>
                <td style="padding: 8px; font-weight: bold;">{c.get('marca', '')}</td>
                <td style="padding: 8px;"><b>Obramat:</b> {c.get('titulo_obramat')}<br><span style="color:#64748b;"><b>Candidato Leroy:</b> {c.get('titulo_leroy')}</span></td>
                <td style="padding: 8px; text-align: center;">{c.get('precio_obramat')} €</td>
                <td style="padding: 8px; text-align: center;">{c.get('precio_leroy')} €</td>
                <td style="padding: 8px; text-align: center; color: #475569;">{c.get('motivo_revision', '')}</td>
                <td style="padding: 8px; text-align: center; white-space: nowrap;">
                    <a href="{c.get('url_obramat')}" target="_blank" style="background-color: #ea580c; color: white; padding: 5px 8px; text-decoration: none; border-radius: 3px; font-size: 11px; margin-right: 3px; display: inline-block;">Obramat</a>
                    <a href="{c.get('url_leroy')}" target="_blank" style="background-color: #15803d; color: white; padding: 5px 8px; text-decoration: none; border-radius: 3px; font-size: 11px; display: inline-block;">Leroy</a>
                </td>
            </tr>
            """
        seccion_revision = f"""
        <div style="margin-top: 25px;">
            <h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 6px; font-size: 16px;">
                Candidatos Susceptibles de Error / En Revisión ({len(candidatos_revision)})
            </h3>
            <p style="font-size: 12px; color: #64748b; margin-bottom: 10px;">
                Referencias que presentan discrepancias leves de gama o dotación (ej. GWS 700 vs 750). Contrastar antes de homologar:
            </p>
            <div style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch;">
                <table style="width: 100%; min-width: 650px; border-collapse: collapse; font-family: Arial, sans-serif;">
                    <thead>
                        <tr style="background-color: #fef3c7; color: #92400e; font-size: 11px; text-transform: uppercase;">
                            <th style="padding: 8px; text-align: left;">Cód. OM</th>
                            <th style="padding: 8px; text-align: left;">Marca</th>
                            <th style="padding: 8px; text-align: left;">Comparativa</th>
                            <th style="padding: 8px; text-align: center;">Obramat</th>
                            <th style="padding: 8px; text-align: center;">Leroy</th>
                            <th style="padding: 8px; text-align: center;">Observación</th>
                            <th style="padding: 8px; text-align: center;">Comprobar</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filas_rev}
                    </tbody>
                </table>
            </div>
        </div>
        """

    # 4. Plantilla Completa
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 12px; color: #334155;">
        <div style="max-width: 880px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div style="border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 16px;">
                <h2 style="color: #0f172a; margin: 0; font-size: 18px;">Observatorio de Precios: Electroportátil y Maquinaria</h2>
                <p style="margin: 4px 0 0 0; color: #64748b; font-size: 13px;">Obramat Murcia-Churra vs Leroy Merlin Murcia | {fecha_str}</p>
            </div>

            <!-- TARJETAS DE COPIADO RÁPIDO DE CÓDIGOS OM -->
            <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;">
                <div style="flex: 1; min-width: 260px; background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 12px;">
                    <div style="font-size: 12px; font-weight: bold; color: #166534; text-transform: uppercase;">Códigos OM Exactos (100% Homologados)</div>
                    <div style="font-family: monospace; font-size: 12px; color: #15803d; margin-top: 6px; word-break: break-all;">
                        {str_codigos_homologados}
                    </div>
                </div>
                <div style="flex: 1; min-width: 260px; background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 12px;">
                    <div style="font-size: 12px; font-weight: bold; color: #92400e; text-transform: uppercase;">Códigos OM en Revisión (Susceptibles Error)</div>
                    <div style="font-family: monospace; font-size: 12px; color: #b45309; margin-top: 6px; word-break: break-all;">
                        {str_codigos_revision}
                    </div>
                </div>
            </div>

            <h3 style="color: #991b1b; border-bottom: 2px solid #fecaca; padding-bottom: 6px; font-size: 16px;">
                Alertas de Competitividad (Leroy Merlin más barato)
            </h3>
            
            <div style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch;">
                <table style="width: 100%; min-width: 650px; border-collapse: collapse; margin-top: 8px;">
                    <thead>
                        <tr style="background-color: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase;">
                            <th style="padding: 8px; text-align: left;">Cód. OM</th>
                            <th style="padding: 8px; text-align: left;">Marca</th>
                            <th style="padding: 8px; text-align: left;">Producto</th>
                            <th style="padding: 8px; text-align: center;">Obramat</th>
                            <th style="padding: 8px; text-align: center;">Leroy</th>
                            <th style="padding: 8px; text-align: center;">Diferencial</th>
                            <th style="padding: 8px; text-align: center;">Verificación</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filas_alertas}
                    </tbody>
                </table>
            </div>

            {seccion_revision}

            <div style="margin-top: 24px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 10px;">
                Sistema Autónomo de Monitorización de Precios • Almacén Murcia-Churra
            </div>
        </div>
    </body>
    </html>
    """

def enviar_email(alertas_precio: list, candidatos_revision: list = None, productos_homologados: list = None, forzar_envio: bool = False):
    if not alertas_precio and not candidatos_revision and not forzar_envio:
        print("[Notificador]: Sin alertas ni candidatos pendientes. No es necesario enviar correo.")
        return False

    if not SMTP_USER or not SMTP_PASS or not EMAIL_DESTINO:
        print("[Notificador Aviso]: Credenciales SMTP no configuradas. Saltando envío de correo.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        asunto = f"🚨 ALERTA PRECIOS: Competidor más barato ({len(alertas_precio)} productos)" if alertas_precio else "📋 Resumen de Vigilancia y Candidatos a Revisión"
        msg["Subject"] = asunto
        msg["From"] = f"Price Intelligence Bot <{SMTP_USER}>"
        msg["To"] = EMAIL_DESTINO

        html_body = generar_html_reporte(alertas_precio, candidatos_revision, productos_homologados)
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [EMAIL_DESTINO], msg.as_string())

        print(f"[Notificador]: Correo enviado con éxito a {EMAIL_DESTINO}")
        return True
    except Exception as e:
        print(f"[Notificador Error]: Fallo al enviar correo: {e}")
        return False