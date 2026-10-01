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
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO", "")


def generar_botones_verificacion(item: dict) -> str:
    botones = []
    
    # 1. Botón Obramat
    url_ob = item.get("url_obramat")
    if url_ob:
        botones.append(
            f'<a href="{url_ob}" target="_blank" style="background-color: #ea580c; color: #ffffff; '
            f'padding: 4px 8px; text-decoration: none; border-radius: 4px; font-size: 11px; font-weight: bold; '
            f'margin: 2px; display: inline-block;">Obramat</a>'
        )
    
    # 2. Botón Leroy Merlin
    url_lm = item.get("url_leroy") or item.get("url_competidor")
    if url_lm:
        botones.append(
            f'<a href="{url_lm}" target="_blank" style="background-color: #15803d; color: #ffffff; '
            f'padding: 4px 8px; text-decoration: none; border-radius: 4px; font-size: 11px; font-weight: bold; '
            f'margin: 2px; display: inline-block;">Leroy</a>'
        )
        
    # 3. Botón Bauhaus
    url_bh = item.get("url_bauhaus")
    if url_bh:
        botones.append(
            f'<a href="{url_bh}" target="_blank" style="background-color: #0284c7; color: #ffffff; '
            f'padding: 4px 8px; text-decoration: none; border-radius: 4px; font-size: 11px; font-weight: bold; '
            f'margin: 2px; display: inline-block;">Bauhaus</a>'
        )
        
    # 4. Preparado para futuros comercios (ej. Amazon)
    url_amz = item.get("url_amazon")
    if url_amz:
        botones.append(
            f'<a href="{url_amz}" target="_blank" style="background-color: #111827; color: #ffffff; '
            f'padding: 4px 8px; text-decoration: none; border-radius: 4px; font-size: 11px; font-weight: bold; '
            f'margin: 2px; display: inline-block;">Amazon</a>'
        )

    if not botones:
        return '<span style="color: #94a3b8; font-size: 11px;">---</span>'

    # Contenedor con envoltura flexible para que en móvil nunca desborde horizontalmente
    return (
        '<div style="display: flex; flex-wrap: wrap; justify-content: center; align-items: center; min-width: 130px; gap: 2px;">'
        + "".join(botones)
        + '</div>'
    )


def generar_html_reporte(alertas_precio: list, candidatos_revision: list = None, productos_homologados: list = None) -> str:
    fecha_str = datetime.now().strftime("%d/%m/%Y - %H:%M")

    # 1. Extracción ÚNICAMENTE de los códigos OM de las alertas presentes en este correo
    codigos_alertas = []
    if alertas_precio:
        for a in alertas_precio:
            ref = str(a.get("id_obramat") or "").strip()
            if ref and ref not in ["None", "S/REF", ""] and ref not in codigos_alertas:
                codigos_alertas.append(ref)

    str_codigos_alertas = ", ".join(codigos_alertas) if codigos_alertas else "Ningún código en alerta hoy"

    # 2. Filas de Alertas de Precio Multi-competidor
    filas_alertas = ""
    if alertas_precio:
        for item in alertas_precio:
            ref_om = item.get("id_obramat") or "S/REF"
            p_ob = item.get("precio_obramat")
            p_ob_txt = f"{p_ob:.2f} €" if isinstance(p_ob, (int, float)) else f"{p_ob} €"

            # Identificar qué competidor es el más barato
            p_lm = item.get("precio_leroy")
            p_bh = item.get("precio_bauhaus")
            mejor_comp = item.get("mejor_competencia") or item.get("precio_competidor")

            detalle_comp = []
            if p_lm is not None:
                detalle_comp.append(f'<span style="color: #15803d; font-weight: bold;">LM: {p_lm:.2f} €</span>')
            if p_bh is not None:
                detalle_comp.append(f'<span style="color: #0284c7; font-weight: bold;">BH: {p_bh:.2f} €</span>')

            str_detalle_comp = "<br>".join(detalle_comp) if detalle_comp else (f"{mejor_comp:.2f} €" if mejor_comp else "---")

            # Formateo de diferencia
            dif_eur = item.get("diferencia_eur")
            dif_pct = item.get("diferencia_pct")
            dif_eur_txt = f"{dif_eur:+.2f} €" if isinstance(dif_eur, (int, float)) else f"{dif_eur} €"
            dif_pct_txt = f"({dif_pct:+.2f}%)" if isinstance(dif_pct, (int, float)) else ""

            botones_html = generar_botones_verificacion(item)

            filas_alertas += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px; font-family: monospace; font-weight: bold; color: #0284c7; white-space: nowrap;">{ref_om}</td>
                <td style="padding: 10px; font-weight: bold; color: #1e293b; white-space: nowrap;">{item.get('marca', '')}</td>
                <td style="padding: 10px; color: #334155; max-width: 260px; word-break: break-word;">{item.get('titulo', '')}</td>
                <td style="padding: 10px; text-align: center; font-weight: bold; white-space: nowrap;">{p_ob_txt}</td>
                <td style="padding: 10px; text-align: center; font-size: 12px; white-space: nowrap;">{str_detalle_comp}</td>
                <td style="padding: 10px; text-align: center; background-color: #fee2e2; color: #991b1b; font-weight: bold; white-space: nowrap;">
                    {dif_eur_txt}<br><span style="font-size: 11px;">{dif_pct_txt}</span>
                </td>
                <td style="padding: 6px; text-align: center;">
                    {botones_html}
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

    # 3. Candidatos en revisión (opcional si existen)
    seccion_revision = ""
    if candidatos_revision:
        filas_rev = ""
        for c in candidatos_revision:
            ref_om = c.get("id_obramat", "S/REF")
            filas_rev += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12px;">
                <td style="padding: 8px; font-family: monospace; font-weight: bold; color: #d97706;">{ref_om}</td>
                <td style="padding: 8px; font-weight: bold;">{c.get('marca', '')}</td>
                <td style="padding: 8px;"><b>Obramat:</b> {c.get('titulo_obramat')}<br><span style="color:#64748b;"><b>Candidato:</b> {c.get('titulo_leroy')}</span></td>
                <td style="padding: 8px; text-align: center;">{c.get('precio_obramat')} €</td>
                <td style="padding: 8px; text-align: center;">{c.get('precio_leroy')} €</td>
                <td style="padding: 8px; text-align: center; color: #475569;">{c.get('motivo_revision', '')}</td>
                <td style="padding: 8px; text-align: center;">
                    <a href="{c.get('url_obramat')}" target="_blank" style="background-color: #ea580c; color: white; padding: 4px 8px; text-decoration: none; border-radius: 3px; font-size: 11px; margin: 2px; display: inline-block;">Obramat</a>
                    <a href="{c.get('url_leroy')}" target="_blank" style="background-color: #15803d; color: white; padding: 4px 8px; text-decoration: none; border-radius: 3px; font-size: 11px; margin: 2px; display: inline-block;">Leroy</a>
                </td>
            </tr>
            """
        seccion_revision = f"""
        <div style="margin-top: 25px;">
            <h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 6px; font-size: 15px;">
                Candidatos Susceptibles de Error / En Revisión ({len(candidatos_revision)})
            </h3>
            <div style="width: 100%; overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif;">
                    <thead>
                        <tr style="background-color: #fef3c7; color: #92400e; font-size: 11px; text-transform: uppercase;">
                            <th style="padding: 8px; text-align: left;">Cód. OM</th>
                            <th style="padding: 8px; text-align: left;">Marca</th>
                            <th style="padding: 8px; text-align: left;">Comparativa</th>
                            <th style="padding: 8px; text-align: center;">Obramat</th>
                            <th style="padding: 8px; text-align: center;">Competidor</th>
                            <th style="padding: 8px; text-align: center;">Observación</th>
                            <th style="padding: 8px; text-align: center;">Verificar</th>
                        </tr>
                    </thead>
                    <tbody>{filas_rev}</tbody>
                </table>
            </div>
        </div>
        """

    total_alertas = len(alertas_precio) if alertas_precio else 0

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 10px; color: #334155;">
    <div style="max-width: 900px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        
        <!-- CABECERA -->
        <div style="border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 14px;">
            <h2 style="color: #0f172a; margin: 0; font-size: 18px;">Observatorio Diario de Precios y Competitividad</h2>
            <p style="margin: 4px 0 0 0; color: #64748b; font-size: 13px;">Obramat Murcia-Churra vs Leroy Merlin & Bauhaus | {fecha_str}</p>
        </div>

        <!-- TARJETA CÓDIGOS OM EN ALERTA -->
        <div style="background-color: #fff1f2; border: 1px solid #fecdd3; border-radius: 6px; padding: 12px; margin-bottom: 18px;">
            <div style="font-size: 12px; font-weight: bold; color: #9f1239; text-transform: uppercase;">
                Códigos Obramat con Alerta Activa Hoy ({total_alertas})
            </div>
            <div style="font-family: monospace; font-size: 13px; font-weight: bold; color: #be123c; margin-top: 6px; word-break: break-all; line-height: 1.5;">
                {str_codigos_alertas}
            </div>
        </div>

        <!-- TABLA PRINCIPAL DE ALERTAS -->
        <h3 style="color: #991b1b; border-bottom: 2px solid #fecaca; padding-bottom: 6px; font-size: 16px; margin: 0 0 10px 0;">
            Pérdidas de Competitividad Detectadas ({total_alertas})
        </h3>
        
        <div style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch;">
            <table style="width: 100%; min-width: 680px; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase;">
                        <th style="padding: 8px; text-align: left;">Cód. OM</th>
                        <th style="padding: 8px; text-align: left;">Marca</th>
                        <th style="padding: 8px; text-align: left;">Producto</th>
                        <th style="padding: 8px; text-align: center;">Obramat</th>
                        <th style="padding: 8px; text-align: center;">Competencia</th>
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
            Price Comparison Agent • Automatización Diaria GitHub Actions
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
        asunto = f"🚨 ALERTA PRECIOS: Competencia más barata ({len(alertas_precio)} productos)" if alertas_precio else "📋 Resumen de Vigilancia"
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