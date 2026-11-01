"""
app.py - Hostel Management REST API (Flask + MySQL), multi-city / multi-branch.
Version 3.1: unified users table, role hierarchy (super admin > city admin >
branch admin > student > visitor), soft delete.

This file only wires things together. The real work is in:

    auth.py       login, tokens, roles, "may this user open this branch?"
    branches.py   cities, city admins, branches, branch admins, service catalog,
                  /network/... summary
    hostel.py     students, rooms, beds, allocations, services, visitors,
                  leaves, attendance, dashboard - inside ONE branch
    bootstrap.py  default roles and default accounts
    helpers.py    ok(), ApiError, validation, pagination, soft_delete
    db.py         MySQL connection pool

Run:  python app.py
"""

import os
from datetime import date, datetime, timedelta
from decimal import Decimal

import mysql.connector
from flask import Flask, jsonify
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

import auth
import branches
import hostel
from helpers import ApiError, ok

# APP SETUP

class CustomJSONProvider(DefaultJSONProvider):
    """Teach Flask how to turn MySQL types (dates, decimals) into JSON."""

    sort_keys = False  # keep keys in the order we wrote them

    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat(sep=" ") if isinstance(o, datetime) else o.isoformat()
        if isinstance(o, timedelta):
            return str(o)
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        return super().default(o)


auth.check_config()          # stop with a clear message if SECRET_KEY is missing

app = Flask(__name__)
app.json = CustomJSONProvider(app)

app.register_blueprint(auth.bp)
app.register_blueprint(branches.bp)
app.register_blueprint(hostel.bp)


# DEFAULT ACCOUNTS
# Runs on EVERY way of starting the API (python app.py, flask run, gunicorn ...),
# not only "python app.py". Safe to repeat: it only creates what is missing.

def prepare_default_accounts():
    from bootstrap import ensure_default_branch_admins, ensure_default_superadmin

    if os.getenv("SECRET_KEY", "").startswith("REPLACE_WITH"):
        print("\n[WARNING] SECRET_KEY in .env is still the placeholder text. Logins work, "
              "but anyone can forge tokens. Generate a real one:\n"
              "          python -c \"import secrets; print(secrets.token_hex(32))\"")

    try:
        state = ensure_default_superadmin()
        created = ensure_default_branch_admins()
    except mysql.connector.Error as error:
        print("\n[STARTUP ERROR] Could not use the Hostel Management database.")
        errno = getattr(error, "errno", None)
        if errno == 1045:
            print("MySQL rejected DB_USER / DB_PASSWORD in .env. This is your MySQL password, "
                  "NOT the superadmin login password.")
        elif errno == 1049:
            print("The database does not exist. Import schema.sql first, or fix DB_NAME in .env "
                  "(version 3 uses DB_NAME=hostel_db_v3).")
        elif errno == 1146:
            print("The tables are missing. Import schema.sql (fresh DB). If you have v2 data, "
                  "import schema.sql and then migrate_v2_to_v3.sql, and set DB_NAME=hostel_db_v3.")
        elif errno in (2003, 2002):
            print("MySQL is not running (or DB_HOST / DB_PORT in .env is wrong). Start the MySQL service.")
        else:
            print("Check that MySQL is running, .env is correct and the schema is imported.")
        print(f"MySQL detail: {error}")
        raise SystemExit(1) from error
    except RuntimeError as error:
        print(f"\n[STARTUP ERROR] {error}")
        raise SystemExit(1) from error

    if state == "created":
        print("[SETUP] Default Super Admin created -> superadmin / admin123")
    for branch_name, username in created:
        print(f"[SETUP] Default admin created for branch '{branch_name}' -> {username} / password1")


# The Flask auto-reloader starts this file twice; only do the work in the first process.
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    prepare_default_accounts()

# ERROR HANDLERS

@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"success": False, "error": error.message}), error.status


@app.errorhandler(HTTPException)
def handle_http_error(error):
    # 404 (wrong URL), 405 (wrong method, e.g. GET instead of POST) ...
    return jsonify({"success": False, "error": error.description}), error.code


@app.errorhandler(mysql.connector.IntegrityError)
def handle_integrity_error(error):
    if error.errno == 1062:
        return jsonify({"success": False,
                        "error": "Duplicate value: this record already exists "
                                 "(or the bed / student is already taken)."}), 409
    if error.errno == 1451:
        return jsonify({"success": False,
                        "error": "Cannot remove: other records still depend on it."}), 409
    if error.errno == 1452:
        return jsonify({"success": False,
                        "error": "Related record does not exist."}), 400
    return jsonify({"success": False, "error": "Database integrity error."}), 409


@app.errorhandler(mysql.connector.Error)
def handle_database_error(error):
    # 1644 = a rule written in schema.sql (trigger), e.g. "allocations.user_id must be
    # a user with role student". The message was written by us, so it is safe to show.
    if getattr(error, "errno", None) == 1644:
        return jsonify({"success": False, "error": error.msg}), 400

    app.logger.exception("Database error")
    body = {"success": False, "error": "Database error"}
    if app.debug:                      # technical detail only while developing
        body["detail"] = str(error)
    return jsonify(body), 500


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception("Unexpected error")
    return jsonify({"success": False, "error": "Internal server error"}), 500

# HOME

@app.get("/")
def home():
    return ok({"service": "Hostel Management API", "version": "3.1"},
              "API is running")

# RUN THE SERVER

if __name__ == "__main__":
    # FLASK_DEBUG=1 (default) auto-restarts on code changes - development only.
    # In production set FLASK_DEBUG=0 and use a real server, see README.md.
    app.run(host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG", "1") == "1")