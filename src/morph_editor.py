import os
import httpx
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

@dataclass
class EditRequest:
    file_path: str
    original_code: str
    target_code: str
    description: str
    line_range: Optional[tuple] = None

@dataclass
class EditResult:
    success: bool
    file_path: str
    changes_made: List[str]
    error: Optional[str] = None

class MorphLLMEditor:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.model = genai.GenerativeModel(model_name)
        self.morph_api_key = os.getenv("MORPH_API_KEY", "")
        self.client = httpx.AsyncClient(timeout=60)
    
    async def apply_edits(self, repo_path: str, edits: List[EditRequest]) -> List[EditResult]:
        results = []
        
        for edit in edits:
            result = await self._apply_single_edit(repo_path, edit)
            results.append(result)
        
        return results
    
    async def _apply_single_edit(self, repo_path: str, edit: EditRequest) -> EditResult:
        try:
            full_path = os.path.join(repo_path, edit.file_path)
            
            if not os.path.exists(full_path):
                return EditResult(
                    success=False,
                    file_path=edit.file_path,
                    changes_made=[],
                    error=f"File not found: {edit.file_path}"
                )
            
            with open(full_path, 'r') as f:
                current_content = f.read()
            
            modified_content = await self._generate_edit(
                current_content,
                edit.original_code,
                edit.target_code,
                edit.description
            )
            
            with open(full_path, 'w') as f:
                f.write(modified_content)
            
            changes = self._extract_changes(current_content, modified_content)
            
            return EditResult(
                success=True,
                file_path=edit.file_path,
                changes_made=changes
            )
            
        except Exception as e:
            return EditResult(
                success=False,
                file_path=edit.file_path,
                changes_made=[],
                error=str(e)
            )
    
    async def _generate_edit(self, full_content: str, old_code: str, 
                            new_code: str, description: str) -> str:
        prompt = f"""You are a code editor. Apply the following transformation to the code.

Current file content:
```
{full_content}
```

Replace this code:
```
{old_code}
```

With this code:
```
{new_code}
```

Description of change: {description}

Return ONLY the complete modified file content, preserving all other parts unchanged.
Maintain exact formatting, indentation, and structure of the original file.
"""
        
        response = self.model.generate_content(prompt)
        content = response.text
        
        if "```" in content:
            lines = content.split('\n')
            start_idx = -1
            end_idx = -1
            
            for i, line in enumerate(lines):
                if line.startswith("```") and start_idx == -1:
                    start_idx = i
                elif line.startswith("```") and start_idx != -1:
                    end_idx = i
                    break
            
            if start_idx != -1 and end_idx != -1:
                return '\n'.join(lines[start_idx+1:end_idx])
        
        return content
    
    def _extract_changes(self, original: str, modified: str) -> List[str]:
        original_lines = original.split('\n')
        modified_lines = modified.split('\n')
        changes = []
        
        import difflib
        differ = difflib.unified_diff(
            original_lines,
            modified_lines,
            lineterm='',
            n=0
        )
        
        for line in differ:
            if line.startswith('+') and not line.startswith('+++'):
                changes.append(f"Added: {line[1:]}")
            elif line.startswith('-') and not line.startswith('---'):
                changes.append(f"Removed: {line[1:]}")
        
        return changes[:10]
    
    async def batch_convert_files(self, repo_path: str, 
                                 transformations: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(transformations)
        successful = 0
        failed = 0
        results = []
        
        for transform in transformations:
            edit = EditRequest(
                file_path=transform['file_path'],
                original_code=transform['original_code'],
                target_code=transform['transformed_code'],
                description=transform.get('description', 'Convert to FlowGlad')
            )
            
            result = await self._apply_single_edit(repo_path, edit)
            results.append(result)
            
            if result.success:
                successful += 1
            else:
                failed += 1
        
        return {
            "total_files": total,
            "successful": successful,
            "failed": failed,
            "results": results
        }
    
    async def validate_changes(self, repo_path: str, file_path: str) -> Dict[str, Any]:
        full_path = os.path.join(repo_path, file_path)
        
        validations = {
            "syntax_valid": False,
            "imports_resolved": False,
            "no_undefined_vars": False,
            "tests_pass": False
        }
        
        try:
            with open(full_path, 'r') as f:
                content = f.read()
            
            if file_path.endswith('.py'):
                import ast
                try:
                    ast.parse(content)
                    validations["syntax_valid"] = True
                except SyntaxError:
                    pass
            
            if 'import flowglad' in content or 'from flowglad' in content:
                validations["imports_resolved"] = True
            
            return validations
            
        except Exception as e:
            return {
                "error": str(e),
                **validations
            }
    
    async def create_pull_request_description(self, changes: List[EditResult]) -> str:
        successful_files = [r.file_path for r in changes if r.success]
        failed_files = [r.file_path for r in changes if not r.success]
        
        description = f"""## FlowGlad Migration

This PR migrates the payment processing from Stripe/Square to FlowGlad.

### Files Modified
{len(successful_files)} files successfully converted:
"""
        
        for file in successful_files[:10]:
            description += f"- {file}\n"
        
        if len(successful_files) > 10:
            description += f"... and {len(successful_files) - 10} more\n"
        
        if failed_files:
            description += f"\n### Failed Conversions\n"
            for file in failed_files:
                description += f"- {file}\n"
        
        description += """

### Changes Made
- Replaced Stripe/Square imports with FlowGlad
- Updated API client initialization
- Converted payment method calls to FlowGlad equivalents
- Updated environment variables
- Adapted parameter names to FlowGlad schema

### Testing Required
- [ ] Run existing payment tests
- [ ] Test checkout flow
- [ ] Verify webhook handling
- [ ] Check subscription management
- [ ] Validate refund processing

### Migration Notes
- Ensure FlowGlad API keys are configured
- Update webhook endpoints in FlowGlad dashboard
- Review and test all payment flows before deployment
"""
        
        return description