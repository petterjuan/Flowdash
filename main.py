#!/usr/bin/env python3
"""
FlowGlad Migration Agent CLI
Automatically migrates payment processing from Stripe/Square to FlowGlad
"""

import asyncio
import os
import sys
from typing import Optional
import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from agent import FlowGladMigrationAgent, AgentConfig

load_dotenv()

app = typer.Typer()
console = Console()

def validate_environment():
    required_vars = ["GITHUB_TOKEN", "GEMINI_API_KEY"]
    missing = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        console.print(f"[red]Missing environment variables: {', '.join(missing)}[/red]")
        console.print("Please copy .env.example to .env and fill in the required values")
        return False
    
    return True

@app.command()
def migrate(
    repo: str = typer.Argument(..., help="GitHub repository (owner/name)"),
    branch: str = typer.Option("flowglad-migration", "--branch", "-b", help="Target branch name"),
    auto_apply: bool = typer.Option(False, "--auto", "-a", help="Automatically apply changes"),
    create_pr: bool = typer.Option(True, "--pr/--no-pr", help="Create pull request")
):
    """
    Migrate a GitHub repository from Stripe/Square to FlowGlad
    """
    
    if not validate_environment():
        raise typer.Exit(1)
    
    console.print(Panel.fit(
        "[bold cyan]FlowGlad Migration Agent[/bold cyan]\n"
        f"Repository: {repo}\n"
        f"Target Branch: {branch}\n"
        f"Auto Apply: {auto_apply}\n"
        f"Create PR: {create_pr}",
        border_style="cyan"
    ))
    
    if not auto_apply:
        console.print("\n[yellow]Note: Running in analysis mode. No changes will be applied.[/yellow]")
        if Confirm.ask("Do you want to continue?"):
            auto_apply = False
        else:
            raise typer.Exit(0)
    
    config = AgentConfig(
        github_token=os.getenv("GITHUB_TOKEN"),
        repo_name=repo,
        target_branch=branch,
        create_pr=create_pr,
        auto_apply=auto_apply,
        llm_provider="gemini"
    )
    
    agent = FlowGladMigrationAgent(config)
    
    try:
        report = asyncio.run(agent.run())
        
        if report.pr_url:
            console.print(f"\n[green]✓ Migration complete![/green]")
            console.print(f"Pull Request: {report.pr_url}")
        else:
            console.print(f"\n[green]✓ Analysis complete![/green]")
            console.print(f"Found {report.payment_flows_found} payment flows in {report.files_analyzed} files")
            console.print(f"Ready to convert {report.files_converted} files")
        
    except Exception as e:
        console.print(f"[red]Migration failed: {str(e)}[/red]")
        raise typer.Exit(1)
    finally:
        asyncio.run(agent.close())

@app.command()
def analyze(
    repo: str = typer.Argument(..., help="GitHub repository (owner/name)")
):
    """
    Analyze a repository's payment implementation without making changes
    """
    
    if not validate_environment():
        raise typer.Exit(1)
    
    config = AgentConfig(
        github_token=os.getenv("GITHUB_TOKEN"),
        repo_name=repo,
        auto_apply=False,
        create_pr=False
    )
    
    agent = FlowGladMigrationAgent(config)
    
    try:
        report = asyncio.run(agent.run())
        
        console.print(f"\n[cyan]Analysis Summary:[/cyan]")
        console.print(f"• Files with payment logic: {report.files_analyzed}")
        console.print(f"• Payment flows detected: {report.payment_flows_found}")
        console.print(f"• Files ready for conversion: {report.files_converted}")
        console.print(f"• Conversion success rate: {report.conversion_success_rate:.1%}")
        
    except Exception as e:
        console.print(f"[red]Analysis failed: {str(e)}[/red]")
        raise typer.Exit(1)
    finally:
        asyncio.run(agent.close())

@app.command()
def setup():
    """
    Interactive setup wizard for configuring the agent
    """
    
    console.print(Panel.fit(
        "[bold cyan]FlowGlad Migration Agent Setup[/bold cyan]",
        border_style="cyan"
    ))
    
    env_path = ".env"
    
    if os.path.exists(env_path):
        if not Confirm.ask(f"{env_path} already exists. Overwrite?"):
            raise typer.Exit(0)
    
    github_token = Prompt.ask("GitHub Personal Access Token", password=True)
    gemini_key = Prompt.ask("Gemini API Key", password=True)
    gemini_model = Prompt.ask("Gemini Model", default="gemini-2.5-flash-lite")
    morph_key = Prompt.ask("Morph API Key (optional)", password=True, default="")
    flowglad_key = Prompt.ask("FlowGlad API Key", password=True)
    mcp_url = Prompt.ask("MCP Server URL", default="http://localhost:3000")
    
    with open(env_path, 'w') as f:
        f.write(f"GITHUB_TOKEN={github_token}\n")
        f.write(f"GEMINI_API_KEY={gemini_key}\n")
        f.write(f"GEMINI_MODEL={gemini_model}\n")
        if morph_key:
            f.write(f"MORPH_API_KEY={morph_key}\n")
        f.write(f"FLOWGLAD_API_KEY={flowglad_key}\n")
        f.write(f"MCP_SERVER_URL={mcp_url}\n")
    
    console.print(f"[green]✓ Configuration saved to {env_path}[/green]")
    console.print("\nYou can now run:")
    console.print("  [cyan]python main.py migrate owner/repo[/cyan] - to migrate a repository")
    console.print("  [cyan]python main.py analyze owner/repo[/cyan] - to analyze without changes")

@app.command()
def test():
    """
    Test the agent configuration and connections
    """
    
    if not validate_environment():
        raise typer.Exit(1)
    
    console.print("[cyan]Testing configuration...[/cyan]")
    
    tests = {
        "Environment Variables": validate_environment(),
        "GitHub Token": bool(os.getenv("GITHUB_TOKEN")),
        "Gemini API Key": bool(os.getenv("GEMINI_API_KEY")),
        "FlowGlad API Key": bool(os.getenv("FLOWGLAD_API_KEY"))
    }
    
    for test, result in tests.items():
        status = "[green]✓[/green]" if result else "[red]✗[/red]"
        console.print(f"{status} {test}")
    
    if all(tests.values()):
        console.print("\n[green]All tests passed! Agent is ready to use.[/green]")
    else:
        console.print("\n[red]Some tests failed. Please run 'python main.py setup' to configure.[/red]")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()