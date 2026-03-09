"""HIVE Engine MCP Server -- JSON-RPC over stdio.

Exposes 15 tools for integration with Claude Desktop and other MCP clients.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from core.feedback import FeedbackEngine
from core.memory import MemoryManager
from core.memory_db import MemoryDB
from core.pipeline import Pipeline
from personas.aegis import Aegis
from personas.apis import Apis
from personas.coda import Coda
from personas.debug import Debug
from personas.forge import Forge
from personas.muse import Muse
from personas.oracle import Oracle
from personas.sentinel import Sentinel


# --- Tool Definitions ---

TOOLS: list[dict[str, Any]] = [
    {
        "name": "hive_oracle",
        "description": "Plan a task using Oracle (RPI planner). Returns structured JSON DAG.",
        "inputSchema": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Task to plan"}},
            "required": ["task"],
        },
    },
    {
        "name": "hive_forge",
        "description": "Generate code using Forge. Iron Gate checks all output.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "Code generation prompt"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "hive_sentinel",
        "description": "Security review using Sentinel. Analyzes code for vulnerabilities.",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Code to review"}},
            "required": ["code"],
        },
    },
    {
        "name": "hive_heal",
        "description": "Auto-heal code using Debug. Runs, catches errors, fixes, retries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code or file path to heal"},
                "max_attempts": {"type": "integer", "description": "Max fix attempts", "default": 3},
            },
            "required": ["code"],
        },
    },
    {
        "name": "hive_muse",
        "description": "Optimize a prompt using Muse. Returns 3 variants.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "Prompt to optimize"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "hive_coda_compress",
        "description": "Compress text using Coda. Returns structured anchor.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to compress"}},
            "required": ["text"],
        },
    },
    {
        "name": "hive_coda_verify",
        "description": "Verify assertions for contradictions using Coda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session to verify"},
                "assertions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of assertions to check",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "hive_aegis",
        "description": "Red team analysis using Aegis. Returns risk score and verdict.",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Code to red-team"}},
            "required": ["code"],
        },
    },
    {
        "name": "hive_aegis_prompt",
        "description": "Check a prompt for injection attacks using Aegis.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "Prompt to check"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "hive_apis_test",
        "description": "Generate a Playwright test script using Apis.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to test"}},
            "required": ["url"],
        },
    },
    {
        "name": "hive_apis_crawl",
        "description": "Generate a Playwright crawl script using Apis.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to crawl"}},
            "required": ["url"],
        },
    },
    {
        "name": "hive_pipeline",
        "description": "Run full pipeline: Oracle->Forge->Sentinel+Aegis.",
        "inputSchema": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Task to run through pipeline"}},
            "required": ["task"],
        },
    },
    {
        "name": "hive_memory_search",
        "description": "Search HIVE memory for past interactions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "persona": {"type": "string", "description": "Filter by persona"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "hive_memory_stats",
        "description": "Get HIVE memory and session statistics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "hive_rate",
        "description": "Rate the current session (+1 or -1).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session to rate"},
                "direction": {"type": "integer", "description": "+1 or -1", "enum": [1, -1]},
            },
            "required": ["session_id", "direction"],
        },
    },
]


class HiveMCPServer:
    """MCP server using JSON-RPC 2.0 over stdio."""

    def __init__(self) -> None:
        self.db = MemoryDB()
        self.memory = MemoryManager()
        self.feedback = FeedbackEngine(self.db)
        self.pipeline = Pipeline()

        self.forge = Forge()
        self.oracle = Oracle()
        self.sentinel = Sentinel()
        self.debug = Debug()
        self.muse = Muse()
        self.coda = Coda()
        self.aegis = Aegis()
        self.apis = Apis()

    def _jsonrpc_response(self, id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": id, "result": result}

    def _jsonrpc_error(self, id: Any, code: int, message: str,
                       data: Any = None) -> dict:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": id, "error": err}

    def handle_initialize(self, id: Any, params: dict) -> dict:
        return self._jsonrpc_response(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": "hive-engine",
                "version": "0.1.0",
            },
        })

    def handle_tools_list(self, id: Any, params: dict) -> dict:
        return self._jsonrpc_response(id, {"tools": TOOLS})

    def handle_tools_call(self, id: Any, params: dict) -> dict:
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            result = self._dispatch_tool(name, arguments)
            return self._jsonrpc_response(id, {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}],
            })
        except Exception as e:
            return self._jsonrpc_response(id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })

    def _dispatch_tool(self, name: str, args: dict) -> Any:
        if name == "hive_oracle":
            return self.oracle.process(args["task"])
        elif name == "hive_forge":
            return self.forge.process(args["prompt"])
        elif name == "hive_sentinel":
            result = self.sentinel.process(args["code"])
            return {
                "findings": [
                    {"issue": f.issue, "severity": f.severity,
                     "line_hint": f.line_hint, "recommendation": f.recommendation}
                    for f in result.findings
                ],
                "overall_risk": result.overall_risk,
                "passed": result.passed,
                "summary": result.summary,
            }
        elif name == "hive_heal":
            result = self.debug.process(args["code"],
                                        max_attempts=args.get("max_attempts", 3))
            return {
                "success": result.success,
                "attempts": len(result.attempts),
                "final_error": result.final_error,
                "final_code": result.final_code,
            }
        elif name == "hive_muse":
            result = self.muse.process(args["prompt"])
            return {
                "precise": result.precise,
                "constrained": result.constrained,
                "creative": result.creative,
            }
        elif name == "hive_coda_compress":
            result = self.coda.process(args["text"])
            return {
                "summary": result.summary,
                "key_decisions": result.key_decisions,
                "constraints": result.constraints,
                "assertions": result.assertions,
            }
        elif name == "hive_coda_verify":
            from personas.coda import CompressedAnchor as CodaAnchor
            assertions = args.get("assertions", [])
            anchors = [CodaAnchor(summary="", assertions=assertions)] if assertions else None
            result = self.coda.verify(args["session_id"], anchors)
            return {
                "valid": result.valid,
                "contradictions": result.contradictions,
                "warnings": result.warnings,
            }
        elif name == "hive_aegis":
            result = self.aegis.process(args["code"])
            return {
                "risk_score": result.risk_score,
                "findings": result.findings,
                "verdict": result.verdict,
            }
        elif name == "hive_aegis_prompt":
            result = self.aegis.prompt_injection_check(args["prompt"])
            return {
                "risk_score": result.risk_score,
                "findings": result.findings,
                "verdict": result.verdict,
            }
        elif name == "hive_apis_test":
            return self.apis.generate_test(args["url"])
        elif name == "hive_apis_crawl":
            return self.apis.generate_crawl(args["url"])
        elif name == "hive_pipeline":
            import asyncio
            result = asyncio.run(self.pipeline.run(args["task"]))
            return {
                "plan": result.plan,
                "code": result.code,
                "security_review": result.security_review,
                "red_team_review": result.red_team_review,
                "success": result.success,
                "errors": result.errors,
            }
        elif name == "hive_memory_search":
            turns = self.db.search_turns(args["query"],
                                         persona=args.get("persona"))
            return [
                {"persona": t.persona, "role": t.role,
                 "content": t.content[:200], "timestamp": t.timestamp}
                for t in turns
            ]
        elif name == "hive_memory_stats":
            return self.db.get_stats()
        elif name == "hive_rate":
            self.feedback.rate(args["session_id"], args["direction"])
            return {"status": "ok", "session_id": args["session_id"],
                    "direction": args["direction"]}
        else:
            raise ValueError(f"Unknown tool: {name}")

    def handle_request(self, request: dict) -> dict | None:
        method = request.get("method", "")
        id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return self.handle_initialize(id, params)
        elif method == "notifications/initialized":
            return None  # notification, no response
        elif method == "tools/list":
            return self.handle_tools_list(id, params)
        elif method == "tools/call":
            return self.handle_tools_call(id, params)
        elif method == "ping":
            return self._jsonrpc_response(id, {})
        else:
            if id is not None:
                return self._jsonrpc_error(id, -32601, f"Method not found: {method}")
            return None  # ignore unknown notifications

    def run(self) -> None:
        """Main stdio loop: read JSON-RPC from stdin, write to stdout."""
        # Use binary mode for reliable line reading
        stdin = sys.stdin
        stdout = sys.stdout

        while True:
            try:
                line = stdin.readline()
                if not line:
                    break  # EOF
                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    # Try reading Content-Length header style
                    if line.startswith("Content-Length:"):
                        length = int(line.split(":")[1].strip())
                        stdin.readline()  # empty line
                        body = stdin.read(length)
                        request = json.loads(body)
                    else:
                        continue

                response = self.handle_request(request)
                if response is not None:
                    response_json = json.dumps(response)
                    stdout.write(response_json + "\n")
                    stdout.flush()

            except Exception:
                traceback.print_exc(file=sys.stderr)
                continue

        self.db.close()


def main() -> None:
    server = HiveMCPServer()
    server.run()


if __name__ == "__main__":
    main()
