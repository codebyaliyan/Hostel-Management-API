"""
bootstrap.py - the default roles and accounts the system creates for you.

    Super Admin (head office, one)      superadmin   / admin123
    Branch Admin (one per hostel)       hosteladmin  / password1

Rules
-----
* The five roles (super_admin, city_admin, branch_admin, student, visitor) are
  inserted by schema.sql. ensure_roles() only adds what is missing.
* Nothing here ever overwrites an existing account's password (except the
  explicit `python createsuperadmin.py --reset` command).
* `users.username` is unique among live users for the whole system, so two hostels
  cannot both own the name "hosteladmin". The first hostel gets exactly
  "hosteladmin"; every further hostel gets "hosteladmin_<branchcode>"
  (e.g. hosteladmin_isbf7). All of them start with the same password.
* A branch that ever had a branch admin (even a deleted one) never gets a
  default admin again, so a deleted default login does not come back by itself.
* Branch admins cannot change anything about their own account. Only the
  Super Admin or the City Admin of that city can
  (PUT /branches/<id>/admins/<user_id>).

Override any of the defaults in .env (see .env.example).
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

from auth import hash_password  # noqa: E402
from db import execute, query_all, query_one  # noqa: E402
from helpers import ApiError, role_id, split_name  # noqa: E402

SUPERADMIN_USERNAME = os.getenv("DEFAULT_SUPERADMIN_USERNAME", "superadmin").strip()
SUPERADMIN_PASSWORD = os.getenv("DEFAULT_SUPERADMIN_PASSWORD", "admin123")
SUPERADMIN_FULL_NAME = (os.getenv("DEFAULT_SUPERADMIN_FULL_NAME", "Super Administrator").strip()
                        or "Super Administrator")

BRANCH_ADMIN_USERNAME = os.getenv("DEFAULT_BRANCH_ADMIN_USERNAME", "hosteladmin").strip()
BRANCH_ADMIN_PASSWORD = os.getenv("DEFAULT_BRANCH_ADMIN_PASSWORD", "password1")


# ROLES

# (code, name, level, scope, can_login, parent code)
ROLES = [
    ("super_admin",  "Super Admin",  0, "global", 1, None),
    ("city_admin",   "City Admin",   1, "city",   1, "super_admin"),
    ("branch_admin", "Branch Admin", 2, "branch", 1, "city_admin"),
    ("student",      "Student",      3, "branch", 0, "branch_admin"),
    ("visitor",      "Visitor",      4, "branch", 0, "student"),
]


def ensure_roles():
    """Insert any of the five roles that is missing (safe to repeat)."""
    for code, name, level, scope, can_login, parent in ROLES:
        if query_one("SELECT id FROM roles WHERE code = %s", (code,)):
            continue
        parent_id = None
        if parent:
            parent_id = query_one("SELECT id FROM roles WHERE code = %s", (parent,))["id"]
        execute("INSERT INTO roles (parent_role_id, code, name, level, scope, can_login) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (parent_id, code, name, level, scope, can_login))


# SUPER ADMIN

def ensure_default_superadmin(reset_password=False):
    """
    Create the head-office account if it does not exist.
    Returns "created", "reset" or "exists".
    """
    if not SUPERADMIN_USERNAME:
        raise RuntimeError("DEFAULT_SUPERADMIN_USERNAME cannot be empty.")

    ensure_roles()

    try:
        password_hash = hash_password(SUPERADMIN_PASSWORD)
    except ApiError as error:
        raise RuntimeError("DEFAULT_SUPERADMIN_PASSWORD: " + error.message) from error

    existing = query_one(
        """SELECT u.id, r.code AS role, u.branch_id, u.city_id
           FROM users u JOIN roles r ON r.id = u.role_id
           WHERE u.username = %s AND u.deleted_at IS NULL""",
        (SUPERADMIN_USERNAME,),
    )

    if existing:
        if existing["role"] != "super_admin":
            raise RuntimeError(
                f"The username '{SUPERADMIN_USERNAME}' already belongs to a non-super-admin "
                "account. Choose a different DEFAULT_SUPERADMIN_USERNAME in .env."
            )
        if reset_password:
            execute("UPDATE users SET password_hash = %s, is_active = 1 WHERE id = %s",
                    (password_hash, existing["id"]))
            return "reset"
        return "exists"

    first, last = split_name(SUPERADMIN_FULL_NAME)
    execute(
        """INSERT INTO users (role_id, city_id, branch_id, username, password_hash,
                              first_name, last_name)
           VALUES (%s, NULL, NULL, %s, %s, %s, %s)""",
        (role_id("super_admin"), SUPERADMIN_USERNAME, password_hash, first, last),
    )
    return "created"


# BRANCH ADMINS

def _username_taken(username):
    return query_one("SELECT id FROM users WHERE username = %s AND deleted_at IS NULL",
                     (username,)) is not None


def pick_branch_admin_username(branch_code):
    """'hosteladmin' if free, otherwise 'hosteladmin_<code>' (+ a number if needed)."""
    base = BRANCH_ADMIN_USERNAME
    if not _username_taken(base):
        return base

    suffix = re.sub(r"[^a-z0-9]", "", str(branch_code).lower()) or "branch"
    candidate = f"{base}_{suffix}"[:50]
    number = 2
    while _username_taken(candidate):
        tail = f"_{number}"
        candidate = f"{base}_{suffix}"[:50 - len(tail)] + tail
        number += 1
    return candidate


def create_default_branch_admin(branch_id, branch_code, branch_name=None):
    """Create the default warden login for one branch. Returns the credentials."""
    try:
        password_hash = hash_password(BRANCH_ADMIN_PASSWORD)
    except ApiError as error:
        raise RuntimeError("DEFAULT_BRANCH_ADMIN_PASSWORD: " + error.message) from error

    username = pick_branch_admin_username(branch_code)
    first = (branch_name or "Branch")[:100]

    execute(
        """INSERT INTO users (role_id, city_id, branch_id, username, password_hash,
                              first_name, last_name)
           VALUES (%s, NULL, %s, %s, %s, %s, 'Administrator')""",
        (role_id("branch_admin"), branch_id, username, password_hash, first),
    )
    return {"username": username, "password": BRANCH_ADMIN_PASSWORD}


def ensure_default_branch_admins():
    """Give every live branch that never had an admin login its default one."""
    ensure_roles()
    branches = query_all(
        """SELECT b.id, b.code, b.name FROM branches b
           WHERE b.deleted_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM users u JOIN roles r ON r.id = u.role_id
                             WHERE u.branch_id = b.id AND r.code = 'branch_admin')
           ORDER BY b.id"""
    )
    created = []
    for branch in branches:
        creds = create_default_branch_admin(branch["id"], branch["code"], branch["name"])
        created.append((branch["name"], creds["username"]))
    return created