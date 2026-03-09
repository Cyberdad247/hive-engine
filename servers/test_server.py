import subprocess
import json
from typing import Optional
from base_server import BaseMCPServer

def test_run(target: Optional[str] = None, filter_str: Optional[str] = None) -> str:
    """Run tests (using pytest as the default underlying engine)."""
    args = ["pytest"]
    if target:
        args.append(target)
    if filter_str:
        args.extend(["-k", filter_str])
        
    try:
        result = subprocess.run(args, capture_output=True, text=True)
        # Attempt to parse structured output if we used plugins, but for now return stdout
        status = "passed" if result.returncode == 0 else "failed"
        
        # We can format a structured JSON return or a human-readable string
        output_data = {
            "status": status,
            "exit_code": result.returncode,
            "output": result.stdout[-5000:], # Return last 5k chars to avoid blowing up payload
            "error_output": result.stderr
        }
        return json.dumps(output_data, indent=2)
    except FileNotFoundError:
        return json.dumps({"error": "pytest not found. Please install pytest."})
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    server = BaseMCPServer("test-server")
    server.register_tool(
        "test.run", "Run test suite",
        {
            "type": "object", 
            "properties": {
                "target": {"type": "string", "description": "Specific test file or directory"},
                "filter_str": {"type": "string", "description": "Filter expressions"}
            }
        }, test_run
    )
    server.run()
