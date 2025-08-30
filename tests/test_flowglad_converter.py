import pytest
from unittest.mock import Mock, patch
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from flowglad_converter import FlowGladConverter, CodeTransformation, ConversionRule


@pytest.fixture
def converter():
    return FlowGladConverter()


class TestFlowGladConverter:
    
    @pytest.mark.unit
    def test_initialization(self, converter):
        assert len(converter.conversion_rules) > 0
        
        stripe_rules = [r for r in converter.conversion_rules if r.provider == "stripe"]
        square_rules = [r for r in converter.conversion_rules if r.provider == "square"]
        
        assert len(stripe_rules) > 0
        assert len(square_rules) > 0
    
    @pytest.mark.unit
    def test_convert_stripe_python_imports(self, converter):
        code = """import stripe

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')"""
        
        transformation = converter.convert_code(code, "stripe", "python")
        
        assert "import flowglad" in transformation.transformed_code
        assert "FLOWGLAD_SECRET_KEY" in transformation.transformed_code
        assert transformation.transformation_type == "full_conversion"
    
    @pytest.mark.unit
    def test_convert_stripe_customer_creation(self, converter):
        code = """
customer = stripe.Customer.create(
    email='test@example.com',
    name='Test User'
)"""
        
        transformation = converter.convert_code(code, "stripe", "python")
        
        assert "flowglad.customers.create" in transformation.transformed_code
        assert "email=" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_stripe_payment_intent(self, converter):
        code = """
payment_intent = stripe.PaymentIntent.create(
    amount=2000,
    currency='usd',
    automatic_payment_methods={'enabled': True}
)"""
        
        transformation = converter.convert_code(code, "stripe", "python")
        
        assert "flowglad.checkout.sessions.create" in transformation.transformed_code
        assert "amount=" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_stripe_subscription(self, converter):
        code = """
subscription = stripe.Subscription.create(
    customer='cus_123',
    items=[{'price': 'price_123'}]
)"""
        
        transformation = converter.convert_code(code, "stripe", "python")
        
        assert "flowglad.subscriptions.create" in transformation.transformed_code
        assert "customer_id=" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_square_python(self, converter):
        code = """
from square.client import Client

client = Client(access_token=os.getenv('SQUARE_ACCESS_TOKEN'))

result = client.payments_api.create_payment(body={
    'source_id': 'cnon:card',
    'amount_money': {'amount': 100, 'currency': 'USD'}
})"""
        
        transformation = converter.convert_code(code, "square", "python")
        
        assert "from flowglad import FlowGlad" in transformation.transformed_code
        assert "FlowGlad(" in transformation.transformed_code
        assert ".payments.create" in transformation.transformed_code
        assert "FLOWGLAD_SECRET_KEY" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_javascript_stripe(self, converter):
        js_code = """
const stripe = require('stripe')('sk_test_123');

const customer = await stripe.customers.create({
    email: 'test@example.com'
});

const paymentIntent = await stripe.paymentIntents.create({
    amount: 1000,
    currency: 'usd'
});"""
        
        transformation = converter.convert_code(js_code, "stripe", "javascript")
        
        assert "flowglad" in transformation.transformed_code
        assert "flowglad.customers.create" in transformation.transformed_code
        assert "flowglad.checkout.sessions.create" in transformation.transformed_code
        assert "FLOWGLAD_SECRET_KEY" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_typescript_stripe(self, converter):
        ts_code = """
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

const subscription = await stripe.subscriptions.create({
    customer: customerId,
    items: [{price: priceId}]
});"""
        
        transformation = converter.convert_code(ts_code, "stripe", "typescript")
        
        assert "FlowGlad" in transformation.transformed_code
        assert "flowglad.subscriptions.create" in transformation.transformed_code
        assert "FLOWGLAD_SECRET_KEY" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_webhook_handling(self, converter):
        code = """
event = stripe.Webhook.construct_event(
    payload, sig_header, webhook_secret
)"""
        
        transformation = converter.convert_code(code, "stripe", "python")
        
        assert "flowglad.webhooks.verify" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_refund_creation(self, converter):
        code = """
refund = stripe.Refund.create(
    payment_intent='pi_123',
    reason='requested_by_customer'
)"""
        
        transformation = converter.convert_code(code, "stripe", "python")
        
        assert "flowglad.refunds.create" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_add_flowglad_imports(self, converter):
        code = """
def process_payment():
    pass"""
        
        result = converter._add_flowglad_imports(code)
        
        assert "import flowglad" in result
        assert "from dotenv import load_dotenv" in result
        assert "load_dotenv()" in result
    
    @pytest.mark.unit
    def test_update_python_params_stripe(self, converter):
        code = """
payment = create_payment(
    amount=1000,
    currency='usd',
    customer='cus_123',
    payment_method='pm_123',
    description='Test payment'
)"""
        
        result = converter._update_python_params(code, "stripe")
        
        assert "amount=" in result
        assert "customer_id=" in result
        assert "payment_method_id=" in result
        assert "description=" in result
    
    @pytest.mark.unit
    def test_update_python_params_square(self, converter):
        code = """
payment = create_payment(
    amount_money={'amount': 100},
    source_id='card_123',
    customer_id='cus_123'
)"""
        
        result = converter._update_python_params(code, "square")
        
        assert "amount=" in result
        assert "payment_source=" in result
        assert "customer_id=" in result
    
    @pytest.mark.unit
    def test_generate_migration_script(self, converter):
        transformations = [
            CodeTransformation(
                original_code="import stripe",
                transformed_code="import flowglad",
                file_path="payment.py",
                line_range=(1, 1),
                transformation_type="import"
            ),
            CodeTransformation(
                original_code="stripe.Customer.create",
                transformed_code="flowglad.customers.create",
                file_path="customer.py",
                line_range=(10, 10),
                transformation_type="api_call"
            )
        ]
        
        script = converter.generate_migration_script(transformations)
        
        assert "#!/usr/bin/env python3" in script
        assert "FlowGlad Migration Script" in script
        assert "backup_files" in script
        assert "apply_transformations" in script
        assert "update_env_file" in script
        assert "payment.py" in script
        assert "customer.py" in script
        assert "import flowglad" in script
    
    @pytest.mark.unit
    def test_convert_checkout_session(self, converter):
        code = """
session = stripe.checkout.Session.create(
    payment_method_types=['card'],
    line_items=[{
        'price': 'price_123',
        'quantity': 1
    }],
    mode='payment',
    success_url='https://example.com/success',
    cancel_url='https://example.com/cancel'
)"""
        
        transformation = converter.convert_code(code, "stripe", "python")
        
        assert "flowglad.checkout.sessions.create" in transformation.transformed_code
        assert "success_url=" in transformation.transformed_code
        assert "cancel_url=" in transformation.transformed_code
    
    @pytest.mark.unit
    def test_convert_generic_file_type(self, converter):
        code = "stripe.Customer.create(email='test@example.com')"
        
        transformation = converter.convert_code(code, "stripe", "generic")
        
        assert "flowglad.customers.create" in transformation.transformed_code
        assert transformation.transformation_type == "generic_conversion"