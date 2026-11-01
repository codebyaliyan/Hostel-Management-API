-- Upgrade an EXISTING hostel_db (version 1, one hostel) to version 2 (cities + branches).
-- Your data is kept: every existing row is placed in ONE default branch.
--
-- BEFORE YOU RUN:
--   1. Back up:   mysqldump -u root -p hostel_db > hostel_backup.sql
--      (MySQL cannot undo ALTER TABLE. If something fails halfway, restore the backup.)
--   2. Edit the 3 SET lines below to the real city / branch your data belongs to.
--   3. Run ONCE:  mysql -u root -p < migrate_to_branches.sql
--   4. Then:      python create_super_admin.py
--
-- NOTE: the old single-column foreign keys (e.g. allocations.student_id -> students.id)
-- are left in place. They are now redundant next to the new composite ones, but harmless.
-- (Only a fresh install with schema.sql gets the cleaner layout without them.)

USE hostel_db;
SET SQL_SAFE_UPDATES = 0;

-- >>> EDIT THESE THREE LINES <<<
SET @city_name   = 'My City';
SET @branch_name = 'Main Branch';
SET @branch_code = 'MAIN';

-- 1. New tables
CREATE TABLE cities (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    name      VARCHAR(100) NOT NULL,
    province  VARCHAR(100) NOT NULL DEFAULT '',
    country   VARCHAR(100) NOT NULL DEFAULT '',
    UNIQUE KEY uq_cities (name, province, country)
);

CREATE TABLE branches (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    city_id    INT          NOT NULL,
    name       VARCHAR(100) NOT NULL,
    code       VARCHAR(20)  NOT NULL UNIQUE,
    address    VARCHAR(255),
    contact    VARCHAR(20),
    is_active  TINYINT(1)   NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_branch_name_in_city (city_id, name),
    CONSTRAINT fk_branches_city FOREIGN KEY (city_id) REFERENCES cities(id)
);

CREATE TABLE users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    branch_id      INT          NULL,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    full_name      VARCHAR(100),
    role           ENUM('super_admin','branch_admin') NOT NULL,
    is_active      TINYINT(1)   NOT NULL DEFAULT 1,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_branch FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- 2. The default branch that receives all existing data
INSERT INTO cities (name) VALUES (@city_name);
SET @city_id = LAST_INSERT_ID();

INSERT INTO branches (city_id, name, code) VALUES (@city_id, @branch_name, @branch_code);
SET @branch_id = LAST_INSERT_ID();

-- 3. students
ALTER TABLE students ADD COLUMN branch_id INT NULL AFTER id;
UPDATE students SET branch_id = @branch_id;
ALTER TABLE students
    MODIFY branch_id INT NOT NULL,
    ADD UNIQUE KEY uq_students_id_branch (id, branch_id),
    ADD KEY idx_students_branch (branch_id),
    ADD CONSTRAINT fk_students_branch FOREIGN KEY (branch_id) REFERENCES branches(id);

-- 4. rooms  (room_number is now unique per branch, not globally)
ALTER TABLE rooms ADD COLUMN branch_id INT NULL AFTER id;
UPDATE rooms SET branch_id = @branch_id;
ALTER TABLE rooms
    MODIFY branch_id INT NOT NULL,
    DROP INDEX room_number,
    ADD UNIQUE KEY uq_rooms_branch_number (branch_id, room_number),
    ADD UNIQUE KEY uq_rooms_id_branch (id, branch_id),
    ADD CONSTRAINT fk_rooms_branch FOREIGN KEY (branch_id) REFERENCES branches(id);

-- 5. beds
ALTER TABLE beds ADD COLUMN branch_id INT NULL AFTER id;
UPDATE beds SET branch_id = @branch_id;
ALTER TABLE beds
    MODIFY branch_id INT NOT NULL,
    ADD UNIQUE KEY uq_beds_id_branch (id, branch_id),
    ADD KEY idx_beds_branch_status (branch_id, status),
    ADD CONSTRAINT fk_beds_room FOREIGN KEY (room_id, branch_id)
        REFERENCES rooms(id, branch_id);

-- 6. allocations
ALTER TABLE allocations ADD COLUMN branch_id INT NULL AFTER id;
UPDATE allocations SET branch_id = @branch_id;
ALTER TABLE allocations
    MODIFY branch_id INT NOT NULL,
    ADD KEY idx_alloc_branch_status (branch_id, status),
    ADD KEY idx_alloc_student_status (student_id, status),
    ADD CONSTRAINT fk_alloc_student FOREIGN KEY (student_id, branch_id)
        REFERENCES students(id, branch_id),
    ADD CONSTRAINT fk_alloc_room FOREIGN KEY (room_id, branch_id)
        REFERENCES rooms(id, branch_id),
    ADD CONSTRAINT fk_alloc_bed FOREIGN KEY (bed_id, branch_id)
        REFERENCES beds(id, branch_id);

-- 7. services
ALTER TABLE services ADD COLUMN branch_id INT NULL AFTER id;
UPDATE services SET branch_id = @branch_id;
ALTER TABLE services
    MODIFY branch_id INT NOT NULL,
    ADD KEY idx_services_branch (branch_id),
    ADD CONSTRAINT fk_services_branch FOREIGN KEY (branch_id) REFERENCES branches(id);

-- 8. visitors
ALTER TABLE visitors ADD COLUMN branch_id INT NULL AFTER id;
UPDATE visitors SET branch_id = @branch_id;
ALTER TABLE visitors
    MODIFY branch_id INT NOT NULL,
    ADD KEY idx_visitors_branch_status (branch_id, status),
    ADD CONSTRAINT fk_visitors_student FOREIGN KEY (student_id, branch_id)
        REFERENCES students(id, branch_id);

-- 9. leaves
ALTER TABLE leaves ADD COLUMN branch_id INT NULL AFTER id;
UPDATE leaves SET branch_id = @branch_id;
ALTER TABLE leaves
    MODIFY branch_id INT NOT NULL,
    ADD KEY idx_leaves_branch_status (branch_id, status),
    ADD CONSTRAINT fk_leaves_student FOREIGN KEY (student_id, branch_id)
        REFERENCES students(id, branch_id);

-- 10. attendance
ALTER TABLE attendance ADD COLUMN branch_id INT NULL AFTER id;
UPDATE attendance SET branch_id = @branch_id;
ALTER TABLE attendance
    MODIFY branch_id INT NOT NULL,
    ADD KEY idx_attendance_branch (branch_id),
    ADD KEY idx_attendance_student_open (student_id, in_time),
    ADD CONSTRAINT fk_attendance_student FOREIGN KEY (student_id, branch_id)
        REFERENCES students(id, branch_id);

-- 11. Check: every number should equal the row count of that table
SELECT 'students'    AS tbl, COUNT(*) AS rows_in_default_branch FROM students    WHERE branch_id = @branch_id
UNION ALL SELECT 'rooms',       COUNT(*) FROM rooms       WHERE branch_id = @branch_id
UNION ALL SELECT 'beds',        COUNT(*) FROM beds        WHERE branch_id = @branch_id
UNION ALL SELECT 'allocations', COUNT(*) FROM allocations WHERE branch_id = @branch_id
UNION ALL SELECT 'services',    COUNT(*) FROM services    WHERE branch_id = @branch_id
UNION ALL SELECT 'visitors',    COUNT(*) FROM visitors    WHERE branch_id = @branch_id
UNION ALL SELECT 'leaves',      COUNT(*) FROM leaves      WHERE branch_id = @branch_id
UNION ALL SELECT 'attendance',  COUNT(*) FROM attendance  WHERE branch_id = @branch_id;