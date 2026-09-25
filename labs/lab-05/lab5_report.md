# Lab 5: Query plans and measured work

Name: Mason Nicoletti

Environment (Python version and operating system): Python 3.12.11

Commands used, student count, and timing repetitions:

## 1. Explain the supplied implementation

- Trace `SELECT name FROM students WHERE gpa > 35`: what does each of
`parse_query`, `_parse_predicate`, and `_parse_term` return?

`parse_query` returns a tuple: `('name', 'students', Predicate('gpa', '>', 35))`

`_parse_predicate` returns the predicate tuple: `Predicate('gpa', '>', 35)`

`_parse_term` returns: `gpa`, `>`, `35`

- Why is `mid2` represented as `F("mid2")`, but `'ds'` is a string literal?

F is a wrapper so that execution reads the field "mid2" from the current row.

- Why must selection happen before projection for this query?

Selection happens before projection because selection filters rows before they are passed on to be displayed.

- Which call starts reading result rows? Why does the runner use `finally`?

The planner, `plan_query` is where rows are starting to be read. The runner uses finally to ensure that the plan is closed before execution ends.

## 2. Write SQL

Complete and submit `queries.sql` (S1–S3 and J1–J3).
Paste the six statements here as well, so this report is readable on its own.

-- S1: Return every student's name.

SELECT name FROM students;

-- S2: Return the names of students with gpa > 35.

SELECT name FROM students WHERE gpa > 35;

-- S3: Return all student columns for exactly the same rows as S2.

SELECT * FROM students WHERE gpa > 35;

-- J1: Return name and dept for students with gpa > 35 in the 'ds' department.

SELECT name, dept FROM students, majors
WHERE gpa > 35 AND dept = 'ds' AND mid = mid2;

-- J2: Return the same fields and rows as J1, but put majors first in FROM.

SELECT name, dept FROM majors, students
WHERE gpa > 35 AND dept = 'ds' AND mid2 = mid;

-- J3: Use J1's table order and department, but require gpa > 38.

SELECT name, dept FROM students, majors
WHERE gpa > 38 AND dept = 'ds' AND mid = mid2;

## 3. Predict before measuring

Keep your original predictions, including any that turn out to be wrong.
For each comparison, give a count or formula and name the operator responsible.


| Comparison                                      | Predicted row visits / pairs / output cells                                                     | Reason                                                                                            |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| S1 vs S2: add a selective WHERE                 | 300/ 600 candidate pairs / the number of students that meet the predicate                       | ">" operator makes candidate pairings binary                                                      |
| S2 vs S3: change only the SELECT list           | 300/ 600 candidate pairs / the number of original rows for each student that meet the predicate | ">" operator makes candidate pairings binary                                                      |
| J1: simple vs early-filter plan                 | 300, 3 / 1800 candidate pairs / 2x cells per student that meets the predicate                   | ">" operator makes candidate pairings binary, as well as major produces 3x candidates per student |
| J1 vs J2: reverse FROM order                    | 3, 300 / 1800 candidate pairs / 2x cells per student that meets the predicate                   | ">" operator makes candidate pairings binary, as well as major produces 3x candidates per student |
| J1 vs J3: make the GPA condition more selective | 300, 3 / 1800 candidate pairs / 2x cells per student that meets the predicate                   | ">" operator makes candidate pairings binary, as well as major produces 3x candidates per student |
| J1 with 300 vs 600 students                     | 600, 3 / 3600 candidate pairs / 2x cells per student that meets the predicate                   | ">" operator makes candidate pairings binary, as well as major produces 3x candidates per student |




## 4. Record evidence

Attach `results-300.json` and `results-600.json`, or include their full contents.
Run the same six queries on both sizes. Record results for both plan modes.


| Query                                     | Students | Plan                                                             | Student row visits | Major row visits | Candidate pairs | Comparisons | Rows | Output cells | Median ms |
| ----------------------------------------- | -------- | ---------------------------------------------------------------- | ------------------ | ---------------- | --------------- | ----------- | ---- | ------------ | --------- |
| SELECT name FROM students                 | 300      | ProjectScan, TableScan                                           | 300                | 0                | 0               | 0           | 300  | 300          | 0.396     |
| "SELECT name FROM students WHERE gpa > 35 | 300      | ProjectScan['name']\n SelectScan[gpa > 35]\n TableScan(students) | 300                | 0                | 0               | 300         | 60   | 60           | 0.440     |




## 5. Explain differences from first principles

1. Did fewer returned rows imply fewer table row visits? Explain from TableScan
  and SelectScan's next() methods; distinguish visits from disk reads.
  1. No, rows visited includes the cartesian product of all rows in tables. Returned rows are only those that meet the criteria of the predicate, causing them to be filtered down in SelectScan. A visit is an iterative look at rows in a table, while disk read involves pulling a whole block of data from storage.
2. Did selecting fewer columns avoid scanning rows? Which work did it reduce?
  1. No, the same number of rows are still scanned. However, selecting fewer columns reduces the number of output cells.
3. Derive the simple and early-filter pair counts for J1. Explain why the early plan still revisits majors even though only one major passes its filter
  1. The early plan still revists majors in order to assemble candidate pairs including all possible combinations of students and majors, iterating through each row of the two tables one at a time. 
4. J1 and J2 return the same rows. Which side is restarted? Explain any changes in base-row visits even when the candidate-pair count stays the same.
  1. In J1, the majors table is restarted each time it iterates through all combinations for a student. This is different than J2, which restarts the students table each time it creates a pair including each student with one of the majors.
5. Explain J3's counts using the number of students that pass its filter.
  1. 15 total students pass J3's filter. Only GPAs above 3.8 (38) are kept, and only majors in the 'ds' department are kept.
6. Which counts doubled with 600 students? Why needn't the measured time double?
  1. Candidate pairs, predicate comparison, rows returned, and output cells all doubled with 600 students. Time didn't double because the planner efficiently moves between steps despite an increased quantity of students.
7. Compare the pair-count ratio with the timing ratio for J1. Use comparisons, source scans, and output work to explain why those ratios can differ.
   1. Ratios can differ depending on what the query is asking and how the planner orients around a query.
8. State what was timed, what was excluded, and how repeats/caching/noise limit a claim that one query is faster. If a timing difference is tiny, say so.
   1. The time to execute a query all the way until display was timed. The most significant differences in timing depend on how a query is tranferred into a plan.



## 6. One failed prediction

Quote an original prediction, the evidence that changed it, and your revised
explanation. If all predictions matched, explain the least obvious result.

I originally predicted that candidate pairs would be greater than they were. I was considering candidate pairs to be the product of all possible rows among the tables being selected from. Instead, candidate pairs applies a layer of filtering that matters based on a predicate.