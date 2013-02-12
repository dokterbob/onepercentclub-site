# coding=utf-8
from apps.cowry.adapters import AbstractPaymentAdapter
from apps.cowry_docdata.models import DocDataPayment
from django.conf import settings
from django.contrib.sites.models import Site
from django.utils.http import urlencode
from django.utils import timezone
from suds.client import Client
from suds.plugin import MessagePlugin
from .exceptions import DocDataPaymentException


class DocDataAPIVersionPlugin(MessagePlugin):
    """ This adds the API version number to the body element. This is required for the DocData soap API."""

    def marshalled(self, context):
        body = context.envelope.getChild('Body')
        request = body[0]
        request.set('version', '1.0')


class DocdataPaymentAdapter(AbstractPaymentAdapter):
    """
        Docdata payments
    """

    # TODO Make setting for this.
    test = True

    live_api_url = 'https://tripledeal.com/ps/services/paymentservice/1_0?wsdl'
    test_api_url = 'https://test.tripledeal.com/ps/services/paymentservice/1_0?wsdl'

    ideal_submethod_mapping = {
                                  'Fortis': '0081',
                                  'Rabobank': '0021',
                                  'ING Bank': '0721',
                                  'SNS Bank': '0751',
                                  'ABN Amro Bank': '0031',
                                  'ASN Bank': '0761',
                                  'SNS Regio Bank': '0771',
                                  'Triodos Bank': '0511',
                                  'Friesland Bank': '0091',
                                  'van Lanschot Bankiers': '0161'
                              },

    payment_methods = {
        'IDEAL': {
            'submethods': ('Fortis', 'Rabobank', 'ING Bank', 'SNS Bank', 'ABN Amro Bank', 'ASN Bank',
                           'SNS Regio Bank', 'Triodos Bank', 'Friesland Bank', 'van Lanschot Bankiers'),
            'restricted_countries': ('NL',),
            'recurring': False,
        },

        'MAESTRO': {'recurring': False, },

        'MASTERCARD': {'max_amount': 10000,  # €100
                       'min_amount': 2000,  # €20
                       'recurring': False, },

        'VISA': {'recurring': False}
    }

    def __init__(self, test=True):
        self.test = test

        # Create the soap client.
        if self.test:
            url = self.test_api_url
        else:
            url = self.live_api_url
        self.client = Client(url, plugins=[DocDataAPIVersionPlugin()])

        # Setup the merchant soap object for use in all requests.
        self.merchant = self.client.factory.create('ns0:merchant')
        # TODO: Make this required if adapter is enabled (i.e. throw an error if not set instead of defaulting to dummy).
        self.merchant._name = getattr(settings, "DOCDATA_MERCHANT_NAME", 'dummy')
        self.merchant._password = getattr(settings, "DOCDATA_MERCHANT_PASSWORD", 'dummy')

        # TODO Work this out better.
        server = Site.objects.get_current().domain
        if server == 'localhost:8000':
            self.return_url = 'http://' + server + '#/support/thanks'
        else:
            self.return_url = 'https://' + server + '#/support/thanks'

        # Preferences for the DocData system
        self.paymentPreferences = self.client.factory.create('ns0:paymentPreferences')
        self.paymentPreferences.profile = 'standard'
        self.paymentPreferences.numberOfDaysToPay = 5
        self.menuPreferences = self.client.factory.create('ns0:menuPreferences')


    def get_payment_methods(self, amount=None, currency=None, country=None, recurring=None):
        return self.payment_methods.keys()

    def get_payment_submethods(self, payment_method):
        if payment_method in self.payment_methods.keys():
            config = self.payment_methods[payment_method]
            if 'submethods' in config.keys():
                return config['submethods']
        return None


    def create_payment_object(self, payment_method='', payment_submethod='', amount=0, currency=''):
        payment = DocDataPayment.objects.create(payment_method=payment_method, payment_submethod=payment_submethod,
                                                amount=amount, currency=currency)
        payment.save()
        return payment


    def create_remote_payment_order(self, payment):
        if payment.payment_order_key:
            raise DocDataPaymentException('ERROR', 'Cannot create two remote DocData Payment orders for same payment.')

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
        address.street = payment.street
        address.houseNumber = payment.house_number
        address.postalCode = payment.postal_code.replace(' ',
                                                         '')  # TODO No space allowed in postal code. Move to serializer.
        address.city = payment.city

        country = self.client.factory.create('ns0:country')
        country._code = payment.country
        address.country = country

        billTo = self.client.factory.create('ns0:destination')
        billTo.address = address
        billTo.name = name

        if self.test:
            # A unique code for testing.
            payment.merchant_order_reference = str(timezone.now())
        else:
            # TODO: use order id for production.
            pass

        # Save in case there's an error creating the payment order.
        payment.save()

        # Execute create payment order request.
        reply = self.client.service.create(self.merchant, payment.merchant_order_reference, self.paymentPreferences,
                                           self.menuPreferences, shopper, amount, billTo)
        if hasattr(reply, 'createSuccess'):
            payment.payment_order_key = reply['createSuccess']['key']
            payment.save()
        elif hasattr(reply, 'createError'):
            error = reply['createError']['error']
            raise DocDataPaymentException(error['_code'], error['value'])
        else:
            raise DocDataPaymentException('REPLY_ERROR',
                                          'Received unknown reply from DocData. Remote Payment not created.')

        # Create and save the redirect url.
        payment.payment_url = self.get_payment_url(payment)
        payment.save()


    def get_payment_url(self, payment):
        """ Return the Payment URL """

        if not payment.payment_order_key:
            self.create_remote_payment_order(payment)
            return payment.payment_url

        params = {
            'command': 'show_payment_cluster',
            'payment_cluster_key': payment.payment_order_key,
            'merchant_name': self.merchant._name,
            # TODO: Enable when have good URLs.
            # 'return_url_success': self.return_url,
            # 'return_url_pending': self.return_url,
            # 'return_url_canceled': self.return_url,
            # 'return_url_error': self.return_url,
            'client_language': payment.language,
            'default_pm': payment.payment_method,
            # TODO: Not currently working. Need to call DocData.
            # 'default_act': 'true',
        }

        if payment.payment_method == 'IDEAL':
            # TODO check that payment_submethod is set
            # TODO get id from submethod dict
            params['ideal_issuer_id'] = payment.payment_submethod

        if self.test:
            redirect_url = 'https://test.docdatapayments.com/ps/menu'
        else:
            redirect_url = 'https://secure.docdatapayments.com/ps/menu'

        payment.payment_url = redirect_url + '?' + urlencode(params)
        payment.save()
        return payment.payment_url


    def map_status(self, status):
        # TODO: Translate the specific statuses into something generic we all understand
        return status




