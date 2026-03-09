import os
import shutil
import subprocess
from typing import Optional, Dict
from base_server import BaseMCPServer

# A simple denylist for safety
DENYLIST = ["rm -rf /", "mkfs", "format"]

def shell_exec(cmd: str, cwd: Optional[str] = None, timeoutMs: Optional[int] = 30000, env: Optional[Dict[str, str]] = None, allowlistTag: Optional[str] = None) -> str:
    """Execute a shell command safely."""
    for bad in DENYLIST:
        if bad in cmd:
            return f"Error: Command contains blocked keywords ({bad})."
            
    try:
        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)
            
        timeout_sec = timeoutMs / 1000.0 if timeoutMs else 30.0
        
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            env=env_vars,
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
            
        if result.returncode != 0:
            output = f"Command failed with exit code {result.returncode}\n" + output
            
        # Max output bytes constraint (e.g. 100KB)
        MAX_BYTES = 100 * 1024
        if len(output.encode('utf-8')) > MAX_BYTES:
            output = output[:MAX_BYTES] + "\n...[OUTPUT TRUNCATED]..."
            
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except Exception as e:
        return f"Error: {str(e)}"

def shell_which(bin: str) -> str:
    """Find the path to an executable."""
    path = shutil.which(bin)
    return path if path else f"Executable '{bin}' not found."

if __name__ == "__main__":
    server = BaseMCPServer("shell-server")
    server.register_tool(
        "shell.exec", "Execute a shell command",
        {
            "type": "object", 
            "properties": {
                "cmd": {"type": "string"},
                "cwd": {"type": "string"},
                "timeoutMs": {"type": "integer"},
                "env": {"type": "object", "additionalProperties": {"type": "string"}}
            },
            "required": ["cmd"]
        }, shell_exec
    )
    server.register_tool(
        "shell.which", "Locate an executable",
        {"type": "object", "properties": {"bin": {"type": "string"}}, "required": ["bin"]}, shell_which
    )
    server.run()
