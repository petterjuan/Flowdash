import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx
from github import Github, Repository
from dotenv import load_dotenv
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

@dataclass
class MCPConfig:
    server_url: str
    github_token: str
    timeout: int = 30

class GitHubMCPConnector:
    def __init__(self, config: Optional[MCPConfig] = None):
        self.config = config or MCPConfig(
            server_url=os.getenv("MCP_SERVER_URL", "http://localhost:3000"),
            github_token=os.getenv("GITHUB_TOKEN", "")
        )
        self.github = Github(self.config.github_token)
        self.client = httpx.AsyncClient(timeout=self.config.timeout)
        self._authenticated = False
        
    async def authenticate(self) -> bool:
        try:
            user = self.github.get_user()
            self._authenticated = True
            return True
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def connect_to_mcp(self) -> Dict[str, Any]:
        response = await self.client.post(
            f"{self.config.server_url}/connect",
            json={
                "provider": "github",
                "token": self.config.github_token
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def get_repository(self, repo_name: str) -> Repository:
        return self.github.get_repo(repo_name)
    
    async def list_repository_files(self, repo: Repository, path: str = "") -> List[Dict[str, Any]]:
        contents = repo.get_contents(path)
        files = []
        
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo.get_contents(file_content.path))
            else:
                files.append({
                    "path": file_content.path,
                    "name": file_content.name,
                    "size": file_content.size,
                    "sha": file_content.sha,
                    "type": file_content.type
                })
        
        return files
    
    async def get_file_content(self, repo: Repository, file_path: str) -> str:
        file_content = repo.get_contents(file_path)
        if isinstance(file_content, list):
            file_content = file_content[0]
        return file_content.decoded_content.decode('utf-8')
    
    async def search_payment_files(self, repo: Repository) -> List[Dict[str, Any]]:
        payment_patterns = [
            "stripe", "square", "payment", "billing", 
            "checkout", "subscription", "charge", "customer"
        ]
        
        query = f"repo:{repo.full_name} " + " OR ".join(payment_patterns)
        code_results = self.github.search_code(query=query)
        
        payment_files = []
        for result in code_results:
            payment_files.append({
                "path": result.path,
                "repository": result.repository.full_name,
                "sha": result.sha,
                "score": result.score
            })
        
        return payment_files
    
    async def create_branch(self, repo: Repository, branch_name: str, base_branch: str = "main") -> str:
        base_ref = repo.get_git_ref(f"heads/{base_branch}")
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_ref.object.sha
        )
        return branch_name
    
    async def update_file(self, repo: Repository, file_path: str, new_content: str, 
                          message: str, branch: str) -> Dict[str, Any]:
        try:
            file = repo.get_contents(file_path, ref=branch)
            result = repo.update_file(
                path=file_path,
                message=message,
                content=new_content,
                sha=file.sha,
                branch=branch
            )
        except:
            result = repo.create_file(
                path=file_path,
                message=message,
                content=new_content,
                branch=branch
            )
        
        return {
            "commit": result["commit"].sha,
            "file": result["content"].path
        }
    
    async def create_pull_request(self, repo: Repository, title: str, body: str, 
                                 head: str, base: str = "main") -> Dict[str, Any]:
        pr = repo.create_pull(
            title=title,
            body=body,
            head=head,
            base=base
        )
        
        return {
            "number": pr.number,
            "url": pr.html_url,
            "state": pr.state
        }
    
    async def close(self):
        await self.client.aclose()