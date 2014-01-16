-- Per project aggregate of donations versus payouts
WITH donations AS (
    SELECT
      project_id,
      MAX(donations.created::date) AS last_donation,
      COUNT(donations.id),
      SUM(amount/100.0)::numeric(12,2) AS amount
    FROM
      fund_donation AS donations
    JOIN
      projects_project AS projects ON projects.id = donations.project_id
    WHERE
     status IN ('paid', 'pending') AND
     donations.created BETWEEN '2013-01-01' AND '2014-01-01'
    GROUP BY project_id
    ORDER BY project_id
), payouts AS (
    SELECT
      project_id,
      MAX(created::date) AS last_payout,
      COUNT(id),
      SUM(amount_raised) AS amount_raised,
      SUM(organization_fee) AS organization_fee,
      SUM(amount_payable) AS amount_payable
    FROM
      payouts_payout AS payouts
    WHERE status IN ('progress', 'completed')
    GROUP BY project_id
    ORDER BY project_id
)
SELECT
  projects.id,
  projects.title,
  donations.last_donation,
  donations.count AS donation_count,
  donations.amount AS donations,
  payouts.count AS payouts_count,
  payouts.amount_raised AS payouts_amount_raised,
  payouts.organization_fee AS payouts_organization_fee,
  payouts.amount_payable AS payouts_amount_paid,
  donations.amount - payouts.amount_raised AS amount_payable
FROM
  donations
LEFT JOIN payouts
  ON payouts.project_id = donations.project_id
JOIN projects_project AS projects
  ON donations.project_id = projects.id
