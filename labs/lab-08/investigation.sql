-- Lab 8 core investigation. Run: python explore_predictions.py
-- The runner loads predictions, rides, and zones from the saved lab files.
-- predictions: ride_id, month, distance, fare, linear_fare, neural_fare.
-- All prediction rows are reserved November-December rides.
-- Join predictions p to rides r ON p.ride_id = r.ride_id for payment,
-- pickup_zone, passengers, or hour. Join zones z ON r.pickup_zone = z.LocationID
-- for z.Borough and z.Zone. Qualify repeated column names, e.g. p.fare.
--
-- First run this overall comparison. Then REPLACE it with your own single
-- SELECT (or WITH ... SELECT) to investigate errors by a chosen group.
-- Include the number of test rides and both models' mean absolute errors.
-- Keep the model and train/test split fixed while investigating the results.

SELECT count(*) AS test_rides,
       avg(abs(fare - linear_fare)) AS linear_mae,
       avg(abs(fare - neural_fare)) AS neural_mae
FROM predictions;
