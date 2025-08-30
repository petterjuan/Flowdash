import pytest
from unittest.mock import Mock, patch
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from payment_analyzer import (
    PaymentLogicAnalyzer, 
    PaymentFlow, 
    PaymentProvider, 
    PaymentPattern
)


@pytest.fixture
def analyzer():
    return PaymentLogicAnalyzer()


class TestPaymentLogicAnalyzer:
    
    @pytest.mark.unit
    def test_analyze_stripe_python_file(self, analyzer):
        python_code = """
import stripe

stripe.api_key = 'sk_test_123'

def create_payment():
    customer = stripe.Customer.create(
        email='test@example.com'
    )
    
    payment_intent = stripe.PaymentIntent.create(
        amount=1000,
        currency='usd',
        customer=customer.id
    )
    
    return payment_intent
"""
        
        flows = analyzer.analyze_file("payment.py", python_code)
        
        assert len(flows) > 0
        assert any(f.provider == PaymentProvider.STRIPE for f in flows)
        assert any(f.flow_type == "customer_creation" for f in flows)
        assert any(f.flow_type == "payment_intent" for f in flows)
    
    @pytest.mark.unit
    def test_analyze_square_python_file(self, analyzer):
        python_code = """
from square.client import Client

client = Client(
    access_token='sandbox-token',
    environment='sandbox'
)

def process_payment():
    result = client.payments_api.create_payment(
        body={
            'source_id': 'cnon:card-nonce',
            'amount_money': {
                'amount': 100,
                'currency': 'USD'
            }
        }
    )
    return result
"""
        
        flows = analyzer.analyze_file("square_payment.py", python_code)
        
        assert len(flows) > 0
        assert any(f.provider == PaymentProvider.SQUARE for f in flows)
        assert any("create_payment" in method for f in flows for method in f.methods)
    
    @pytest.mark.unit
    def test_analyze_javascript_file(self, analyzer):
        js_code = """
const stripe = require('stripe')('sk_test_123');

async function createCheckoutSession() {
    const session = await stripe.checkout.sessions.create({
        payment_method_types: ['card'],
        line_items: [{
            price: 'price_123',
            quantity: 1,
        }],
        mode: 'payment',
        success_url: 'https://example.com/success',
        cancel_url: 'https://example.com/cancel',
    });
    
    return session;
}
"""
        
        flows = analyzer.analyze_file("checkout.js", js_code)
        
        assert len(flows) > 0
        assert any(f.provider == PaymentProvider.STRIPE for f in flows)
        assert any("checkout" in f.flow_type.lower() for f in flows)
    
    @pytest.mark.unit
    def test_analyze_typescript_file(self, analyzer):
        ts_code = """
import Stripe from 'stripe';

const stripe = new Stripe('sk_test_123', {
    apiVersion: '2023-10-16',
});

export async function createSubscription(customerId: string) {
    const subscription = await stripe.subscriptions.create({
        customer: customerId,
        items: [{ price: 'price_monthly' }],
    });
    
    return subscription;
}
"""
        
        flows = analyzer.analyze_file("subscription.ts", ts_code)
        
        assert len(flows) > 0
        assert any(f.provider == PaymentProvider.STRIPE for f in flows)
        assert any("subscription" in f.flow_type.lower() for f in flows)
    
    @pytest.mark.unit
    def test_analyze_java_file(self, analyzer):
        java_code = """
import com.stripe.Stripe;
import com.stripe.model.Customer;
import com.stripe.model.PaymentIntent;

public class PaymentService {
    public PaymentService() {
        Stripe.apiKey = "sk_test_123";
    }
    
    public PaymentIntent createPayment(long amount) {
        PaymentIntentCreateParams params = PaymentIntentCreateParams.builder()
            .setAmount(amount)
            .setCurrency("usd")
            .build();
            
        return PaymentIntent.create(params);
    }
}
"""
        
        flows = analyzer.analyze_file("PaymentService.java", java_code)
        
        assert len(flows) > 0
        assert any(f.provider == PaymentProvider.STRIPE for f in flows)
        assert any("initialization" in f.flow_type for f in flows)
        assert any("payment_intent" in f.flow_type for f in flows)
    
    @pytest.mark.unit
    def test_extract_payment_architecture(self, analyzer):
        flows = [
            PaymentFlow(
                provider=PaymentProvider.STRIPE,
                flow_type="customer_creation",
                file_path="payment.py",
                line_start=10,
                line_end=15,
                methods=["stripe.Customer.create"],
                endpoints=["/api/customers"]
            ),
            PaymentFlow(
                provider=PaymentProvider.STRIPE,
                flow_type="payment_intent",
                file_path="payment.py",
                line_start=20,
                line_end=25,
                methods=["stripe.PaymentIntent.create"]
            ),
            PaymentFlow(
                provider=PaymentProvider.SQUARE,
                flow_type="payment_creation",
                file_path="square.py",
                line_start=5,
                line_end=10,
                methods=["square.payments_api.create_payment"]
            )
        ]
        
        architecture = analyzer.extract_payment_architecture(flows)
        
        assert "stripe" in architecture["providers"]
        assert "square" in architecture["providers"]
        assert len(architecture["providers"]["stripe"]["flows"]) == 2
        assert "payment.py" in architecture["providers"]["stripe"]["files"]
        assert architecture["flow_summary"]["customer_creation"] == 1
        assert architecture["flow_summary"]["payment_intent"] == 1
        assert architecture["flow_summary"]["payment_creation"] == 1
    
    @pytest.mark.unit
    def test_fallback_analysis_on_syntax_error(self, analyzer):
        invalid_python = """
import stripe

def broken_function(
    # Missing closing parenthesis
    stripe.Customer.create(email='test@example.com')
"""
        
        flows = analyzer.analyze_file("broken.py", invalid_python)
        
        # Should still detect stripe patterns even with syntax error
        assert len(flows) > 0
        assert any(f.provider == PaymentProvider.STRIPE for f in flows)
    
    @pytest.mark.unit
    def test_analyze_function_with_payment_keywords(self, analyzer):
        python_code = """
import stripe

def process_payment_and_subscription(customer_email):
    customer = stripe.Customer.create(email=customer_email)
    
    subscription = stripe.Subscription.create(
        customer=customer.id,
        items=[{'price': 'price_monthly'}]
    )
    
    return subscription
"""
        
        flows = analyzer.analyze_file("payment_sub.py", python_code)
        
        assert len(flows) > 0
        subscription_flows = [f for f in flows if "subscription" in f.flow_type]
        assert len(subscription_flows) > 0
    
    @pytest.mark.unit
    def test_webhook_detection(self, analyzer):
        python_code = """
import stripe

def handle_webhook(payload, sig_header):
    event = stripe.Webhook.construct_event(
        payload, sig_header, webhook_secret
    )
    
    if event.type == 'payment_intent.succeeded':
        payment_intent = event.data.object
        process_successful_payment(payment_intent)
    
    return event
"""
        
        flows = analyzer.analyze_file("webhook.py", python_code)
        
        assert any(f.flow_type == "webhook" for f in flows)
        assert any(f.provider == PaymentProvider.STRIPE for f in flows)
    
    @pytest.mark.unit
    def test_refund_detection(self, analyzer):
        python_code = """
import stripe

def create_refund(payment_intent_id):
    refund = stripe.Refund.create(
        payment_intent=payment_intent_id,
        reason='requested_by_customer'
    )
    return refund
"""
        
        flows = analyzer.analyze_file("refund.py", python_code)
        
        assert any(f.flow_type == "refund" for f in flows)
        assert any(f.provider == PaymentProvider.STRIPE for f in flows)
    
    @pytest.mark.unit
    def test_empty_file(self, analyzer):
        flows = analyzer.analyze_file("empty.py", "")
        assert len(flows) == 0
    
    @pytest.mark.unit
    def test_non_payment_file(self, analyzer):
        python_code = """
def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)
"""
        
        flows = analyzer.analyze_file("fibonacci.py", python_code)
        assert len(flows) == 0