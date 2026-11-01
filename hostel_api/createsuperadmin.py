"""Create (or repair) the default accounts from the command line.

    python createsuperadmin.py            create anything that is missing
    python createsuperadmin.py --reset    ALSO force the Super Admin password
                                          back to the default (admin123)

Defaults:
    Super Admin    superadmin   / admin123
    Branch admins  hosteladmin  / password1   (one per branch that never had one)

It also makes sure the five roles exist (super_admin, city_admin, branch_admin,
student, visitor). City admins are created through the API:
POST /cities/<id>/admins  (super admin token).

The real logic lives in bootstrap.py. The server runs the same steps
automatically every time it starts, so you normally do not need this file.
"""

import sys

from bootstrap import (
    SUPERADMIN_USERNAME,
    SUPERADMIN_PASSWORD,
    ensure_default_branch_admins,
    ensure_default_superadmin,
)


def main():
    reset = "--reset" in sys.argv
    try:
        state = ensure_default_superadmin(reset_password=reset)
        created = ensure_default_branch_admins()
    except Exception as error:
        print("\nCould not prepare the default accounts.")
        print(f"Reason: {error}")
        print("Check .env (DB_PASSWORD!) and make sure MySQL is running and schema.sql was imported (database hostel_db_v3).")
        raise SystemExit(1) from error

    if state == "created":
        print(f"Super Admin created:   {SUPERADMIN_USERNAME} / {SUPERADMIN_PASSWORD}")
    elif state == "reset":
        print(f"Super Admin password reset: {SUPERADMIN_USERNAME} / {SUPERADMIN_PASSWORD}")
    else:
        print(f"Super Admin '{SUPERADMIN_USERNAME}' already exists (password untouched; "
              "use --reset to set it back to the default).")

    for branch_name, username in created:
        print(f"Branch admin created for {branch_name}: {username}")


if __name__ == "__main__":
    main()