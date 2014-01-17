-- Show consistency between Docdata payments, Docdata payouts, the backend and bank statements

SELECT
  *
FROM
  public.accounting_docdatapayment imported_payments
LEFT JOIN
  public.cowry_docdata_docdatapaymentorder payment_clusters ON imported_payments.merchant_reference = payment_clusters.merchant_order_reference
LEFT JOIN
  public.cowry_payment payments ON payment_clusters.payment_ptr_id = payments.id
LEFT JOIN
  public.fund_order orders ON orders.id = payments.order_id
LEFT JOIN
  public.fund_donation donations ON donations.order_id = payments.order_id
ORDER BY triple_deal_reference
