import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

print("🔍 Testing Supabase Connection...")
print(f"Host: {os.getenv('DB_HOST')}")
print(f"Port: {os.getenv('DB_PORT')}")
print(f"User: {os.getenv('DB_USER')}")
print(f"Database: {os.getenv('DB_NAME')}")
print("-" * 50)

try:
    conn = psycopg2.connect(
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        sslmode='require',
        connect_timeout=10
    )
    print("✅ SUCCESS! Connected to Supabase!")
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\n💡 Troubleshooting:")
    print("1. Check that your host is exactly: db.kgfadynbzzrnbvzfzpgep.supabase.co")
    print("2. Verify your password is correct")
    print("3. In Supabase Dashboard → Project Settings → Database → Network Restrictions")
    print("4. Temporarily enable 'Allow all IPs'")