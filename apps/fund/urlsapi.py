from django.conf.urls import patterns, url
from surlex.dj import surl
from .views import (FundApi, OrderList, OrderDetail, OrderDonationDetail, PaymentOrderProfileCurrent,
                    PaymentMethodList, VoucherDetail, PaymentMethodInfoCurrent,
                    OrderVoucherList, OrderVoucherDetail, VoucherDonationList, VoucherDonationDetail,
                    CustomVoucherRequestList, OrderDonationList)


urlpatterns = patterns('',
    url(r'^$', FundApi.as_view(), name='fund-order-list'),

    # Orders
    url(r'^orders/$', OrderList.as_view(), name='fund-order-list'),
    surl(r'^orders/<pk:#>$', OrderDetail.as_view(), name='fund-order-detail'),
    surl(r'^orders/<order_id:#>/donations/$', OrderDonationList.as_view(), name='fund-order-donation-list'),
    surl(r'^orders/<order_id:#>/donations/<pk:#>$', OrderDonationDetail.as_view(), name='fund-order-donation-detail'),
    surl(r'^orders/<order_id:#>/vouchers/$', OrderVoucherList.as_view(), name='fund-order-voucher-list'),
    surl(r'^orders/<order_id:#>/vouchers/<pk:#>$', OrderVoucherDetail.as_view(), name='fund-order-voucher-detail'),

    # Current Order (i.e. the server-side shopping cart).
    url(r'^orders/current$', OrderDetail.as_view(), {'alias': 'current'}, name='fund-order-detail'),
    url(r'^orders/current/donations/$', OrderDonationList.as_view(), {'alias': 'current'}, name='fund-order-donation-list'),
    surl(r'^orders/current/donations/<pk:#>$', OrderDonationDetail.as_view(), {'alias': 'current'}, name='fund-order-donation-detail'),
    url(r'^orders/current/vouchers/$', OrderVoucherList.as_view(), {'alias': 'current'}, name='fund-order-voucher-list'),
    surl(r'^orders/current/vouchers/<pk:#>$', OrderVoucherDetail.as_view(), {'alias': 'current'}, name='fund-order-voucher-detail'),

    surl(r'^vouchers/<code:s>$', VoucherDetail.as_view(), name='voucher-detail'),
    surl(r'^vouchers/<code:s>/donations/$', VoucherDonationList.as_view(), name='voucher-donation-list'),
    surl(r'^vouchers/<code:s>/donations/<pk:#>$', VoucherDonationDetail.as_view(), name='voucher-donation-list'),
    surl(r'^customvouchers/$', CustomVoucherRequestList.as_view(), name='custom-voucher-request-list'),


    url(r'^paymentorderprofiles/current$', PaymentOrderProfileCurrent.as_view(), name='fund-payment-order-profile-current'),

    url(r'^paymentmethods/$', PaymentMethodList.as_view(), name='fund-payment-method-list'),
    surl(r'^paymentmethods/<slug:s>$', PaymentMethodList.as_view(), name='fund-payment-method-detail'),

    url(r'^paymentmethodinfo/current$', PaymentMethodInfoCurrent.as_view(), name='fund-payment-method-ideal-current'),


)