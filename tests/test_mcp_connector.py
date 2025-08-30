import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_connector import GitHubMCPConnector, MCPConfig
from github import Repository


@pytest.fixture
def mock_config():
    return MCPConfig(
        server_url="http://localhost:3000",
        github_token="test_token_123"
    )


@pytest.fixture
def mock_github():
    with patch('mcp_connector.Github') as mock:
        yield mock


@pytest.fixture
def connector(mock_config, mock_github):
    return GitHubMCPConnector(mock_config)


class TestGitHubMCPConnector:
    
    @pytest.mark.unit
    async def test_authenticate_success(self, connector, mock_github):
        mock_user = Mock()
        mock_github.return_value.get_user.return_value = mock_user
        
        result = await connector.authenticate()
        
        assert result is True
        assert connector._authenticated is True
        mock_github.return_value.get_user.assert_called_once()
    
    @pytest.mark.unit
    async def test_authenticate_failure(self, connector, mock_github):
        mock_github.return_value.get_user.side_effect = Exception("Auth failed")
        
        result = await connector.authenticate()
        
        assert result is False
        assert connector._authenticated is False
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_to_mcp(self, connector):
        with patch.object(connector.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_response.json.return_value = {"status": "connected"}
            mock_post.return_value = mock_response
            
            result = await connector.connect_to_mcp()
            
            assert result == {"status": "connected"}
            mock_post.assert_called_once_with(
                "http://localhost:3000/connect",
                json={"provider": "github", "token": "test_token_123"}
            )
    
    @pytest.mark.unit
    async def test_get_repository(self, connector, mock_github):
        mock_repo = Mock(spec=Repository)
        mock_github.return_value.get_repo.return_value = mock_repo
        
        result = await connector.get_repository("owner/repo")
        
        assert result == mock_repo
        mock_github.return_value.get_repo.assert_called_once_with("owner/repo")
    
    @pytest.mark.unit
    async def test_list_repository_files(self, connector):
        mock_repo = Mock(spec=Repository)
        
        mock_file1 = Mock()
        mock_file1.type = "file"
        mock_file1.path = "src/payment.py"
        mock_file1.name = "payment.py"
        mock_file1.size = 1024
        mock_file1.sha = "abc123"
        
        mock_dir = Mock()
        mock_dir.type = "dir"
        mock_dir.path = "tests"
        
        mock_file2 = Mock()
        mock_file2.type = "file"
        mock_file2.path = "tests/test_payment.py"
        mock_file2.name = "test_payment.py"
        mock_file2.size = 512
        mock_file2.sha = "def456"
        
        mock_repo.get_contents.side_effect = [
            [mock_file1, mock_dir],
            [mock_file2]
        ]
        
        files = await connector.list_repository_files(mock_repo)
        
        assert len(files) == 2
        assert files[0]["path"] == "src/payment.py"
        assert files[1]["path"] == "tests/test_payment.py"
    
    @pytest.mark.unit
    async def test_get_file_content(self, connector):
        mock_repo = Mock(spec=Repository)
        mock_file = Mock()
        mock_file.decoded_content = b"import stripe\nstripe.api_key = 'sk_test'"
        mock_repo.get_contents.return_value = mock_file
        
        content = await connector.get_file_content(mock_repo, "payment.py")
        
        assert content == "import stripe\nstripe.api_key = 'sk_test'"
        mock_repo.get_contents.assert_called_once_with("payment.py")
    
    @pytest.mark.unit
    async def test_search_payment_files(self, connector, mock_github):
        mock_result1 = Mock()
        mock_result1.path = "src/stripe_payment.py"
        mock_result1.repository.full_name = "owner/repo"
        mock_result1.sha = "abc123"
        mock_result1.score = 1.0
        
        mock_result2 = Mock()
        mock_result2.path = "lib/square_checkout.js"
        mock_result2.repository.full_name = "owner/repo"
        mock_result2.sha = "def456"
        mock_result2.score = 0.9
        
        mock_github.return_value.search_code.return_value = [mock_result1, mock_result2]
        
        mock_repo = Mock(spec=Repository)
        mock_repo.full_name = "owner/repo"
        
        payment_files = await connector.search_payment_files(mock_repo)
        
        assert len(payment_files) == 2
        assert payment_files[0]["path"] == "src/stripe_payment.py"
        assert payment_files[1]["path"] == "lib/square_checkout.js"
    
    @pytest.mark.unit
    async def test_create_branch(self, connector):
        mock_repo = Mock(spec=Repository)
        mock_ref = Mock()
        mock_ref.object.sha = "main123"
        mock_repo.get_git_ref.return_value = mock_ref
        mock_repo.create_git_ref.return_value = Mock()
        
        branch_name = await connector.create_branch(mock_repo, "flowglad-migration")
        
        assert branch_name == "flowglad-migration"
        mock_repo.get_git_ref.assert_called_once_with("heads/main")
        mock_repo.create_git_ref.assert_called_once_with(
            ref="refs/heads/flowglad-migration",
            sha="main123"
        )
    
    @pytest.mark.unit
    async def test_update_existing_file(self, connector):
        mock_repo = Mock(spec=Repository)
        mock_file = Mock()
        mock_file.sha = "old_sha"
        mock_repo.get_contents.return_value = mock_file
        
        mock_result = {
            "commit": Mock(sha="new_sha"),
            "content": Mock(path="payment.py")
        }
        mock_repo.update_file.return_value = mock_result
        
        result = await connector.update_file(
            mock_repo, 
            "payment.py", 
            "new content", 
            "Update payment", 
            "feature-branch"
        )
        
        assert result["commit"] == "new_sha"
        assert result["file"] == "payment.py"
    
    @pytest.mark.unit
    async def test_create_new_file(self, connector):
        mock_repo = Mock(spec=Repository)
        mock_repo.get_contents.side_effect = Exception("File not found")
        
        mock_result = {
            "commit": Mock(sha="new_sha"),
            "content": Mock(path="new_file.py")
        }
        mock_repo.create_file.return_value = mock_result
        
        result = await connector.update_file(
            mock_repo,
            "new_file.py",
            "new content",
            "Create new file",
            "feature-branch"
        )
        
        assert result["commit"] == "new_sha"
        assert result["file"] == "new_file.py"
    
    @pytest.mark.unit
    async def test_create_pull_request(self, connector):
        mock_repo = Mock(spec=Repository)
        mock_pr = Mock()
        mock_pr.number = 42
        mock_pr.html_url = "https://github.com/owner/repo/pull/42"
        mock_pr.state = "open"
        mock_repo.create_pull.return_value = mock_pr
        
        result = await connector.create_pull_request(
            mock_repo,
            "Migrate to FlowGlad",
            "This PR migrates payment processing",
            "flowglad-migration"
        )
        
        assert result["number"] == 42
        assert result["url"] == "https://github.com/owner/repo/pull/42"
        assert result["state"] == "open"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close(self, connector):
        with patch.object(connector.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await connector.close()
            mock_close.assert_called_once()