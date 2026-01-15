#!/usr/bin/env python3
"""
UNAD Agenda Sync -> Notion
--------------------------
Parsea archivos HTML de agenda UNAD y crea tareas en Notion usando Gemini para extracción.

Uso:
    python poblar_agenda_v2.py "Estructuras de datos.html"
    python poblar_agenda_v2.py --dry-run "Estructuras de datos.html"
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Lazy imports para mejor rendimiento
_notion_client = None
_genai = None


def get_notion_client():
    """Lazy load del cliente Notion."""
    global _notion_client
    if _notion_client is None:
        from notion_client import Client
        _notion_client = Client(auth=os.getenv("NOTION_TOKEN"))
    return _notion_client


def get_genai():
    """Lazy load del cliente google-genai."""
    global _genai
    if _genai is None:
        from google import genai
        _genai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _genai


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

@dataclass
class Config:
    """Configuración del script."""
    notion_token: str
    gemini_api_key: str
    courses_db_id: str
    tasks_db_id: str
    gemini_model: str = "gemini-2.5-flash"
    dry_run: bool = False
    
    @classmethod
    def from_env(cls, dry_run: bool = False) -> "Config":
        """Carga configuración desde variables de entorno."""
        load_dotenv()
        
        required_vars = {
            "NOTION_TOKEN": os.getenv("NOTION_TOKEN"),
            "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
            "COURSES_DB_ID": os.getenv("COURSES_DB_ID"),
            "TASKS_DB_ID": os.getenv("TASKS_DB_ID"),
        }
        
        missing = [k for k, v in required_vars.items() if not v]
        if missing:
            raise EnvironmentError(
                f"Variables de entorno faltantes: {', '.join(missing)}\n"
                f"Asegurate de tener un archivo .env con estas variables."
            )
        
        # Ya validamos que no son None arriba
        return cls(
            notion_token=str(required_vars["NOTION_TOKEN"]),
            gemini_api_key=str(required_vars["GEMINI_API_KEY"]),
            courses_db_id=str(required_vars["COURSES_DB_ID"]),
            tasks_db_id=str(required_vars["TASKS_DB_ID"]),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            dry_run=dry_run,
        )


# =============================================================================
# DATACLASSES PARA TAREAS
# =============================================================================

@dataclass
class Task:
    """Representa una tarea extraída de la agenda."""
    title: str
    description: str
    start_date: str  # ISO 8601: YYYY-MM-DD
    end_date: str    # ISO 8601: YYYY-MM-DD
    emoji: str = "📚"
    weight: Optional[int] = None  # Peso evaluativo
    stage: Optional[str] = None   # Inicial, Intermedia, Final
    feedback_start_date: Optional[str] = None
    feedback_end_date: Optional[str] = None
    topic: Optional[str] = None
    activity_type: Optional[str] = None  # Individual, Colaborativa
    deliverable: Optional[str] = None    # PDF, Word, etc.
    unit: Optional[str] = None           # Unidad 1, Unidad 2, etc.
    recommendations: Optional[str] = None


# =============================================================================
# EXTRACCIÓN CON GEMINI
# =============================================================================

EXTRACTION_PROMPT = """Analiza este HTML de una agenda de curso universitario UNAD (Colombia).

Extrae TODAS las actividades que contengan "Fase" en el nombre.

Para cada actividad devuelve un objeto JSON con:
- "title": Nombre de la actividad (ej: "Fase 1 - Evaluación del escenario")
- "description": descripción completa de la actividad
- "start_date": Fecha inicio formato YYYY-MM-DD (FEB=02, MAR=03, ABR=04, MAY=05)
- "end_date": Fecha cierre formato YYYY-MM-DD
- "emoji": 🎥 para video, 💻 para código, 🔬 para práctica, 🚀 para final
- "weight": Peso evaluativo (número)
- "stage": Etapa del curso en la que se realiza (Inicial, Intermedia, Final)
- "feedback_start_date": Fecha inicio retroalimentación formato YYYY-MM-DD
- "feedback_end_date": Fecha cierre retroalimentación formato YYYY-MM-DD
- "topic": Tema de la actividad
- "activity_type": Tipo de actividad (ej: "Colaborativa", "Individual")
- "deliverable": Entregable de la actividad (ej: "Documento escrito", "Presentación", "Video", "Código", "Cuestionario", "Foro", "Zip", "PDF")
- "unit": Unidad de la actividad (ej: "Unidad 1", "Unidad 2", "Unidad 3", "Unidad 4", "Inicio", "Final")
- "recommendations": Recomendaciones de estudio (libros, videos, OVI, OVA, etc.) mencionado en la descripción o entorno inicial.

Retorna SOLO el array JSON, sin explicaciones.

HTML:
"""


def extract_tasks_with_gemini(html_content: str, config: Config) -> list[Task]:
    """
    Extrae tareas del HTML usando Gemini.
    
    Args:
        html_content: Contenido HTML de la agenda
        config: Configuración del script
        
    Returns:
        Lista de objetos Task
        
    Raises:
        ValueError: Si Gemini retorna JSON inválido
        RuntimeError: Si hay error en la API de Gemini
    """
    from google.genai import types
    
    client = get_genai()
    
    prompt = EXTRACTION_PROMPT + html_content
    
    print(f"🤖 Enviando HTML a Gemini ({config.gemini_model})...")
    
    try:
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=8192,
            )
        )
        
        # Guardar respuesta cruda para debugging
        with open("gemini_response.txt", "w", encoding="utf-8") as f:
            f.write(response.text)

    except Exception as e:
        raise RuntimeError(f"Error al llamar a Gemini: {e}")
    
    # Debug: verificar finish_reason
    if hasattr(response, 'candidates') and response.candidates:
        candidate = response.candidates[0]
        finish_reason = getattr(candidate, 'finish_reason', None)
        if finish_reason and str(finish_reason) not in ("STOP", "1", "FinishReason.STOP"):
            print(f"⚠️  Respuesta truncada. finish_reason: {finish_reason}")
    
    response_text = response.text.strip()
    
    # Limpiar respuesta - Gemini a veces envuelve JSON en ```json ... ```
    if response_text.startswith("```"):
        response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
        response_text = re.sub(r"\n?```$", "", response_text)
    
    try:
        tasks_data = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"❌ Error parseando JSON de Gemini:")
        print(f"   Respuesta recibida: {response_text[:500]}...")
        raise ValueError(f"JSON inválido de Gemini: {e}")
    
    if not isinstance(tasks_data, list):
        raise ValueError(f"Se esperaba una lista, se recibió: {type(tasks_data)}")
    
    tasks = []
    for i, task_dict in enumerate(tasks_data):
        try:
            task = Task(
                title=task_dict.get("title", f"Tarea {i+1}"),
                description=task_dict.get("description", ""),
                start_date=task_dict.get("start_date", ""),
                end_date=task_dict.get("end_date", ""),
                emoji=task_dict.get("emoji", "📚"),
                weight=task_dict.get("weight"),
                stage=task_dict.get("stage"),
                feedback_start_date=task_dict.get("feedback_start_date"),
                feedback_end_date=task_dict.get("feedback_end_date"),
                topic=task_dict.get("topic"),
                activity_type=task_dict.get("activity_type"),
                deliverable=task_dict.get("deliverable"),
                unit=task_dict.get("unit"),
                recommendations=task_dict.get("recommendations"),
            )
            tasks.append(task)
        except Exception as e:
            print(f"⚠️  Error procesando tarea {i+1}: {e}")
            continue
    
    print(f"✅ Extraídas {len(tasks)} tareas")
    return tasks


# =============================================================================
# INTEGRACIÓN CON NOTION
# =============================================================================

def normalize_db_id(db_id: str) -> str:
    """Normaliza el ID de base de datos (remueve guiones si los tiene)."""
    return db_id.replace("-", "")


def find_course_page(course_name: str, config: Config) -> Optional[dict]:
    """
    Busca la página del curso en la base de datos de Courses.
    
    Args:
        course_name: Nombre del curso a buscar
        config: Configuración
        
    Returns:
        Diccionario con info de la página o None si no se encuentra
    """
    client = get_notion_client()
    
    print(f"🔍 Buscando curso: '{course_name}'...")
    print(f"   DB de cursos esperada: {config.courses_db_id}")
    
    try:
        # Usar search API para buscar el curso
        response = client.search(
            query=course_name,
            filter={"property": "object", "value": "page"},
            page_size=20
        )
        
        results = response.get("results", [])
        print(f"   📊 Search devolvió {len(results)} resultados")
        print(results)
        
        # Debug: mostrar todos los resultados
        for i, page in enumerate(results):
            parent = page.get("parent", {})
            parent_type = parent.get("type", "unknown")
            parent_id = parent.get("database_id", parent.get("page_id", "N/A"))
            
            # Intentar obtener título
            props = page.get("properties", {})
            title = "Sin título"
            for prop_name, prop_val in props.items():
                if prop_val.get("type") == "title":
                    title_arr = prop_val.get("title", [])
                    if title_arr:
                        title = title_arr[0].get("plain_text", "Sin título")
                    break
            
            print(f"   [{i+1}] '{title}' | parent: {parent_type} | parent_id: {normalize_db_id(parent_id)}")
        
        # Usar el primer resultado encontrado (Usuario solicitó ignorar parent check)
        if results:
            page = results[0]
            page_id = page["id"]
            
            # Extraer el nombre del título
            title_prop = page.get("properties", {}).get("Name", {})
            title_content = title_prop.get("title", [])
            title_text = title_content[0]["plain_text"] if title_content else "Sin nombre"
            
            print(f"✅ Curso encontrado: '{title_text}' (ID: {page_id})")
            
            return {
                "id": page_id,
                "name": title_text
            }
        
        print(f"⚠️  No se encontró el curso '{course_name}'")
        return None
        
    except Exception as e:
        print(f"❌ Error buscando curso: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_tasks_db_schema(config: Config) -> dict:
    """
    Obtiene el schema de la base de datos de tareas.
    Útil para debugging y validación.
    """
    client = get_notion_client()
    
    try:
        # Buscar la base de datos por ID
        response = client.search(
            filter={"property": "object", "value": "data_source"},
            page_size=100
        )

        print(f"   📊 Search devolvió {len(response.get('results', []))} resultados")
        
        for db in response.get("results", []):
            # Obtener nombre de la DB/Data Source
            title = "Sin título"
            if db.get("title"):
                title = db["title"][0].get("plain_text", "")
            
            # Verificación por ID o por NOMBRE (Petición explícita usuario)
            is_id_match = normalize_db_id(db.get("id", "")) == normalize_db_id(config.tasks_db_id)
            is_name_match = title in ["To-do’s", "To-do's", "Tasks", "Tareas"]
            
            if is_id_match or is_name_match:
                found_id = db.get("id")
                object_type = db.get("object")
                
                print(f"      ✅ Encontrada DB candidata: '{title}' (ID: {found_id}, Type: {object_type})")
                
                # FIX: Si es un data_source, el ID real de la base de datos suele estar en el parent
                if object_type == "data_source":
                    parent = db.get("parent", {})
                    if parent.get("type") == "database_id" and parent.get("database_id"):
                        real_db_id = parent.get("database_id")
                        print(f"      🔄 Resolviendo 'data_source' al ID de base de datos padre: {real_db_id}")
                        found_id = real_db_id
                
                # Actualizar config si encontramos por nombre proactivamente O si resolvimos un ID diferente
                if is_name_match or found_id != config.tasks_db_id:
                    print(f"      🔄 Actualizando ID de Tareas a: {found_id}")
                    config.tasks_db_id = found_id
                    
                return db.get("properties", {})
        
        print(f"⚠️  No se encontró la DB de tareas en search con ID {config.tasks_db_id} ni por nombre 'To-do’s'")
        
    except Exception as e:
        print(f"⚠️  No se pudo obtener schema: {e}")
        return {}


def find_relation_property(config: Config) -> Optional[str]:
    """
    Encuentra el nombre de la propiedad de relación con Courses.
    
    Returns:
        Nombre de la propiedad o None
    """
    schema = get_tasks_db_schema(config)
    
    for prop_name, prop_config in schema.items():
        if prop_config.get("type") == "relation":
            # Verificar si la relación apunta a la DB de cursos
            relation_config = prop_config.get("relation", {})
            related_db = relation_config.get("database_id", "")
            
            if normalize_db_id(related_db) == normalize_db_id(config.courses_db_id):
                print(f"📎 Propiedad de relación encontrada: '{prop_name}'")
                return prop_name
    
    return None


def create_task_in_notion(
    task: Task,
    course_page_id: str,
    relation_property: str,
    config: Config
) -> Optional[str]:
    """
    Crea una tarea en la base de datos de Notion.
    
    Args:
        task: Tarea a crear
        course_page_id: ID de la página del curso relacionado
        relation_property: Nombre de la propiedad de relación
        config: Configuración
        
    Returns:
        ID de la página creada o None si falla
    """
    if config.dry_run:
        print(f"   [DRY-RUN] Crearía: {task.emoji} {task.title}")
        return "dry-run-id"
    
    client = get_notion_client()
    
    # Construir propiedades de la página
    properties = {
        "Name": {
            "title": [
                {
                    "text": {
                        "content": task.title
                    }
                }
            ]
        },
        # Relación con el curso
        relation_property: {
            "relation": [
                {"id": course_page_id}
            ]
        },
    }
    
    # Agregar fecha si están disponibles
    if task.start_date and task.end_date:
        properties["Tiempo de actividad"] = {
            "date": {
                "start": task.start_date,
                "end": task.end_date,
            }
        }
    elif task.end_date:
        properties["Tiempo de actividad"] = {
            "date": {
                "start": task.end_date,
            }
        }
        
    # Map additional properties
    if task.weight is not None:
        properties["Puntos"] = {"number": task.weight}
        
    if task.stage:
        properties["Etapa"] = {"select": {"name": task.stage}}
        
    if task.topic:
        properties["Tema"] = {
            "rich_text": [{"text": {"content": task.topic}}]
        }
        
    if task.activity_type:
        properties["Tipo Actividad"] = {"select": {"name": task.activity_type}}
        
    if task.deliverable:
        # Multi-select requires a list of dicts
        properties["Tipo Entregable"] = {"multi_select": [{"name": task.deliverable}]}
        
    if task.unit:
        properties["Unidad"] = {"multi_select": [{"name": task.unit}]}

    if task.feedback_start_date:
        feedback_date = {"start": task.feedback_start_date}
        if task.feedback_end_date:
            feedback_date["end"] = task.feedback_end_date
        properties["Entrega Retroalimentación"] = {"date": feedback_date}

    # Intentar agregar Status (puede fallar si la propiedad no existe o tiene otro nombre)
    # Lo manejamos de forma opcional
    
    # Construct block children content
    children = []
    
    if task.description:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": task.description}}]
            }
        })
        
    if task.recommendations:
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": "Recomendaciones"}}]
            }
        })
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": task.recommendations}}]
            }
        })

    try:
        response = client.pages.create(
            parent={"database_id": config.tasks_db_id},
            icon={"type": "emoji", "emoji": task.emoji},
            properties=properties,
            children=children
        )
        
        return response.get("id")
        
    except Exception as e:
        print(f"❌ Error creando tarea '{task.title}': {e}")
        
        # Si falla, intentar sin la relación (por si el nombre de propiedad es incorrecto)
        try:
            del properties[relation_property]
            response = client.pages.create(
                parent={"database_id": config.tasks_db_id},
                icon={"type": "emoji", "emoji": task.emoji},
                properties=properties,
            )
            print(f"   ⚠️  Creada SIN relación al curso")
            return response.get("id")
        except Exception as e2:
            print(f"   ❌ También falló sin relación: {e2}")
            return None


# =============================================================================
# FLUJO PRINCIPAL
# =============================================================================

def extract_course_name_from_html(html_path: Path) -> str:
    """
    Extrae el nombre del curso del archivo HTML.
    
    Intenta extraer del título HTML primero, luego del nombre del archivo.
    """
    try:
        content = html_path.read_text(encoding="utf-8")
        
        # Buscar en el tag <title>
        # Formato típico: "Agenda - 301305 - ESTRUCTURAS DE DATOS - 2026 I PERIODO 16-01 (2201)"
        title_match = re.search(r"<title>.*?-\s*\d+\s*-\s*(.+?)\s*-\s*\d{4}", content)
        if title_match:
            return title_match.group(1).strip()
        
        # Buscar en el contenido del curso
        # <p>ESTRUCTURAS DE DATOS - Curso Metodológico (TP) - 301305 de 3 créditos</p>
        content_match = re.search(r"<p>([A-ZÁÉÍÓÚÑ\s]+)\s*-\s*Curso", content)
        if content_match:
            return content_match.group(1).strip()
            
    except Exception:
        pass
    
    # Fallback: usar nombre del archivo sin extensión
    return html_path.stem


def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Sincroniza agenda UNAD con Notion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
    python poblar_agenda_v2.py "Estructuras de datos.html"
    python poblar_agenda_v2.py --dry-run "Mi Curso.html"
    python poblar_agenda_v2.py --model gemini-1.5-pro "Agenda.html"
        """
    )
    parser.add_argument(
        "html_file",
        type=str,
        help="Ruta al archivo HTML de la agenda"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sin crear tareas en Notion"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Modelo de Gemini a usar (default: gemini-2.5-flash)"
    )
    parser.add_argument(
        "--course-name",
        type=str,
        default=None,
        help="Nombre del curso (override, por defecto se extrae del HTML)"
    )
    
    args = parser.parse_args()
    
    # Validar archivo
    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"❌ Archivo no encontrado: {html_path}")
        sys.exit(1)
    
    if not html_path.suffix.lower() == ".html":
        print(f"⚠️  Advertencia: El archivo no tiene extensión .html")
    
    # Cargar configuración
    try:
        config = Config.from_env(dry_run=args.dry_run)
        if args.model:
            config.gemini_model = args.model
    except EnvironmentError as e:
        print(f"❌ Error de configuración: {e}")
        sys.exit(1)
    
    print("=" * 60)
    print("🎓 UNAD Agenda Sync -> Notion")
    print("=" * 60)
    
    if config.dry_run:
        print("⚠️  MODO DRY-RUN: No se crearán tareas reales")
    
    # 1. Leer HTML
    print(f"\n📄 Leyendo: {html_path.name}")
    html_content = html_path.read_text(encoding="utf-8")
    
    # 2. Extraer nombre del curso
    course_name = args.course_name or extract_course_name_from_html(html_path)
    print(f"📚 Curso detectado: {course_name}")
    
    # 3. Extraer tareas con Gemini
    print("\n--- Extracción con IA ---")
    try:
        tasks = extract_tasks_with_gemini(html_content, config)
    except Exception as e:
        print(f"❌ Error en extracción: {e}")
        sys.exit(1)
    
    if not tasks:
        print("⚠️  No se encontraron tareas en el HTML")
        sys.exit(0)
    
    # Mostrar resumen de tareas
    print("\n📋 Tareas a crear:")
    for i, task in enumerate(tasks, 1):
        weight_str = f" ({task.weight} pts)" if task.weight else ""
        print(f"   {i}. {task.emoji} {task.title}{weight_str}")
        print(f"      📅 {task.start_date} → {task.end_date}")
        if task.stage: print(f"      🏁 Etapa: {task.stage}")
        if task.unit: print(f"      📦 Unidad: {task.unit}")
        if task.activity_type: print(f"      👥 Tipo: {task.activity_type}")
        if task.deliverable: print(f"      📄 Entregable: {task.deliverable}")
        if task.feedback_start_date: print(f"      💬 Retroalimentación: {task.feedback_start_date} → {task.feedback_end_date}")
    
    # 4. Buscar curso en Notion
    print("\n--- Contexto Notion ---")
    course_page = find_course_page(course_name, config)
    
    if not course_page and not config.dry_run:
        print("❌ No se puede continuar sin encontrar el curso")
        print("   Opciones:")
        print(f"   1. Crear el curso '{course_name}' en Notion primero")
        print("   2. Usar --course-name para especificar otro nombre")
        sys.exit(1)
    
    # 5. Encontrar propiedad de relación
    relation_prop = find_relation_property(config)
    if not relation_prop:
        # Fallback a nombres comunes
        relation_prop = "Course"
        print(f"⚠️  Usando nombre de relación por defecto: '{relation_prop}'")
    
    # 6. Crear tareas
    print("\n--- Sincronización ---")
    created = 0
    failed = 0
    
    for task in tasks:
        course_id = course_page["id"] if course_page else "mock-id"
        
        result = create_task_in_notion(
            task=task,
            course_page_id=course_id,
            relation_property=relation_prop,
            config=config
        )
        
        if result:
            print(f"✅ Creada: {task.emoji} {task.title}")
            created += 1
        else:
            failed += 1
    
    # Resumen final
    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print("=" * 60)
    print(f"   ✅ Creadas: {created}")
    print(f"   ❌ Fallidas: {failed}")
    print(f"   📚 Curso: {course_name}")
    
    if config.dry_run:
        print("\n⚠️  Ejecuta sin --dry-run para crear las tareas realmente")


if __name__ == "__main__":
    main()
