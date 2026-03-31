from src.database import database
from src.config import settings as config

# Connect
client = database.get_es_client()

if client:
    # Delete the index
    print(f"🗑️ Wiping index: {config.INDEX_NAME}...")
    try:
        client.indices.delete(index=config.INDEX_NAME, ignore=[400, 404])
        print("✅ Database is now completely EMPTY.")
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("❌ Could not connect to database.")
