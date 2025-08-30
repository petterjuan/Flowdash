from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class PaymentFlowMap:
    original_provider: str
    flow_description: str
    steps: List[Dict[str, Any]]
    entities: List[str]
    api_calls: List[str]
    business_logic: str
    validation_rules: List[str]
    error_handling: List[str]

class PaymentFlowMapper:
    def __init__(self, llm_provider: str = "gemini"):
        self.llm_provider = llm_provider
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.client = genai.GenerativeModel(model_name)
    
    def map_payment_flow(self, code_content: str, provider: str, flow_type: str) -> PaymentFlowMap:
        prompt = self._create_mapping_prompt(code_content, provider, flow_type)
        response = self._get_llm_response(prompt)
        return self._parse_flow_response(response, provider)
    
    def _create_mapping_prompt(self, code: str, provider: str, flow_type: str) -> str:
        return f"""Analyze this {provider} {flow_type} payment implementation and extract:

1. Business flow steps (in order)
2. Data entities involved
3. API calls made
4. Business logic rules
5. Validation checks
6. Error handling

Code:
```
{code}
```

Provide a structured analysis in JSON format with these fields:
- steps: Array of flow steps with description and code references
- entities: Array of data entities (customer, payment, subscription, etc.)
- api_calls: Array of API endpoints/methods called
- business_logic: Summary of core business rules
- validation_rules: Array of validation checks
- error_handling: Array of error scenarios handled

Focus on understanding the payment flow logic, not just the code structure."""
    
    def _get_llm_response(self, prompt: str) -> str:
        response = self.client.generate_content(prompt)
        return response.text
    
    def _parse_flow_response(self, response: str, provider: str) -> PaymentFlowMap:
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response
            
            data = json.loads(json_str.strip())
            
            return PaymentFlowMap(
                original_provider=provider,
                flow_description=data.get("flow_description", ""),
                steps=data.get("steps", []),
                entities=data.get("entities", []),
                api_calls=data.get("api_calls", []),
                business_logic=data.get("business_logic", ""),
                validation_rules=data.get("validation_rules", []),
                error_handling=data.get("error_handling", [])
            )
        except Exception as e:
            return PaymentFlowMap(
                original_provider=provider,
                flow_description=f"Error parsing flow: {str(e)}",
                steps=[],
                entities=[],
                api_calls=[],
                business_logic="",
                validation_rules=[],
                error_handling=[]
            )
    
    def generate_documentation(self, flow_map: PaymentFlowMap) -> str:
        doc = f"""# Payment Flow Documentation

## Original Provider: {flow_map.original_provider}

## Flow Description
{flow_map.flow_description}

## Process Steps
"""
        for i, step in enumerate(flow_map.steps, 1):
            doc += f"{i}. {step.get('description', 'Step ' + str(i))}\n"
            if 'code_reference' in step:
                doc += f"   - Code: {step['code_reference']}\n"
        
        doc += f"""

## Data Entities
{', '.join(flow_map.entities)}

## API Calls
"""
        for call in flow_map.api_calls:
            doc += f"- {call}\n"
        
        doc += f"""

## Business Logic
{flow_map.business_logic}

## Validation Rules
"""
        for rule in flow_map.validation_rules:
            doc += f"- {rule}\n"
        
        doc += f"""

## Error Handling
"""
        for error in flow_map.error_handling:
            doc += f"- {error}\n"
        
        return doc
    
    def compare_with_flowglad(self, flow_map: PaymentFlowMap) -> Dict[str, Any]:
        flowglad_mapping = {
            "stripe": {
                "customer_creation": "flowglad.customers.create",
                "payment_intent": "flowglad.checkout.create",
                "subscription": "flowglad.subscriptions.create",
                "webhook": "flowglad.webhooks.handle",
                "refund": "flowglad.refunds.create"
            },
            "square": {
                "payment_creation": "flowglad.payments.create",
                "customer_creation": "flowglad.customers.create",
                "subscription": "flowglad.subscriptions.create",
                "checkout": "flowglad.checkout.create",
                "refund": "flowglad.refunds.create"
            }
        }
        
        provider_lower = flow_map.original_provider.lower()
        equivalents = []
        
        for api_call in flow_map.api_calls:
            for pattern, flowglad_method in flowglad_mapping.get(provider_lower, {}).items():
                if pattern in api_call.lower():
                    equivalents.append({
                        "original": api_call,
                        "flowglad": flowglad_method
                    })
        
        return {
            "provider": flow_map.original_provider,
            "flowglad_equivalents": equivalents,
            "migration_complexity": self._assess_complexity(flow_map),
            "required_changes": self._identify_required_changes(flow_map)
        }
    
    def _assess_complexity(self, flow_map: PaymentFlowMap) -> str:
        num_steps = len(flow_map.steps)
        num_entities = len(flow_map.entities)
        num_validations = len(flow_map.validation_rules)
        
        complexity_score = num_steps + num_entities + num_validations
        
        if complexity_score < 10:
            return "Low"
        elif complexity_score < 25:
            return "Medium"
        else:
            return "High"
    
    def _identify_required_changes(self, flow_map: PaymentFlowMap) -> List[str]:
        changes = []
        
        if "webhook" in str(flow_map.api_calls).lower():
            changes.append("Update webhook endpoints to FlowGlad format")
        
        if "subscription" in str(flow_map.api_calls).lower():
            changes.append("Migrate subscription models to FlowGlad subscription API")
        
        if "customer" in str(flow_map.entities).lower():
            changes.append("Convert customer data model to FlowGlad schema")
        
        if flow_map.validation_rules:
            changes.append("Adapt validation rules to FlowGlad requirements")
        
        changes.append("Update API authentication to use FlowGlad keys")
        changes.append("Replace provider-specific SDKs with FlowGlad SDK")
        
        return changes