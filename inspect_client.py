import os
from notion_client import Client
from dotenv import load_dotenv
import pkg_resources

load_dotenv()

try:
    version = pkg_resources.get_distribution("notion-client").version
    print(f"📦 Version instalada de notion-client: {version}")
except Exception as e:
    print(f"Error obteniendo version: {e}")

try:
    client = Client(auth=os.getenv("NOTION_TOKEN"))
    print("\n🔍 Métodos en client.databases:")
    print(dir(client.databases))
except Exception as e:
    print(f"\n❌ Error inspeccionando client: {e}")
