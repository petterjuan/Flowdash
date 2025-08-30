import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from flow_mapper import PaymentFlowMapper, PaymentFlowMap


@pytest.fixture
def mock_genai():
    with patch('flow_mapper.genai') as mock:
        yield mock


@pytest.fixture
def mapper(mock_genai):
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test_key', 'GEMINI_MODEL': 'gemini-2.5-flash-lite'}):
        return PaymentFlowMapper()


class TestPaymentFlowMapper:
    
    @pytest.mark.unit
    def test_initialization(self, mock_genai):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test_key', 'GEMINI_MODEL': 'gemini-2.5-flash-lite'}):
            mapper = PaymentFlowMapper()
            
            mock_genai.configure.assert_called_once_with(api_key='test_key')
            mock_genai.GenerativeModel.assert_called_once_with('gemini-2.5-flash-lite')
    
    @pytest.mark.unit
    def test_map_payment_flow(self, mapper):
        code = """
        stripe.Customer.create(email='test@example.com')
        stripe.PaymentIntent.create(amount=1000)
        """
        
        mock_response = Mock()
        mock_response.text = json.dumps({
            "flow_description": "Customer creation and payment",
            "steps": [
                {"description": "Create customer", "code_reference": "line 1"},
                {"description": "Create payment intent", "code_reference": "line 2"}
            ],
            "entities": ["customer", "payment_intent"],
            "api_calls": ["stripe.Customer.create", "stripe.PaymentIntent.create"],
            "business_logic": "Create customer then charge payment",
            "validation_rules": ["Email validation", "Amount validation"],
            "error_handling": ["Handle API errors"]
        })
        
        mapper.client.generate_content = Mock(return_value=mock_response)
        
        flow_map = mapper.map_payment_flow(code, "stripe", "payment")
        
        assert flow_map.original_provider == "stripe"
        assert len(flow_map.steps) == 2
        assert "customer" in flow_map.entities
        assert "stripe.Customer.create" in flow_map.api_calls
    
    @pytest.mark.unit
    def test_parse_flow_response_with_json_block(self, mapper):
        response = """
        Here's the analysis:
        ```json
        {
            "flow_description": "Test flow",
            "steps": [],
            "entities": [],
            "api_calls": [],
            "business_logic": "Test logic",
            "validation_rules": [],
            "error_handling": []
        }
        ```
        """
        
        flow_map = mapper._parse_flow_response(response, "stripe")
        
        assert flow_map.flow_description == "Test flow"
        assert flow_map.business_logic == "Test logic"
        assert flow_map.original_provider == "stripe"
    
    @pytest.mark.unit
    def test_parse_flow_response_error_handling(self, mapper):
        response = "Invalid JSON response"
        
        flow_map = mapper._parse_flow_response(response, "stripe")
        
        assert "Error parsing flow" in flow_map.flow_description
        assert flow_map.original_provider == "stripe"
        assert len(flow_map.steps) == 0
    
    @pytest.mark.unit
    def test_generate_documentation(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="stripe",
            flow_description="Payment processing flow",
            steps=[
                {"description": "Validate input"},
                {"description": "Process payment", "code_reference": "payment.py:25"}
            ],
            entities=["customer", "payment"],
            api_calls=["stripe.PaymentIntent.create"],
            business_logic="Process customer payment",
            validation_rules=["Amount > 0", "Valid card"],
            error_handling=["Retry on timeout", "Log failures"]
        )
        
        doc = mapper.generate_documentation(flow_map)
        
        assert "# Payment Flow Documentation" in doc
        assert "stripe" in doc
        assert "Validate input" in doc
        assert "customer, payment" in doc
        assert "stripe.PaymentIntent.create" in doc
        assert "Amount > 0" in doc
        assert "Retry on timeout" in doc
    
    @pytest.mark.unit
    def test_compare_with_flowglad_stripe(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="stripe",
            flow_description="",
            steps=[],
            entities=["customer"],
            api_calls=["stripe.Customer.create", "stripe.PaymentIntent.create"],
            business_logic="",
            validation_rules=["Email validation"],
            error_handling=[]
        )
        
        comparison = mapper.compare_with_flowglad(flow_map)
        
        assert comparison["provider"] == "stripe"
        assert len(comparison["flowglad_equivalents"]) > 0
        assert any(eq["flowglad"] == "flowglad.customers.create" 
                  for eq in comparison["flowglad_equivalents"])
        assert comparison["migration_complexity"] in ["Low", "Medium", "High"]
        assert len(comparison["required_changes"]) > 0
    
    @pytest.mark.unit
    def test_compare_with_flowglad_square(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="square",
            flow_description="",
            steps=[],
            entities=["payment"],
            api_calls=["square.payments_api.create_payment"],
            business_logic="",
            validation_rules=[],
            error_handling=[]
        )
        
        comparison = mapper.compare_with_flowglad(flow_map)
        
        assert comparison["provider"] == "square"
        assert any(eq["flowglad"] == "flowglad.payments.create" 
                  for eq in comparison["flowglad_equivalents"])
    
    @pytest.mark.unit
    def test_assess_complexity_low(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="stripe",
            flow_description="",
            steps=[{"step": 1}],
            entities=["customer"],
            api_calls=[],
            business_logic="",
            validation_rules=["rule1"],
            error_handling=[]
        )
        
        complexity = mapper._assess_complexity(flow_map)
        assert complexity == "Low"
    
    @pytest.mark.unit
    def test_assess_complexity_medium(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="stripe",
            flow_description="",
            steps=[{"step": i} for i in range(5)],
            entities=["customer", "payment", "subscription"],
            api_calls=[],
            business_logic="",
            validation_rules=["rule1", "rule2", "rule3"],
            error_handling=[]
        )
        
        complexity = mapper._assess_complexity(flow_map)
        assert complexity == "Medium"
    
    @pytest.mark.unit
    def test_assess_complexity_high(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="stripe",
            flow_description="",
            steps=[{"step": i} for i in range(15)],
            entities=["customer", "payment", "subscription", "invoice", "refund"],
            api_calls=[],
            business_logic="",
            validation_rules=["rule" + str(i) for i in range(10)],
            error_handling=[]
        )
        
        complexity = mapper._assess_complexity(flow_map)
        assert complexity == "High"
    
    @pytest.mark.unit
    def test_identify_required_changes_webhooks(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="stripe",
            flow_description="",
            steps=[],
            entities=["customer"],
            api_calls=["stripe.Webhook.construct_event"],
            business_logic="",
            validation_rules=["Email validation"],
            error_handling=[]
        )
        
        changes = mapper._identify_required_changes(flow_map)
        
        assert "Update webhook endpoints to FlowGlad format" in changes
        assert "Convert customer data model to FlowGlad schema" in changes
        assert "Adapt validation rules to FlowGlad requirements" in changes
        assert "Update API authentication to use FlowGlad keys" in changes
    
    @pytest.mark.unit
    def test_identify_required_changes_subscriptions(self, mapper):
        flow_map = PaymentFlowMap(
            original_provider="stripe",
            flow_description="",
            steps=[],
            entities=[],
            api_calls=["stripe.Subscription.create"],
            business_logic="",
            validation_rules=[],
            error_handling=[]
        )
        
        changes = mapper._identify_required_changes(flow_map)
        
        assert "Migrate subscription models to FlowGlad subscription API" in changes