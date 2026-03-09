import subprocess
from typing import Optional
from base_server import BaseMCPServer

def run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Git error:\n{e.stderr}"
    except FileNotFoundError:
        return "Error: Git executable not found on system."

def git_status() -> str:
    return run_git(["status"])

def git_diff(target: Optional[str] = None) -> str:
    args = ["diff"]
    if target:
        args.append(target)
    return run_git(args)

def git_commit(message: str) -> str:
    return run_git(["commit", "-m", message])

def git_checkout(branch: str) -> str:
    return run_git(["checkout", branch])

def git_log(limit: int = 10) -> str:
    return run_git(["log", f"-n{limit}", "--oneline"])

if __name__ == "__main__":
    server = BaseMCPServer("git-server")
    server.register_tool("git.status", "Get working tree status", {"type": "object", "properties": {}}, git_status)
    server.register_tool(
        "git.diff", "Show changes between commits/trees",
        {"type": "object", "properties": {"target": {"type": "string"}}}, git_diff
    )
    server.register_tool(
        "git.commit", "Record changes to the repository",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}, git_commit
    )
    server.register_tool(
        "git.checkout", "Switch branches or restore working tree files",
        {"type": "object", "properties": {"branch": {"type": "string"}}, "required": ["branch"]}, git_checkout
    )
    server.register_tool(
        "git.log", "Show commit logs",
        {"type": "object", "properties": {"limit": {"type": "integer"}}}, git_log
    )
    server.run()
