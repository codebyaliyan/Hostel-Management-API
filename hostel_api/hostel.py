"""
hostel.py - the daily work of ONE branch.

Every URL here starts with /branches/<branch_id>, for example:

    GET  /branches/2/students
    POST /branches/2/allocations

How it stays safe:
  1. Before every request, guard() checks the login token and that the caller
     may open this branch (see auth.require_branch_access):
        branch admin -> own branch only,  city admin -> branches of their city,
        super admin -> any branch.
  2. Every query below is limited to  branch_id = bid()  - directly (rooms, users)
     or through the user / room it belongs to (allocations, leaves, visits ...).
  3. Students, visitors, leaves and attendance all live on the single `users`
     table, so every lookup also checks the ROLE (get_person) - and the database
     triggers check it a second time.

Soft delete: nothing is ever removed. A row is "live" while deleted_at IS NULL, and
every query below says so. DELETE endpoints just set deleted_at / deleted_by.

Derived values (no stored copy that could disagree):
    bed Occupied      <=>  it has an allocation with checkout_date IS NULL   (view v_beds)
    allocation status <=>  checkout_date IS NULL -> 'Active', else 'Checked-out'
    visitor status    <=>  check_out IS NULL     -> 'CheckedIn', else 'CheckedOut'
    attendance status <=>  in_time IS NULL       -> 'OUTSIDE',  else 'IN'
"""

from flask import Blueprint, g, request

from auth import require_authority_over, require_branch_access
from db import db_cursor, execute, query_all, query_one
from helpers import (ApiError, check_gender, ensure_exists, get_json, get_person, ok,
                     person_name, query_page, require, role_id, soft_delete,
                     text_or_none, to_date, to_int)

bp = Blueprint("hostel", __name__, url_prefix="/branches/<int:branch_id>")


@bp.url_value_preprocessor
def pull_branch_id(endpoint, values):
    """Take <branch_id> out of the URL so the functions below don't need it as an argument."""
    if values:
        g.branch_id = values.pop("branch_id")


@bp.before_request
def guard():
    if request.method == "OPTIONS":      # browser pre-flight requests carry no token
        return None
    g.branch = require_branch_access(g.branch_id)


def bid():
    """The branch this request is about."""
    return g.branch_id


def me():
    """The logged-in admin (for deleted_by / decided_by)."""
    return g.user["id"]


# STUDENTS   (users with role 'student' + optional user_profiles row)

STUDENT_REQUIRED = ["first_name", "last_name", "dob", "contact", "gender"]

STUDENT_FROM = """FROM users u
                  JOIN roles r ON r.id = u.role_id AND r.code = 'student'
                  LEFT JOIN user_profiles p ON p.user_id = u.id AND p.deleted_at IS NULL"""


def student_values(data):
    """
    Validate the body. Returns (user_values, profile_values):
        user    -> first_name, last_name, dob, contact, email, address, gender
        profile -> father_name, mother_name, vehicle_number, college_workplace
    """
    require(data, STUDENT_REQUIRED)
    check_gender(data["gender"])
    to_date(data["dob"], "dob")

    user = (data["first_name"], data["last_name"], data["dob"], data["contact"],
            data.get("email"), data.get("address"), data["gender"])
    profile = (data.get("father_name"), data.get("mother_name"),
               data.get("vehicle_number"), data.get("college_workplace"))
    return user, profile


@bp.post("/students")
def add_student():
    user, profile = student_values(get_json())
    student_role = role_id("student")

    # users row + user_profiles row together (all or nothing)
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO users (role_id, branch_id, first_name, last_name, dob,
                                  contact, email, address, gender)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (student_role, bid()) + user,
        )
        student_id = cur.lastrowid

        cur.execute(
            """INSERT INTO user_profiles
               (user_id, father_name, mother_name, vehicle_number, college_workplace)
               VALUES (%s, %s, %s, %s, %s)""",
            (student_id,) + profile,
        )

    return ok({"id": student_id}, "Student added", 201)


@bp.get("/students")
def list_students():
    rows, meta = query_page(
        "u.id, u.first_name, u.last_name, u.gender, u.contact",
        STUDENT_FROM + " WHERE u.branch_id = %s AND u.deleted_at IS NULL",
        (bid(),), "u.id",
    )
    return ok(rows, meta=meta)


@bp.get("/students/<int:student_id>")
def view_student(student_id):
    row = query_one(
        """SELECT u.id, u.branch_id, u.first_name, u.last_name,
                  p.father_name, p.mother_name, u.dob, u.contact, u.email, u.address,
                  p.vehicle_number, p.college_workplace, u.gender, u.created_at
           """ + STUDENT_FROM + """
           WHERE u.id = %s AND u.branch_id = %s AND u.deleted_at IS NULL""",
        (student_id, bid()))

    if row is None:
        raise ApiError("Student not found", 404)

    return ok(row)


@bp.put("/students/<int:student_id>")
def update_student(student_id):
    user, profile = student_values(get_json())

    with db_cursor() as cur:
        get_person(student_id, "student", "Student", bid(), cur)

        cur.execute(
            """UPDATE users SET first_name = %s, last_name = %s, dob = %s, contact = %s,
                                email = %s, address = %s, gender = %s
               WHERE id = %s AND branch_id = %s""",
            user + (student_id, bid()),
        )
        # the profile row is optional: create it, or revive a deleted one
        cur.execute(
            """INSERT INTO user_profiles
               (user_id, father_name, mother_name, vehicle_number, college_workplace)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   father_name = VALUES(father_name), mother_name = VALUES(mother_name),
                   vehicle_number = VALUES(vehicle_number),
                   college_workplace = VALUES(college_workplace),
                   deleted_at = NULL, deleted_by = NULL""",
            (student_id,) + profile,
        )

    return ok({"id": student_id}, "Student updated")


@bp.delete("/students/<int:student_id>")
def delete_student(student_id):
    """
    Soft delete: the student disappears from lists, the history (allocations,
    leaves, visits, attendance) stays. A bed the student still holds is freed.
    """
    with db_cursor() as cur:
        get_person(student_id, "student", "Student", bid(), cur)

        cur.execute(
            "UPDATE allocations SET checkout_date = CURDATE() "
            "WHERE user_id = %s AND checkout_date IS NULL AND deleted_at IS NULL",
            (student_id,))
        freed = cur.rowcount

        cur.execute("UPDATE user_profiles SET deleted_at = NOW(), deleted_by = %s "
                    "WHERE user_id = %s AND deleted_at IS NULL", (me(), student_id))
        soft_delete("users", student_id, me(), cur)

    return ok(None, "Student deleted" + (" and bed freed" if freed else ""))


@bp.post("/students/<int:student_id>/restore")
def restore_student(student_id):
    """Undo a delete (the student's old bed is NOT given back)."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id
               WHERE u.id = %s AND u.branch_id = %s AND r.code = 'student'
                 AND u.deleted_at IS NOT NULL FOR UPDATE""",
            (student_id, bid()))
        if cur.fetchone() is None:
            raise ApiError("Deleted student not found", 404)

        cur.execute("UPDATE users SET deleted_at = NULL, deleted_by = NULL WHERE id = %s",
                    (student_id,))
        cur.execute("UPDATE user_profiles SET deleted_at = NULL, deleted_by = NULL "
                    "WHERE user_id = %s", (student_id,))

    return ok({"id": student_id}, "Student restored")


# ROOMS AND BEDS

@bp.post("/rooms")
def add_room():
    data = get_json()
    require(data, ["room_number", "floor", "capacity", "gender"])

    try:
        floor = int(data["floor"])
    except (TypeError, ValueError):
        raise ApiError("floor must be a whole number")

    capacity = to_int(data["capacity"], "capacity")
    check_gender(data["gender"])

    if capacity > 20:
        raise ApiError("capacity cannot be more than 20")

    # Room + all its beds are created together (all or nothing).
    # room_number only has to be unique among the live rooms of this branch.
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO rooms (branch_id, room_number, floor, capacity, gender) "
            "VALUES (%s, %s, %s, %s, %s)",
            (bid(), data["room_number"], floor, capacity, data["gender"]),
        )
        room_id = cur.lastrowid

        beds = [(room_id, "Bed" + str(i)) for i in range(1, capacity + 1)]
        cur.executemany("INSERT INTO beds (room_id, bed_name) VALUES (%s, %s)", beds)

    return ok({"id": room_id, "beds_created": capacity}, "Room added", 201)


@bp.get("/rooms")
def list_rooms():
    rows, meta = query_page(
        """r.id, r.room_number, r.floor, r.capacity, r.gender,
           (SELECT COUNT(*) FROM v_beds vb WHERE vb.room_id = r.id)
               AS total_beds,
           (SELECT COUNT(*) FROM v_beds vb
             WHERE vb.room_id = r.id AND vb.status = 'Available')
               AS available_beds""",
        "FROM rooms r WHERE r.branch_id = %s AND r.deleted_at IS NULL",
        (bid(),), "r.id",
    )

    for row in rows:
        row["status"] = "Available" if row["available_beds"] > 0 else "Full"

    return ok(rows, meta=meta)


@bp.get("/rooms/<int:room_id>/beds")
def view_room_beds(room_id):
    ensure_exists("rooms", room_id, "Room", branch_id=bid())

    rows = query_all(
        "SELECT id, room_id, bed_name, status FROM v_beds "
        "WHERE room_id = %s AND branch_id = %s ORDER BY id",
        (room_id, bid()),
    )
    return ok(rows)


@bp.delete("/rooms/<int:room_id>")
def delete_room(room_id):
    """Soft delete the room and its beds. Refused while a student still sleeps in it."""
    with db_cursor() as cur:
        ensure_exists("rooms", room_id, "Room", cur, bid())

        cur.execute(
            """SELECT COUNT(*) AS n FROM active_allocations aa
               JOIN beds b ON b.id = aa.bed_id
               WHERE b.room_id = %s AND b.deleted_at IS NULL""", (room_id,))
        if cur.fetchone()["n"]:
            raise ApiError("Room still has students allocated. Check them out first.", 409)

        cur.execute("UPDATE beds SET deleted_at = NOW(), deleted_by = %s "
                    "WHERE room_id = %s AND deleted_at IS NULL", (me(), room_id))
        soft_delete("rooms", room_id, me(), cur)

    return ok(None, "Room deleted")


@bp.get("/beds/available")
def list_available_beds():
    rows, meta = query_page(
        "vb.id AS bed_id, vb.room_id, r.room_number, vb.bed_name",
        """FROM v_beds vb
           JOIN rooms r ON r.id = vb.room_id
           WHERE vb.branch_id = %s AND vb.status = 'Available'""",
        (bid(),), "vb.id",
    )
    return ok(rows, meta=meta)


# ALLOCATIONS   (room is always bed -> room; "active" = checkout_date IS NULL)

ALLOCATION_STATUSES = ("Active", "Checked-out")


@bp.post("/allocations")
def create_allocation():
    data = get_json()
    require(data, ["student_id", "room_id", "bed_id"])

    student_id = to_int(data["student_id"], "student_id")
    room_id = to_int(data["room_id"], "room_id")
    bed_id = to_int(data["bed_id"], "bed_id")

    with db_cursor() as cur:
        get_person(student_id, "student", "Student", bid(), cur)
        ensure_exists("rooms", room_id, "Room", cur, bid())

        # FOR UPDATE OF b locks the bed row so two requests cannot book the same bed.
        cur.execute(
            """SELECT b.id, b.room_id FROM beds b
               JOIN rooms r ON r.id = b.room_id
               WHERE b.id = %s AND r.branch_id = %s
                 AND b.deleted_at IS NULL AND r.deleted_at IS NULL
               FOR UPDATE OF b""",
            (bed_id, bid()),
        )
        bed = cur.fetchone()

        if bed is None:
            raise ApiError("Bed not found", 404)
        if bed["room_id"] != room_id:
            raise ApiError("Bed does not belong to this room")

        cur.execute("SELECT id FROM active_allocations WHERE bed_id = %s", (bed_id,))
        if cur.fetchone() is not None:
            raise ApiError("Bed is not available", 409)

        cur.execute("SELECT id FROM active_allocations WHERE user_id = %s", (student_id,))
        if cur.fetchone() is not None:
            raise ApiError("Student already has an active allocation", 409)

        cur.execute(
            "INSERT INTO allocations (user_id, bed_id, allocated_date) "
            "VALUES (%s, %s, CURDATE())",
            (student_id, bed_id),
        )
        allocation_id = cur.lastrowid

    return ok({"id": allocation_id}, "Allocation created", 201)


@bp.get("/allocations")
def list_allocations():
    where = "WHERE rm.branch_id = %s AND al.deleted_at IS NULL"
    params = [bid()]

    status = request.args.get("status")  # optional: /allocations?status=Active
    if status:
        if status not in ALLOCATION_STATUSES:
            raise ApiError("status must be one of: " + ", ".join(ALLOCATION_STATUSES))
        where += " AND al.checkout_date IS " + ("NULL" if status == "Active" else "NOT NULL")

    rows, meta = query_page(
        """al.id, al.user_id AS student_id,
           CONCAT_WS(' ', s.first_name, s.last_name) AS student_name,
           rm.id AS room_id, rm.room_number, al.bed_id, b.bed_name,
           al.allocated_date, al.checkout_date,
           IF(al.checkout_date IS NULL, 'Active', 'Checked-out') AS status""",
        """FROM allocations al
           JOIN users s  ON s.id = al.user_id
           JOIN beds b   ON b.id = al.bed_id
           JOIN rooms rm ON rm.id = b.room_id """ + where,
        tuple(params), "al.id",
    )
    return ok(rows, meta=meta)


@bp.patch("/allocations/<int:allocation_id>/checkout")
def checkout_allocation(allocation_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT al.id, al.checkout_date FROM allocations al
               JOIN beds b   ON b.id = al.bed_id
               JOIN rooms rm ON rm.id = b.room_id
               WHERE al.id = %s AND rm.branch_id = %s AND al.deleted_at IS NULL
               FOR UPDATE OF al""",
            (allocation_id, bid()),
        )
        allocation = cur.fetchone()

        if allocation is None:
            raise ApiError("Allocation not found", 404)
        if allocation["checkout_date"] is not None:
            raise ApiError("Already checked out", 409)

        # the bed becomes Available by itself: it no longer has an active allocation
        cur.execute("UPDATE allocations SET checkout_date = CURDATE() WHERE id = %s",
                    (allocation_id,))

    return ok(None, "Checked out. Bed is now available.")


# SERVICES  (one network-wide catalog; this branch picks the ones it offers)

@bp.post("/services")
def add_service():
    """
    Body: {"name": "...", "description": "..."}   find-or-create in the catalog, then link it
      or: {"service_id": 3}                        link an existing catalog service
    """
    data = get_json()

    with db_cursor() as cur:
        if data.get("service_id") not in (None, ""):
            service_id = to_int(data["service_id"], "service_id")
            ensure_exists("services", service_id, "Service", cur)
        else:
            require(data, ["name"])
            name = str(data["name"]).strip()

            cur.execute("SELECT id FROM services WHERE name = %s AND deleted_at IS NULL",
                        (name,))
            found = cur.fetchone()
            if found:
                service_id = found["id"]
            else:
                cur.execute("INSERT INTO services (name, description) VALUES (%s, %s)",
                            (name, text_or_none(data.get("description"))))
                service_id = cur.lastrowid

        # branches <-> services is many-to-many through branch_services
        cur.execute("SELECT deleted_at FROM branch_services "
                    "WHERE branch_id = %s AND service_id = %s FOR UPDATE",
                    (bid(), service_id))
        link = cur.fetchone()

        if link is None:
            cur.execute("INSERT INTO branch_services (branch_id, service_id) VALUES (%s, %s)",
                        (bid(), service_id))
        elif link["deleted_at"] is None:
            raise ApiError("This branch already offers that service", 409)
        else:   # offered before, removed, now added again
            cur.execute("UPDATE branch_services SET deleted_at = NULL, deleted_by = NULL "
                        "WHERE branch_id = %s AND service_id = %s", (bid(), service_id))

    return ok({"id": service_id}, "Service added", 201)


@bp.get("/services")
def list_services():
    return ok(query_all(
        """SELECT s.id, s.name, s.description
           FROM branch_services bs
           JOIN services s ON s.id = bs.service_id AND s.deleted_at IS NULL
           WHERE bs.branch_id = %s AND bs.deleted_at IS NULL
           ORDER BY s.id""",
        (bid(),),
    ))


@bp.delete("/services/<int:service_id>")
def remove_service(service_id):
    """This branch stops offering the service (the catalog entry stays)."""
    with db_cursor() as cur:
        cur.execute("UPDATE branch_services SET deleted_at = NOW(), deleted_by = %s "
                    "WHERE branch_id = %s AND service_id = %s AND deleted_at IS NULL",
                    (me(), bid(), service_id))
        if cur.rowcount == 0:
            raise ApiError("This branch does not offer that service", 404)

    return ok(None, "Service removed from this branch")


# VISITORS   (a visitor is a users row with role 'visitor'; a visit links it to the host student)

@bp.post("/visitors")
def add_visitor():
    """
    Creates (or reuses) the visitor's users row, then opens a visit.
    The same person (same name + contact) visiting again reuses their row.
    Returns the VISIT id (use it for /visitors/<id>/checkout) and the visitor_id.
    """
    data = get_json()
    require(data, ["student_id", "visitor_name", "contact", "reason"])

    student_id = to_int(data["student_id"], "student_id")
    first, last = person_name({"full_name": data["visitor_name"]})
    visitor_role = role_id("visitor")

    with db_cursor() as cur:
        get_person(student_id, "student", "Student", bid(), cur)

        cur.execute(
            """SELECT id FROM users
               WHERE role_id = %s AND branch_id = %s AND contact = %s
                 AND first_name = %s AND last_name <=> %s AND deleted_at IS NULL
               LIMIT 1""",
            (visitor_role, bid(), data["contact"], first, last))
        found = cur.fetchone()

        if found:
            visitor_id = found["id"]
            if data.get("address"):
                cur.execute("UPDATE users SET address = %s WHERE id = %s",
                            (data["address"], visitor_id))

            cur.execute("SELECT id FROM visits WHERE visitor_id = %s "
                        "AND check_out IS NULL AND deleted_at IS NULL", (visitor_id,))
            if cur.fetchone() is not None:
                raise ApiError("This visitor is already checked in", 409)
        else:
            cur.execute(
                """INSERT INTO users (role_id, branch_id, first_name, last_name, contact, address)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (visitor_role, bid(), first, last, data["contact"], data.get("address")))
            visitor_id = cur.lastrowid

        cur.execute(
            """INSERT INTO visits (visitor_id, student_id, reason, check_in)
               VALUES (%s, %s, %s, NOW())""",
            (visitor_id, student_id, data["reason"]))
        visit_id = cur.lastrowid

    return ok({"id": visit_id, "visitor_id": visitor_id}, "Visitor added", 201)


@bp.get("/visitors")
def list_visitors():
    rows, meta = query_page(
        """v.id, v.visitor_id, v.student_id,
           CONCAT_WS(' ', s.first_name, s.last_name) AS student_name,
           CONCAT_WS(' ', vu.first_name, vu.last_name) AS visitor_name,
           vu.contact, v.reason, v.check_in, v.check_out,
           IF(v.check_out IS NULL, 'CheckedIn', 'CheckedOut') AS status""",
        """FROM visits v
           JOIN users vu ON vu.id = v.visitor_id
           JOIN users s  ON s.id  = v.student_id
           WHERE vu.branch_id = %s AND v.deleted_at IS NULL""",
        (bid(),), "v.id",
    )
    return ok(rows, meta=meta)


@bp.patch("/visitors/<int:visit_id>/checkout")
def checkout_visitor(visit_id):
    visit = query_one(
        """SELECT v.id, v.check_out FROM visits v
           JOIN users vu ON vu.id = v.visitor_id
           WHERE v.id = %s AND vu.branch_id = %s AND v.deleted_at IS NULL""",
        (visit_id, bid()))

    if visit is None:
        raise ApiError("Visitor not found", 404)
    if visit["check_out"] is not None:
        raise ApiError("Already checked out", 409)

    execute("UPDATE visits SET check_out = NOW() WHERE id = %s", (visit_id,))
    return ok(None, "Visitor checked out")


# LEAVES

LEAVE_STATUSES = ("Pending", "Approved", "Rejected")


@bp.post("/leaves")
def apply_leave():
    data = get_json()
    require(data, ["student_id", "reason", "application_date", "return_date"])

    student_id = to_int(data["student_id"], "student_id")
    start = to_date(data["application_date"], "application_date")
    end = to_date(data["return_date"], "return_date")

    if end < start:
        raise ApiError("return_date cannot be before application_date")

    get_person(student_id, "student", "Student", bid())

    leave_id = execute(
        """INSERT INTO leaves (user_id, reason, application_date, return_date)
           VALUES (%s, %s, %s, %s)""",
        (student_id, data["reason"], data["application_date"], data["return_date"]),
    )
    return ok({"id": leave_id}, "Leave applied (status: Pending)", 201)


@bp.get("/leaves")
def list_leaves():
    where = "WHERE s.branch_id = %s AND l.deleted_at IS NULL"
    params = [bid()]

    status = request.args.get("status")  # optional: /leaves?status=Pending
    if status:
        if status not in LEAVE_STATUSES:
            raise ApiError("status must be one of: " + ", ".join(LEAVE_STATUSES))
        where += " AND l.status = %s"
        params.append(status)

    rows, meta = query_page(
        """l.id, l.user_id AS student_id,
           CONCAT_WS(' ', s.first_name, s.last_name) AS student_name,
           l.reason, l.application_date, l.return_date, l.status,
           l.decided_by, l.decided_at""",
        """FROM leaves l
           JOIN users s ON s.id = l.user_id """ + where,
        tuple(params), "l.id",
    )
    return ok(rows, meta=meta)


def set_leave_status(leave_id, status):
    leave = query_one(
        """SELECT l.id, l.user_id FROM leaves l
           JOIN users s ON s.id = l.user_id
           WHERE l.id = %s AND s.branch_id = %s AND l.deleted_at IS NULL""",
        (leave_id, bid()))
    if leave is None:
        raise ApiError("Leave not found", 404)

    # the decider must be higher in the hierarchy than the student (ERD query 8.8)
    require_authority_over(leave["user_id"])

    execute("UPDATE leaves SET status = %s, decided_by = %s, decided_at = NOW() WHERE id = %s",
            (status, me(), leave_id))
    return ok({"id": leave_id, "status": status}, "Leave status set to " + status)


@bp.patch("/leaves/<int:leave_id>/approve")
def approve_leave(leave_id):
    return set_leave_status(leave_id, "Approved")


@bp.patch("/leaves/<int:leave_id>/reject")
def reject_leave(leave_id):
    return set_leave_status(leave_id, "Rejected")


# ATTENDANCE

@bp.post("/attendance/out")
def mark_out():
    data = get_json()
    require(data, ["student_id", "purpose"])

    student_id = to_int(data["student_id"], "student_id")

    with db_cursor() as cur:
        get_person(student_id, "student", "Student", bid(), cur)

        cur.execute(
            "SELECT id FROM attendance "
            "WHERE user_id = %s AND in_time IS NULL AND deleted_at IS NULL",
            (student_id,),
        )
        if cur.fetchone() is not None:
            raise ApiError("Student already has an active OUT record", 409)

        cur.execute(
            """INSERT INTO attendance (user_id, purpose, out_time, remarks)
               VALUES (%s, %s, NOW(), %s)""",
            (student_id, data["purpose"], data.get("remarks")),
        )
        attendance_id = cur.lastrowid

    return ok({"id": attendance_id}, "OUT recorded", 201)


@bp.post("/attendance/in")
def mark_in():
    data = get_json()
    require(data, ["student_id"])

    student_id = to_int(data["student_id"], "student_id")

    with db_cursor() as cur:
        get_person(student_id, "student", "Student", bid(), cur)

        cur.execute(
            "SELECT id FROM attendance "
            "WHERE user_id = %s AND in_time IS NULL AND deleted_at IS NULL",
            (student_id,),
        )
        record = cur.fetchone()

        if record is None:
            raise ApiError("No active OUT record found for this student", 404)

        cur.execute("UPDATE attendance SET in_time = NOW() WHERE id = %s",
                    (record["id"],))

    return ok({"id": record["id"]}, "IN recorded")


@bp.get("/attendance")
def list_attendance():
    where = "WHERE s.branch_id = %s AND a.deleted_at IS NULL"
    params = [bid()]

    student_id = request.args.get("student_id")  # optional filter
    if student_id:
        where += " AND a.user_id = %s"
        params.append(to_int(student_id, "student_id"))

    rows, meta = query_page(
        """a.id, a.user_id AS student_id,
           CONCAT_WS(' ', s.first_name, s.last_name) AS student_name,
           a.purpose, a.out_time, a.in_time, a.remarks,
           IF(a.in_time IS NULL, 'OUTSIDE', 'IN') AS status""",
        """FROM attendance a
           JOIN users s ON s.id = a.user_id """ + where,
        tuple(params), "a.id DESC",
    )
    return ok(rows, meta=meta)


# DASHBOARD  (this branch only - for the other branches see /network/overview)

@bp.get("/dashboard")
def show_dashboard():
    row = query_one(
        """SELECT
             (SELECT COUNT(*) FROM users u JOIN roles r ON r.id = u.role_id
                WHERE r.code = 'student' AND u.branch_id = %s
                  AND u.deleted_at IS NULL)                              AS total_students,
             (SELECT COUNT(*) FROM rooms
                WHERE branch_id = %s AND deleted_at IS NULL)             AS total_rooms,
             (SELECT COUNT(DISTINCT room_id) FROM v_beds
                WHERE branch_id = %s AND status = 'Available')           AS available_rooms,
             (SELECT COUNT(*) FROM v_beds WHERE branch_id = %s)          AS total_beds,
             (SELECT COUNT(*) FROM v_beds
                WHERE branch_id = %s AND status = 'Available')           AS available_beds,
             (SELECT COUNT(*) FROM attendance a JOIN users u ON u.id = a.user_id
                WHERE u.branch_id = %s AND a.in_time IS NULL
                  AND a.deleted_at IS NULL)                              AS students_outside,
             (SELECT COUNT(*) FROM leaves l JOIN users u ON u.id = l.user_id
                WHERE u.branch_id = %s AND l.status = 'Pending'
                  AND l.deleted_at IS NULL)                              AS pending_leaves,
             (SELECT COUNT(*) FROM visits v JOIN users u ON u.id = v.visitor_id
                WHERE u.branch_id = %s AND v.check_out IS NULL
                  AND v.deleted_at IS NULL)                              AS visitors_inside""",
        (bid(),) * 8,
    )

    row["occupied_rooms"] = row["total_rooms"] - row["available_rooms"]
    row["occupied_beds"] = row["total_beds"] - row["available_beds"]

    return ok({"branch_id": g.branch["id"], "branch_name": g.branch["name"], **row})