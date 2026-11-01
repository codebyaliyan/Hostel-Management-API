-- Copy your v2 data (database `hostel_db`, one `students` table ...) into the
-- v3 database `hostel_db_v3` (unified users, roles, soft delete, visits ...).
--
-- THIS FILE ONLY READS `hostel_db`. Your old database is never changed, so if anything
-- looks wrong you can drop hostel_db_v3, fix the problem and run again.
--
-- STEPS
--   1. mysqldump -u root -p hostel_db > hostel_v2_backup.sql      (backup anyway)
--   2. mysql -u root -p < schema.sql                              (creates empty hostel_db_v3)
--   3. mysql -u root -p < migrate_v2_to_v3.sql                    (this file)
--   4. .env:  DB_NAME=hostel_db_v3     then  python app.py
--
-- If your old database is not called `hostel_db`, replace `hostel_db.` below (find & replace).
-- The whole copy runs in ONE transaction: on any error mysql stops and nothing is kept.
--
-- WHAT HAPPENS TO EACH OLD TABLE
--   cities, branches   -> same rows, same ids
--   students           -> users (role student), SAME ids, + user_profiles (father, mother, vehicle ...)
--   users (admins)     -> users (super_admin / branch_admin), id = old id + @admin_off, same passwords
--   visitors           -> users (role visitor, one per old row) + visits, visit id = old visitor id
--   rooms, beds        -> same ids (beds.status is dropped: it is derived now)
--   allocations        -> same ids (room_id and status dropped: derived now)
--   services           -> one catalog row per distinct name + branch_services links
--   leaves, attendance -> same ids, student_id becomes user_id
--
-- Student ids stay the same, so ids your React app already stored for students keep working.
-- Admin ids and visitor ids change (they all share one table now); see the offsets below.

USE hostel_db_v3;

START TRANSACTION;

SET @r_super   = (SELECT id FROM roles WHERE code = 'super_admin');
SET @r_branch  = (SELECT id FROM roles WHERE code = 'branch_admin');
SET @r_student = (SELECT id FROM roles WHERE code = 'student');
SET @r_visitor = (SELECT id FROM roles WHERE code = 'visitor');

-- ids: students keep theirs, admins and visitors are shifted behind them
SET @admin_off   = (SELECT COALESCE(MAX(id), 0) FROM hostel_db.students);
SET @visitor_off = @admin_off + (SELECT COALESCE(MAX(id), 0) FROM hostel_db.users);

-- 1. organisation
INSERT INTO cities (id, name, province, country)
SELECT id, name, province, country FROM hostel_db.cities;

INSERT INTO branches (id, city_id, name, code, address, contact, is_active, created_at)
SELECT id, city_id, name, code, address, contact, is_active, created_at FROM hostel_db.branches;

-- 2. people
INSERT INTO users (id, role_id, branch_id, first_name, last_name, gender, dob,
                     contact, email, address, created_at)
                     
SELECT id, @r_student, branch_id, first_name, last_name, gender, dob,
       contact, email, address, created_at
FROM hostel_db.students;

INSERT INTO user_profiles (user_id, father_name, mother_name, vehicle_number, college_workplace)
SELECT id, father_name, mother_name, vehicle_number, college_workplace FROM hostel_db.students;

INSERT INTO users (id, role_id, branch_id, username, password_hash, first_name, last_name,
                   is_active, created_at)
SELECT u.id + @admin_off,
       IF(u.role = 'super_admin', @r_super, @r_branch),
       u.branch_id,
       u.username,
       u.password_hash,
       LEFT(COALESCE(NULLIF(TRIM(SUBSTRING_INDEX(u.full_name, ' ', 1)), ''), u.username), 100),
       LEFT(NULLIF(TRIM(SUBSTRING(u.full_name, LOCATE(' ', u.full_name))), ''), 100),
       u.is_active,
       u.created_at
FROM hostel_db.users u;

INSERT INTO users (id, role_id, branch_id, first_name, last_name, contact, address, created_at)
SELECT v.id + @visitor_off,
       @r_visitor,
       v.branch_id,
       LEFT(COALESCE(NULLIF(TRIM(SUBSTRING_INDEX(v.visitor_name, ' ', 1)), ''), 'Visitor'), 100),
       LEFT(NULLIF(TRIM(SUBSTRING(v.visitor_name, LOCATE(' ', v.visitor_name))), ''), 100),
       v.contact,
       v.address,
       v.check_in
FROM hostel_db.visitors v;

-- 3. accommodation
INSERT INTO rooms (id, branch_id, room_number, floor, capacity, gender)
SELECT id, branch_id, room_number, floor, capacity, gender FROM hostel_db.rooms;

INSERT INTO beds (id, room_id, bed_name)
SELECT id, room_id, bed_name FROM hostel_db.beds;

INSERT INTO allocations (id, user_id, bed_id, allocated_date, checkout_date)
SELECT id, student_id, bed_id, allocated_date,
       IF(status = 'Active', NULL, COALESCE(checkout_date, allocated_date))
FROM hostel_db.allocations;

-- 4. services: one catalog + junction
INSERT INTO services (name, description)
SELECT name, MAX(description) FROM hostel_db.services GROUP BY name;

INSERT INTO branch_services (branch_id, service_id)
SELECT DISTINCT os.branch_id, s.id
FROM hostel_db.services os
JOIN services s ON s.name = os.name COLLATE utf8mb4_unicode_ci;

-- 5. daily activity
INSERT INTO visits (id, visitor_id, student_id, reason, check_in, check_out)
SELECT id, id + @visitor_off, student_id, COALESCE(reason, ''), check_in, check_out
FROM hostel_db.visitors;

INSERT INTO leaves (id, user_id, reason, application_date, return_date, status)
SELECT id, student_id, reason, application_date, return_date, status FROM hostel_db.leaves;

INSERT INTO attendance (id, user_id, purpose, out_time, in_time, remarks)
SELECT id, student_id, purpose, out_time, in_time, remarks FROM hostel_db.attendance;

COMMIT;

-- CHECK: in every row `old_rows` must equal `new_rows`
SELECT 'cities' AS tbl,
       (SELECT COUNT(*) FROM hostel_db.cities)      AS old_rows,
       (SELECT COUNT(*) FROM cities)                AS new_rows
UNION ALL SELECT 'branches',
       (SELECT COUNT(*) FROM hostel_db.branches),   (SELECT COUNT(*) FROM branches)
UNION ALL SELECT 'users (students + admins + visitors)',
       (SELECT COUNT(*) FROM hostel_db.students) + (SELECT COUNT(*) FROM hostel_db.users)
                                                   + (SELECT COUNT(*) FROM hostel_db.visitors),
       (SELECT COUNT(*) FROM users)
UNION ALL SELECT 'rooms',
       (SELECT COUNT(*) FROM hostel_db.rooms),      (SELECT COUNT(*) FROM rooms)
UNION ALL SELECT 'beds',
       (SELECT COUNT(*) FROM hostel_db.beds),       (SELECT COUNT(*) FROM beds)
UNION ALL SELECT 'allocations',
       (SELECT COUNT(*) FROM hostel_db.allocations),(SELECT COUNT(*) FROM allocations)
UNION ALL SELECT 'visits',
       (SELECT COUNT(*) FROM hostel_db.visitors),   (SELECT COUNT(*) FROM visits)
UNION ALL SELECT 'leaves',
       (SELECT COUNT(*) FROM hostel_db.leaves),     (SELECT COUNT(*) FROM leaves)
UNION ALL SELECT 'attendance',
       (SELECT COUNT(*) FROM hostel_db.attendance), (SELECT COUNT(*) FROM attendance)
UNION ALL SELECT 'services (distinct names)',
       (SELECT COUNT(DISTINCT name) FROM hostel_db.services), (SELECT COUNT(*) FROM services);

-- After this, python app.py gives every branch that has no admin its default login
-- and recreates the default super admin if it is missing.