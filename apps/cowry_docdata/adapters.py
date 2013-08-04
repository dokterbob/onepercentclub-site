# coding=utf-8
import logging
from decimal import Decimal, ROUND_HALF_UP
from urllib2 import URLError
from apps.cowry.adapters import AbstractPaymentAdapter
from apps.cowry.models import PaymentStatuses, PaymentLogTypes, PaymentLogLevels
from django.conf import settings
from django.utils.http import urlencode
from django.utils import timezone
from suds.client import Client
from suds.plugin import MessagePlugin
from .exceptions import DocDataPaymentException
from .models import DocDataPaymentOrder, DocDataPayment, DocDataPaymentLogEntry

logger = logging.getLogger(__name__)


# These defaults can be overridden with the COWRY_PAYMENT_METHODS setting.
default_payment_methods = {
    'dd-ideal': {
        'id': 'IDEAL',
        'profile': 'ideal',
        'name': 'iDeal',
        'submethods': {
            '0081': 'Fortis',
            '0021': 'Rabobank',
            '0721': 'ING Bank',
            '0751': 'SNS Bank',
            '0031': 'ABN Amro Bank',
            '0761': 'ASN Bank',
            '0771': 'SNS Regio Bank',
            '0511': 'Triodos Bank',
            '0091': 'Friesland Bank',
            '0161': 'van Lanschot Bankiers'
        },
        'restricted_countries': ('NL',),
        'supports_recurring': False,
    },

    'dd-direct-debit': {
        'id': 'DIRECT_DEBIT',
        'profile': 'directdebit',
        'name': 'Direct Debit',
        'max_amount': 10000,  # €100
        'restricted_countries': ('NL',),
        'supports_recurring': True,
        'supports_single': False,
    },

    'dd-creditcard': {
        'profile': 'creditcard',
        'name': 'Credit Cards',
        'supports_recurring': False,
    },

    'dd-webmenu': {
        'profile': 'webmenu',
        'name': 'Web Menu',
        'supports_recurring': True,
    }
}


def log_status_update(payment, level, message):
    log_entry = DocDataPaymentLogEntry(docdata_payment_order=payment, level=level, message=message, type=PaymentLogTypes.status_update)
    log_entry.save()


def log_status_change(payment, level, message):
    log_entry = DocDataPaymentLogEntry(docdata_payment_order=payment, level=level, message=message, type=PaymentLogTypes.status_change)
    log_entry.save()


class DocDataAPIVersionPlugin(MessagePlugin):
    """
    This adds the API version number to the body element. This is required for the DocData soap API.
    """
    def marshalled(self, context):
        body = context.envelope.getChild('Body')
        request = body[0]
        request.set('version', '1.0')


class DocdataPaymentAdapter(AbstractPaymentAdapter):

    # Mapping of DocData statuses to Cowry statuses. Statuses are from:
    #
    #   Integration Manual Order API 1.0 - Document version 1.0, 08-12-2012 - Page 35
    #
    # The documentation is incorrect for the following statuses:
    #
    #   Documented          Actual
    #   ==========          ======
    #
    #   CANCELLED           CANCELED
    #   CLOSED_CANCELED     CLOSED_CANCELED (guessed based on old api)
    #
    status_mapping = {
        'NEW': PaymentStatuses.new,
        'STARTED': PaymentStatuses.in_progress,
        'AUTHORIZED': PaymentStatuses.pending,
        'AUTHORIZATION_REQUESTED': PaymentStatuses.pending,
        'PAID': PaymentStatuses.pending,
        'CANCELED': PaymentStatuses.cancelled,
        'CHARGED-BACK': PaymentStatuses.cancelled,
        'CONFIRMED_PAID': PaymentStatuses.paid,
        'CONFIRMED_CHARGEDBACK': PaymentStatuses.cancelled,
        'CLOSED_SUCCESS': PaymentStatuses.paid,
        'CLOSED_CANCELED': PaymentStatuses.cancelled,
    }

    # TODO: Create defaults for this like the payment_methods
    id_to_model_mapping = {
        'dd-ideal': DocDataPayment,
        'dd-direct-debit': DocDataPayment,
        'dd-creditcard': DocDataPayment,
        'dd-webmenu': DocDataPayment,
    }

    def _init_docdata(self):
        # Create the soap client.
        if self.test:
            # Test API URL.
            url = 'https://test.tripledeal.com/ps/services/paymentservice/1_0?wsdl'
        else:
            # Live API URL.
            url = 'https://tripledeal.com/ps/services/paymentservice/1_0?wsdl'

        try:
            self.client = Client(url, plugins=[DocDataAPIVersionPlugin()])
        except URLError as e:
            self.client = None
            logger.warn('Could not connect to DocData: ' + str(e))
        else:
            # Setup the merchant soap object for use in all requests.
            self.merchant = self.client.factory.create('ns0:merchant')
            if self.test:
                self.merchant._name = getattr(settings, "COWRY_DOCDATA_TEST_MERCHANT_NAME", None)
                self.merchant._password = getattr(settings, "COWRY_DOCDATA_TEST_MERCHANT_PASSWORD", None)
            else:
                self.merchant._name = getattr(settings, "COWRY_DOCDATA_LIVE_MERCHANT_NAME", None)
                self.merchant._password = getattr(settings, "COWRY_DOCDATA_LIVE_MERCHANT_PASSWORD", None)

    def __init__(self):
        super(DocdataPaymentAdapter, self).__init__()
        self._init_docdata()

    def get_payment_methods(self):
        # Override the payment_methods if they're set. This isn't in __init__ because
        # we want to override the settings in the tests.
        if not hasattr(self, '_payment_methods'):
            settings_payment_methods = getattr(settings, 'COWRY_PAYMENT_METHODS', None)
            if settings_payment_methods:
                # Only override the parameters that are set.
                self._payment_methods = {}
                for pmi in settings_payment_methods:
                    settings_pm = settings_payment_methods[pmi]
                    if pmi in default_payment_methods:
                        default_pm = default_payment_methods[pmi]
                        for param in settings_pm:
                            default_pm[param] = settings_pm[param]
                        self._payment_methods[pmi] = default_pm
                    else:
                        self._payment_methods[pmi] = settings_pm
            else:
                self._payment_methods = default_payment_methods

        return self._payment_methods

    def create_payment_object(self, order, payment_method_id='', payment_submethod_id='', amount=0, currency=''):
        payment = DocDataPaymentOrder(payment_method_id=payment_method_id,
                                      payment_submethod_id=payment_submethod_id,
                                      amount=amount, currency=currency)
        payment.order = order
        payment.save()
        return payment

    def create_remote_payment_order(self, payment):
        # Some preconditions.
        if payment.payment_order_id:
            raise DocDataPaymentException('ERROR', 'Cannot create two remote DocData Payment orders for same payment.')
        if not payment.payment_method_id:
            raise DocDataPaymentException('ERROR', 'payment_method_id is not set')

        # We can't do anything if DocData isn't available.
        if not self.client:
            self._init_docdata()
            if not self.client:
                return

        # Preferences for the DocData system
        paymentPreferences = self.client.factory.create('ns0:paymentPreferences')
        paymentPreferences.profile = self.get_payment_methods()[payment.payment_method_id]['profile'],
        paymentPreferences.numberOfDaysToPay = 5
        menuPreferences = self.client.factory.create('ns0:menuPreferences')

        # Order Amount.
        amount = self.client.factory.create('ns0:amount')
        amount.value = str(payment.amount)
        amount._currency = payment.currency

        # Customer information.
        language = self.client.factory.create('ns0:language')
        language._code = payment.language

        name = self.client.factory.create('ns0:name')
        name.first = payment.first_name
        name.last = payment.last_name

        shopper = self.client.factory.create('ns0:shopper')
        shopper.gender = "U"  # Send unknown gender.
        shopper.language = language
        shopper.email = payment.email
        shopper._id = payment.customer_id
        shopper.name = name

        # Billing information.
        address = self.client.factory.create('ns0:address')
        address.street = payment.address
        address.houseNumber = 'N/A'
        address.postalCode = payment.postal_code.replace(' ', '')  # Spaces aren't allowed in the DocData postal code.
        address.city = payment.city

        country = self.client.factory.create('ns0:country')
        country._code = payment.country
        address.country = country

        billTo = self.client.factory.create('ns0:destination')
        billTo.address = address
        billTo.name = name

        # Set the description if there's an order.
        description = payment.order.__unicode__()[:50]
        if not description:
            # TODO Add a setting for default description.
            description = "1%CLUB"

        if self.test:
            # A unique code for testing.
            payment.merchant_order_reference = ('COWRY-' + str(timezone.now()))[:30].replace(' ', '-')
        else:
            payment.merchant_order_reference = str(payment.id)

        # Execute create payment order request.
        reply = self.client.service.create(self.merchant, payment.merchant_order_reference, paymentPreferences,
                                           menuPreferences, shopper, amount, billTo, description)
        if hasattr(reply, 'createSuccess'):
            payment.payment_order_id = str(reply['createSuccess']['key'])
            self._change_status(payment, PaymentStatuses.in_progress)  # Note: _change_status calls payment.save().
        elif hasattr(reply, 'createError'):
            payment.save()
            error = reply['createError']['error']
            raise DocDataPaymentException(error['_code'], error['value'])
        else:
            payment.save()
            raise DocDataPaymentException('REPLY_ERROR',
                                          'Received unknown reply from DocData. Remote Payment not created.')

    def cancel_payment(self, payment):
        # Some preconditions.
        if not payment.payment_order_id:
            logger.warn('Attempt to cancel payment on Order id {0} which has no payment_order_id.'.format(payment.order.id))
            return

        # Execute create payment order request.
        reply = self.client.service.cancel(self.merchant, payment.payment_order_id)
        if hasattr(reply, 'cancelSuccess'):
            for docdata_payment in payment.docdata_payments.all():
                docdata_payment.status = 'CANCELLED'
                docdata_payment.save()
            self._change_status(payment, PaymentStatuses.cancelled)  # Note: change_status calls payment.save().
        elif hasattr(reply, 'cancelError'):
            error = reply['cancelError']['error']
            raise DocDataPaymentException(error['_code'], error['value'])
        else:
            raise DocDataPaymentException('REPLY_ERROR',
                                          'Received unknown reply from DocData. Remote Payment not cancelled.')

    def get_payment_url(self, payment, return_url_base=None):
        """ Return the Payment URL """

        if payment.amount <= 0 or not payment.payment_method_id or \
                not self.id_to_model_mapping[payment.payment_method_id] == DocDataPayment:
            return None

        if not payment.payment_order_id:
            self.create_remote_payment_order(payment)

        # The basic parameters.
        params = {
            'payment_cluster_key': payment.payment_order_id,
            'merchant_name': self.merchant._name,
            'client_language': payment.language,
        }

        # Add a default payment method if the config has an id.
        payment_methods = self.get_payment_methods()
        if hasattr(payment_methods[payment.payment_method_id], 'id'):
            params['default_pm'] = payment_methods[payment.payment_method_id]['id'],

        # Add return urls.
        if return_url_base:
            params['return_url_success'] = return_url_base + '#!/support/thanks/' + str(payment.order.id)
            params['return_url_pending'] = return_url_base + '#!/support/thanks/' + str(payment.order.id)
            # TODO This assumes that the order is always a donation order. These Urls will be used when buying vouchers
            # TODO too which is incorrect.
            params['return_url_canceled'] = return_url_base + '#!/support/donations'
            params['return_url_error'] = return_url_base + '#!/support/payment/error'

        # Special parameters for iDeal.
        if payment.payment_method_id == 'dd-ideal' and payment.payment_submethod_id:
            params['ideal_issuer_id'] = payment.payment_submethod_id
            params['default_act'] = 'true'

        if self.test:
            payment_url_base = 'https://test.docdatapayments.com/ps/menu'
        else:
            payment_url_base = 'https://secure.docdatapayments.com/ps/menu'

        # Create a DocDataPayment when we need it.
        docdata_payment = payment.latest_docdata_payment
        if not docdata_payment or not isinstance(docdata_payment, DocDataPayment):
            docdata_payment = DocDataPayment()
            docdata_payment.docdata_payment_order = payment
            docdata_payment.save()

        return payment_url_base + '?' + urlencode(params)

    def update_payment_status(self, payment, status_changed_notification=False):
        # Don't do anything if there's no payment or payment_order_id.
        if not payment or not payment.payment_order_id:
            return

        # Execute status request.
        reply = self.client.service.status(self.merchant, payment.payment_order_id)
        if hasattr(reply, 'statusSuccess'):
            report = reply['statusSuccess']['report']
        elif hasattr(reply, 'statusError'):
            error = reply['statusError']['error']
            log_status_update(payment, PaymentLogLevels.error, "{1} {2}".format(error['_code'], error['value']))
            return
        else:
            log_status_update(payment, PaymentLogLevels.error,
                              "REPLY_ERROR Received unknown status reply from DocData.")
            return

        if not hasattr(report, 'payment'):
            if status_changed_notification:
                log_status_update(payment, PaymentLogLevels.warn,
                                  "Status changed notification received but status report had no payment reports.")
            return

        statusChanged = False
        for payment_report in report.payment:
            # Find or create the DocDataPayment for current report.
            try:
                ddpayment = DocDataPayment.objects.get(payment_id=str(payment_report.id))
            except DocDataPayment.DoesNotExist:
                ddpayment_list = payment.docdata_payments.filter(status='NEW')
                ddpayment_list_len = len(ddpayment_list)
                if ddpayment_list_len == 0:
                    ddpayment = DocDataPayment()
                    ddpayment.docdata_payment_order = payment
                elif ddpayment_list_len == 1:
                    ddpayment = ddpayment_list[0]
                else:
                    log_status_update(payment, PaymentLogLevels.error,
                                      "Cannot determine where to save the payment report.")
                    continue

                # Save some information from the report.
                ddpayment.payment_id = str(payment_report.id)
                ddpayment.payment_method = str(payment_report.paymentMethod)
                docdata_fees = getattr(settings, "COWRY_DOCDATA_FEES", None)
                ddpayment.save()

                # Set the payment fee.
                if docdata_fees:
                    if ddpayment.payment_method in docdata_fees:
                        payment_cost_setting = str(docdata_fees[ddpayment.payment_method])
                        if '%' in payment_cost_setting:
                            # Note: This assumes that the amount in the payment method will cover the full cost of the
                            # payment order. It seems that DocData allows multiple payments to make up the full order
                            # total. The method used here should be ok for 1%CLUB but it may not be suitable for others.
                            cost_percent = Decimal(payment_cost_setting.replace('%', '')) / 100
                            payment_cost = cost_percent * payment.amount
                        else:
                            payment_cost = Decimal(payment_cost_setting) * 100

                        # TODO: Check if this is the rounding rule for the Netherlands / the Euro.
                        payment.fee = payment_cost.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)
                        payment.save()

                    else:
                        log_status_update(payment, PaymentLogLevels.warn,
                                          "Can't set payment fee for {0} because payment method is not in COWRY_DOCDATA_FEES.".format(
                                          ddpayment.payment_id))
                else:
                    log_status_update(payment, PaymentLogLevels.warn,
                                      "Can't set payment fee for {0} because COWRY_DOCDATA_FEES is not in set.".format(
                                          ddpayment.payment_id))


            # Some additional checks.
            if not payment_report.paymentMethod == ddpayment.payment_method:
                log_status_update(payment, PaymentLogLevels.warn,
                                  "Payment method from DocData doesn't match saved payment method." \
                                  "Storing the payment method received from DocData for payment id {0}: {1}".format(
                                      ddpayment.payment_id, payment_report.paymentMethod))
                ddpayment.payment_method = str(payment_report.paymentMethod)
                ddpayment.save()

            if not payment_report.authorization.status in self.status_mapping:
                # Note: We continue to process the payment status change on this error.
                log_status_update(payment, PaymentLogLevels.error,
                                  "Received unknown payment status from DocData: {0}".format(
                                      payment_report.authorization.status))

            # Update the DocDataPayment status.
            if ddpayment.status != payment_report.authorization.status:
                log_status_change(payment, PaymentLogLevels.info,
                                  "DocData payment status changed for payment id {0}: {1} -> {2}".format(
                                      payment_report.id, ddpayment.status, payment_report.authorization.status))
                ddpayment.status = str(payment_report.authorization.status)
                ddpayment.save()
                statusChanged = True

        # Use the latest DocDataPayment status to set the status on the Cowry Payment.
        latest_ddpayment = payment.latest_docdata_payment
        latest_payment_report = None
        for payment_report in report.payment:
            if payment_report.id == latest_ddpayment.payment_id:
                latest_payment_report = payment_report
                break
        old_status = payment.status
        new_status = self._map_status(latest_ddpayment.status, payment, report.approximateTotals,
                                      latest_payment_report.authorization)

        # TODO: Move this logging to AbstractPaymentAdapter when PaymentLogEntry is not abstract.
        if old_status != new_status:
            if new_status not in PaymentStatuses.values:
                log_status_change(payment, PaymentLogLevels.warn,
                                  "Payment status changed {0} -> {1}".format(old_status, PaymentStatuses.unknown))
            else:
                log_status_change(payment, PaymentLogLevels.info,
                                  "Payment status changed {0} -> {1}".format(old_status, new_status))

        self._change_status(payment, new_status)  # Note: change_status calls payment.save().

    def _map_status(self, status, payment=None, totals=None, authorization=None):
        new_status = super(DocdataPaymentAdapter, self)._map_status(status)

        # Some status mapping overrides.
        #
        # Integration Manual Order API 1.0 - Document version 1.0, 08-12-2012 - Page 33:
        #
        # Safe route: The safest route to check whether all payments were made is for the merchants
        # to refer to the “Total captured” amount to see whether this equals the “Total registered
        # amount”. While this may be the safest indicator, the downside is that it can sometimes take a
        # long time for acquirers or shoppers to actually have the money transferred and it can be
        # captured.
        #
        log_status_update(payment, PaymentLogLevels.info,
                          "Total Registered: {0} Total Captured: {1}".format(totals.totalRegistered, totals.totalCaptured))
        if totals.totalRegistered == totals.totalCaptured:
            new_status = PaymentStatuses.paid

        return new_status

    # TODO Use status change log to investigate if these overrides are needed.
    #     # These overrides are really just guessing.
    #     latest_capture = authorization.capture[-1]
    #     if status == 'AUTHORIZED':
    #         if hasattr(authorization, 'refund') or hasattr(authorization, 'chargeback'):
    #             new_status = 'cancelled'
    #         if latest_capture.status == 'FAILED' or latest_capture == 'ERROR':
    #             new_status = 'failed'
    #         elif latest_capture.status == 'CANCELLED':
    #             new_status = 'cancelled'
