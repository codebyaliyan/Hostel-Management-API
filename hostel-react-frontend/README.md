# StayWise Hostel Management Frontend

A React + Vite UI aligned to the uploaded Flask/MySQL API v2. It uses Bearer-token authentication and scopes day-to-day operations to `/branches/:branch_id/...`.

## Requirements

- Node.js LTS and npm
- The Flask backend running at `http://127.0.0.1:5000`
- The MySQL schema and an initial super-admin account configured on the backend

## Run locally

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite dev server proxies `/api/*` to Flask on port 5000; no CORS configuration is needed for this local setup.

## API / role behavior

- `POST /auth/login` and `GET /auth/me` for login and session restoration.
- `super_admin`: network overview; city and branch administration; creation of branch-admin users; can open active branches.
- `branch_admin`: their assigned branch workspace and network-level counts; branch details remain scoped by the API.
- Branch pages use `/branches/{branch_id}/students`, `/rooms`, `/allocations`, `/services`, `/visitors`, `/leaves`, `/attendance`, and `/dashboard`.
- Student add/edit/delete, room creation and bed viewing, allocation and checkout, service creation, visitor logging/check-out, leave approval/rejection, and attendance IN/OUT are supported by available endpoints.
- List endpoints that support pagination use `page` and `limit`; the UI shows page controls where the API returns metadata.

## Production configuration

For a separately hosted API, set `VITE_API_BASE_URL` to the deployed API base URL when building the frontend, then configure CORS on Flask for the exact frontend origin. Do not use wildcard origins with credentials or expose debug mode in production.
