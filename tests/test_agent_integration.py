import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent import (
    FlowGladMigrationAgent, 
    AgentConfig, 
    AgentStatus,
    MigrationReport
)
from payment_analyzer import PaymentFlow, PaymentProvider
from flowglad_converter import CodeTransformation


@pytest.fixture
def agent_config():
    return AgentConfig(
        github_token="test_token",
        repo_name="test/repo",
        target_branch="flowglad-migration",
        create_pr=True,
        auto_apply=True,
        llm_provider="gemini"
    )


@pytest.fixture
def agent(agent_config):
    with patch.dict(os.environ, {
        'GITHUB_TOKEN': 'test_token',
        'GEMINI_API_KEY': 'test_key',
        'GEMINI_MODEL': 'gemini-2.5-flash-lite',
        'MCP_SERVER_URL': 'http://localhost:3000'
    }):
        return FlowGladMigrationAgent(agent_config)


class TestFlowGladMigrationAgent:
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_agent_initialization(self, agent, agent_config):
        assert agent.config == agent_config
        assert agent.status == AgentStatus.IDLE
        assert agent.report is None
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_successful_migration_flow(self, agent):
        # Mock authentication
        with patch.object(agent.mcp_connector, 'authenticate', new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = True
            
            with patch.object(agent.mcp_connector, 'connect_to_mcp', new_callable=AsyncMock):
                
                # Mock repository analysis
                mock_flows = [
                    PaymentFlow(
                        provider=PaymentProvider.STRIPE,
                        flow_type="payment_intent",
                        file_path="payment.py",
                        line_start=10,
                        line_end=20
                    )
                ]
                
                with patch.object(agent, '_analyze_repository', new_callable=AsyncMock) as mock_analyze:
                    mock_analyze.return_value = mock_flows
                    
                    # Mock flow mapping
                    with patch.object(agent, '_map_flows', new_callable=AsyncMock) as mock_map:
                        mock_map.return_value = [{"flow": f, "map": Mock(), "comparison": Mock()} for f in mock_flows]
                        
                        # Mock code conversion
                        mock_transformations = [
                            CodeTransformation(
                                original_code="stripe code",
                                transformed_code="flowglad code",
                                file_path="payment.py",
                                line_range=(10, 20),
                                transformation_type="conversion"
                            )
                        ]
                        
                        with patch.object(agent, '_convert_code', new_callable=AsyncMock) as mock_convert:
                            mock_convert.return_value = mock_transformations
                            
                            # Mock applying changes
                            with patch.object(agent, '_apply_changes', new_callable=AsyncMock) as mock_apply:
                                mock_apply.return_value = "https://github.com/test/repo/pull/1"
                                
                                # Run the agent
                                report = await agent.run()
                                
                                # Verify the flow
                                mock_auth.assert_called_once()
                                mock_analyze.assert_called_once()
                                mock_map.assert_called_once()
                                mock_convert.assert_called_once()
                                mock_apply.assert_called_once()
                                
                                # Check report
                                assert report.repo_name == "test/repo"
                                assert report.files_analyzed > 0
                                assert report.pr_url == "https://github.com/test/repo/pull/1"
                                assert agent.status == AgentStatus.COMPLETE
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_authentication_failure(self, agent):
        with patch.object(agent.mcp_connector, 'authenticate', new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = False
            
            with pytest.raises(Exception, match="GitHub authentication failed"):
                await agent.run()
            
            assert agent.status == AgentStatus.ERROR
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_analyze_repository(self, agent):
        mock_repo = Mock()
        mock_repo.full_name = "test/repo"
        
        with patch.object(agent.mcp_connector, 'get_repository', new_callable=AsyncMock) as mock_get_repo:
            mock_get_repo.return_value = mock_repo
            
            mock_payment_files = [
                {"path": "payment.py", "repository": "test/repo", "sha": "abc123", "score": 1.0},
                {"path": "checkout.js", "repository": "test/repo", "sha": "def456", "score": 0.9}
            ]
            
            with patch.object(agent.mcp_connector, 'search_payment_files', new_callable=AsyncMock) as mock_search:
                mock_search.return_value = mock_payment_files
                
                with patch.object(agent.mcp_connector, 'get_file_content', new_callable=AsyncMock) as mock_get_content:
                    mock_get_content.side_effect = [
                        "import stripe\nstripe.Customer.create()",
                        "const stripe = require('stripe')"
                    ]
                    
                    flows = await agent._analyze_repository()
                    
                    assert len(flows) > 0
                    mock_get_repo.assert_called_once_with("test/repo")
                    mock_search.assert_called_once()
                    assert mock_get_content.call_count == 2
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_map_flows(self, agent):
        mock_flow = PaymentFlow(
            provider=PaymentProvider.STRIPE,
            flow_type="payment",
            file_path="payment.py",
            line_start=1,
            line_end=10
        )
        
        mock_repo = Mock()
        with patch.object(agent.mcp_connector, 'get_repository', new_callable=AsyncMock) as mock_get_repo:
            mock_get_repo.return_value = mock_repo
            
            with patch.object(agent.mcp_connector, 'get_file_content', new_callable=AsyncMock) as mock_get_content:
                mock_get_content.return_value = "stripe.Customer.create()"
                
                with patch.object(agent.mapper, 'map_payment_flow') as mock_map:
                    mock_flow_map = Mock()
                    mock_map.return_value = mock_flow_map
                    
                    with patch.object(agent.mapper, 'compare_with_flowglad') as mock_compare:
                        mock_comparison = {"provider": "stripe", "flowglad_equivalents": []}
                        mock_compare.return_value = mock_comparison
                        
                        flow_maps = await agent._map_flows([mock_flow])
                        
                        assert len(flow_maps) == 1
                        assert flow_maps[0]["flow"] == mock_flow
                        assert flow_maps[0]["comparison"] == mock_comparison
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_convert_code(self, agent):
        mock_flows = [
            PaymentFlow(
                provider=PaymentProvider.STRIPE,
                flow_type="payment",
                file_path="payment.py",
                line_start=1,
                line_end=10
            ),
            PaymentFlow(
                provider=PaymentProvider.SQUARE,
                flow_type="checkout",
                file_path="checkout.py",
                line_start=1,
                line_end=20
            )
        ]
        
        mock_repo = Mock()
        with patch.object(agent.mcp_connector, 'get_repository', new_callable=AsyncMock) as mock_get_repo:
            mock_get_repo.return_value = mock_repo
            
            with patch.object(agent.mcp_connector, 'get_file_content', new_callable=AsyncMock) as mock_get_content:
                mock_get_content.side_effect = [
                    "import stripe\nstripe.Customer.create()",
                    "from square.client import Client"
                ]
                
                with patch.object(agent.converter, 'convert_code') as mock_convert:
                    mock_convert.side_effect = [
                        CodeTransformation(
                            original_code="stripe code",
                            transformed_code="flowglad code 1",
                            file_path="",
                            line_range=(0, 0),
                            transformation_type="conversion"
                        ),
                        CodeTransformation(
                            original_code="square code",
                            transformed_code="flowglad code 2",
                            file_path="",
                            line_range=(0, 0),
                            transformation_type="conversion"
                        )
                    ]
                    
                    transformations = await agent._convert_code(mock_flows)
                    
                    assert len(transformations) == 2
                    assert transformations[0].file_path == "payment.py"
                    assert transformations[1].file_path == "checkout.py"
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_apply_changes(self, agent):
        mock_transformations = [
            CodeTransformation(
                original_code="old",
                transformed_code="new",
                file_path="test.py",
                line_range=(1, 10),
                transformation_type="conversion"
            )
        ]
        
        mock_repo = Mock()
        mock_repo.clone_url = "https://github.com/test/repo.git"
        
        with patch.object(agent.mcp_connector, 'get_repository', new_callable=AsyncMock) as mock_get_repo:
            mock_get_repo.return_value = mock_repo
            
            with patch.object(agent.mcp_connector, 'create_branch', new_callable=AsyncMock) as mock_create_branch:
                mock_create_branch.return_value = "flowglad-migration"
                
                with patch.object(agent.editor, 'batch_convert_files', new_callable=AsyncMock) as mock_batch:
                    mock_batch.return_value = {
                        "successful": 1,
                        "failed": 0,
                        "results": [Mock(success=True)]
                    }
                    
                    with patch.object(agent.editor, 'create_pull_request_description', new_callable=AsyncMock) as mock_pr_desc:
                        mock_pr_desc.return_value = "PR Description"
                        
                        with patch.object(agent.mcp_connector, 'create_pull_request', new_callable=AsyncMock) as mock_create_pr:
                            mock_create_pr.return_value = {
                                "number": 1,
                                "url": "https://github.com/test/repo/pull/1"
                            }
                            
                            pr_url = await agent._apply_changes(mock_transformations)
                            
                            assert pr_url == "https://github.com/test/repo/pull/1"
                            mock_create_branch.assert_called_once()
                            mock_batch.assert_called_once()
                            mock_create_pr.assert_called_once()
    
    @pytest.mark.integration
    def test_get_file_type(self, agent):
        assert agent._get_file_type("test.py") == "python"
        assert agent._get_file_type("test.js") == "javascript"
        assert agent._get_file_type("test.jsx") == "javascript"
        assert agent._get_file_type("test.ts") == "typescript"
        assert agent._get_file_type("test.tsx") == "typescript"
        assert agent._get_file_type("Test.java") == "java"
        assert agent._get_file_type("test.rb") == "ruby"
        assert agent._get_file_type("test.txt") == "generic"
    
    @pytest.mark.integration
    def test_generate_report(self, agent):
        flows = [
            PaymentFlow(
                provider=PaymentProvider.STRIPE,
                flow_type="payment",
                file_path="payment.py",
                line_start=1,
                line_end=10
            ),
            PaymentFlow(
                provider=PaymentProvider.STRIPE,
                flow_type="subscription",
                file_path="payment.py",
                line_start=20,
                line_end=30
            ),
            PaymentFlow(
                provider=PaymentProvider.SQUARE,
                flow_type="checkout",
                file_path="checkout.py",
                line_start=1,
                line_end=20
            )
        ]
        
        transformations = [
            CodeTransformation(
                original_code="old1",
                transformed_code="new1",
                file_path="payment.py",
                line_range=(1, 10),
                transformation_type="conversion"
            ),
            CodeTransformation(
                original_code="old2",
                transformed_code="new2",
                file_path="checkout.py",
                line_range=(1, 20),
                transformation_type="conversion"
            )
        ]
        
        pr_url = "https://github.com/test/repo/pull/1"
        
        report = agent._generate_report(flows, transformations, pr_url)
        
        assert report.repo_name == "test/repo"
        assert report.files_analyzed == 2  # unique files
        assert report.payment_flows_found == 3
        assert report.files_converted == 2
        assert report.conversion_success_rate == 1.0
        assert report.pr_url == pr_url
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_close(self, agent):
        with patch.object(agent.mcp_connector, 'close', new_callable=AsyncMock) as mock_close:
            with patch.object(agent.editor.client, 'aclose', new_callable=AsyncMock) as mock_editor_close:
                await agent.close()
                
                mock_close.assert_called_once()
                mock_editor_close.assert_called_once()