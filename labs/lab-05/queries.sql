-- Lab 5: write one SELECT for each request. End each statement with a semicolon.
-- Run: python3 measure_sql.py --queries queries.sql --repeat 7
-- Use students(sid, name, gpa, mid) and majors(mid2, dept).
-- GPA is stored as an integer from 20 through 39; 35 represents 3.5.

-- S1: Return every student's name.

-- S2: Return the names of students with gpa > 35.

-- S3: Return all student columns for exactly the same rows as S2.

-- J1: Return name and dept for students with gpa > 35 in the 'ds' department.
-- Join students.mid to majors.mid2; put students first in FROM.

-- J2: Return the same fields and rows as J1, but put majors first in FROM.

-- J3: Use J1's table order and department, but require gpa > 38.
