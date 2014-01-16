-- Organization payouts versus payouts versus calculated fees
WITH payouts AS (
    SELECT
      completed,
      amount_raised,
      organization_fee,
      amount_payable
    FROM
      payouts_payout AS payouts
    WHERE
      payouts.status = 'completed'
), fees AS (
    SELECT
      payments.fee,
      donations.ready
    FROM
      public.cowry_payment payments
    JOIN
      public.fund_donation donations ON payments.order_id = donations.order_id
    WHERE
      payments.status IN ('paid', 'chargedback', 'refunded')
)
