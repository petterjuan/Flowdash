import pytest
from unittest.mock import Mock, patch, AsyncMock, mock_open
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from morph_editor import MorphLLMEditor, EditRequest, EditResult


@pytest.fixture
def mock_genai():
    with patch('morph_editor.genai') as mock:
        yield mock


@pytest.fixture
def editor(mock_genai):
    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test_key', 'GEMINI_MODEL': 'gemini-2.5-flash-lite'}):
        return MorphLLMEditor()


class TestMorphLLMEditor:
    
    @pytest.mark.unit
    def test_initialization(self, mock_genai):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test_key', 'GEMINI_MODEL': 'gemini-2.5-flash-lite'}):
            editor = MorphLLMEditor()
            
            mock_genai.configure.assert_called_once_with(api_key='test_key')
            mock_genai.GenerativeModel.assert_called_once_with('gemini-2.5-flash-lite')
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_apply_edits_success(self, editor):
        edit_request = EditRequest(
            file_path="payment.py",
            original_code="stripe.Customer.create()",
            target_code="flowglad.customers.create()",
            description="Convert to FlowGlad"
        )
        
        with patch('morph_editor.os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="stripe.Customer.create()")):
                mock_response = Mock()
                mock_response.text = "flowglad.customers.create()"
                editor.model.generate_content = Mock(return_value=mock_response)
                
                results = await editor.apply_edits("/repo", [edit_request])
                
                assert len(results) == 1
                assert results[0].success is True
                assert results[0].file_path == "payment.py"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_apply_edits_file_not_found(self, editor):
        edit_request = EditRequest(
            file_path="nonexistent.py",
            original_code="code",
            target_code="new_code",
            description="Test"
        )
        
        with patch('morph_editor.os.path.exists', return_value=False):
            results = await editor.apply_edits("/repo", [edit_request])
            
            assert len(results) == 1
            assert results[0].success is False
            assert "File not found" in results[0].error
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_apply_single_edit(self, editor):
        edit_request = EditRequest(
            file_path="test.py",
            original_code="old_code",
            target_code="new_code",
            description="Test edit"
        )
        
        with patch('morph_editor.os.path.join', return_value="/repo/test.py"):
            with patch('morph_editor.os.path.exists', return_value=True):
                with patch('builtins.open', mock_open(read_data="old_code")):
                    mock_response = Mock()
                    mock_response.text = "new_code"
                    editor.model.generate_content = Mock(return_value=mock_response)
                    
                    result = await editor._apply_single_edit("/repo", edit_request)
                    
                    assert result.success is True
                    assert result.file_path == "test.py"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_edit_with_code_block(self, editor):
        full_content = "import stripe\nstripe.Customer.create()"
        old_code = "stripe.Customer.create()"
        new_code = "flowglad.customers.create()"
        
        mock_response = Mock()
        mock_response.text = """
```python
import flowglad
flowglad.customers.create()
```
"""
        editor.model.generate_content = Mock(return_value=mock_response)
        
        result = await editor._generate_edit(full_content, old_code, new_code, "Convert to FlowGlad")
        
        assert "import flowglad" in result
        assert "flowglad.customers.create()" in result
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_edit_without_code_block(self, editor):
        full_content = "old content"
        
        mock_response = Mock()
        mock_response.text = "new content"
        editor.model.generate_content = Mock(return_value=mock_response)
        
        result = await editor._generate_edit(full_content, "old", "new", "Test")
        
        assert result == "new content"
    
    @pytest.mark.unit
    def test_extract_changes(self, editor):
        original = "line1\nline2\nline3"
        modified = "line1\nline2_modified\nline3\nline4"
        
        changes = editor._extract_changes(original, modified)
        
        assert any("Removed: line2" in change for change in changes)
        assert any("Added: line2_modified" in change for change in changes)
        assert any("Added: line4" in change for change in changes)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_convert_files(self, editor):
        transformations = [
            {
                "file_path": "file1.py",
                "original_code": "old1",
                "transformed_code": "new1",
                "description": "Convert 1"
            },
            {
                "file_path": "file2.py",
                "original_code": "old2",
                "transformed_code": "new2",
                "description": "Convert 2"
            }
        ]
        
        with patch.object(editor, '_apply_single_edit', new_callable=AsyncMock) as mock_apply:
            mock_apply.side_effect = [
                EditResult(success=True, file_path="file1.py", changes_made=[]),
                EditResult(success=False, file_path="file2.py", changes_made=[], error="Error")
            ]
            
            result = await editor.batch_convert_files("/repo", transformations)
            
            assert result["total_files"] == 2
            assert result["successful"] == 1
            assert result["failed"] == 1
            assert len(result["results"]) == 2
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_validate_changes_python_valid(self, editor):
        with patch('morph_editor.os.path.join', return_value="/repo/test.py"):
            with patch('builtins.open', mock_open(read_data="import flowglad\nprint('hello')")):
                validations = await editor.validate_changes("/repo", "test.py")
                
                assert validations["syntax_valid"] is True
                assert validations["imports_resolved"] is True
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_validate_changes_python_invalid_syntax(self, editor):
        with patch('morph_editor.os.path.join', return_value="/repo/test.py"):
            with patch('builtins.open', mock_open(read_data="import flowglad\nprint('hello")):
                validations = await editor.validate_changes("/repo", "test.py")
                
                assert validations["syntax_valid"] is False
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_validate_changes_error(self, editor):
        with patch('morph_editor.os.path.join', return_value="/repo/test.py"):
            with patch('builtins.open', side_effect=FileNotFoundError("Not found")):
                validations = await editor.validate_changes("/repo", "test.py")
                
                assert "error" in validations
                assert validations["syntax_valid"] is False
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_pull_request_description(self, editor):
        changes = [
            EditResult(success=True, file_path="file1.py", changes_made=["Added flowglad"]),
            EditResult(success=True, file_path="file2.py", changes_made=["Removed stripe"]),
            EditResult(success=False, file_path="file3.py", changes_made=[], error="Failed")
        ]
        
        description = await editor.create_pull_request_description(changes)
        
        assert "## FlowGlad Migration" in description
        assert "file1.py" in description
        assert "file2.py" in description
        assert "file3.py" in description
        assert "### Failed Conversions" in description
        assert "### Testing Required" in description
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_pull_request_description_many_files(self, editor):
        changes = [
            EditResult(success=True, file_path=f"file{i}.py", changes_made=[])
            for i in range(15)
        ]
        
        description = await editor.create_pull_request_description(changes)
        
        assert "15 files successfully converted" in description
        assert "... and 5 more" in description
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_client_timeout_configuration(self, editor):
        assert editor.client.timeout == 60