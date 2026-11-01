-- Hostel Management System - MySQL schema, version 3.1 (ERD v3.1)
-- Unified users, role hierarchy (super admin > city admin > branch admin > student > visitor),
-- soft delete on every table, derived values instead of stored copies.
--
-- REQUIRES MySQL 8.0.13+  (generated columns, views, triggers, CTE)
--
-- FRESH INSTALL:   mysql -u root -p < schema.sql
-- HAVE v2 DATA?    Run this file first, then migrate_v2_to_v3.sql (it COPIES your data;
--                  your old `hostel_db` database is never modified).
--
-- The database is called  hostel_db_v3  so it can live next to your old v2 database.
-- Put  DB_NAME=hostel_db_v3  in .env.
--
-- READING GUIDE
--   Every table ends with the same 4 audit columns:
--        created_at, updated_at, deleted_at, deleted_by
--   A row is LIVE when deleted_at IS NULL.  "Delete" = set deleted_at / deleted_by.
--
--   is_live  (generated column) = 1 for live rows, NULL for deleted rows.
--   A UNIQUE key that ends with is_live is unique among LIVE rows only, so a
--   soft-deleted room/branch/username can be created again (MySQL allows many NULLs
--   inside a UNIQUE key).
--
--   Derived values (no stored copies that could disagree):
--        bed is occupied      <=> it has a row in active_allocations
--        visit is open        <=> visits.check_out IS NULL
--        student is outside   <=> attendance.in_time IS NULL

CREATE DATABASE IF NOT EXISTS hostel_db_v3
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE hostel_db_v3;

-- 1. ROLES  (self-referencing hierarchy)

CREATE TABLE roles (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    parent_role_id  INT NULL,
    code            VARCHAR(30) NOT NULL UNIQUE,
    name            VARCHAR(50) NOT NULL,
    level           TINYINT     NOT NULL,                                 -- lower = more authority
    scope           ENUM('global','city','branch') NOT NULL DEFAULT 'branch',
    can_login       TINYINT(1)  NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP NULL,
    deleted_by      INT NULL,
    CONSTRAINT fk_roles_parent FOREIGN KEY (parent_role_id) REFERENCES roles(id)
);

INSERT INTO roles (id, parent_role_id, code, name, level, scope, can_login) VALUES
    (1, NULL, 'super_admin',  'Super Admin',  0, 'global', 1),
    (2, 1,    'city_admin',   'City Admin',   1, 'city',   1),
    (3, 2,    'branch_admin', 'Branch Admin', 2, 'branch', 1),
    (4, 3,    'student',      'Student',      3, 'branch', 0),
    (5, 4,    'visitor',      'Visitor',      4, 'branch', 0);

-- 2. ORGANISATION: cities, branches

CREATE TABLE cities (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    province    VARCHAR(100) NOT NULL DEFAULT '',
    country     VARCHAR(100) NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMP NULL,
    deleted_by  INT NULL,
    is_live     TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL)) STORED,
    UNIQUE KEY uq_cities (name, province, country, is_live)
);

CREATE TABLE branches (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    city_id     INT          NOT NULL,
    name        VARCHAR(100) NOT NULL,
    code        VARCHAR(20)  NOT NULL,                  -- short code, e.g. ISB-F10 (always capitals)
    address     VARCHAR(255) NULL,
    contact     VARCHAR(20)  NULL,
    is_active   TINYINT(1)   NOT NULL DEFAULT 1,        -- 0 = temporarily closed (reversible)
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMP NULL,
    deleted_by  INT NULL,
    is_live     TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL)) STORED,
    UNIQUE KEY uq_branches_code (code, is_live),
    UNIQUE KEY uq_branches_name_in_city (city_id, name, is_live),
    KEY ix_branches_city (city_id),
    CONSTRAINT fk_branches_city FOREIGN KEY (city_id) REFERENCES cities(id)
);

-- 3. USERS  (super admins, city admins, branch admins, students, visitors)

CREATE TABLE users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    role_id        INT          NOT NULL,
    city_id        INT          NULL,                   -- ONLY for city_admin
    branch_id      INT          NULL,                   -- branch_admin, student, visitor
    username       VARCHAR(50)  NULL,                   -- NULL for people who never log in
    password_hash  VARCHAR(255) NULL,
    first_name     VARCHAR(100) NOT NULL,
    last_name      VARCHAR(100) NULL,
    gender         ENUM('Male','Female','Other') NULL,
    dob            DATE         NULL,
    contact        VARCHAR(20)  NULL,
    email          VARCHAR(100) NULL,
    address        VARCHAR(255) NULL,
    is_active      TINYINT(1)   NOT NULL DEFAULT 1,     -- 0 = login suspended (reversible)
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at     TIMESTAMP NULL,
    deleted_by     INT NULL,
    is_live        TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL)) STORED,
    UNIQUE KEY uq_users_username (username, is_live),
    KEY ix_users_role   (role_id),
    KEY ix_users_city   (city_id),
    KEY ix_users_branch (branch_id),
    CONSTRAINT fk_users_role   FOREIGN KEY (role_id)   REFERENCES roles(id),
    CONSTRAINT fk_users_city   FOREIGN KEY (city_id)   REFERENCES cities(id),
    CONSTRAINT fk_users_branch FOREIGN KEY (branch_id) REFERENCES branches(id),
    CONSTRAINT fk_users_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

-- deleted_by of the tables created before `users` can only be linked now
ALTER TABLE roles    ADD CONSTRAINT fk_roles_deleted_by    FOREIGN KEY (deleted_by) REFERENCES users(id);
ALTER TABLE cities   ADD CONSTRAINT fk_cities_deleted_by   FOREIGN KEY (deleted_by) REFERENCES users(id);
ALTER TABLE branches ADD CONSTRAINT fk_branches_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id);

-- 1 : 1 with users - optional personal details (any role may have them)
CREATE TABLE user_profiles (
    user_id            INT PRIMARY KEY,
    father_name        VARCHAR(100) NULL,
    mother_name        VARCHAR(100) NULL,
    vehicle_number     VARCHAR(20)  NULL,
    college_workplace  VARCHAR(150) NULL,
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at         TIMESTAMP NULL,
    deleted_by         INT NULL,
    CONSTRAINT fk_profiles_user       FOREIGN KEY (user_id)    REFERENCES users(id),
    CONSTRAINT fk_profiles_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

-- 4. ACCOMMODATION: rooms, beds, allocations

CREATE TABLE rooms (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    branch_id    INT         NOT NULL,
    room_number  VARCHAR(20) NOT NULL,
    floor        INT         NOT NULL,
    capacity     INT         NOT NULL,
    gender       ENUM('Male','Female','Other') NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at   TIMESTAMP NULL,
    deleted_by   INT NULL,
    is_live      TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL)) STORED,
    UNIQUE KEY uq_rooms_branch_number (branch_id, room_number, is_live),
    CONSTRAINT fk_rooms_branch     FOREIGN KEY (branch_id)  REFERENCES branches(id),
    CONSTRAINT fk_rooms_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

-- a bed reaches its branch through its room (no branch_id here)
CREATE TABLE beds (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    room_id     INT         NOT NULL,
    bed_name    VARCHAR(20) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMP NULL,
    deleted_by  INT NULL,
    is_live     TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL)) STORED,
    UNIQUE KEY uq_beds_room_name (room_id, bed_name, is_live),
    CONSTRAINT fk_beds_room       FOREIGN KEY (room_id)    REFERENCES rooms(id),
    CONSTRAINT fk_beds_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

-- no status column and no room_id: the room is bed -> room, "active" = checkout_date IS NULL
CREATE TABLE allocations (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT  NOT NULL,                  -- must be a student (trigger)
    bed_id          INT  NOT NULL,
    allocated_date  DATE NOT NULL,
    checkout_date   DATE NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP NULL,
    deleted_by      INT NULL,
    -- "one active allocation per bed / per student", enforced by the database itself
    active_bed_key  INT GENERATED ALWAYS AS
        (IF(checkout_date IS NULL AND deleted_at IS NULL, bed_id,  NULL)) STORED,
    active_user_key INT GENERATED ALWAYS AS
        (IF(checkout_date IS NULL AND deleted_at IS NULL, user_id, NULL)) STORED,
    UNIQUE KEY uq_alloc_active_bed  (active_bed_key),
    UNIQUE KEY uq_alloc_active_user (active_user_key),
    KEY ix_alloc_user (user_id),
    KEY ix_alloc_bed  (bed_id),
    CONSTRAINT fk_alloc_user       FOREIGN KEY (user_id)    REFERENCES users(id),
    CONSTRAINT fk_alloc_bed        FOREIGN KEY (bed_id)     REFERENCES beds(id),
    CONSTRAINT fk_alloc_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

-- 5. SERVICES: one catalog + junction  (branches <-> services is many-to-many)

CREATE TABLE services (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    description  VARCHAR(255) NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at   TIMESTAMP NULL,
    deleted_by   INT NULL,
    is_live      TINYINT GENERATED ALWAYS AS (IF(deleted_at IS NULL, 1, NULL)) STORED,
    UNIQUE KEY uq_services_name (name, is_live),
    CONSTRAINT fk_services_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

CREATE TABLE branch_services (
    branch_id   INT NOT NULL,
    service_id  INT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMP NULL,
    deleted_by  INT NULL,
    PRIMARY KEY (branch_id, service_id),               -- re-adding a removed service revives this row
    KEY ix_branch_services_service (service_id),
    CONSTRAINT fk_bs_branch     FOREIGN KEY (branch_id)  REFERENCES branches(id),
    CONSTRAINT fk_bs_service    FOREIGN KEY (service_id) REFERENCES services(id),
    CONSTRAINT fk_bs_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

-- 6. DAILY ACTIVITY: visits, leaves, attendance

-- a visitor is a users row (role visitor); a visit links visitor and host student
CREATE TABLE visits (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    visitor_id  INT          NOT NULL,                 -- must be a visitor (trigger)
    student_id  INT          NOT NULL,                 -- host, must be a student (trigger)
    reason      VARCHAR(255) NOT NULL,
    check_in    DATETIME     NOT NULL,
    check_out   DATETIME     NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMP NULL,
    deleted_by  INT NULL,
    KEY ix_visits_visitor (visitor_id, check_out),
    KEY ix_visits_student (student_id),
    CONSTRAINT fk_visits_visitor    FOREIGN KEY (visitor_id) REFERENCES users(id),
    CONSTRAINT fk_visits_student    FOREIGN KEY (student_id) REFERENCES users(id),
    CONSTRAINT fk_visits_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

CREATE TABLE leaves (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    user_id           INT          NOT NULL,           -- must be a student (trigger)
    reason            VARCHAR(255) NOT NULL,
    application_date  DATE         NOT NULL,
    return_date       DATE         NOT NULL,
    status            ENUM('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
    decided_by        INT          NULL,               -- admin who approved / rejected
    decided_at        DATETIME     NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at        TIMESTAMP NULL,
    deleted_by        INT NULL,
    KEY ix_leaves_user (user_id, status),
    CONSTRAINT fk_leaves_user       FOREIGN KEY (user_id)    REFERENCES users(id),
    CONSTRAINT fk_leaves_decided_by FOREIGN KEY (decided_by) REFERENCES users(id),
    CONSTRAINT fk_leaves_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

CREATE TABLE attendance (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT          NOT NULL,                 -- must be a student (trigger)
    purpose     VARCHAR(255) NOT NULL,
    out_time    DATETIME     NOT NULL,
    in_time     DATETIME     NULL,                     -- NULL while the student is outside
    remarks     VARCHAR(255) NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  TIMESTAMP NULL,
    deleted_by  INT NULL,
    -- "one open OUT record at a time"
    open_user_key INT GENERATED ALWAYS AS
        (IF(in_time IS NULL AND deleted_at IS NULL, user_id, NULL)) STORED,
    UNIQUE KEY uq_attendance_open (open_user_key),
    KEY ix_attendance_user (user_id),
    CONSTRAINT fk_attendance_user       FOREIGN KEY (user_id)    REFERENCES users(id),
    CONSTRAINT fk_attendance_deleted_by FOREIGN KEY (deleted_by) REFERENCES users(id)
);

-- 7. VIEWS (keep the SQL in the API short)

-- every live user with the city and branch they effectively belong to
CREATE VIEW v_user_scope AS
SELECT u.id AS user_id, u.role_id, r.code AS role_code, r.level, r.scope,
       u.branch_id,
       COALESCE(b.city_id, u.city_id) AS city_id
FROM users u
JOIN roles r         ON r.id = u.role_id
LEFT JOIN branches b ON b.id = u.branch_id
WHERE u.deleted_at IS NULL;

CREATE VIEW active_allocations AS
SELECT id, user_id, bed_id, allocated_date
FROM allocations
WHERE checkout_date IS NULL AND deleted_at IS NULL;

-- live beds with their branch and a DERIVED status
CREATE VIEW v_beds AS
SELECT b.id, b.room_id, r.branch_id, b.bed_name,
       IF(aa.id IS NULL, 'Available', 'Occupied') AS status
FROM beds b
JOIN rooms r ON r.id = b.room_id AND r.deleted_at IS NULL
LEFT JOIN active_allocations aa ON aa.bed_id = b.id
WHERE b.deleted_at IS NULL;

-- 8. RULES A FOREIGN KEY CANNOT EXPRESS (triggers)
-- The API checks the same things first and gives friendly errors; these are
-- the safety net if somebody inserts rows by hand or a code bug slips in.

DELIMITER $$

CREATE FUNCTION fn_user_branch(p_user_id INT) RETURNS INT
    READS SQL DATA
BEGIN
    DECLARE v_branch INT;
    SELECT branch_id INTO v_branch FROM users WHERE id = p_user_id;
    RETURN v_branch;
END$$

CREATE FUNCTION fn_bed_branch(p_bed_id INT) RETURNS INT
    READS SQL DATA
BEGIN
    DECLARE v_branch INT;
    SELECT r.branch_id INTO v_branch
    FROM beds b JOIN rooms r ON r.id = b.room_id
    WHERE b.id = p_bed_id;
    RETURN v_branch;
END$$

-- "this user must have role X"
CREATE PROCEDURE assert_user_role(IN p_user_id INT, IN p_role VARCHAR(30), IN p_label VARCHAR(40))
BEGIN
    DECLARE v_code VARCHAR(30);
    DECLARE v_msg VARCHAR(255);
    SELECT r.code INTO v_code FROM users u JOIN roles r ON r.id = u.role_id WHERE u.id = p_user_id;
    IF v_code IS NULL OR v_code <> p_role THEN
        SET v_msg = CONCAT(p_label, ' must be a user with role ', p_role);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
    END IF;
END$$

-- scope rule of roles:  global -> no city/branch,  city -> city only,  branch -> branch only
CREATE PROCEDURE check_user_scope(IN p_role_id INT, IN p_city_id INT, IN p_branch_id INT,
                                  IN p_username VARCHAR(50), IN p_password_hash VARCHAR(255))
BEGIN
    DECLARE v_scope VARCHAR(10);
    DECLARE v_login TINYINT;

    SELECT scope, can_login INTO v_scope, v_login FROM roles WHERE id = p_role_id;

    IF v_scope = 'global' AND (p_city_id IS NOT NULL OR p_branch_id IS NOT NULL) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A global role (super admin) must have no city_id and no branch_id';
    END IF;
    IF v_scope = 'city' AND (p_city_id IS NULL OR p_branch_id IS NOT NULL) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A city role (city admin) needs city_id and must have no branch_id';
    END IF;
    IF v_scope = 'branch' AND (p_branch_id IS NULL OR p_city_id IS NOT NULL) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A branch role needs branch_id and must have no city_id';
    END IF;
    IF v_login = 1 AND (p_username IS NULL OR p_password_hash IS NULL) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'This role can log in, so username and password are required';
    END IF;
END$$

CREATE TRIGGER trg_users_bi BEFORE INSERT ON users FOR EACH ROW
BEGIN
    CALL check_user_scope(NEW.role_id, NEW.city_id, NEW.branch_id, NEW.username, NEW.password_hash);
END$$

CREATE TRIGGER trg_users_bu BEFORE UPDATE ON users FOR EACH ROW
BEGIN
    CALL check_user_scope(NEW.role_id, NEW.city_id, NEW.branch_id, NEW.username, NEW.password_hash);
END$$

-- allocation: user is a student AND student and bed are in the same branch
CREATE TRIGGER trg_allocations_bi BEFORE INSERT ON allocations FOR EACH ROW
BEGIN
    CALL assert_user_role(NEW.user_id, 'student', 'allocations.user_id');
    IF fn_user_branch(NEW.user_id) IS NULL
       OR fn_bed_branch(NEW.bed_id) IS NULL
       OR fn_user_branch(NEW.user_id) <> fn_bed_branch(NEW.bed_id) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Student and bed belong to different branches';
    END IF;
END$$

-- leave: user is a student; whoever decides is an admin
CREATE PROCEDURE check_leave(IN p_user_id INT, IN p_decided_by INT)
    BEGIN
    DECLARE v_code VARCHAR(30);
    CALL assert_user_role(p_user_id, 'student', 'leaves.user_id');
    IF p_decided_by IS NOT NULL THEN
        SELECT r.code INTO v_code FROM users u JOIN roles r ON r.id = u.role_id WHERE u.id = p_decided_by;
        IF v_code IS NULL OR v_code NOT IN ('super_admin', 'city_admin', 'branch_admin') THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'leaves.decided_by must be an admin';
        END IF;
    END IF;
END$$

CREATE TRIGGER trg_leaves_bi BEFORE INSERT ON leaves FOR EACH ROW
BEGIN
    CALL check_leave(NEW.user_id, NEW.decided_by);
END$$

CREATE TRIGGER trg_leaves_bu BEFORE UPDATE ON leaves FOR EACH ROW
BEGIN
    CALL check_leave(NEW.user_id, NEW.decided_by);
END$$

CREATE TRIGGER trg_attendance_bi BEFORE INSERT ON attendance FOR EACH ROW
BEGIN
    CALL assert_user_role(NEW.user_id, 'student', 'attendance.user_id');
END$$

-- visit: visitor is a visitor, host is a student, both in the same branch
CREATE TRIGGER trg_visits_bi BEFORE INSERT ON visits FOR EACH ROW
BEGIN
    CALL assert_user_role(NEW.visitor_id, 'visitor', 'visits.visitor_id');
    CALL assert_user_role(NEW.student_id, 'student', 'visits.student_id');
    IF fn_user_branch(NEW.visitor_id) IS NULL
       OR fn_user_branch(NEW.visitor_id) <> fn_user_branch(NEW.student_id) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Visitor and host student belong to different branches';
    END IF;
END$$

DELIMITER ;