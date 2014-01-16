﻿-- Monthly aggregate of donations versus payouts
WITH donations AS (
    SELECT
      date_trunc('month', donations.created)::date AS month,
      COUNT(donations.id),
      SUM(donations.amount/100.0)::numeric(12,2) AS amount
    FROM
      fund_donation AS donations
    JOIN
      projects_project AS projects ON projects.id = donations.project_id
    WHERE status IN ('paid', 'pending')
    GROUP BY month
    ORDER BY month
), payouts AS (
    SELECT
      date_trunc('month', created)::date AS month,
      COUNT(id),
      SUM(amount_raised) AS amount_raised,
      SUM(organization_fee) AS organization_fee,
      SUM(amount_payable) AS amount_payable
    FROM
      payouts_payout AS payouts
    WHERE status IN ('completed')
    GROUP BY month
    ORDER BY month
)
SELECT
  donations.month,
  donations.count AS donation_count,
  donations.amount AS donations_amount,
  payouts.count AS payouts_count,
  payouts.amount_raised AS payouts_amount_raised,
  payouts.organization_fee AS payouts_organization_fee,
  payouts.amount_payable AS payouts_amount_paid,
  donations.amount - payouts.amount_raised AS amount_payable,
  SUM(donations.amount - payouts.amount_raised) OVER(ORDER BY donations.month) as running_payable
FROM donations
LEFT JOIN
  payouts ON payouts.month = donations.month
WHERE donations.month BETWEEN '2013-01-01' AND '2014-01-01'