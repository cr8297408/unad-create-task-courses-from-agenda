import os
import sys
import argparse
from datetime import datetime
import locale
from typing import List, Dict, Optional
import google.generativeai as genai
from notion_client import Client
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
COURSES_DB_ID = os.getenv("COURSES_DB_ID")
TASKS_DB_ID = os.getenv("TASKS_DB_ID")

MONTH_MAP = {
    "ENE": "01", "FEB": "02", "MAR": "03", "ABR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AGO": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DIC": "12"
}

class GeminiProcessor:
    def __init__(self, api_key: str):
        if not api_key:
            print("Warning: GEMINI_API_KEY not found. AI features will be disabled.")
            self.model = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    def enhance_task(self, title: str, description: str) -> Dict[str, str]:
        if not self.model:
            return {"title": title, "description": description, "emoji": "📅"}

        prompt = f"""
        Analyze this course activity:
        Title: {title}
        Description: {description}

        1. Create a concise, actionable title (remove "Fase X -", just keep the core name if it's too long, or keep it if it's good).
        2. Create a clean summary description. Remove academic codes like "RAC 1", "RAC 2".
        3. Suggest a single emoji relevant to the task (e.g. 💻, 📝, 📹).

        Return strictly JSON format:
        {{
            "title": "New Title",
            "description": "Cleaned description",
            "emoji": "🔥"
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            # Simple cleanup to ensure we get just the JSON part if the model chats
            text = response.text.replace("```json", "").replace("```", "").strip()
            import json
            return json.loads(text)
        except Exception as e:
            print(f"Gemini Error: {e}")
            return {"title": title, "description": description, "emoji": "📅"}

class UnadAgendaParser:
    def parse_date(self, date_str: str) -> Optional[str]:
        # Format: 17/FEB/2026 23:55 or 04/FEB/2026 00:00
        try:
            # Clean string
            date_str = date_str.strip()
            for spanish, num in MONTH_MAP.items():
                date_str = date_str.replace(spanish, num)
            
            # Check format
            dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            return dt.isoformat()
        except ValueError:
            return None

    def parse_file(self, file_path: str) -> List[Dict]:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')

        activities = []
        rows = soup.find_all('tr')
        
        # Skip header rows. Simple heuristic: look for rows with 'Fase' or known structure
        for row in rows:
            cols = row.find_all('td')
            # Typical row has many columns. Let's look for specific length or classes
            # Based on HTML: cols are [Momento, RAC, Nombre, Desc, Tipo, Peso, Inicio, Fin, Alerta, Realim]
            if len(cols) >= 8: # Ensure enough columns
                try:
                    name_node = cols[2]
                    desc_node = cols[3]
                    start_node = cols[6]
                    end_node = cols[7] # Check if it has id like "cie_X"
                    
                    if not end_node.get("id", "").startswith("cie_"):
                        continue

                    title = name_node.get_text(strip=True)
                    description = desc_node.get_text(separator="\n", strip=True)
                    start_date = self.parse_date(start_node.get_text(strip=True))
                    end_date = self.parse_date(end_node.get_text(strip=True))

                    if title and start_date and end_date:
                        activities.append({
                            "original_title": title,
                            "original_description": description,
                            "start": start_date,
                            "end": end_date
                        })
                except IndexError:
                    continue
        
        return activities

class NotionSync:
    def __init__(self, token: str, courses_db: str, tasks_db: str):
        self.client = Client(auth=token)
        self.courses_db = courses_db
        self.tasks_db = tasks_db

    def find_course_page(self, course_name_query: str) -> Optional[str]:
        """Finds a course page by name in the Courses database."""
        # Simple normalization
        query = course_name_query.split(".")[0] # Remove extension
        
        print(f"Searching for course: {query}...")
        results = self.client.databases.query(
            database_id=self.courses_db,
            filter={
                "property": "Name", # Adjust if your property is 'Nombre' or 'Title'
                "title": {
                    "contains": query
                }
            }
        )
        
        if results["results"]:
            return results["results"][0]["id"]
        return None

    def create_task(self, course_id: str, task_data: Dict):
        print(f"Creating task: {task_data['title']}")
        
        properties = {
            "Name": {"title": [{"text": {"content": task_data['title']}}]},
            "Course": {"relation": [{"id": course_id}]}, # Adjust relation property name if needed
            "Date": {"date": {"start": task_data['start'], "end": task_data['end']}},
            "Status": {"status": {"name": "Not started"}} # Adjust default status
        }
        
        # Add description to page content (children)
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": task_data['description']}}]
                }
            }
        ]

        self.client.pages.create(
            parent={"database_id": self.tasks_db},
            icon={"emoji": task_data.get('emoji', "📅")},
            properties=properties,
            children=children
        )

def main():
    parser = argparse.ArgumentParser(description="Sync UNAD Course Schedule to Notion")
    parser.add_argument("file_path", help="Path to the HTML file")
    args = parser.parse_args()

    # Validate Environment
    if not all([NOTION_TOKEN, COURSES_DB_ID, TASKS_DB_ID]):
        print("Error: Missing Environment Variables. Please set NOTION_TOKEN, COURSES_DB_ID, TASKS_DB_ID")
        return

    # 1. Parse File
    print(f"Parsing {args.file_path}...")
    unad_parser = UnadAgendaParser()
    activities = unad_parser.parse_file(args.file_path)
    print(f"Found {len(activities)} activities.")

    # 2. Setup Clients
    notion = NotionSync(NOTION_TOKEN, COURSES_DB_ID, TASKS_DB_ID)
    gemini = GeminiProcessor(GEMINI_API_KEY)

    # 3. Find Context
    file_name = os.path.basename(args.file_path)
    # Heuristic: Remove extension and use as course name
    course_name = os.path.splitext(file_name)[0]
    
    course_id = notion.find_course_page(course_name)
    if not course_id:
        print(f"Critcal: Could not find a course named '{course_name}' in Notion DB {COURSES_DB_ID}")
        print("Please ensure the file name matches a course name in your Notion 'Courses' database.")
        return

    # 4. Sync
    print(f"Syncing to Course ID: {course_id}")
    for activity in activities:
        # Improve with AI
        enhanced = gemini.enhance_task(
            activity["original_title"], 
            activity["original_description"]
        )
        
        # Merge data
        final_task = {**activity, **enhanced}
        
        # Create
        try:
            notion.create_task(course_id, final_task)
        except Exception as e:
            print(f"Failed to create task {final_task['title']}: {e}")

if __name__ == "__main__":
    main()
