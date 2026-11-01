# StayWise Hostel Management API + Frontend

Updated React/Vite frontend aligned to the Flask/MySQL API v2 in `backend/`, plus manager-ready ERD and relationship documentation in `docs/`.

## Project structure

```text
hostel-management-updated/
├── backend/       # Flask API, schema/migration SQL, Postman collection
├── frontend/      # React + Vite responsive dashboard
└── docs/          # ERD diagram and relationship mapping
```

## 1. Backend setup

Use Python 3.10+ and MySQL 8+ (or a compatible MySQL release).

```bash
cd backend
python -m venv .venv
```

Activate the environment:

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Install packages and configure environment variables:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env`. Set `DB_PASSWORD` to the actual password for your local MySQL account (leave it blank only if that account truly has no password), and set a long random `SECRET_KEY`. Do not commit `.env`. The Super Admin login itself is seeded automatically and does not require interactive input.

**Database setup: choose one path only.**

- **Fresh database:** `mysql -u root -p < schema.sql`
- **Existing older database with data:** back it up first, then follow the comments at the top of `migratetobranches.sql` and edit the migration settings before running it.

Start the backend:

```bash
python app.py
```

On startup, the backend automatically creates the default head-office administrator if it does not already exist. For a fresh local/demo setup, use:

- Username: `superadmin`
- Password: `admin123`

You can also run `python createsuperadmin.py` to perform the same non-interactive check manually. Existing `superadmin` accounts are not overwritten and keep their current password. The API should then be available at `http://127.0.0.1:5000`. It issues a Bearer token after login.

## 2. Frontend setup

Open a second terminal:

```bash
cd frontend
npm install
```

Copy `.env.example` to `.env` if you need to change the API target, then run:

```bash
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development proxy routes `/api/*` to Flask at `http://127.0.0.1:5000` and strips the `/api` prefix, so a frontend request such as `/api/auth/login` reaches Flask `/auth/login`.

Available frontend settings:

- `VITE_API_BASE_URL=/api` — frontend API base.
- `VITE_API_PROXY_TARGET=http://127.0.0.1:5000` — local Flask target for the Vite proxy.

For a separately deployed frontend/API, set `VITE_API_BASE_URL` to the API origin and configure Flask CORS to allow the exact frontend origin.

## 3. Frontend functionality

- Bearer-token login and session restoration (`/auth/login`, `/auth/me`).
- Role-aware screens for `super_admin` and `branch_admin`.
- Network counts and city/branch management for head office.
- Branch admin management, branch editing and activation/deactivation.
- Branch workspace for students, rooms/beds, allocations/checkouts, services, visitors/checkouts, leave decisions, attendance IN/OUT, and dashboard counts.
- Paginated list views where supported by the API.

Operational records are requested through `/branches/{branch_id}/...`. A branch administrator should see only their own branch's records; the network view supplies counts for the rest of the network, not other branches' resident-level data.

## 4. ERD and manager explanation

- Open [`docs/ERD_AND_RELATION_MAPPING.md`](docs/ERD_AND_RELATION_MAPPING.md) for the written summary.
- Open [`docs/hostel_erd.png`](docs/hostel_erd.png) for the visual ERD.
- [`docs/Hostel_API_ERD_and_Relation_Mapping.docx`](docs/Hostel_API_ERD_and_Relation_Mapping.docx) is the manager-ready handout.

The central model is `cities → branches → branch-owned operational records`. Composite foreign keys ensure that allocations, visitors, leaves and attendance cannot link a resident to records from another branch.

## 5. Verification notes

The updated JSX passed TypeScript's JSX parse/transpile checks. A full Vite build and live API test could not be completed in this workspace because the uploaded archive's `node_modules` contained platform-specific Windows native binaries and package installation was not available here. Run `npm install` and `npm run build` in your local development environment to complete the build check; start Flask/MySQL and test login and CRUD flows against your database.

## Security note

`superadmin` / `admin123` is an intentionally simple local/demo credential. Do not expose this app publicly with the default password. Before deployment, disable or replace automatic default-account seeding, set a strong unique Super Admin password, and remove/update the frontend's visible default-credential hint and prefilled fields. Changing bootstrap values in `.env` does not reset an account that already exists. Use a strong `SECRET_KEY`, and never commit `.env`. The uploaded source archive contained a real database configuration file; it has not been copied into this cleaned bundle.
