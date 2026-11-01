# Hostel Management API v3.1 (Flask + MySQL)

Built from **ERD v3.1**: one `users` table, a role hierarchy, soft delete everywhere,
and no stored values that can be derived.

```
super_admin  >  city_admin  >  branch_admin  >  student  >  visitor
  (global)        (one city)     (one branch)    (one branch)  (one branch)
```

Requires **MySQL 8.0.13+** (generated columns, views, triggers).

## What changed from v2

| Area | v2 | v3.1 |
|---|---|---|
| People | `students`, `users` (admins), `visitors` tables | **one `users` table**, `roles` table decides who is who |
| Student extras (father, mother, vehicle, college) | columns on `students` | `user_profiles` (1:1 with users) |
| Roles | super_admin, branch_admin | + **city_admin** (`users.city_id`), `roles.parent_role_id/level/scope` |
| Delete | hard `DELETE`, 409 when records depend on the row | **soft delete** (`deleted_at`, `deleted_by`), history is kept |
| Bed / allocation / visit / attendance status | stored columns | **derived** (`checkout_date IS NULL`, `check_out IS NULL`, `in_time IS NULL`) |
| `branch_id` | copied onto every table | only on `users` and `rooms` (other tables reach it through those) |
| Services | typed again for every branch | one **catalog** + `branch_services` (many-to-many) |
| Visitors | one row per visit | a visitor is a **user**; `visits` links visitor and host student |
| Leaves | status only | + `decided_by`, `decided_at` |
| Cross-branch safety | composite foreign keys | `require_branch_access` + database **triggers** |
| Database name | `hostel_db` | **`hostel_db_v3`** (so your v2 data is never touched) |

URLs under `/branches/<id>/...` and the response bodies are the same as v2, so your React app keeps working.
The few differences are listed in **"Behaviour changes"** below.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | **New database** (tables, views, triggers, the 5 roles) |
| `migrate_v2_to_v3.sql` | Copies your v2 data into the new database (old DB untouched) |
| `app.py` | Starts the app, registers the parts, error handlers |
| `auth.py` | Login, tokens, role checks, branch/city access, authority check (ERD query 8.8) |
| `branches.py` | Roles, cities, **city admins**, branches, branch admins, hierarchy, service catalog, `/network/...` |
| `hostel.py` | Students, rooms, beds, allocations, services, visitors, leaves, attendance, dashboard |
| `bootstrap.py` | Makes sure the roles exist; creates default super admin / branch admins |
| `helpers.py` | `ok()`, `ApiError`, validation, pagination, `get_person()`, `soft_delete()` |
| `db.py` | MySQL connection pool |
| `createsuperadmin.py` | Command line version of the default-account setup |
| `.env.example`, `requirements.txt` | Settings and packages |
| `Hostel_API_postman_collection.json` | 91 requests, in run order |

## Setup

1. `pip install -r requirements.txt`
2. Database - pick ONE:
   * **Fresh:** `mysql -u root -p < schema.sql`
   * **Upgrade from v2:**
     ```bash
     mysqldump -u root -p hostel_db > hostel_v2_backup.sql
     mysql -u root -p < schema.sql
     mysql -u root -p < migrate_v2_to_v3.sql      # the last SELECT must show old_rows = new_rows
     ```
3. `.env`: copy `.env.example`, set `DB_PASSWORD`, `SECRET_KEY`, and keep `DB_NAME=hostel_db_v3`.
4. `python app.py` -> http://127.0.0.1:5000/ . On start the API creates `superadmin / admin123`
   (if missing) and a default `hosteladmin / password1` for every branch that never had an admin.
5. Postman: import the collection and **Run** it. The folders `14` (isolation) and the 403/404/409 requests
   are *supposed* to be refused.

## Who may do what

| Action | super_admin | city_admin | branch_admin |
|---|---|---|---|
| Create / edit / delete cities, city admins, service catalog | yes | no | no |
| Create / edit / delete / close branches | any city | **own city** | no |
| Create / edit / delete branch admins | any | **branches of own city** | no |
| Open `/branches/<id>/...` (students, rooms ...) | any branch | **branches of own city** | **own branch** |
| Approve / reject a leave | yes | yes (own city) | yes (own branch) |
| `/network/...` (counts only) and `/branches` (basic info) | yes | yes | yes |

The "approve / edit an admin" rule is ERD query 8.8: the caller must be **higher in level** than the target
and the target must be inside the caller's city / branch (`auth.require_authority_over`).

## Endpoints

Login: `POST /auth/login`, `GET /auth/me` (now also returns `role`, `city_id`).

### Head office / city level
| Action | Method | URL | Who |
|---|---|---|---|
| Role hierarchy | GET | `/roles` | any login |
| Add / list cities | POST / GET | `/cities` | super / any |
| Update / delete / restore city | PUT / DELETE / POST | `/cities/<id>`, `/cities/<id>/restore` | super |
| **City admins** add / list | POST / GET | `/cities/<id>/admins` | super |
| **City admin** update / delete | PUT / DELETE | `/cities/<id>/admins/<user_id>` | super |
| Add branch (+ default admin) | POST | `/branches` | super, city admin (own city) |
| List / view branches | GET | `/branches` (`?city_id=`), `/branches/<id>` | any login |
| Update / close branch | PUT | `/branches/<id>` (`is_active` true/false) | super, city admin |
| **Delete** / restore branch | DELETE / POST | `/branches/<id>`, `/branches/<id>/restore` | super, city admin / super |
| Branch admins add / list | POST / GET | `/branches/<id>/admins` | super, city admin |
| Branch admin update / **delete** | PUT / DELETE | `/branches/<id>/admins/<user_id>` | super, city admin |
| Who is above this branch | GET | `/branches/<id>/hierarchy` | anyone who may open the branch |
| Service catalog | GET / POST | `/services` | any / super |
| Service catalog update / delete | PUT / DELETE | `/services/<id>` | super |
| Counts of every branch / per city | GET | `/network/overview` (`?city_id=`), `/network/cities` | any login |

Admin bodies accept `username`, `password` (min 8), and either `full_name` **or** `first_name` + `last_name`,
plus optional `contact`, `email`; update also `is_active`. Send only what you want to change.

### Inside a branch: prefix `/branches/<branch_id>`
| Action | Method | URL (after the prefix) |
|---|---|---|
| Add / list / view / update student | POST / GET / GET / PUT | `/students`, `/students/<id>` |
| **Delete** (soft) / **restore** student | DELETE / POST | `/students/<id>`, `/students/<id>/restore` |
| Add / list room (+beds) | POST / GET | `/rooms` |
| **Delete room** (soft, refused while occupied) | DELETE | `/rooms/<id>` |
| Beds of a room / available beds | GET | `/rooms/<id>/beds`, `/beds/available` |
| Allocate / list / checkout | POST / GET / PATCH | `/allocations`, `/allocations/<id>/checkout` |
| Services of this branch: add / list / **remove** | POST / GET / DELETE | `/services`, `/services/<service_id>` |
| Visitors: add / list / checkout | POST / GET / PATCH | `/visitors`, `/visitors/<visit_id>/checkout` |
| Leaves: apply / list / approve / reject | POST / GET / PATCH | `/leaves`, `/leaves/<id>/approve`, `/leaves/<id>/reject` |
| Attendance: OUT / IN / list | POST / POST / GET | `/attendance/out`, `/attendance/in`, `/attendance` |
| Dashboard | GET | `/dashboard` |

`POST /services` body: `{"name": "...", "description": "..."}` (found or created in the catalog, then linked to
this branch) or `{"service_id": 3}`.

## Behaviour changes your React app should know

1. **Delete is soft.** `DELETE /students/<id>` now succeeds even when the student has leaves, visits or allocations
   (v2 answered 409). The student disappears from every list and lookup (404), history stays in the database.
   An active bed is freed automatically.
2. **Visitors:** `POST /visitors` returns `{"id": <visit id>, "visitor_id": <user id>}`. Use the visit `id` for
   `/visitors/<id>/checkout`. The same name + contact reuses the visitor's user row. A visitor who is still checked in
   cannot be checked in twice (409).
3. **Services:** adding a name that already exists in the catalog links it instead of duplicating it.
   Adding a service the branch already offers returns 409.
4. **Statuses are computed**, same values as before: bed `Available/Occupied`, allocation `Active/Checked-out`,
   visitor `CheckedIn/CheckedOut`, attendance `OUTSIDE/IN`. Invalid `?status=` values now return 400.
5. **Ids:** migrated students keep their ids. Admin and visitor ids change (they share one table now).
6. Unique values only count **live** rows: a deleted room number, branch code, username or service name can be used again.
7. Closed (`is_active = false`) branches stay visible to head office and to that city's admin; branch admins are locked out.
8. `GET /branches/<id>` etc. return **404** for deleted branches; deleting a branch is refused (409) while it has rooms,
   students or visitors. Its branch admins are deleted with it.

## Soft delete rules

* Every table has `created_at, updated_at, deleted_at, deleted_by`. Live row = `deleted_at IS NULL`.
* `is_active` (branch closed / login suspended) is separate and reversible, as in the ERD.
* A unique rule such as "room number per branch" is a UNIQUE key that includes the generated column `is_live`
  (1 for live rows, NULL for deleted ones), so deleted rows never block new ones.
* Restore endpoints exist for cities, branches and students. Restoring a city or branch does **not** bring back
  the admins that were deleted with it.

## Rules enforced by the database itself

| Rule | How |
|---|---|
| One active allocation per bed, and per student | unique keys on generated columns of `allocations` |
| One open OUT record per student | unique key on a generated column of `attendance` |
| Allocation: user is a student and student + bed are in the same branch | trigger `trg_allocations_bi` |
| Leave / attendance user is a student; `decided_by` is an admin | triggers on `leaves`, `attendance` |
| Visit: visitor is a visitor, host is a student, same branch | trigger `trg_visits_bi` |
| super_admin: no city/branch; city_admin: city only; branch roles: branch only; login roles need username + password | `check_user_scope` trigger on `users` |

A violated trigger returns **400** with its message. The API checks the same things first and gives friendlier errors.

## Response format and status codes

Unchanged: `{"success": true, "message": ..., "data": ..., "meta": {...}}` for lists, `{"success": false, "error": "..."}`
for errors. 200/201 OK, 400 bad input, 401 login problem, 403 not allowed, 404 not found (also other branch / deleted),
405 wrong method, 409 conflict, 500 server.

## Deliberate small differences from the ERD picture

* `users.contact` is nullable (admins created by the API or at start-up have no phone number). Students and visitors
  still must send `contact`; the API requires it.
* `users.first_name` / `last_name` are 100 characters so a long visitor name fits.
* The 5 roles are inserted by `schema.sql` and re-checked at every start (`bootstrap.ensure_roles`).

## Troubleshooting

| Problem | Fix |
|---|---|
| `Unknown database 'hostel_db_v3'` | Import `schema.sql`, and keep `DB_NAME=hostel_db_v3` |
| `Table ... doesn't exist` / `Unknown column` | You are still pointing at the v2 database |
| `Access denied for user 'root'` | Wrong `DB_PASSWORD` in `.env` |
| `SECRET_KEY is missing` | Add it to `.env` (see `.env.example`) |
| `CREATE FUNCTION` / trigger error while importing `schema.sql` | Use a MySQL user with trigger/routine rights (root), MySQL 8.0.13+ |
| 400 "... must be a user with role student" | The id belongs to a visitor/admin, not a student |
| 403 "This branch is in another city" | You are a city admin; use `/network/overview` for other cities |
| 409 "Branch still has N room(s) ..." | Delete the rooms / students first, then the branch |

## Not included yet

* CORS for the React app (add `flask-cors` together with the frontend)
* Student login portal (the `student` role exists with `can_login = 0`; set it to 1 and add a password to enable)
* Moving a student between branches, login rate limiting, gender check between student and room
* Restore endpoints for rooms and admins (set `deleted_at = NULL` by hand for now)

**Default logins** (`superadmin / admin123`, `hosteladmin / password1`) are for local development only. Change them before going public.

For production: `FLASK_DEBUG=0` and `waitress-serve --port=5000 app:app` (or gunicorn).