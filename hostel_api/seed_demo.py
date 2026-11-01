from auth import hash_password
from bootstrap import ensure_default_superadmin, ensure_roles
from db import execute, query_one
from helpers import role_id

def get_or_create_city(name, province, country):
    row = query_one("SELECT id FROM cities WHERE name=%s AND province=%s AND country=%s AND deleted_at IS NULL", (name, province, country))
    if row: return row["id"]
    return execute("INSERT INTO cities (name, province, country) VALUES (%s,%s,%s)", (name, province, country))

def get_or_create_branch(city_id, name, code):
    row = query_one("SELECT id FROM branches WHERE code=%s AND deleted_at IS NULL", (code,))
    if row: return row["id"]
    return execute("INSERT INTO branches (city_id, name, code, address, contact) VALUES (%s,%s,%s,%s,%s)", (city_id, name, code, "Demo", "0000"))

def get_or_create_user(username, password, role, first, last, city_id=None, branch_id=None):
    row = query_one("SELECT id FROM users WHERE username=%s AND deleted_at IS NULL", (username,))
    if row: return row["id"]
    return execute("""INSERT INTO users (role_id, city_id, branch_id, username, password_hash, first_name, last_name) 
                      VALUES (%s,%s,%s,%s,%s,%s,%s)""", (role_id(role), city_id, branch_id, username, hash_password(password), first, last))

def main():
    ensure_roles()
    ensure_default_superadmin()

    isb = get_or_create_city("Islamabad", "ICT", "Pakistan")
    lhr = get_or_create_city("Lahore", "Punjab", "Pakistan")

    b_isb = get_or_create_branch(isb, "F-10 Hostel", "ISB-F10")
    b_lhr = get_or_create_branch(lhr, "Gulberg Hostel", "LHR-GUL")

    get_or_create_user("cityadmin", "City1234", "city_admin", "Sara", "Malik", city_id=isb)
    get_or_create_user("branchadmin", "Branch1234", "branch_admin", "Usman", "Tariq", branch_id=b_isb)
    get_or_create_user("branchadmin2", "Branch1234", "branch_admin", "Hina", "Shah", branch_id=b_lhr)

    print("\n--- DEMO ACCOUNTS READY ---")
    print("Super Admin : superadmin / admin123")
    print("City Admin  : cityadmin / City1234 (Islamabad)")
    print("Branch Admin: branchadmin / Branch1234 (F-10)")
    print("Branch Admin: branchadmin2 / Branch1234 (Gulberg)")
    print("---------------------------\n")

if __name__ == "__main__":
    main()