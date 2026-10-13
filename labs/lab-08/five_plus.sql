-- Run this same query on the starter's predictions and on each model trial.
-- The first row is the challenge score: MAE across ALL rides >= 5 miles.
-- The other rows help explain which distances improved or got worse.
SELECT '0. All rides >= 5 miles' AS distance_group,
       count(*) AS rides,
       avg(abs(fare - linear_fare)) AS linear_mae,
       avg(abs(fare - neural_fare)) AS neural_mae,
       avg(abs(fare - linear_fare)) - avg(abs(fare - neural_fare))
           AS improvement_over_line
FROM predictions
WHERE month BETWEEN 11 AND 12 AND distance >= 5
UNION ALL
SELECT CASE WHEN distance < 10 THEN '1. 5 to under 10 miles'
            ELSE '2. 10 miles or more' END AS distance_group,
       count(*) AS rides,
       avg(abs(fare - linear_fare)) AS linear_mae,
       avg(abs(fare - neural_fare)) AS neural_mae,
       avg(abs(fare - linear_fare)) - avg(abs(fare - neural_fare))
           AS improvement_over_line
FROM predictions
WHERE month BETWEEN 11 AND 12 AND distance >= 5
GROUP BY 1
ORDER BY distance_group;
