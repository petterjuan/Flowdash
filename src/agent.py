import asyncio
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import json
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.panel import Panel

from mcp_connector import GitHubMCPConnector, MCPConfig
from payment_analyzer import PaymentLogicAnalyzer, PaymentFlow
from flow_mapper import PaymentFlowMapper
from flowglad_converter import FlowGladConverter, CodeTransformation
from morph_editor import MorphLLMEditor, EditRequest

console = Console()

class AgentStatus(Enum):
    IDLE = "idle"
    AUTHENTICATING = "authenticating"
    ANALYZING = "analyzing"
    MAPPING = "mapping"
    CONVERTING = "converting"
    APPLYING = "applying"
    COMPLETE = "complete"
    ERROR = "error"

@dataclass
class AgentConfig:
    github_token: str
    repo_name: str
    target_branch: str = "flowglad-migration"
    create_pr: bool = True
    auto_apply: bool = False
    llm_provider: str = "anthropic"

@dataclass
class MigrationReport:
    repo_name: str
    files_analyzed: int
    payment_flows_found: int
    files_converted: int
    conversion_success_rate: float
    pr_url: Optional[str] = None
    errors: List[str] = None

class FlowGladMigrationAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.status = AgentStatus.IDLE
        self.mcp_connector = GitHubMCPConnector(
            MCPConfig(
                server_url=os.getenv("MCP_SERVER_URL", "http://localhost:3000"),
                github_token=config.github_token
            )
        )
        self.analyzer = PaymentLogicAnalyzer()
        self.mapper = PaymentFlowMapper(llm_provider=config.llm_provider)
        self.converter = FlowGladConverter()
        self.editor = MorphLLMEditor()
        self.report = None
    
    async def run(self) -> MigrationReport:
        try:
            console.print(Panel.fit(
                f"[bold cyan]FlowGlad Migration Agent[/bold cyan]\n"
                f"Repository: {self.config.repo_name}",
                border_style="cyan"
            ))
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                
                auth_task = progress.add_task("[cyan]Authenticating with GitHub...", total=1)
                self.status = AgentStatus.AUTHENTICATING
                await self._authenticate()
                progress.update(auth_task, completed=1)
                
                analyze_task = progress.add_task("[cyan]Analyzing payment logic...", total=1)
                self.status = AgentStatus.ANALYZING
                payment_flows = await self._analyze_repository()
                progress.update(analyze_task, completed=1)
                
                map_task = progress.add_task("[cyan]Mapping payment flows...", total=1)
                self.status = AgentStatus.MAPPING
                flow_maps = await self._map_flows(payment_flows)
                progress.update(map_task, completed=1)
                
                convert_task = progress.add_task("[cyan]Converting to FlowGlad...", total=1)
                self.status = AgentStatus.CONVERTING
                transformations = await self._convert_code(payment_flows)
                progress.update(convert_task, completed=1)
                
                if self.config.auto_apply:
                    apply_task = progress.add_task("[cyan]Applying changes...", total=1)
                    self.status = AgentStatus.APPLYING
                    pr_url = await self._apply_changes(transformations)
                    progress.update(apply_task, completed=1)
                else:
                    pr_url = None
            
            self.status = AgentStatus.COMPLETE
            report = self._generate_report(payment_flows, transformations, pr_url)
            self._display_report(report)
            
            return report
            
        except Exception as e:
            self.status = AgentStatus.ERROR
            console.print(f"[red]Error: {str(e)}[/red]")
            raise
    
    async def _authenticate(self):
        success = await self.mcp_connector.authenticate()
        if not success:
            raise Exception("GitHub authentication failed")
        
        await self.mcp_connector.connect_to_mcp()
        console.print("[green]✓[/green] Authenticated with GitHub")
    
    async def _analyze_repository(self) -> List[PaymentFlow]:
        repo = await self.mcp_connector.get_repository(self.config.repo_name)
        payment_files = await self.mcp_connector.search_payment_files(repo)
        
        console.print(f"Found {len(payment_files)} potential payment files")
        
        all_flows = []
        for file_info in payment_files:
            try:
                content = await self.mcp_connector.get_file_content(repo, file_info['path'])
                flows = self.analyzer.analyze_file(file_info['path'], content)
                all_flows.extend(flows)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not analyze {file_info['path']}: {e}[/yellow]")
        
        console.print(f"[green]✓[/green] Identified {len(all_flows)} payment flows")
        return all_flows
    
    async def _map_flows(self, payment_flows: List[PaymentFlow]) -> List[Dict[str, Any]]:
        flow_maps = []
        
        for flow in payment_flows:
            try:
                repo = await self.mcp_connector.get_repository(self.config.repo_name)
                content = await self.mcp_connector.get_file_content(repo, flow.file_path)
                
                flow_map = self.mapper.map_payment_flow(
                    content,
                    flow.provider.value,
                    flow.flow_type
                )
                
                comparison = self.mapper.compare_with_flowglad(flow_map)
                flow_maps.append({
                    "flow": flow,
                    "map": flow_map,
                    "comparison": comparison
                })
                
            except Exception as e:
                console.print(f"[yellow]Warning: Could not map flow in {flow.file_path}: {e}[/yellow]")
        
        console.print(f"[green]✓[/green] Mapped {len(flow_maps)} payment flows")
        return flow_maps
    
    async def _convert_code(self, payment_flows: List[PaymentFlow]) -> List[CodeTransformation]:
        transformations = []
        files_processed = set()
        
        for flow in payment_flows:
            if flow.file_path in files_processed:
                continue
            
            files_processed.add(flow.file_path)
            
            try:
                repo = await self.mcp_connector.get_repository(self.config.repo_name)
                content = await self.mcp_connector.get_file_content(repo, flow.file_path)
                
                file_type = self._get_file_type(flow.file_path)
                transformation = self.converter.convert_code(
                    content,
                    flow.provider.value,
                    file_type
                )
                
                transformation.file_path = flow.file_path
                transformations.append(transformation)
                
            except Exception as e:
                console.print(f"[yellow]Warning: Could not convert {flow.file_path}: {e}[/yellow]")
        
        console.print(f"[green]✓[/green] Generated {len(transformations)} code transformations")
        return transformations
    
    async def _apply_changes(self, transformations: List[CodeTransformation]) -> Optional[str]:
        repo = await self.mcp_connector.get_repository(self.config.repo_name)
        
        branch_name = await self.mcp_connector.create_branch(
            repo,
            self.config.target_branch
        )
        
        console.print(f"Created branch: {branch_name}")
        
        edit_requests = [
            EditRequest(
                file_path=t.file_path,
                original_code=t.original_code,
                target_code=t.transformed_code,
                description="Convert to FlowGlad"
            )
            for t in transformations
        ]
        
        results = await self.editor.batch_convert_files(
            repo.clone_url.replace("https://", "").replace(".git", ""),
            [
                {
                    "file_path": t.file_path,
                    "original_code": t.original_code,
                    "transformed_code": t.transformed_code,
                    "description": "Convert to FlowGlad"
                }
                for t in transformations
            ]
        )
        
        console.print(f"Applied {results['successful']} transformations")
        
        if self.config.create_pr:
            pr_description = await self.editor.create_pull_request_description(
                results['results']
            )
            
            pr_info = await self.mcp_connector.create_pull_request(
                repo,
                title="Migrate payment processing to FlowGlad",
                body=pr_description,
                head=branch_name
            )
            
            console.print(f"[green]✓[/green] Created PR: {pr_info['url']}")
            return pr_info['url']
        
        return None
    
    def _get_file_type(self, file_path: str) -> str:
        if file_path.endswith('.py'):
            return "python"
        elif file_path.endswith(('.js', '.jsx')):
            return "javascript"
        elif file_path.endswith(('.ts', '.tsx')):
            return "typescript"
        elif file_path.endswith('.java'):
            return "java"
        elif file_path.endswith('.rb'):
            return "ruby"
        else:
            return "generic"
    
    def _generate_report(self, flows: List[PaymentFlow], 
                        transformations: List[CodeTransformation],
                        pr_url: Optional[str]) -> MigrationReport:
        unique_files = set(f.file_path for f in flows)
        
        return MigrationReport(
            repo_name=self.config.repo_name,
            files_analyzed=len(unique_files),
            payment_flows_found=len(flows),
            files_converted=len(transformations),
            conversion_success_rate=len(transformations) / len(unique_files) if unique_files else 0,
            pr_url=pr_url,
            errors=[]
        )
    
    def _display_report(self, report: MigrationReport):
        table = Table(title="Migration Report", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")
        
        table.add_row("Repository", report.repo_name)
        table.add_row("Files Analyzed", str(report.files_analyzed))
        table.add_row("Payment Flows Found", str(report.payment_flows_found))
        table.add_row("Files Converted", str(report.files_converted))
        table.add_row("Success Rate", f"{report.conversion_success_rate:.1%}")
        
        if report.pr_url:
            table.add_row("Pull Request", report.pr_url)
        
        console.print(table)
    
    async def close(self):
        await self.mcp_connector.close()
        await self.editor.client.aclose()