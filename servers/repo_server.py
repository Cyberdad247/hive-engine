import glob
import os
import re
from pathlib import Path
from typing import Optional
from base_server import BaseMCPServer

def list_files(pattern: str = "**/*") -> str:
    """List files matching a glob pattern."""
    files = glob.glob(pattern, recursive=True)
    return "\n".join(files)

def read_file(path: str) -> str:
    """Read contents of a file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path: str, content: str, mode: str = "w") -> str:
    """Write or append content to a file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        f.write(content)
    return f"Successfully wrote to {path}"

def search(query: str, glob_pattern: Optional[str] = None, case_sensitive: bool = False) -> str:
    """Search for a string in files."""
    flags = 0 if case_sensitive else re.IGNORECASE
    regex = re.compile(query, flags)
    results = []
    
    files = glob.glob(glob_pattern or "**/*", recursive=True)
    for f_path in files:
        if os.path.isfile(f_path):
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if regex.search(line):
                            results.append(f"{f_path}:{i+1}: {line.strip()}")
            except UnicodeDecodeError:
                pass
    
    return "\n".join(results) if results else "No matches found."

def get_symbols(path: str) -> str:
    """Mock implementation of getting symbols (functions, classes)."""
    if not os.path.exists(path):
        return f"File {path} does not exist."
    
    symbols = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line_str = line.strip()
            if line_str.startswith("def ") or line_str.startswith("class "):
                symbols.append(f"Line {i+1}: {line_str}")
    return "\n".join(symbols) if symbols else "No symbols found."

if __name__ == "__main__":
    server = BaseMCPServer("repo-server")
    server.register_tool(
        "repo.list_files", "List files matching a glob pattern",
        {"type": "object", "properties": {"pattern": {"type": "string"}}}, list_files
    )
    server.register_tool(
        "repo.read_file", "Read file contents",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, read_file
    )
    server.register_tool(
        "repo.write_file", "Write to a file",
        {
            "type": "object", 
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "mode": {"type": "string", "default": "w"}
            },
            "required": ["path", "content"]
        }, write_file
    )
    server.register_tool(
        "repo.search", "Search file contents",
        {
            "type": "object", 
            "properties": {
                "query": {"type": "string"},
                "glob_pattern": {"type": "string"},
                "case_sensitive": {"type": "boolean"}
            },
            "required": ["query"]
        }, search
    )
    server.register_tool(
        "repo.get_symbols", "Extract symbols from a file",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, get_symbols
    )
    server.run()
