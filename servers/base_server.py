import json
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

class BaseMCPServer:
    """Base class for stdio JSON-RPC MCP servers."""
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: List[Dict[str, Any]] = []
        self._handlers: Dict[str, Callable] = {}

    def register_tool(self, name: str, description: str, input_schema: dict, handler: Callable):
        self.tools.append({
            "name": name,
            "description": description,
            "inputSchema": input_schema
        })
        self._handlers[name] = handler

    def _write_message(self, data: dict) -> None:
        """Write a JSON-RPC message with Content-Length header."""
        body = json.dumps(data)
        body_bytes = body.encode("utf-8")
        header = f"Content-Length: {len(body_bytes)}\r\n\r\n"
        sys.stdout.buffer.write(header.encode("utf-8"))
        sys.stdout.buffer.write(body_bytes)
        sys.stdout.buffer.flush()

    def _read_message(self) -> dict | None:
        """Read a JSON-RPC message with Content-Length framing."""
        line = sys.stdin.buffer.readline()
        if not line:
            return None

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            return None

        if line_str.startswith("Content-Length:"):
            length = int(line_str.split(":", 1)[1].strip())
            while True:
                separator = sys.stdin.buffer.readline()
                if separator.decode("utf-8", errors="replace").strip() == "":
                    break
            
            body_bytes = b""
            while len(body_bytes) < length:
                chunk = sys.stdin.buffer.read(length - len(body_bytes))
                if not chunk:
                    break
                body_bytes += chunk
            return json.loads(body_bytes.decode("utf-8", errors="replace"))
        else:
            try:
                return json.loads(line_str)
            except json.JSONDecodeError:
                return None

    def handle_request(self, request: dict) -> dict | None:
        method = request.get("method", "")
        msg_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version}
                }
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.tools}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            if tool_name in self._handlers:
                try:
                    result = self._handlers[tool_name](**tool_args)
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"content": [{"type": "text", "text": str(result)}]}
                    }
                except Exception as e:
                    traceback.print_exc(file=sys.stderr)
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                            "isError": True
                        }
                    }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}
                }
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        
        if msg_id is not None:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}
        return None

    def run(self) -> None:
        """Main stdio loop: read JSON-RPC from stdin, write to stdout."""
        while True:
            try:
                request = self._read_message()
                if request is None:
                    if sys.stdin.buffer.closed:
                        break
                    continue

                response = self.handle_request(request)
                if response is not None:
                    self._write_message(response)
            except Exception:
                traceback.print_exc(file=sys.stderr)
                continue
