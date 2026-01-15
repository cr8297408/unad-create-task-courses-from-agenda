# UNAD Agenda Sync -> Notion

Sincroniza automáticamente las agendas de cursos UNAD (archivos HTML) con tu workspace de Notion.

## Requisitos

- Python 3.10+
- Cuenta de Notion con API key
- API key de Google Gemini

## Instalación

```bash
# Crear entorno virtual
python3 -m venv venv

# Activar entorno virtual
source venv/bin/activate      # bash/zsh
source venv/bin/activate.fish # fish
.\venv\Scripts\activate       # Windows

# Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Crear un archivo `.env` en la raíz del proyecto:

```env
NOTION_TOKEN=tu_token_de_notion
GEMINI_API_KEY=tu_api_key_de_gemini
COURSES_DB_ID=id_de_tu_base_de_datos_courses
TASKS_DB_ID=id_de_tu_base_de_datos_tasks

# Opcional: modelo de Gemini (default: gemini-2.5-flash)
GEMINI_MODEL=gemini-2.5-flash
```

### Obtener los IDs

1. **NOTION_TOKEN**: Crear una integración en https://www.notion.so/my-integrations
2. **COURSES_DB_ID**: Abrir la base de datos de cursos en Notion, copiar el ID de la URL
3. **TASKS_DB_ID**: Abrir la base de datos de tareas en Notion, copiar el ID de la URL
4. **GEMINI_API_KEY**: Obtener en https://makersuite.google.com/app/apikey

### Schema de Notion esperado

**Base de datos Courses:**
- `Name` (Title): Nombre del curso

**Base de datos Tasks:**
- `Name` (Title): Nombre de la tarea
- `Due Date` (Date): Fecha de entrega (start/end)
- `Related to Courses` (Relation): Relación a la base de datos de Courses
- `Puntos` (Number): Peso evaluativo de la actividad
- `Etapa` (Select): 'Inicial', 'Intermedia', 'Final'
- `Tema` (Rich Text): Tema principal de la actividad
- `Tipo Actividad` (Select): 'Individual', 'Colaborativa'
- `Tipo Entregable` (Multi-select): 'PDF', 'Zip', 'Foro', etc.
- `Unidad` (Multi-select): Unidad a la que pertenece (e.g., 'Unidad 1')
- `Year` (Select): Periodo académico (e.g., '2026-1')
- `Entrega Retroalimentación` (Date): Rango de fechas para la retroalimentación

## Uso

### Modo simulación (dry-run) - RECOMENDADO PRIMERO

```bash
python poblar_agenda_v2.py --dry-run "Prueba App Integrator.html"
```

Esto muestra qué tareas se crearían sin modificar Notion.

### Ejecutar sincronización

```bash
python poblar_agenda_v2.py "Prueba App Integrator.html"
```

### Opciones disponibles

```bash
# Ver ayuda
python poblar_agenda_v2.py --help

# Usar modelo Gemini diferente
python poblar_agenda_v2.py --model gemini-2.5-pro "archivo.html"

# Especificar nombre del curso manualmente
python poblar_agenda_v2.py --course-name "Estructuras de Datos" archivo.html

# Combinar opciones
python poblar_agenda_v2.py --dry-run --model gemini-2.5-pro "archivo.html"
```

## Cómo funciona

1. **Lee el HTML** de la agenda UNAD
2. **Extrae el nombre del curso** del título del HTML
3. **Envía el HTML a Gemini** para extraer las actividades (Fases)
4. **Busca el curso** en la base de datos de Courses de Notion
5. **Crea las tareas** en la base de datos de Tasks, vinculadas al curso

## Ejemplo de salida

```
============================================================
🎓 UNAD Agenda Sync -> Notion
============================================================

📄 Leyendo: Prueba App Integrator.html
📚 Curso detectado: ESTRUCTURAS DE DATOS

--- Extracción con IA ---
🤖 Enviando HTML a Gemini (gemini-2.5-flash)...
✅ Extraídas 5 tareas

📋 Tareas a crear:
   1. 🎥 Fase 1 - Evaluación del escenario (25 pts)
      📅 2026-02-04 → 2026-02-17
   2. 💻 Fase 2 - Abstracción y Diseño (125 pts)
      📅 2026-02-18 → 2026-03-17
   ...

--- Contexto Notion ---
🔍 Buscando curso: 'ESTRUCTURAS DE DATOS'...
✅ Curso encontrado: 'Estructuras de Datos' (ID: xxx)
📎 Propiedad de relación encontrada: 'Related to Courses'

--- Sincronización ---
✅ Creada: 🎥 Fase 1 - Evaluación del escenario
✅ Creada: 💻 Fase 2 - Abstracción y Diseño
...

============================================================
📊 RESUMEN
============================================================
   ✅ Creadas: 5
   ❌ Fallidas: 0
   📚 Curso: ESTRUCTURAS DE DATOS
```

## Troubleshooting

### "No se encontró el curso"
- Verificar que el curso existe en la base de datos de Courses en Notion
- Usar `--course-name` para especificar el nombre exacto

### "Error de API de Notion"
- Verificar que la integración tiene acceso a las bases de datos
- En Notion: Abrir cada base de datos > ... > Connections > Agregar tu integración

### "JSON inválido de Gemini"
- Puede pasar si el HTML es muy largo o tiene estructura inusual
- Intentar con `--model gemini-2.5-pro` para mejor precisión

## Scripts disponibles

| Script | Descripción |
|--------|-------------|
| `poblar_agenda_v2.py` | Script principal con Gemini (recomendado) |
| `poblar_agenda.py` | Script legacy (si existe) |
