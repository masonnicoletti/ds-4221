"""Lecture 10: prepare, train, evaluate, and predict inside DuckDB.

Run with Python 3 after `python3 -m pip install duckdb`:
    python3 in_database_ml.py
    python3 in_database_ml.py --explain

Python submits SQL and displays results. DuckDB performs every calculation.
The six hand-chosen rows illustrate execution, not real-world model accuracy.
An in-memory connection makes each run independent; no files or cloud account
are needed. An on-disk DuckDB connection could retain the model table.
"""

import argparse

try:
    import duckdb
except ImportError as exc:
    raise SystemExit("Install DuckDB first: python3 -m pip install duckdb") from exc


SETUP_SQL = """
CREATE TABLE ml_rides (
    ride_id INTEGER, distance DOUBLE, fare DOUBLE, split VARCHAR
);
INSERT INTO ml_rides VALUES
    (1, 1.0,  6.0, 'train'),
    (2, 2.0,  6.0, 'train'),
    (3, 3.0,  8.0, 'train'),
    (4, 4.0, 12.0, 'train'),
    (5, 2.5,  9.0, 'test'),
    (6, 4.5, 11.0, 'test');

-- distance is miles; fare is dollars. The split was assigned before fitting.
CREATE VIEW fare_features AS
SELECT ride_id, distance, fare, split
FROM ml_rides
WHERE distance > 0 AND fare >= 0;
"""

TRAIN_SQL = """
SELECT regr_intercept(fare, distance) AS intercept,
       regr_slope(fare, distance) AS slope,
       count(*) AS training_rows
FROM fare_features
WHERE split = 'train'
"""

SCORE_SQL = """
SELECT r.ride_id, r.distance, r.fare,
       m.intercept + m.slope * r.distance AS predicted_fare
FROM fare_features AS r
CROSS JOIN fare_model AS m
WHERE r.split = 'test'
"""

EVALUATE_SQL = """
SELECT count(*) AS test_rows,
       avg(abs(fare - predicted_fare)) AS mae,
       sqrt(avg(pow(fare - predicted_fare, 2))) AS rmse
FROM held_out_predictions
"""

PREDICT_SQL = """
SELECT r.ride_id, r.distance,
       m.intercept + m.slope * r.distance AS predicted_fare
FROM (VALUES (7, 3.5)) AS r(ride_id, distance)
CROSS JOIN fare_model AS m
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explain", action="store_true",
                        help="also show DuckDB's training and scoring plans")
    args = parser.parse_args()

    with duckdb.connect(":memory:") as con:
        con.execute(SETUP_SQL)
        con.execute("CREATE TABLE fare_model AS " + TRAIN_SQL)
        con.execute("CREATE VIEW held_out_predictions AS " + SCORE_SQL)

        for title, query in [
            ("1. Feature rows (miles and dollars; split already assigned)",
             "SELECT * FROM fare_features ORDER BY ride_id"),
            ("2. Model fitted on training rows",
             "SELECT * FROM fare_model"),
            ("3. Held-out predictions (these fares were not used to fit)",
             "SELECT * FROM held_out_predictions ORDER BY ride_id"),
            ("4. Held-out error in dollars",
             EVALUATE_SQL),
            ("5. Inference for an unlabeled 3.5-mile ride",
             PREDICT_SQL),
        ]:
            print("\n" + title)
            con.sql(query).show()

        if args.explain:
            for title, query in [("Training", TRAIN_SQL), ("Scoring", SCORE_SQL)]:
                print("\n" + title + " query plan")
                for _, plan in con.execute("EXPLAIN " + query).fetchall():
                    print(plan)

    print("Synthetic demonstration only; two test rows cannot establish accuracy.")


if __name__ == "__main__":
    main()
