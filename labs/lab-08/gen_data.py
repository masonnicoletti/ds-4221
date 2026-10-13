"""Lab 8: unpack the rides dataset. Run once:  python3 gen_data.py

The data is real. It is 60,000 New York City yellow-taxi trips from 2024:
5,000 sampled at random (seed 6042) from each month's public TLC trip file,
which holds about 3 million trips a month. Before sampling, each month was
cleaned with these rules, and you should know them because they shape every
number you compute:

    passengers between 1 and 6         (drops 6% of raw rows: nulls and zeros)
    distance between 0.1 and 100 mi    (drops zero-distance and GPS-glitch trips)
    fare between $1 and $500           (drops refunds, negatives, and outliers)
    tip between $0 and $200
    payment type card or cash only     (drops disputes, no-charge, unknown)
    duration between 1 and 180 minutes

One quirk survives cleaning on purpose: cash tips are all zero, because the
TLC only records tips paid by card. Q3 and Q5 will show you that.

Creates:
    data/rides.csv                 60,000 rows, 12 columns
    data/rides.parquet             the same rows, columnar
    data/rides_by_month/month=N/   the same rows, hive-partitioned by month
    data/zones.csv                 the TLC taxi-zone lookup: 265 zones -> borough
    data/rides.jsonl               the same rides as nested JSON (for the JSON exercise)

Schema of rides:
    ride_id INT · month INT · day INT · passengers INT · distance DOUBLE (miles)
    fare DOUBLE · tip DOUBLE · payment TEXT ('card' | 'cash')
    pickup_zone INT · dropoff_zone INT (join to zones.LocationID)
    hour INT (pickup hour, 0-23) · duration_min DOUBLE
"""

import gzip
import os
import shutil

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    os.makedirs("data", exist_ok=True)
    with gzip.open(os.path.join(HERE, "rides_2024_sample.csv.gz"), "rt") as src, \
            open("data/rides.csv", "w") as dst:
        shutil.copyfileobj(src, dst)
    shutil.copy(os.path.join(HERE, "taxi_zone_lookup.csv"), "data/zones.csv")

    con = duckdb.connect()
    con.execute("CREATE TABLE rides AS SELECT * FROM 'data/rides.csv'")
    con.execute("COPY rides TO 'data/rides.parquet' (FORMAT parquet)")
    con.execute("""
        COPY rides TO 'data/rides_by_month'
        (FORMAT parquet, PARTITION_BY (month), OVERWRITE_OR_IGNORE)
    """)
    con.execute("""
        COPY (SELECT ride_id,
                     {'zone': pickup_zone, 'month': month, 'day': day, 'hour': hour} AS pickup,
                     {'zone': dropoff_zone, 'minutes': duration_min} AS dropoff,
                     {'type': payment, 'fare': fare, 'tip': tip} AS payment,
                     passengers, distance
              FROM rides ORDER BY ride_id)
        TO 'data/rides.jsonl' (FORMAT json)
    """)
    n = con.execute("SELECT count(*) FROM rides").fetchone()[0]
    print(f"wrote data/rides.csv, data/rides.parquet, data/rides_by_month/ (12 partitions), "
          f"data/zones.csv, data/rides.jsonl: {n:,} real 2024 NYC taxi rides")


if __name__ == "__main__":
    main()
