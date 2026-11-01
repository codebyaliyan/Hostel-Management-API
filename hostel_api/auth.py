"""
auth.py - "who is calling?" and "what may they touch?"

Five roles live in ONE users table (see roles table, ERD v3.1):

    super_admin   level 0  global   Head office. Everything.
    city_admin    level 1  city     Manages every branch of ONE city.
    branch_admin  level 2  branch   Warden of ONE branch.
    student       level 3  branch   Lives in a branch. Does not log in (yet).
    visitor       level 4  branch   Visits a student. Does not log in.

A lower level means more authority. Only roles with can_login = 1 get a token.

Flow:
    1. POST /auth/login  {username, password}   ->  returns a token
    2. Every other request sends the header:   Authorization: Bearer <token>

The token is signed with SECRET_KEY (itsdangerous, already installed with
Flask), so nobody can forge or edit it. It expires after TOKEN_HOURS.
"""

import os
from pathlib import Path
from functools import wraps

from dotenv import load_dotenv
from flask import Blueprint, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from db import query_one
from helpers import ApiError, get_json, ok, require

load_dotenv(Path(__file__).resolve().with_name(".env"))

bp = Blueprint("auth", __name__, url_prefix="/auth")

TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "12"))
MIN_PASSWORD_LENGTH = 8

ADMIN_ROLES = ("super_admin", "city_admin", "branch_admin")


def check_config():
    """Called once when the app starts, so a missing key fails loudly."""
    if not os.getenv("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is missing. Add a long random text to your .env file, e.g. "
            "SECRET_KEY=<output of: python -c \"import secrets; print(secrets.token_hex(32))\">"
        )


def _serializer():
    return URLSafeTimedSerializer(os.environ["SECRET_KEY"], salt="hostel-auth")


def hash_password(password):
    """Only the hash is stored in the database, never the password."""
    if len(str(password)) < MIN_PASSWORD_LENGTH:
        raise ApiError("password must be at least " + str(MIN_PASSWORD_LENGTH) + " characters")
    return generate_password_hash(str(password))


# WHO IS CALLING?

# One query gives the user, the role and the EFFECTIVE city
# (a branch admin's city comes from their branch, a city admin's from users.city_id).
USER_SELECT = """SELECT u.id, u.username, u.first_name, u.last_name,
                        CONCAT_WS(' ', u.first_name, u.last_name) AS full_name,
                        u.is_active, u.branch_id,
                        COALESCE(b.city_id, u.city_id) AS city_id,
                        r.code AS role, r.level, r.scope, r.can_login
                 FROM users u
                 JOIN roles r         ON r.id = u.role_id
                 LEFT JOIN branches b ON b.id = u.branch_id
                 WHERE u.id = %s AND u.deleted_at IS NULL"""


def load_user():
    """Return the logged-in user (a dict) or stop with 401."""
    if "user" in g:
        return g.user

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError("Login required. Send the header "
                       "'Authorization: Bearer <token>' (get a token from POST /auth/login).", 401)

    try:
        payload = _serializer().loads(header[7:].strip(), max_age=TOKEN_HOURS * 3600)
    except SignatureExpired:
        raise ApiError("Token expired. Please log in again.", 401)
    except BadSignature:
        raise ApiError("Invalid token.", 401)

    # Read the user fresh from the database, so a disabled or deleted account
    # is locked out immediately, not only when its token expires.
    user = query_one(USER_SELECT, (payload.get("uid"),))
    if user is None or not user["is_active"] or not user["can_login"]:
        raise ApiError("Account not found or disabled.", 401)

    g.user = user
    return user


def login_required(view):
    """Any logged-in user (super admin, city admin or branch admin)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        load_user()
        return view(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """Only the listed roles, e.g. @role_required("super_admin", "city_admin")."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = load_user()
            if user["role"] not in roles:
                raise ApiError("Your role (" + user["role"] + ") cannot do this. "
                               "Allowed: " + ", ".join(roles) + ".", 403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def super_admin_required(view):
    """Head office only."""
    return role_required("super_admin")(view)


def staff_required(view):
    """Head office or a city admin (people who manage branches)."""
    return role_required("super_admin", "city_admin")(view)


# WHAT MAY THEY TOUCH?

def require_city_access(city_id):
    """
    super admin -> any city,  city admin -> only their own city,
    branch admin -> no city-level actions.  Returns the city row.
    """
    user = load_user()

    if user["role"] == "branch_admin":
        raise ApiError("Branch admins cannot manage cities.", 403)
    if user["role"] == "city_admin" and user["city_id"] != city_id:
        raise ApiError("You can only manage your own city (id " + str(user["city_id"]) + ").", 403)

    city = query_one("SELECT id, name FROM cities WHERE id = %s AND deleted_at IS NULL",
                     (city_id,))
    if city is None:
        raise ApiError("City not found", 404)
    return city


def require_branch_access(branch_id):
    """
    The key privacy rule of the whole API.
    Used for every URL that starts with /branches/<branch_id>/...

    - branch admin -> only their own branch_id
    - city admin   -> any branch whose city is their city
    - super admin  -> any branch
    Returns the branch row (id, name, code, city_id, is_active).
    """
    user = load_user()

    if user["role"] == "branch_admin" and user["branch_id"] != branch_id:
        raise ApiError(
            "You can only open your own branch (id " + str(user["branch_id"]) + "). "
            "Other branches share only general numbers: GET /network/overview", 403)

    branch = query_one(
        """SELECT b.id, b.name, b.code, b.city_id, b.is_active
           FROM branches b
           JOIN cities c ON c.id = b.city_id AND c.deleted_at IS NULL
           WHERE b.id = %s AND b.deleted_at IS NULL""",
        (branch_id,))
    if branch is None:
        raise ApiError("Branch not found", 404)

    if user["role"] == "city_admin" and branch["city_id"] != user["city_id"]:
        raise ApiError(
            "This branch is in another city. City admins manage only their own city "
            "(id " + str(user["city_id"]) + "). Other branches: GET /network/overview", 403)

    if not branch["is_active"] and user["role"] == "branch_admin":
        raise ApiError("This branch is deactivated. Contact your city admin or head office.", 403)

    return branch


# Query 8.8 of the ERD: "may the caller act on that user?"
AUTHORITY_SQL = """SELECT 1 AS allowed
                   FROM v_user_scope a
                   JOIN v_user_scope t ON t.user_id = %s
                   WHERE a.user_id = %s
                     AND a.level < t.level
                     AND ( a.scope = 'global'
                        OR (a.scope = 'city'   AND a.city_id   = t.city_id)
                        OR (a.scope = 'branch' AND a.branch_id = t.branch_id) )"""


def require_authority_over(target_user_id):
    """
    The caller must be HIGHER in the hierarchy than the target user
    and the target must sit inside the caller's city / branch.
    Use before approving a leave, editing or deleting an admin.
    """
    caller = load_user()
    if query_one(AUTHORITY_SQL, (target_user_id, caller["id"])) is None:
        raise ApiError("You do not have authority over this user.", 403)


# ENDPOINTS

@bp.post("/login")
def login():
    data = get_json()
    require(data, ["username", "password"])

    user = query_one(
        """SELECT u.id, u.username, u.first_name, u.last_name, u.password_hash, u.is_active,
                  u.branch_id, COALESCE(b.city_id, u.city_id) AS city_id,
                  r.code AS role, r.can_login,
                  b.name AS branch_name, c.name AS city_name
           FROM users u
           JOIN roles r         ON r.id = u.role_id
           LEFT JOIN branches b ON b.id = u.branch_id
           LEFT JOIN cities c   ON c.id = COALESCE(b.city_id, u.city_id)
           WHERE u.username = %s AND u.deleted_at IS NULL""",
        (str(data["username"]),),
    )

    # One message for every failure, so attackers cannot learn which usernames exist.
    if (user is None or not user["is_active"] or not user["can_login"]
            or not user["password_hash"]
            or not check_password_hash(user["password_hash"], str(data["password"]))):
        raise ApiError("Invalid username or password", 401)

    token = _serializer().dumps({"uid": user["id"]})

    return ok({
        "token": token,
        "token_type": "Bearer",
        "expires_in_hours": TOKEN_HOURS,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": " ".join(p for p in (user["first_name"], user["last_name"]) if p),
            "role": user["role"],
            "city_id": user["city_id"],
            "city_name": user["city_name"],
            "branch_id": user["branch_id"],
            "branch_name": user["branch_name"],
        },
    }, "Login successful")


@bp.get("/me")
@login_required
def who_am_i():
    return ok(g.user)