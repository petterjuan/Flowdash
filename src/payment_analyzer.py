import re
import ast
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

class PaymentProvider(Enum):
    STRIPE = "stripe"
    SQUARE = "square"
    PAYPAL = "paypal"
    BRAINTREE = "braintree"
    UNKNOWN = "unknown"

@dataclass
class PaymentFlow:
    provider: PaymentProvider
    flow_type: str
    file_path: str
    line_start: int
    line_end: int
    methods: List[str] = field(default_factory=list)
    endpoints: List[str] = field(default_factory=list)
    models: List[str] = field(default_factory=list)
    webhooks: List[str] = field(default_factory=list)
    api_keys: List[str] = field(default_factory=list)
    
@dataclass
class PaymentPattern:
    pattern: str
    provider: PaymentProvider
    flow_type: str
    confidence: float

class PaymentLogicAnalyzer:
    def __init__(self):
        self.patterns = self._initialize_patterns()
        
    def _initialize_patterns(self) -> List[PaymentPattern]:
        return [
            PaymentPattern(r"stripe\.Stripe", PaymentProvider.STRIPE, "initialization", 0.9),
            PaymentPattern(r"stripe\.Customer\.create", PaymentProvider.STRIPE, "customer_creation", 0.95),
            PaymentPattern(r"stripe\.PaymentIntent", PaymentProvider.STRIPE, "payment_intent", 0.95),
            PaymentPattern(r"stripe\.Subscription", PaymentProvider.STRIPE, "subscription", 0.95),
            PaymentPattern(r"stripe\.Checkout\.Session", PaymentProvider.STRIPE, "checkout", 0.95),
            PaymentPattern(r"stripe\.Webhook", PaymentProvider.STRIPE, "webhook", 0.9),
            PaymentPattern(r"stripe\.Price", PaymentProvider.STRIPE, "pricing", 0.9),
            PaymentPattern(r"stripe\.Product", PaymentProvider.STRIPE, "product", 0.9),
            PaymentPattern(r"stripe\.Invoice", PaymentProvider.STRIPE, "invoice", 0.9),
            PaymentPattern(r"stripe\.Refund", PaymentProvider.STRIPE, "refund", 0.9),
            
            PaymentPattern(r"square\.Client", PaymentProvider.SQUARE, "initialization", 0.9),
            PaymentPattern(r"square\.models\.CreatePayment", PaymentProvider.SQUARE, "payment_creation", 0.95),
            PaymentPattern(r"square\.models\.CreateCustomer", PaymentProvider.SQUARE, "customer_creation", 0.95),
            PaymentPattern(r"square\.SubscriptionsApi", PaymentProvider.SQUARE, "subscription", 0.95),
            PaymentPattern(r"square\.CheckoutApi", PaymentProvider.SQUARE, "checkout", 0.95),
            PaymentPattern(r"square\.WebhooksApi", PaymentProvider.SQUARE, "webhook", 0.9),
            PaymentPattern(r"square\.CatalogApi", PaymentProvider.SQUARE, "catalog", 0.9),
            PaymentPattern(r"square\.InvoicesApi", PaymentProvider.SQUARE, "invoice", 0.9),
            PaymentPattern(r"square\.RefundsApi", PaymentProvider.SQUARE, "refund", 0.9),
        ]
    
    def analyze_file(self, file_path: str, content: str) -> List[PaymentFlow]:
        flows = []
        
        if file_path.endswith('.py'):
            flows.extend(self._analyze_python(file_path, content))
        elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
            flows.extend(self._analyze_javascript(file_path, content))
        elif file_path.endswith(('.java', '.kt')):
            flows.extend(self._analyze_java(file_path, content))
        
        return flows
    
    def _analyze_python(self, file_path: str, content: str) -> List[PaymentFlow]:
        flows = []
        lines = content.split('\n')
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if 'stripe' in alias.name.lower():
                            flow = self._create_flow(PaymentProvider.STRIPE, "import", file_path, node.lineno)
                            flows.append(flow)
                        elif 'square' in alias.name.lower():
                            flow = self._create_flow(PaymentProvider.SQUARE, "import", file_path, node.lineno)
                            flows.append(flow)
                
                elif isinstance(node, ast.Call):
                    call_str = self._get_call_string(node, lines)
                    for pattern in self.patterns:
                        if re.search(pattern.pattern, call_str):
                            flow = self._create_flow(
                                pattern.provider, 
                                pattern.flow_type, 
                                file_path, 
                                node.lineno
                            )
                            flow.methods.append(call_str)
                            flows.append(flow)
                            
                elif isinstance(node, ast.FunctionDef):
                    func_name = node.name.lower()
                    if any(keyword in func_name for keyword in ['payment', 'charge', 'subscription', 'checkout', 'billing']):
                        flow = self._analyze_function(node, file_path, lines)
                        if flow:
                            flows.append(flow)
        
        except SyntaxError:
            flows.extend(self._fallback_analysis(file_path, content))
        
        return flows
    
    def _analyze_javascript(self, file_path: str, content: str) -> List[PaymentFlow]:
        flows = []
        lines = content.split('\n')
        
        js_patterns = [
            (r"require\(['\"]stripe['\"]\)", PaymentProvider.STRIPE, "import"),
            (r"import.*from ['\"]stripe['\"]", PaymentProvider.STRIPE, "import"),
            (r"require\(['\"]square['\"]\)", PaymentProvider.SQUARE, "import"),
            (r"import.*from ['\"]square['\"]", PaymentProvider.SQUARE, "import"),
            (r"stripe\.customers\.create", PaymentProvider.STRIPE, "customer_creation"),
            (r"stripe\.paymentIntents\.create", PaymentProvider.STRIPE, "payment_intent"),
            (r"stripe\.subscriptions\.create", PaymentProvider.STRIPE, "subscription"),
            (r"stripe\.checkout\.sessions\.create", PaymentProvider.STRIPE, "checkout"),
            (r"square\.paymentsApi\.createPayment", PaymentProvider.SQUARE, "payment_creation"),
            (r"square\.customersApi\.createCustomer", PaymentProvider.SQUARE, "customer_creation"),
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern, provider, flow_type in js_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    flow = self._create_flow(provider, flow_type, file_path, i)
                    flow.methods.append(line.strip())
                    flows.append(flow)
        
        return flows
    
    def _analyze_java(self, file_path: str, content: str) -> List[PaymentFlow]:
        flows = []
        lines = content.split('\n')
        
        java_patterns = [
            (r"import com\.stripe\.", PaymentProvider.STRIPE, "import"),
            (r"import com\.squareup\.", PaymentProvider.SQUARE, "import"),
            (r"Stripe\.apiKey", PaymentProvider.STRIPE, "initialization"),
            (r"new SquareClient\.Builder", PaymentProvider.SQUARE, "initialization"),
            (r"Customer\.create", PaymentProvider.STRIPE, "customer_creation"),
            (r"PaymentIntent\.create", PaymentProvider.STRIPE, "payment_intent"),
            (r"Subscription\.create", PaymentProvider.STRIPE, "subscription"),
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern, provider, flow_type in java_patterns:
                if re.search(pattern, line):
                    flow = self._create_flow(provider, flow_type, file_path, i)
                    flow.methods.append(line.strip())
                    flows.append(flow)
        
        return flows
    
    def _analyze_function(self, node: ast.FunctionDef, file_path: str, lines: List[str]) -> Optional[PaymentFlow]:
        provider = PaymentProvider.UNKNOWN
        flow_type = "unknown"
        methods = []
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_str = self._get_call_string(child, lines)
                for pattern in self.patterns:
                    if re.search(pattern.pattern, call_str):
                        provider = pattern.provider
                        flow_type = pattern.flow_type
                        methods.append(call_str)
        
        if provider != PaymentProvider.UNKNOWN:
            flow = self._create_flow(provider, flow_type, file_path, node.lineno)
            flow.line_end = node.end_lineno or node.lineno
            flow.methods = methods
            return flow
        
        return None
    
    def _get_call_string(self, node: ast.Call, lines: List[str]) -> str:
        if hasattr(node.func, 'id'):
            return node.func.id
        elif hasattr(node.func, 'attr'):
            parts = []
            current = node.func
            while hasattr(current, 'value'):
                if hasattr(current, 'attr'):
                    parts.append(current.attr)
                current = current.value
                if hasattr(current, 'id'):
                    parts.append(current.id)
                    break
            return '.'.join(reversed(parts))
        return ""
    
    def _create_flow(self, provider: PaymentProvider, flow_type: str, 
                    file_path: str, line_start: int) -> PaymentFlow:
        return PaymentFlow(
            provider=provider,
            flow_type=flow_type,
            file_path=file_path,
            line_start=line_start,
            line_end=line_start
        )
    
    def _fallback_analysis(self, file_path: str, content: str) -> List[PaymentFlow]:
        flows = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            for pattern in self.patterns:
                if re.search(pattern.pattern, line):
                    flow = self._create_flow(
                        pattern.provider,
                        pattern.flow_type,
                        file_path,
                        i
                    )
                    flow.methods.append(line.strip())
                    flows.append(flow)
        
        return flows
    
    def extract_payment_architecture(self, flows: List[PaymentFlow]) -> Dict[str, Any]:
        architecture = {
            "providers": {},
            "endpoints": [],
            "webhooks": [],
            "models": [],
            "flow_summary": {}
        }
        
        for flow in flows:
            provider_name = flow.provider.value
            
            if provider_name not in architecture["providers"]:
                architecture["providers"][provider_name] = {
                    "flows": [],
                    "files": set(),
                    "methods": set()
                }
            
            architecture["providers"][provider_name]["flows"].append(flow.flow_type)
            architecture["providers"][provider_name]["files"].add(flow.file_path)
            architecture["providers"][provider_name]["methods"].update(flow.methods)
            
            architecture["endpoints"].extend(flow.endpoints)
            architecture["webhooks"].extend(flow.webhooks)
            architecture["models"].extend(flow.models)
            
            if flow.flow_type not in architecture["flow_summary"]:
                architecture["flow_summary"][flow.flow_type] = 0
            architecture["flow_summary"][flow.flow_type] += 1
        
        for provider in architecture["providers"]:
            architecture["providers"][provider]["files"] = list(architecture["providers"][provider]["files"])
            architecture["providers"][provider]["methods"] = list(architecture["providers"][provider]["methods"])
        
        return architecture