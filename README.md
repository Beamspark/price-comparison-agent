# price-comparison-agent
Automated retail price comparator using Python, Gemini API and GitHub Actions

## 🤖 Integración del Agente de IA (Google Gemini API)

El sistema integra un agente impulsado por el modelo **Google Gemini** (mediante `GEMINI_API_KEY`), diseñado para realizar tareas de alto nivel cognitivo dentro del flujo de datos:

* **Normalización y homologación de referencias:** Análisis de descripciones complejas de productos de diferentes catálogos para confirmar equivalencias técnicas entre tiendas (verificar que una referencia de Obramat se corresponde exactamente con el modelo homólogo en Leroy Merlin o Bauhaus, validando potencias, medidas o accesorios incluidos).
* **Análisis de competitividad y síntesis:** Evaluación contextual de márgenes, detección de discrepancias anómalas y redacción automatizada de resúmenes ejecutivos para los informes periódicos.

> **Delimitación técnica respecto a la extracción web:**  
> Se evaluó la viabilidad de delegar en el agente de IA la navegación o consulta directa de URLs en vivo. Se concluyó que un LLM carece de capacidades de evasión perimetral de red: cualquier llamada HTTP subyacente que realice un agente se enfrenta a los mismos bloqueos de WAF (403 / Captchas) y adolece de falta de geolocalización local (no puede simular de forma nativa la sesión del almacén físico de Murcia). Por tanto, la IA opera estrictamente como **motor de análisis y estructuración sobre los datos extraídos**, no como mecanismo de recolección en red.

---

## 🛡️ Retos Técnicos y Evolución de la Extracción de Datos

El objetivo del proyecto es monitorizar y comparar en tiempo real los precios locales de referencias clave en **Obramat (Murcia-Churra)**, **Leroy Merlin (Murcia Sur)** y **Bauhaus**. A diferencia de los catálogos web nacionales, los precios y disponibilidades varían por almacén físico, lo que exige conservar el contexto geográfico y de sesión en cada consulta.

A continuación se documentan las fases de investigación técnica, los mecanismos evaluados y las conclusiones de viabilidad:

### 1. Intentos de Automatización y Limitaciones Detectadas

#### Fase 1: Peticiones HTTP directas (`curl_cffi` / `requests`)
* **Enfoque:** Simulación de peticiones HTTP con emulación de TLS/JA3 mediante `curl_cffi` e inyección de cabeceras de usuario.
* **Resultado:** Fallo sistemático con **HTTP 403 Forbidden** tanto en Obramat como en Leroy Merlin.
* **Causa:** Ambas plataformas (Grupo Adeo) utilizan sistemas perimetrales avanzados de mitigación de bots y WAF (**DataDome / Cloudflare**), que bloquean cualquier llamada carente de contexto de navegación legítimo.

#### Fase 2: Automatización en la nube vía CI/CD (GitHub Actions)
* **Enfoque:** Orquestación de ejecuciones periódicas desatendidas en runners de GitHub Actions.
* **Resultado:** Bloqueo perimetral inmediato (403).
* **Causa:** Los runners de GitHub operan bajo rangos de IP públicas pertenecientes a centros de datos de Microsoft Azure. Estas subredes están catalogadas globalmente por los WAFs comerciales, denegando la conexión independientemente de las firmas del cliente.

#### Fase 3: Inyección manual de cookies de sesión
* **Enfoque:** Extracción de cookies de contexto de tienda (`cctx`, variables de almacén) desde un navegador manual para reutilizarlas en scripts de extracción.
* **Resultado:** Inviable para producción.
* **Causa:** Las cookies de sesión perimetrales están vinculadas a la huella criptográfica de la sesión de origen y caducan en plazos cortos (12–24 horas), lo que exigiría intervención manual constante y anularía la estabilidad del sistema.

#### Fase 4: Navegación automatizada aislada (Playwright Headless / Headful)
* **Enfoque:** Uso de navegadores automatizados con técnicas de evasión (`playwright-stealth`, desactivación de `AutomationControlled`).
* **Resultado:** Bloqueo por desafío anti-bot.
* **Causa:** La telemetría en tiempo de ejecución de DataDome intercepta los puertos de depuración de Chromium y las propiedades del entorno automatizado (`navigator.webdriver`). Incluso al resolver manualmente los retos interactivos (captchas deslizantes), la sesión queda invalidada al detectar variables internas de automatización.

---

### 2. Estado Actual y Vía de Investigación

Tras descartar el scraping directo no asistido contra los cortafuegos perimetrales, el núcleo del proyecto (normalización de catálogo, integración del agente Gemini, cálculo de márgenes y lógica de alertas) permanece completamente operativo.

Actualmente se está validando el siguiente enfoque:

* **Extracción asistida mediante conexión CDP (Chrome DevTools Protocol):**
  * Uso de una instancia legítima de navegador con perfil de usuario persistente en entorno local.
  * Conexión del script de extracción a través del puerto de depuración remoto (`connect_over_cdp`), evitando la inyección de firmas de automatización en el arranque y preservando las sesiones de tienda física seleccionadas.

> *Nota: Esta sección se actualizará con la especificación técnica definitiva una vez concluida la fase de pruebas.*
