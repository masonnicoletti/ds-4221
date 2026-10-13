"""Lab 8: run your investigation query against saved test predictions.

Run gen_data.py and pytorch_fares.py first, then edit investigation.sql and run:
    python explore_predictions.py
This opens DuckDB locally; it does not retrain either model.
"""

import argparse
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent


def load_tables(con, data, predictions):
    required = [data / "rides.parquet", data / "zones.csv", predictions]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}. Run gen_data.py, then pytorch_fares.py first.")
    con.execute("CREATE TABLE rides AS SELECT * FROM read_parquet(?)", [str(required[0])])
    con.execute("CREATE TABLE zones AS SELECT * FROM read_csv_auto(?)", [str(required[1])])
    con.execute("CREATE TABLE predictions AS SELECT * FROM read_csv_auto(?)", [str(predictions)])


def run_query(con, sql, output):
    statements = con.extract_statements(sql)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise ValueError("Write one SELECT or WITH ... SELECT statement in investigation.sql.")
    result = con.sql(sql)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.write_csv(str(output), header=True)
    # Display the saved result, so even a nondeterministic query is evaluated once.
    con.read_csv(str(output)).show(max_rows=20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, default=HERE / "investigation.sql")
    parser.add_argument("--data", type=Path, default=HERE / "data")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    predictions = args.predictions or args.data / "pytorch-results/predictions.csv"
    output = args.output or args.data / "pytorch-results/query-results.csv"
    try:
        sql = args.query.read_text()
        with duckdb.connect() as con:
            load_tables(con, args.data, predictions)
            run_query(con, sql, output)
    except (OSError, ValueError, duckdb.Error) as error:
        parser.exit(1, f"{error}\n")
    print(f"Saved query results to {output}")


if __name__ == "__main__":
    main()
