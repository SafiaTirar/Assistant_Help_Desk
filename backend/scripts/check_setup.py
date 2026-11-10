import os
from dotenv import load_dotenv
import psycopg2
from qdrant_client import QdrantClient

load_dotenv()

def check_postgres():
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        conn.close()
        print("✅ PostgreSQL : connexion OK")
    except Exception as e:
        print(f"❌ PostgreSQL : échec — {e}")

def check_qdrant():
    try:
        client = QdrantClient(url=os.getenv("QDRANT_URL"))
        print(f"✅ Qdrant : connexion OK — collections existantes : {client.get_collections()}")
    except Exception as e:
        print(f"❌ Qdrant : échec — {e}")

if __name__ == "__main__":
    check_postgres()
    check_qdrant()
