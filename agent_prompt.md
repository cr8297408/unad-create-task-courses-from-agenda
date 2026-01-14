# Prompt para Agente de Desarrollo: Script de Sincronización UNAD -> Notion

Actúa como un desarrollador Python experto. Tu tarea es crear un script robusto (`poblar_agenda_v2.py`) que parsee un archivo HTML de agenda de la UNAD y crea las tareas correspondientes en una base de datos de Notion.

## Contexto
El usuario tiene:
1.  **Archivos HTML** con la agenda del curso (e.g., "Estructuras de datos.html").
2.  **Notion Workspace** con dos bases de datos relacionadas: "Courses" y "Draft AND Tasks".
3.  **API Keys**: `NOTION_TOKEN` y `GEMINI_API_KEY` (para mejorar textos con IA).

## Requerimientos Técnicos

### 1. Entorno y Librerías
- Python 3.10+
- `notion-client` (Usar `client.request` directamente si `databases.query` falla en versiones recientes).
- `beautifulsoup4` (Parsing HTML).
- `google-generativeai` (Mejora de texto).
- `python-dotenv` (Variables de entorno).

### 2. Bases de Datos Notion (Información de Schema real)

**Base de Datos 1: Courses**
- **ID**: `b4b5cac8-73f7-43c6-9418-3fab85b7c9e9`
- **Identificación**: Buscar la página del curso usando la propiedad `Name` (Title) que coincida con el nombre del archivo HTML (e.g., "Estructuras de datos").

**Base de Datos 2: Draft AND Tasks** (La DB de tareas real)
- **ID**: `7aa35ffd-a514-4d27-8931-2bb9cbbb2422`
- **Mapeo de Propiedades para crear la tarea**:
    - `Name` (Title): Título de la actividad extraído del HTML.
    - `Related to Courses (Tasks)` (Relation): Relación con la página del curso encontrada. **Nota**: El ID de la propiedad es `sJ%60M` (o búscalo dinámicamente si es posible, pero asumiendo este nombre).
    - `Due Date` (Date): Fecha de inicio y fin extraída de la agenda.
    - `Status` (Status): Establecer por defecto a "To-do" o "Not started".
    - `Priority` (Select): Opcional, por defecto "Medium".

### 3. Parsing y Extracción con IA (Gemini)
En lugar de parsear el HTML manualmente con código, delegaremos la comprensión de la estructura a Gemini.

**Flujo de Extracción:**
1.  Leer el contenido completo del archivo HTML.
2.  Enviar el HTML crudo a Gemini (`google-generativeai`) con un prompt estructurado.
3.  **Prompt para Gemini**:
    > "Analiza este HTML de una agenda de curso (UNAD). Extrae todas las actividades 'FaseX'. Para cada una devuelve un objeto JSON con:
    > - `title`: Nombre limpio de la actividad (e.g., 'Evaluación del escenario' en lugar de 'Fase 1 - Evaluación...').
    > - `description`: Resumen breve de la descripción.
    > - `start_date`: Fecha de inicio en formato ISO 8601 (YYYY-MM-DD). Nota: Convierte meses como 'FEB' a '02'.
    > - `end_date`: Fecha de cierre en formato ISO 8601 (YYYY-MM-DD).
    > - `emoji`: Un emoji relevante.
    > Retorna SOLO una lista de objetos JSON."

### 4. Flujo del Script (`poblar_agenda_v2.py`)
1.  **Configuración**: Cargar `.env`.
2.  **Lectura**: Leer el archivo HTML pasado como argumento.
3.  **Extracción IA**: Enviar HTML a Gemini y recibir la lista JSON de tareas. Validar errores de JSON.
4.  **Contexto Notion**: Buscar el ID de la página del curso en la DB "Courses" (ID: `b4b5cac8...`) usando el nombre del archivo.
5.  **Sincronización**:
    - Iterar sobre la lista de tareas devuelta por la IA.
    - Crear cada tarea en la DB "Draft AND Tasks" (ID: `7aa35ffd...`) vinculándola al curso.
    - Imprimir progreso en consola (e.g., "✅ Creada: Validación integral").

### 5. Configuración del Modelo
- Usar `gemini-1.5-flash` o `gemini-1.5-pro` (permitir configurar en script).
- Asegurar manejo de límites de tokens si el HTML es muy grande (aunque estos archivos suelen ser pequeños).

## Entrega
Genera el código completo de `poblar_agenda_v2.py` y `requirements.txt`.
