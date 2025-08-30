import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import ast

@dataclass
class ConversionRule:
    pattern: str
    replacement: str
    description: str
    provider: str

@dataclass
class CodeTransformation:
    original_code: str
    transformed_code: str
    file_path: str
    line_range: Tuple[int, int]
    transformation_type: str

class FlowGladConverter:
    def __init__(self):
        self.conversion_rules = self._initialize_conversion_rules()
        
    def _initialize_conversion_rules(self) -> List[ConversionRule]:
        return [
            # Stripe to FlowGlad conversions
            ConversionRule(
                pattern=r"import stripe",
                replacement="import flowglad",
                description="Replace Stripe import",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Stripe\((.*?)\)",
                replacement=r"flowglad.FlowGlad(\1)",
                description="Initialize FlowGlad client",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Customer\.create",
                replacement="flowglad.customers.create",
                description="Create customer",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.PaymentIntent\.create",
                replacement="flowglad.checkout.sessions.create",
                description="Create payment",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Subscription\.create",
                replacement="flowglad.subscriptions.create",
                description="Create subscription",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Price\.create",
                replacement="flowglad.prices.create",
                description="Create price",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Product\.create",
                replacement="flowglad.products.create",
                description="Create product",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Webhook\.construct_event",
                replacement="flowglad.webhooks.verify",
                description="Verify webhook",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Refund\.create",
                replacement="flowglad.refunds.create",
                description="Create refund",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.Invoice",
                replacement="flowglad.invoices",
                description="Invoice operations",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"stripe\.checkout\.Session\.create",
                replacement="flowglad.checkout.sessions.create",
                description="Create checkout session",
                provider="stripe"
            ),
            
            # Square to FlowGlad conversions
            ConversionRule(
                pattern=r"from square\.client import Client",
                replacement="from flowglad import FlowGlad",
                description="Replace Square import",
                provider="square"
            ),
            ConversionRule(
                pattern=r"Client\((.*?)\)",
                replacement=r"FlowGlad(\1)",
                description="Initialize FlowGlad client",
                provider="square"
            ),
            ConversionRule(
                pattern=r"\.payments_api\.create_payment",
                replacement=".payments.create",
                description="Create payment",
                provider="square"
            ),
            ConversionRule(
                pattern=r"\.customers_api\.create_customer",
                replacement=".customers.create",
                description="Create customer",
                provider="square"
            ),
            ConversionRule(
                pattern=r"\.subscriptions_api\.create_subscription",
                replacement=".subscriptions.create",
                description="Create subscription",
                provider="square"
            ),
            ConversionRule(
                pattern=r"\.catalog_api\.upsert_catalog_object",
                replacement=".products.create",
                description="Create product",
                provider="square"
            ),
            ConversionRule(
                pattern=r"\.refunds_api\.refund",
                replacement=".refunds.create",
                description="Create refund",
                provider="square"
            ),
            
            # Environment variable conversions
            ConversionRule(
                pattern=r"STRIPE_SECRET_KEY",
                replacement="FLOWGLAD_SECRET_KEY",
                description="Update API key env var",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"STRIPE_PUBLISHABLE_KEY",
                replacement="FLOWGLAD_PUBLISHABLE_KEY",
                description="Update publishable key env var",
                provider="stripe"
            ),
            ConversionRule(
                pattern=r"SQUARE_ACCESS_TOKEN",
                replacement="FLOWGLAD_SECRET_KEY",
                description="Update Square token env var",
                provider="square"
            ),
            ConversionRule(
                pattern=r"SQUARE_ENVIRONMENT",
                replacement="FLOWGLAD_ENVIRONMENT",
                description="Update Square environment env var",
                provider="square"
            ),
        ]
    
    def convert_code(self, code: str, provider: str, file_type: str = "python") -> CodeTransformation:
        if file_type == "python":
            return self._convert_python(code, provider)
        elif file_type in ["javascript", "typescript"]:
            return self._convert_javascript(code, provider)
        else:
            return self._convert_generic(code, provider)
    
    def _convert_python(self, code: str, provider: str) -> CodeTransformation:
        transformed_code = code
        provider_rules = [r for r in self.conversion_rules if r.provider == provider]
        
        for rule in provider_rules:
            transformed_code = re.sub(rule.pattern, rule.replacement, transformed_code)
        
        transformed_code = self._update_python_params(transformed_code, provider)
        transformed_code = self._add_flowglad_imports(transformed_code)
        
        return CodeTransformation(
            original_code=code,
            transformed_code=transformed_code,
            file_path="",
            line_range=(0, 0),
            transformation_type="full_conversion"
        )
    
    def _convert_javascript(self, code: str, provider: str) -> CodeTransformation:
        js_rules = {
            "stripe": [
                (r"const stripe = require\('stripe'\)", "const flowglad = require('flowglad')"),
                (r"import Stripe from 'stripe'", "import FlowGlad from 'flowglad'"),
                (r"new Stripe\((.*?)\)", r"new FlowGlad(\1)"),
                (r"stripe\.customers\.create", "flowglad.customers.create"),
                (r"stripe\.paymentIntents\.create", "flowglad.checkout.sessions.create"),
                (r"stripe\.subscriptions\.create", "flowglad.subscriptions.create"),
                (r"stripe\.prices\.create", "flowglad.prices.create"),
                (r"stripe\.products\.create", "flowglad.products.create"),
                (r"stripe\.webhooks\.constructEvent", "flowglad.webhooks.verify"),
                (r"process\.env\.STRIPE_SECRET_KEY", "process.env.FLOWGLAD_SECRET_KEY"),
            ],
            "square": [
                (r"const \{ Client \} = require\('square'\)", "const { FlowGlad } = require('flowglad')"),
                (r"import \{ Client \} from 'square'", "import { FlowGlad } from 'flowglad'"),
                (r"new Client\((.*?)\)", r"new FlowGlad(\1)"),
                (r"\.paymentsApi\.createPayment", ".payments.create"),
                (r"\.customersApi\.createCustomer", ".customers.create"),
                (r"\.subscriptionsApi\.createSubscription", ".subscriptions.create"),
                (r"process\.env\.SQUARE_ACCESS_TOKEN", "process.env.FLOWGLAD_SECRET_KEY"),
            ]
        }
        
        transformed_code = code
        for pattern, replacement in js_rules.get(provider, []):
            transformed_code = re.sub(pattern, replacement, transformed_code)
        
        return CodeTransformation(
            original_code=code,
            transformed_code=transformed_code,
            file_path="",
            line_range=(0, 0),
            transformation_type="full_conversion"
        )
    
    def _convert_generic(self, code: str, provider: str) -> CodeTransformation:
        transformed_code = code
        provider_rules = [r for r in self.conversion_rules if r.provider == provider]
        
        for rule in provider_rules:
            transformed_code = re.sub(rule.pattern, rule.replacement, transformed_code)
        
        return CodeTransformation(
            original_code=code,
            transformed_code=transformed_code,
            file_path="",
            line_range=(0, 0),
            transformation_type="generic_conversion"
        )
    
    def _update_python_params(self, code: str, provider: str) -> str:
        param_mappings = {
            "stripe": {
                "amount": "amount",
                "currency": "currency",
                "customer": "customer_id",
                "payment_method": "payment_method_id",
                "description": "description",
                "metadata": "metadata",
                "automatic_payment_methods": "auto_confirm",
                "payment_method_types": "payment_methods",
                "line_items": "items",
                "mode": "checkout_mode",
                "success_url": "success_url",
                "cancel_url": "cancel_url",
                "price": "price_id",
                "quantity": "quantity",
            },
            "square": {
                "amount_money": "amount",
                "source_id": "payment_source",
                "idempotency_key": "idempotency_key",
                "customer_id": "customer_id",
                "location_id": "location_id",
                "reference_id": "reference_id",
                "note": "description",
                "card_id": "payment_method_id",
            }
        }
        
        if provider in param_mappings:
            for old_param, new_param in param_mappings[provider].items():
                code = re.sub(
                    rf'\b{old_param}=',
                    f'{new_param}=',
                    code
                )
        
        return code
    
    def _add_flowglad_imports(self, code: str) -> str:
        lines = code.split('\n')
        import_added = False
        
        for i, line in enumerate(lines):
            if 'import flowglad' in line or 'from flowglad' in line:
                import_added = True
                break
        
        if not import_added:
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    lines.insert(i, 'import flowglad')
                    lines.insert(i+1, 'from dotenv import load_dotenv')
                    lines.insert(i+2, 'load_dotenv()')
                    lines.insert(i+3, '')
                    break
        
        return '\n'.join(lines)
    
    def generate_migration_script(self, transformations: List[CodeTransformation]) -> str:
        script = """#!/usr/bin/env python3
\"\"\"
FlowGlad Migration Script
Automatically converts Stripe/Square code to FlowGlad
\"\"\"

import os
import shutil
from datetime import datetime

def backup_files(files):
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    for file in files:
        shutil.copy2(file, os.path.join(backup_dir, os.path.basename(file)))
    
    return backup_dir

def apply_transformations(transformations):
    for transform in transformations:
        with open(transform['file_path'], 'w') as f:
            f.write(transform['transformed_code'])
    
    print(f"Applied {len(transformations)} transformations")

def update_env_file():
    env_updates = {
        'STRIPE_SECRET_KEY': 'FLOWGLAD_SECRET_KEY',
        'STRIPE_PUBLISHABLE_KEY': 'FLOWGLAD_PUBLISHABLE_KEY',
        'SQUARE_ACCESS_TOKEN': 'FLOWGLAD_SECRET_KEY',
    }
    
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            content = f.read()
        
        for old, new in env_updates.items():
            content = content.replace(old, new)
        
        with open('.env', 'w') as f:
            f.write(content)
        
        print("Updated .env file")

def main():
    transformations = [
"""
        
        for t in transformations:
            script += f"""        {{
            'file_path': '{t.file_path}',
            'transformed_code': '''{t.transformed_code}'''
        }},
"""
        
        script += """    ]
    
    files = [t['file_path'] for t in transformations]
    backup_dir = backup_files(files)
    print(f"Created backup in {backup_dir}")
    
    apply_transformations(transformations)
    update_env_file()
    
    print("Migration complete!")
    print("Run 'pip install flowglad' to install the FlowGlad SDK")

if __name__ == "__main__":
    main()
"""
        
        return script