# StayWise Hostel Management API — ERD & Relation Mapping

## 1. Short system overview

The updated database supports multiple cities, several hostel branches in each city, branch-level administrator accounts, and day-to-day hostel records. Users authenticate through `/auth/login` and send the returned Bearer token for protected API requests. Network endpoints return branch-level counts, while full student and operational records are accessed through `/branches/{branch_id}/...` and checked against the caller's role by the API.

## 2. Entity relationship diagram

![StayWise Hostel Management ERD](hostel_erd.png)

The schema currently contains 11 tables: `cities`, `branches`, `users`, `students`, `rooms`, `beds`, `allocations`, `services`, `visitors`, `leaves`, and `attendance`.

## 3. Relation mapping

| Parent entity | Child entity | Cardinality | Foreign-key mapping / explanation |
|---|---|---:|---|
| `cities` | `branches` | 1 : N | `branches.city_id → cities.id`. One city can contain multiple hostel branches. |
| `branches` | `users` | 1 : N (optional for head office) | `users.branch_id → branches.id`; a `super_admin` has `branch_id = NULL`, while a `branch_admin` is assigned to one branch. |
| `branches` | `students` | 1 : N | `students.branch_id → branches.id`. Each resident belongs to one branch. |
| `branches` | `rooms` | 1 : N | `rooms.branch_id → branches.id`. Room number uniqueness is enforced within a branch, not across the whole network. |
| `branches` | `services` | 1 : N | `services.branch_id → branches.id`. Each branch manages its own service list. |
| `rooms` | `beds` | 1 : N | Composite FK `beds(room_id, branch_id) → rooms(id, branch_id)`. A bed belongs to one room and cannot be attached to a room from another branch. |
| `students` | `allocations` | 1 : N over time | Composite FK `allocations(student_id, branch_id) → students(id, branch_id)`. Allocations keep both active and historical stays. |
| `rooms` | `allocations` | 1 : N over time | Composite FK `allocations(room_id, branch_id) → rooms(id, branch_id)`. The room and allocation must belong to the same branch. |
| `beds` | `allocations` | 1 : N over time | Composite FK `allocations(bed_id, branch_id) → beds(id, branch_id)`. An allocation references the selected bed; checkout releases it. |
| `students` | `visitors` | 1 : N | Composite FK `visitors(student_id, branch_id) → students(id, branch_id)`. Each visitor log is associated with a resident in the same branch. |
| `students` | `leaves` | 1 : N | Composite FK `leaves(student_id, branch_id) → students(id, branch_id)`. A resident can submit multiple leave applications. |
| `students` | `attendance` | 1 : N | Composite FK `attendance(student_id, branch_id) → students(id, branch_id)`. Each OUT/IN movement belongs to a resident in that branch. |

### Important integrity rule: branch isolation

The schema uses composite unique keys such as `(id, branch_id)` on `students`, `rooms`, and `beds`, with composite foreign keys in dependent tables. This means an allocation cannot combine a resident from Branch A with a room or bed from Branch B, even if a future application-level check is missed. The API adds a second layer by verifying the caller's branch before serving `/branches/{branch_id}/...` requests.

## 4. How API areas map to tables

| API area | Main endpoints | Main tables read / written |
|---|---|---|
| Authentication | `POST /auth/login`, `GET /auth/me` | `users`, `branches` |
| Network structure | `GET/POST /cities`, `GET/POST /branches`, `PUT /branches/{id}` | `cities`, `branches` |
| Branch administrators | `/branches/{id}/admins` | `users`, `branches` |
| Network summary | `GET /network/overview`, `GET /network/cities` | Aggregates `branches`, `rooms`, `beds`, `students` |
| Branch dashboard | `GET /branches/{id}/dashboard` | Aggregates `students`, `rooms`, `beds`, `attendance`, `leaves`, `visitors` |
| Residents | `/branches/{id}/students` | `students` |
| Rooms / beds | `/branches/{id}/rooms`, `/beds/available`, `/rooms/{id}/beds` | `rooms`, `beds` |
| Allocation lifecycle | `/branches/{id}/allocations` | `allocations`, `students`, `rooms`, `beds` |
| Services | `/branches/{id}/services` | `services` |
| Visitors | `/branches/{id}/visitors` | `visitors`, `students` |
| Leave workflow | `/branches/{id}/leaves` | `leaves`, `students` |
| Attendance / movement | `/branches/{id}/attendance` | `attendance`, `students` |

## 5. Recommended manager walkthrough

1. Explain that `cities → branches` provides the multi-location structure.
2. Show that the `users` table separates head-office (`super_admin`) accounts from branch-level (`branch_admin`) accounts.
3. Explain that operational records are scoped by `branch_id`; this is enforced in both Flask authorization checks and MySQL foreign keys.
4. Walk through a resident's lifecycle: insert into `students`, allocate a room/bed through `allocations`, track visitors/leaves/attendance against the same resident, then check out the allocation so the bed becomes available.

**Scope note:** This mapping is based on the provided `schema.sql` and Python endpoint code. It reflects the current implementation rather than proposed future tables or features.
