"""
helpers.py - small tools shared by every other file.

New in v3 (ERD v3.1):
    * ensure_exists() ignores soft-deleted rows (deleted_at IS NULL)
    * get_person()    finds a user AND checks its role (student / visitor ...)
    * soft_delete()   the one place that "deletes" a row
    * role_id()       role code -> roles.id
    * person_name()   accepts first_name/last_name or one full_name
"""

from datetime import datetime
from math import ceil

from flask import jsonify, request

from db import query_all, query_one

GENDERS = ("Male", "Female", "Other")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class ApiError(Exception):
    """Raise this anywhere to stop and return a clean JSON error."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def ok(data=None, message=None, status=200, meta=None):
    """
    Every successful response has the same shape.
    'meta' is only added for paginated lists (page, limit, total, pages).
    """
    body = {"success": True, "message": message, "data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


# VALIDATION

def get_json():
    """Read the JSON body that Postman sends."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise ApiError("Request body must be valid JSON "
                       "(Body -> raw -> JSON in Postman).")
    return data


def require(data, fields):
    """Make sure the required fields are present and not empty."""
    missing = [f for f in fields if data.get(f) in (None, "")]

    if missing:
        raise ApiError("Missing required field(s): " + ", ".join(missing))


def to_int(value, field):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiError(field + " must be a whole number")

    if number <= 0:
        raise ApiError(field + " must be greater than 0")

    return number


def to_date(value, field):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(field + " must be in YYYY-MM-DD format")


def check_gender(value):
    if value not in GENDERS:
        raise ApiError("gender must be one of: " + ", ".join(GENDERS))
    return value


def text_or_none(value):
    """'  abc ' -> 'abc',  '' or None -> None."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def split_name(full_name):
    """'Ali Raza Khan' -> ('Ali', 'Raza Khan');  'Ali' -> ('Ali', None)."""
    parts = str(full_name or "").strip().split(None, 1)
    if not parts:
        return None, None
    return parts[0][:100], (parts[1].strip()[:100] if len(parts) > 1 else None)


def person_name(data, required=True):
    """
    Names arrive as first_name (+ last_name) or as a single full_name
    (the v2 admin body used full_name, so both keep working).
    """
    first = text_or_none(data.get("first_name"))
    last = text_or_none(data.get("last_name"))

    if first is None and data.get("full_name"):
        first, last = split_name(data["full_name"])

    if first is None and required:
        raise ApiError("Missing required field(s): first_name (or full_name)")
    return first, last


# ROLES

_role_ids = {}


def role_id(code):
    """roles.code -> roles.id (cached for the life of the process)."""
    if code not in _role_ids:
        row = query_one("SELECT id FROM roles WHERE code = %s", (code,))
        if row is None:
            raise ApiError("Role '" + code + "' is missing in the roles table. "
                           "Import schema.sql again.", 500)
        _role_ids[code] = row["id"]
    return _role_ids[code]


# LOOKUPS (live rows only)

def _fetch_one(sql, params, cur):
    if cur is None:
        return query_one(sql, params)
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_exists(table, record_id, label, cur=None, branch_id=None):
    """
    Return 404 if the row does not exist or was soft-deleted.
    Pass branch_id to also make sure the row belongs to that branch
    (only for tables that have a branch_id column: rooms, users).
    (table names come from our code only, never from the user)
    """
    sql = "SELECT id FROM " + table + " WHERE id = %s AND deleted_at IS NULL"
    params = (record_id,)

    if branch_id is not None:
        sql += " AND branch_id = %s"
        params = (record_id, branch_id)

    if _fetch_one(sql, params, cur) is None:
        raise ApiError(label + " not found", 404)


def get_person(user_id, role_code, label, branch_id=None, cur=None):
    """
    Find a live user with the given role (a foreign key cannot say
    "this user must be a student", so the code checks it here and the
    database triggers check it again).
    A student of branch 2 is "not found" when asked for through branch 1.
    """
    sql = """SELECT u.id, u.branch_id, u.first_name, u.last_name
             FROM users u JOIN roles r ON r.id = u.role_id
             WHERE u.id = %s AND r.code = %s AND u.deleted_at IS NULL"""
    params = [user_id, role_code]

    if branch_id is not None:
        sql += " AND u.branch_id = %s"
        params.append(branch_id)

    row = _fetch_one(sql, tuple(params), cur)
    if row is None:
        raise ApiError(label + " not found", 404)
    return row


def soft_delete(table, record_id, by_user_id, cur=None):
    """
    The only way rows are removed: set deleted_at / deleted_by.
    Returns how many rows changed (0 = was already deleted or does not exist).
    """
    sql = ("UPDATE " + table + " SET deleted_at = NOW(), deleted_by = %s "
           "WHERE id = %s AND deleted_at IS NULL")
    if cur is None:
        from db import execute_rowcount
        return execute_rowcount(sql, (by_user_id, record_id))
    cur.execute(sql, (by_user_id, record_id))
    return cur.rowcount


# PAGINATION

def query_page(columns, from_where, params, order_by):
    """
    Run a list query one page at a time:  ?page=2&limit=50

        rows, meta = query_page("u.id, u.first_name",
                                "FROM users u WHERE u.branch_id = %s",
                                (branch_id,), "u.id")
        return ok(rows, meta=meta)

    Without ?page / ?limit we return page 1 with DEFAULT_PAGE_SIZE rows,
    so one huge branch can never produce a huge response.
    """
    page = to_int(request.args.get("page", 1), "page")
    limit = to_int(request.args.get("limit", DEFAULT_PAGE_SIZE), "limit")

    if limit > MAX_PAGE_SIZE:
        raise ApiError("limit cannot be more than " + str(MAX_PAGE_SIZE))

    total = query_one("SELECT COUNT(*) AS n " + from_where, params)["n"]

    rows = query_all(
        "SELECT " + columns + " " + from_where +
        " ORDER BY " + order_by + " LIMIT %s OFFSET %s",
        tuple(params) + (limit, (page - 1) * limit),
    )

    meta = {"page": page, "limit": limit, "total": total,
            "pages": ceil(total / limit) if total else 0}
    return rows, meta