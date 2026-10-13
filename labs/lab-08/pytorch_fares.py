"""Lab 8 core: DuckDB prepares batches; PyTorch trains; SQL calls the model.

Run gen_data.py first, then: python3 pytorch_fares.py
Uses the existing TLC sample, a CPU, and no network service.
See ../duckdb.html#pytorch for the guided exercise and source links.
"""

import argparse
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow as pa
import torch
from torch import nn


def prepare(con, parquet):
    # Parameter binding keeps the local filename separate from SQL syntax.
    con.execute("CREATE TABLE rides AS SELECT * FROM read_parquet(?)", [str(parquet)])
    con.execute("""
        CREATE VIEW features AS
        SELECT ride_id, month, distance::DOUBLE AS distance, fare::DOUBLE AS fare
        FROM rides
        WHERE distance > 0 AND fare >= 0
          AND isfinite(distance) AND isfinite(fare)
    """)
    counts = con.execute("""
        SELECT count(*) FILTER (WHERE month <= 10),
               count(*) FILTER (WHERE month >= 11) FROM features
    """).fetchone()
    if min(counts) < 2:
        raise ValueError("Need January–October training rides and November–December test rides.")
    # Learn scaling and the straight-line baseline only from training rows.
    stats = con.execute("""
        SELECT avg(distance), stddev_pop(distance), avg(fare), stddev_pop(fare)
        FROM features WHERE month <= 10
    """).fetchone()
    if stats[1] == 0 or stats[3] == 0:
        raise ValueError("Training distances and fares must vary.")
    con.execute("""
        CREATE TABLE linear_model AS
        SELECT regr_intercept(fare, distance) AS intercept,
               regr_slope(fare, distance) AS slope
        FROM features WHERE month <= 10
    """)
    return counts, stats


def fit(con, stats, epochs, batch_size):
    x_mean, x_std, y_mean, y_std = stats
    torch.manual_seed(6042)
    torch.set_num_threads(1)
    # One input, 16 hidden units, one output. ReLU lets the fitted curve bend.
    model = nn.Sequential(nn.Linear(1, 16), nn.ReLU(), nn.Linear(16, 1))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()
    history = []
    model.train()
    for epoch in range(epochs):
        reader = con.execute("""
            SELECT distance, fare FROM features
            WHERE month <= 10 ORDER BY hash(ride_id)
        """).to_arrow_reader(batch_size=batch_size)
        squared_error, n = 0.0, 0
        for batch in reader:
            # Conversion allocates tensors. Arrow is the batch handoff format.
            x = torch.tensor(batch.column("distance").to_numpy(), dtype=torch.float32).reshape(-1, 1)
            y = torch.tensor(batch.column("fare").to_numpy(), dtype=torch.float32).reshape(-1, 1)
            prediction = model((x - x_mean) / x_std)
            loss = loss_fn(prediction, (y - y_mean) / y_std)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            squared_error += loss.item() * len(x) * y_std ** 2
            n += len(x)
        history.append((squared_error / n) ** 0.5)
        if epoch == 0 or (epoch + 1) % 10 == 0 or epoch + 1 == epochs:
            print(f"Epoch {epoch + 1:2}: training-batch RMSE ${history[-1]:.2f}")
    model.eval()
    return model, history


def register_predictor(con, model, stats):
    x_mean, x_std, y_mean, y_std = stats

    def predict_fare(distances):
        x = torch.tensor(distances.to_numpy(), dtype=torch.float32).reshape(-1, 1)
        with torch.inference_mode():
            fares = model((x - x_mean) / x_std) * y_std + y_mean
        return pa.array(fares.flatten().numpy().astype(np.float64))

    # SQL can call this function in THIS Python connection. It invokes PyTorch.
    con.create_function("predict_fare_nn", predict_fare, ["DOUBLE"], "DOUBLE", type="arrow")


def evaluate(con):
    # Materialize predictions once so later SQL can compare and group the errors.
    con.execute("""
        CREATE TABLE predictions AS
        SELECT ride_id, month, distance, fare,
               m.intercept + m.slope * distance AS linear_fare,
               predict_fare_nn(distance) AS neural_fare
        FROM features CROSS JOIN linear_model m
        WHERE month >= 11
    """)
    metrics = con.execute("""
        SELECT 'Straight line' AS model, count(*) AS test_rides,
               avg(abs(fare - linear_fare)) AS mae,
               sqrt(avg(pow(fare - linear_fare, 2))) AS rmse
        FROM predictions
        UNION ALL
        SELECT 'Neural network', count(*), avg(abs(fare - neural_fare)),
               sqrt(avg(pow(fare - neural_fare, 2)))
        FROM predictions
    """).fetchall()
    groups = con.execute("""
        SELECT CASE WHEN distance < 2 THEN '1. Under 2 miles'
                    WHEN distance < 5 THEN '2. 2 to under 5'
                    WHEN distance < 10 THEN '3. 5 to under 10'
                    ELSE '4. 10 miles or more' END AS distance_group,
               count(*) AS test_rides,
               avg(abs(fare - linear_fare)) AS linear_mae,
               avg(abs(fare - neural_fare)) AS neural_mae
        FROM predictions GROUP BY distance_group ORDER BY distance_group
    """).fetchall()
    return metrics, groups


def plot_results(con, history, groups, destination):
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 1, figsize=(9, 12), layout="constrained")
    axes[0].plot(range(1, len(history) + 1), history, color="#30785b")
    axes[0].set(title="Learning from January–October", xlabel="Pass through training rides (epoch)",
                ylabel="Training-batch RMSE ($)")
    # Every test ride contributes to each error metric. Only the scatter is sampled.
    sample = np.array(con.execute("""
        SELECT fare, neural_fare FROM predictions ORDER BY hash(ride_id) LIMIT 600
    """).fetchall())
    axes[1].scatter(sample[:, 0], sample[:, 1], s=9, alpha=0.35, color="#356885")
    limit = max(1, float(sample.max()))
    axes[1].plot([0, limit], [0, limit], color="#61716a", linestyle="--", label="Perfect prediction")
    axes[1].set(title="Neural predictions on later rides", xlabel="Recorded fare ($)", ylabel="Predicted fare ($)")
    axes[1].legend(fontsize=9)
    x = np.arange(len(groups))
    axes[2].bar(x - 0.18, [g[2] for g in groups], width=0.36, color="#c06335", label="Straight line")
    axes[2].bar(x + 0.18, [g[3] for g in groups], width=0.36, color="#30785b", label="Neural network")
    axes[2].set_xticks(x, [g[0].split('. ', 1)[1].replace(' miles', '') + f"\n(n={g[1]:,})" for g in groups], fontsize=9)
    axes[2].set(title="Where does each model miss?", xlabel="Distance in miles · all test rides", ylabel="Mean absolute error ($)")
    axes[2].legend(fontsize=9)
    fig.suptitle("Same input: distance. Same test: November–December rides.", fontsize=15)
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).parent / "data/rides.parquet")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data/pytorch-results")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=1024)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        parser.error("epochs and batch-size must be positive")
    if not args.data.exists():
        parser.error("Run gen_data.py in the starter folder first, or provide --data rides.parquet")
    args.output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        counts, stats = prepare(con, args.data)
        print(f"Train on {counts[0]:,} January–October rides; reserve {counts[1]:,} November–December rides.")
        model, history = fit(con, stats, args.epochs, args.batch_size)
        register_predictor(con, model, stats)
        metrics, groups = evaluate(con)
        for name, n, mae, rmse in metrics:
            print(f"{name}: {n:,} test rides, MAE ${mae:.2f}, RMSE ${rmse:.2f}")
        print("\nSQL groups the errors by trip distance:")
        for label, n, linear, neural in groups:
            print(f"{label:22} n={n:5,}  line MAE ${linear:.2f}  network MAE ${neural:.2f}")
        print("\nA new 3.5-mile ride, without a known fare:")
        con.sql("SELECT 3.5 AS distance, round(predict_fare_nn(3.5::DOUBLE), 2) AS predicted_fare").show()
        con.execute("COPY predictions TO ? (HEADER, DELIMITER ',')", [str(args.output / "predictions.csv")])
        plot_results(con, history, groups, args.output / "fare-models.png")
        torch.save({"state_dict": model.state_dict(), "scaling": stats}, args.output / "fare-model.pt")
    print(f"\nOpen {args.output / 'fare-models.png'}")
    print("Predictions and model weights are saved beside the chart. Results are not a promise of accuracy.")


if __name__ == "__main__":
    main()
