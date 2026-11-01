"""
branches.py - the organisation part of the API: who owns what.

    ROLES               GET        /roles
    CITIES              POST/GET   /cities              PUT/DELETE /cities/<id>
                        POST       /cities/<id>/restore
    CITY ADMINS         POST/GET   /cities/<id>/admins
                        PUT/DELETE /cities/<id>/admins/<user_id>      (super admin only)
    BRANCHES            POST/GET   /branches            GET/PUT/DELETE /branches/<id>
                        POST       /branches/<id>/restore
    BRANCH ADMINS       POST/GET   /branches/<id>/admins
                        PUT/DELETE /branches/<id>/admins/<user_id>    (super admin or that city's admin)
    HIERARCHY           GET        /branches/<id>/hierarchy           (who is above this branch)
    SERVICE CATALOG     GET/POST   /services           PUT/DELETE /services/<id>
    NETWORK SUMMARY     GET        /network/overview    GET /network/cities

The daily work inside a branch (students, rooms, beds ...) is in hostel.py.

Who may do what
---------------
    super_admin   everything
    city_admin    their own city: add / edit / delete branches, branch admins; open every branch of it
    branch_admin  only their own branch (hostel.py)

What other branches are allowed to see
--------------------------------------
/network/... returns ONLY counts: rooms, free rooms, beds, free beds, students.
No names, no phone numbers, no records. Detailed data is only reachable through
/branches/<id>/..., which auth.require_branch_access() locks to your own branch / city.

Nothing is ever removed from the database: DELETE sets deleted_at / deleted_by.
"""

from flask import Blueprint, g, request

from auth import (hash_password, login_required, require_authority_over,
                  require_branch_access, require_city_access, staff_required,
                  super_admin_required)
from bootstrap import create_default_branch_admin
from db import db_cursor, execute, query_all, query_one
from helpers import (ApiError, ensure_exists, get_json, ok, person_name, require,
                     role_id, soft_delete, text_or_none, to_int)

bp = Blueprint("branches", __name__)


# ROLES

@bp.get("/roles")
@login_required
def list_roles():
    """The role hierarchy: super_admin > city_admin > branch_admin > student > visitor."""
    return ok(query_all(
        """SELECT r.id, r.code, r.name, r.level, r.scope, r.can_login,
                  p.code AS parent_role
           FROM roles r LEFT JOIN roles p ON p.id = r.parent_role_id
           WHERE r.deleted_at IS NULL ORDER BY r.level"""))


# ADMIN ACCOUNTS (shared by city admins and branch admins)

ADMIN_FIELDS = """u.id, u.username,
                  CONCAT_WS(' ', u.first_name, u.last_name) AS full_name,
                  u.first_name, u.last_name, u.contact, u.email,
                  u.is_active, u.created_at"""


def create_admin(role_code, data, city_id=None, branch_id=None):
    """Insert a city admin (city_id) or a branch admin (branch_id). Returns the new id."""
    require(data, ["username", "password"])

    username = str(data["username"]).strip()
    if not 3 <= len(username) <= 50:
        raise ApiError("username must be 3 to 50 characters")
    if query_one("SELECT id FROM users WHERE username = %s AND deleted_at IS NULL", (username,)):
        raise ApiError("Username already taken", 409)

    first, last = person_name(data, required=False)

    return execute(
        """INSERT INTO users (role_id, city_id, branch_id, username, password_hash,
                              first_name, last_name, contact, email)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (role_id(role_code), city_id, branch_id, username, hash_password(data["password"]),
         first or username, last, text_or_none(data.get("contact")),
         text_or_none(data.get("email"))),
    )


def list_admins(role_code, scope_column, scope_id):
    # scope_column is "city_id" or "branch_id" - written by us, never by the user
    return query_all(
        "SELECT " + ADMIN_FIELDS + """ FROM users u JOIN roles r ON r.id = u.role_id
           WHERE u.""" + scope_column + """ = %s AND r.code = %s AND u.deleted_at IS NULL
           ORDER BY u.id""",
        (scope_id, role_code))


def find_admin(role_code, scope_column, scope_id, user_id, label):
    row = query_one(
        """SELECT u.id, u.username FROM users u JOIN roles r ON r.id = u.role_id
           WHERE u.id = %s AND u.""" + scope_column + """ = %s
             AND r.code = %s AND u.deleted_at IS NULL""",
        (user_id, scope_id, role_code))
    if row is None:
        raise ApiError(label + " not found", 404)
    return row


def update_admin(admin, data):
    """
    Change an admin's login. Send only what you want to change:
        {"username": "...", "password": "...", "full_name": "...", "first_name": "...",
         "last_name": "...", "contact": "...", "email": "...", "is_active": true}
    """
    require_authority_over(admin["id"])     # caller must be above this admin
    changes, params = [], []

    if data.get("username") not in (None, ""):
        username = str(data["username"]).strip()
        if not 3 <= len(username) <= 50:
            raise ApiError("username must be 3 to 50 characters")
        if query_one("SELECT id FROM users WHERE username = %s AND id <> %s "
                     "AND deleted_at IS NULL", (username, admin["id"])):
            raise ApiError("Username already taken", 409)
        changes.append("username = %s")
        params.append(username)

    if data.get("password") not in (None, ""):
        changes.append("password_hash = %s")
        params.append(hash_password(data["password"]))      # enforces 8+ characters

    if data.get("first_name") not in (None, "") or data.get("full_name") not in (None, ""):
        first, last = person_name(data)
        changes += ["first_name = %s", "last_name = %s"]
        params += [first, last]
    elif "last_name" in data:
        changes.append("last_name = %s")
        params.append(text_or_none(data["last_name"]))

    for field in ("contact", "email"):
        if field in data:
            changes.append(field + " = %s")
            params.append(text_or_none(data[field]))

    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            raise ApiError("is_active must be true or false")
        changes.append("is_active = %s")
        params.append(1 if data["is_active"] else 0)

    if not changes:
        raise ApiError("Nothing to update. Send username, password, full_name, "
                       "contact, email or is_active.")

    execute("UPDATE users SET " + ", ".join(changes) + " WHERE id = %s",
            tuple(params) + (admin["id"],))


def delete_admin(admin):
    if admin["id"] == g.user["id"]:
        raise ApiError("You cannot delete your own account.", 400)
    require_authority_over(admin["id"])
    soft_delete("users", admin["id"], g.user["id"])


# CITIES

def city_values(data):
    require(data, ["name"])
    return (str(data["name"]).strip(), str(data.get("province") or "").strip(),
            str(data.get("country") or "").strip())


@bp.post("/cities")
@super_admin_required
def add_city():
    city_id = execute(
        "INSERT INTO cities (name, province, country) VALUES (%s, %s, %s)",
        city_values(get_json()),
    )
    return ok({"id": city_id}, "City added", 201)


@bp.get("/cities")
@login_required
def list_cities():
    rows = query_all(
        """SELECT c.id, c.name, c.province, c.country, COUNT(b.id) AS branches
           FROM cities c
           LEFT JOIN branches b ON b.city_id = c.id AND b.deleted_at IS NULL
           WHERE c.deleted_at IS NULL
           GROUP BY c.id
           ORDER BY c.name"""
    )
    for row in rows:
        row["is_your_city"] = row["id"] == g.user["city_id"]
    return ok(rows)


@bp.put("/cities/<int:city_id>")
@super_admin_required
def update_city(city_id):
    values = city_values(get_json())
    ensure_exists("cities", city_id, "City")
    execute("UPDATE cities SET name = %s, province = %s, country = %s WHERE id = %s",
            values + (city_id,))
    return ok({"id": city_id}, "City updated")


@bp.delete("/cities/<int:city_id>")
@super_admin_required
def delete_city(city_id):
    """Soft delete. Refused while the city still has live branches."""
    ensure_exists("cities", city_id, "City")

    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM branches "
                    "WHERE city_id = %s AND deleted_at IS NULL", (city_id,))
        live = cur.fetchone()["n"]
        if live:
            raise ApiError("City still has " + str(live) + " branch(es). "
                           "Delete or move them first.", 409)

        # the city's own city admins go with it
        cur.execute("UPDATE users SET deleted_at = NOW(), deleted_by = %s "
                    "WHERE city_id = %s AND deleted_at IS NULL", (g.user["id"], city_id))
        soft_delete("cities", city_id, g.user["id"], cur)

    return ok(None, "City deleted")


@bp.post("/cities/<int:city_id>/restore")
@super_admin_required
def restore_city(city_id):
    if query_one("SELECT id FROM cities WHERE id = %s AND deleted_at IS NOT NULL",
                 (city_id,)) is None:
        raise ApiError("Deleted city not found", 404)
    execute("UPDATE cities SET deleted_at = NULL, deleted_by = NULL WHERE id = %s", (city_id,))
    return ok({"id": city_id}, "City restored (city admins are not restored; create them again)")


# CITY ADMINS  (super admin only)

@bp.post("/cities/<int:city_id>/admins")
@super_admin_required
def add_city_admin(city_id):
    data = get_json()
    require_city_access(city_id)
    user_id = create_admin("city_admin", data, city_id=city_id)
    return ok({"id": user_id}, "City admin created", 201)


@bp.get("/cities/<int:city_id>/admins")
@super_admin_required
def list_city_admins(city_id):
    require_city_access(city_id)
    return ok(list_admins("city_admin", "city_id", city_id))


@bp.put("/cities/<int:city_id>/admins/<int:user_id>")
@super_admin_required
def update_city_admin(city_id, user_id):
    data = get_json()
    require_city_access(city_id)
    admin = find_admin("city_admin", "city_id", city_id, user_id, "City admin")
    update_admin(admin, data)
    return ok({"id": user_id}, "City admin updated")


@bp.delete("/cities/<int:city_id>/admins/<int:user_id>")
@super_admin_required
def delete_city_admin(city_id, user_id):
    require_city_access(city_id)
    admin = find_admin("city_admin", "city_id", city_id, user_id, "City admin")
    delete_admin(admin)
    return ok(None, "City admin deleted")


# BRANCHES

def branch_values(data):
    """Validate the body and return values in the same order as the SQL below."""
    require(data, ["city_id", "name", "code"])
    city_id = to_int(data["city_id"], "city_id")
    require_city_access(city_id)    # 404 if missing, 403 if a city admin picks another city

    return (
        city_id,
        str(data["name"]).strip(),
        str(data["code"]).strip().upper(),   # codes are always stored in capitals, e.g. ISB-F7
        data.get("address"),
        data.get("contact"),
    )


@bp.post("/branches")
@staff_required
def add_branch():
    values = branch_values(get_json())

    branch_id = execute(
        "INSERT INTO branches (city_id, name, code, address, contact) "
        "VALUES (%s, %s, %s, %s, %s)",
        values,
    )

    # Every new hostel gets its default warden login (hosteladmin / password1).
    # Only the super admin or the city admin can change it afterwards.
    default_admin = create_default_branch_admin(branch_id, values[2], values[1])

    return ok({"id": branch_id, "default_admin": default_admin},
              "Branch added", 201)


BRANCH_SELECT = """SELECT b.id, b.name, b.code, b.address, b.contact, b.is_active,
                          c.id AS city_id, c.name AS city, c.province, c.country
                   FROM branches b
                   JOIN cities c ON c.id = b.city_id AND c.deleted_at IS NULL"""


def sees_closed_branch(city_id):
    """Closed (inactive) branches are visible to head office and to that city's admin."""
    user = g.user
    return user["role"] == "super_admin" or (
        user["role"] == "city_admin" and user["city_id"] == city_id)


@bp.get("/branches")
@login_required
def list_branches():
    """Basic public info (name, city, address, phone) of every branch."""
    sql = BRANCH_SELECT + " WHERE b.deleted_at IS NULL"
    params = []

    if g.user["role"] == "branch_admin":
        sql += " AND b.is_active = 1"           # others never see closed branches
    elif g.user["role"] == "city_admin":
        sql += " AND (b.is_active = 1 OR b.city_id = %s)"
        params.append(g.user["city_id"])

    city_id = request.args.get("city_id")       # optional: /branches?city_id=2
    if city_id:
        sql += " AND b.city_id = %s"
        params.append(to_int(city_id, "city_id"))

    rows = query_all(sql + " ORDER BY c.name, b.name", tuple(params))

    for row in rows:
        row["is_your_branch"] = row["id"] == g.user["branch_id"]
    return ok(rows)


@bp.get("/branches/<int:branch_id>")
@login_required
def view_branch(branch_id):
    row = query_one(BRANCH_SELECT + " WHERE b.id = %s AND b.deleted_at IS NULL", (branch_id,))

    if row is None or (not row["is_active"] and not sees_closed_branch(row["city_id"])):
        raise ApiError("Branch not found", 404)

    row["is_your_branch"] = row["id"] == g.user["branch_id"]
    return ok(row)


@bp.put("/branches/<int:branch_id>")
@staff_required
def update_branch(branch_id):
    data = get_json()
    require_branch_access(branch_id)        # city admin: must be a branch of their city
    values = branch_values(data)            # ... and may not be moved to another city

    is_active = data.get("is_active", True)
    if not isinstance(is_active, bool):
        raise ApiError("is_active must be true or false")

    execute(
        """UPDATE branches SET city_id = %s, name = %s, code = %s,
                               address = %s, contact = %s, is_active = %s
           WHERE id = %s""",
        values + (1 if is_active else 0, branch_id),
    )
    return ok({"id": branch_id}, "Branch updated")


@bp.delete("/branches/<int:branch_id>")
@staff_required
def delete_branch(branch_id):
    """
    Soft delete. Refused while the branch still has live rooms, students or visitors.
    Its branch admins and service links are soft-deleted in the same transaction.
    """
    require_branch_access(branch_id)
    me = g.user["id"]

    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM rooms "
                    "WHERE branch_id = %s AND deleted_at IS NULL", (branch_id,))
        rooms = cur.fetchone()["n"]

        cur.execute(
            """SELECT COUNT(*) AS n FROM users u JOIN roles r ON r.id = u.role_id
               WHERE u.branch_id = %s AND u.deleted_at IS NULL
                 AND r.code IN ('student', 'visitor')""", (branch_id,))
        people = cur.fetchone()["n"]

        if rooms or people:
            raise ApiError("Branch still has " + str(rooms) + " room(s) and " + str(people) +
                           " student/visitor record(s). Remove them first.", 409)

        cur.execute(
            """UPDATE users u JOIN roles r ON r.id = u.role_id
               SET u.deleted_at = NOW(), u.deleted_by = %s
               WHERE u.branch_id = %s AND r.code = 'branch_admin' AND u.deleted_at IS NULL""",
            (me, branch_id))
        cur.execute("UPDATE branch_services SET deleted_at = NOW(), deleted_by = %s "
                    "WHERE branch_id = %s AND deleted_at IS NULL", (me, branch_id))
        soft_delete("branches", branch_id, me, cur)

    return ok(None, "Branch deleted")


@bp.post("/branches/<int:branch_id>/restore")
@super_admin_required
def restore_branch(branch_id):
    if query_one(
            """SELECT b.id FROM branches b JOIN cities c ON c.id = b.city_id
               WHERE b.id = %s AND b.deleted_at IS NOT NULL AND c.deleted_at IS NULL""",
            (branch_id,)) is None:
        raise ApiError("Deleted branch not found (or its city is deleted)", 404)

    execute("UPDATE branches SET deleted_at = NULL, deleted_by = NULL WHERE id = %s",
            (branch_id,))
    return ok({"id": branch_id},
              "Branch restored (admins and services are not restored; add them again)")


# BRANCH ADMINS (the wardens who log in)

@bp.post("/branches/<int:branch_id>/admins")
@staff_required
def add_branch_admin(branch_id):
    data = get_json()
    require_branch_access(branch_id)
    user_id = create_admin("branch_admin", data, branch_id=branch_id)
    return ok({"id": user_id}, "Branch admin created", 201)


@bp.get("/branches/<int:branch_id>/admins")
@staff_required
def list_branch_admins(branch_id):
    require_branch_access(branch_id)
    return ok(list_admins("branch_admin", "branch_id", branch_id))


@bp.put("/branches/<int:branch_id>/admins/<int:user_id>")
@staff_required
def update_branch_admin(branch_id, user_id):
    """
    Change a branch admin's login. Super admin or that city's admin only -
    branch admins have no way to change their own username or password.
    """
    data = get_json()
    require_branch_access(branch_id)
    admin = find_admin("branch_admin", "branch_id", branch_id, user_id, "Branch admin")
    update_admin(admin, data)
    return ok({"id": user_id}, "Branch admin updated")


@bp.delete("/branches/<int:branch_id>/admins/<int:user_id>")
@staff_required
def delete_branch_admin(branch_id, user_id):
    require_branch_access(branch_id)
    admin = find_admin("branch_admin", "branch_id", branch_id, user_id, "Branch admin")
    delete_admin(admin)
    return ok(None, "Branch admin deleted")


@bp.get("/branches/<int:branch_id>/hierarchy")
@login_required
def branch_hierarchy(branch_id):
    """Who is in charge of this branch: its admins, its city admins, head office."""
    branch = require_branch_access(branch_id)

    def people(role_code, column, value):
        sql = ("SELECT u.id, CONCAT_WS(' ', u.first_name, u.last_name) AS full_name "
               "FROM users u JOIN roles r ON r.id = u.role_id "
               "WHERE r.code = %s AND u.deleted_at IS NULL")
        params = [role_code]
        if column:
            sql += " AND u." + column + " = %s"
            params.append(value)
        return query_all(sql + " ORDER BY u.id", tuple(params))

    city_admins = people("city_admin", "city_id", branch["city_id"])
    return ok({
        "branch_id": branch["id"], "branch": branch["name"], "code": branch["code"],
        "branch_admins": people("branch_admin", "branch_id", branch_id),
        "city_admins": city_admins,                  # may be empty -> head office answers
        "super_admins": people("super_admin", None, None),
    })


# SERVICE CATALOG  (one list for the whole network; each branch picks from it)

@bp.get("/services")
@login_required
def list_catalog():
    return ok(query_all(
        """SELECT s.id, s.name, s.description, COUNT(bs.branch_id) AS branches
           FROM services s
           LEFT JOIN branch_services bs ON bs.service_id = s.id AND bs.deleted_at IS NULL
           WHERE s.deleted_at IS NULL
           GROUP BY s.id ORDER BY s.name"""))


@bp.post("/services")
@super_admin_required
def add_catalog_service():
    data = get_json()
    require(data, ["name"])
    service_id = execute("INSERT INTO services (name, description) VALUES (%s, %s)",
                         (str(data["name"]).strip(), text_or_none(data.get("description"))))
    return ok({"id": service_id}, "Service added to the catalog", 201)


@bp.put("/services/<int:service_id>")
@super_admin_required
def update_catalog_service(service_id):
    data = get_json()
    require(data, ["name"])
    ensure_exists("services", service_id, "Service")
    execute("UPDATE services SET name = %s, description = %s WHERE id = %s",
            (str(data["name"]).strip(), text_or_none(data.get("description")), service_id))
    return ok({"id": service_id}, "Service updated")


@bp.delete("/services/<int:service_id>")
@super_admin_required
def delete_catalog_service(service_id):
    ensure_exists("services", service_id, "Service")
    with db_cursor() as cur:
        cur.execute("UPDATE branch_services SET deleted_at = NOW(), deleted_by = %s "
                    "WHERE service_id = %s AND deleted_at IS NULL", (g.user["id"], service_id))
        soft_delete("services", service_id, g.user["id"], cur)
    return ok(None, "Service deleted from the catalog and from every branch")


# NETWORK SUMMARY  (the part every branch may see about the others)

def network_rows(city_id=None):
    """
    One row of counts per active branch. Each count is computed in its own
    sub-query, so the numbers can never multiply each other (a classic
    JOIN mistake).

    Beds come from the view v_beds, whose status is DERIVED from the allocations
    (occupied = has an allocation without checkout_date).

    free_rooms = rooms that still have at least one free bed.
    """
    sql = """
        SELECT b.id AS branch_id, b.name AS branch_name, b.code,
               c.id AS city_id, c.name AS city,
               COALESCE(rm.total_rooms, 0)     AS total_rooms,
               COALESCE(bd.free_rooms, 0)      AS free_rooms,
               COALESCE(bd.total_beds, 0)      AS total_beds,
               COALESCE(bd.available_beds, 0)  AS available_beds,
               COALESCE(st.total_students, 0)  AS total_students
        FROM branches b
        JOIN cities c ON c.id = b.city_id AND c.deleted_at IS NULL
        LEFT JOIN (SELECT branch_id, COUNT(*) AS total_rooms
                   FROM rooms WHERE deleted_at IS NULL
                   GROUP BY branch_id) rm ON rm.branch_id = b.id
        LEFT JOIN (SELECT branch_id,
                          COUNT(*) AS total_beds,
                          SUM(status = 'Available') AS available_beds,
                          COUNT(DISTINCT CASE WHEN status = 'Available'
                                              THEN room_id END) AS free_rooms
                   FROM v_beds GROUP BY branch_id) bd ON bd.branch_id = b.id
        LEFT JOIN (SELECT u.branch_id, COUNT(*) AS total_students
                   FROM users u JOIN roles r ON r.id = u.role_id AND r.code = 'student'
                   WHERE u.deleted_at IS NULL
                   GROUP BY u.branch_id) st ON st.branch_id = b.id
        WHERE b.is_active = 1 AND b.deleted_at IS NULL"""
    params = ()

    if city_id is not None:
        sql += " AND b.city_id = %s"
        params = (city_id,)

    rows = query_all(sql + " ORDER BY c.name, b.name", params)

    for row in rows:
        row["occupied_beds"] = row["total_beds"] - row["available_beds"]
        row["full_rooms"] = row["total_rooms"] - row["free_rooms"]
        row["is_your_branch"] = row["branch_id"] == g.user["branch_id"]
        row["is_your_city"] = row["city_id"] == g.user["city_id"]

    return rows


COUNT_FIELDS = ("total_rooms", "free_rooms", "full_rooms", "total_beds",
                "available_beds", "occupied_beds", "total_students")


def add_up(rows):
    """Sum the count columns of several branch rows."""
    return {field: sum(r[field] for r in rows) for field in COUNT_FIELDS}


@bp.get("/network/overview")
@login_required
def network_overview():
    """Every active branch with its counts + grand totals.  Optional: ?city_id=2"""
    city_id = request.args.get("city_id")
    rows = network_rows(to_int(city_id, "city_id") if city_id else None)

    totals = add_up(rows)
    totals["branches"] = len(rows)

    return ok({"totals": totals, "branches": rows})


@bp.get("/network/cities")
@login_required
def network_cities():
    """The same numbers rolled up per city."""
    cities = {}

    for row in network_rows():
        city = cities.setdefault(row["city_id"], {
            "city_id": row["city_id"], "city": row["city"], "rows": []})
        city["rows"].append(row)

    result = []
    for city in cities.values():
        summary = add_up(city["rows"])
        summary.update(city_id=city["city_id"], city=city["city"],
                       branches=len(city["rows"]),
                       is_your_city=city["city_id"] == g.user["city_id"])
        result.append(summary)

    return ok(result)