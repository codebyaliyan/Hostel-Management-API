import os
from pathlib import Path

# 1. Force create the .env file correctly
env_content = """DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=RootPass123!
DB_NAME=hostel_db_v3
DB_POOL_SIZE=10
SECRET_KEY=my_super_secret_key_12345
TOKEN_HOURS=12
DEFAULT_SUPERADMIN_USERNAME=superadmin
DEFAULT_SUPERADMIN_PASSWORD=admin123
DEFAULT_SUPERADMIN_FULL_NAME=Super Administrator
DEFAULT_BRANCH_ADMIN_USERNAME=hosteladmin
DEFAULT_BRANCH_ADMIN_PASSWORD=password1
"""

env_path = Path(__file__).resolve().with_name(".env")
with open(env_path, "w", encoding="utf-8") as f:
    f.write(env_content)

print(f"Created .env file at: {env_path}")

# 2. Test the connection immediately
import mysql.connector
try:
    print("Testing connection to MySQL...")
    conn = mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="RootPass123!",
        database="hostel_db_v3"
    )
    print("========================================")
    print("SUCCESS! Python successfully connected to MySQL.")
    print("========================================")
    conn.close()
except Exception as e:
    print("========================================")
    print(f"FAILED TO CONNECT: {e}")
    print("========================================")