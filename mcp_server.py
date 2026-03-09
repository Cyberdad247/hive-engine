"""HIVE Engine MCP Server -- JSON-RPC over stdio with Content-Length framing.

Exposes tools for integration with Claude Desktop / Claude Code and other MCP clients.
Loads .env at startup, supports Content-Length headers, resources/list, hive_status,
and hive_switch_provider.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

# ─── Load .env ──────────────────────────────────────────────────────
def _load_dotenv() -> None:
    """Load .env file from the project root using stdlib only (no pip)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Remove surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            os.environ.setdefault(key, value)

_load_dotenv()

# Now import project modules (they may depend on env vars)
from core.feedback import FeedbackEngine
from core.memory import MemoryManager
from core.memory_db import MemoryDB
from core.pipeline import Pipeline
from core import router
from personas.aegis import Aegis
from personas.apis import Apis
from personas.coda import Coda
from personas.debug import Debug
from personas.forge import Forge
from personas.muse import Muse
from personas.oracle import Oracle
from personas.sentinel import Sentinel


# ─── Tool Definitions ──────────────────────────────────────────────

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
    {
        "name": "hive_status",
        "description": (
            "Get full HIVE Engine status: current provider, model ladder, "
            "all 8 persona statuses, memory stats, and session info."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "hive_switch_provider",
        "description": (
            "Switch the active LLM provider. Available: gemini, gemini-3.1, "
            "openai, anthropic, ollama, ollama-tiered."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Provider name to switch to",
                },
            },
            "required": ["provider"],
        },
    },
    # ── Forge extended tools ──
    {
        "name": "hive_forge_refactor",
        "description": "Refactor code using Forge. Optionally specify a refactoring goal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to refactor"},
                "goal": {"type": "string", "description": "Refactoring goal (optional)"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "hive_forge_tests",
        "description": "Generate tests for code using Forge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to generate tests for"},
                "framework": {"type": "string", "description": "Test framework", "default": "pytest"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "hive_forge_convert",
        "description": "Convert code to another programming language using Forge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to convert"},
                "target_language": {"type": "string", "description": "Target programming language"},
            },
            "required": ["code", "target_language"],
        },
    },
    {
        "name": "hive_forge_document",
        "description": "Add documentation to code using Forge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to document"},
            },
            "required": ["code"],
        },
    },
    # ── Oracle extended tools ──
    {
        "name": "hive_oracle_deps",
        "description": "Analyze dependencies for a codebase or description using Oracle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code_or_description": {"type": "string", "description": "Code or description to analyze dependencies for"},
            },
            "required": ["code_or_description"],
        },
    },
    {
        "name": "hive_oracle_diagram",
        "description": "Generate an ASCII architecture diagram using Oracle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "System description to diagram"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "hive_oracle_estimate",
        "description": "Estimate implementation effort for a task using Oracle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_description": {"type": "string", "description": "Task to estimate effort for"},
            },
            "required": ["task_description"],
        },
    },
    # ── Sentinel extended tools ──
    {
        "name": "hive_sentinel_deps",
        "description": "Scan dependencies for known vulnerabilities using Sentinel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "requirements": {"type": "string", "description": "Requirements/dependency list to scan"},
            },
            "required": ["requirements"],
        },
    },
    {
        "name": "hive_sentinel_owasp",
        "description": "Run OWASP Top 10 checklist against code using Sentinel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to check"},
                "app_type": {"type": "string", "description": "Application type", "default": "web"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "hive_sentinel_compliance",
        "description": "Check code against a compliance standard using Sentinel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to check"},
                "standard": {"type": "string", "description": "Compliance standard (general, gdpr, hipaa, pci-dss)", "default": "general"},
            },
            "required": ["code"],
        },
    },
    # ── Debug extended tools ──
    {
        "name": "hive_debug_profile",
        "description": "Profile code for performance issues using Debug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to profile"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "hive_debug_trace",
        "description": "Trace the root cause of an error using Debug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "error_message": {"type": "string", "description": "Error message to trace"},
                "code": {"type": "string", "description": "Related code (optional)"},
            },
            "required": ["error_message"],
        },
    },
    {
        "name": "hive_debug_stacktrace",
        "description": "Explain a stack trace in plain language using Debug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stacktrace": {"type": "string", "description": "Stack trace to explain"},
            },
            "required": ["stacktrace"],
        },
    },
    # ── Muse extended tools ──
    {
        "name": "hive_muse_mockup",
        "description": "Generate an ASCII UI mockup using Muse.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "UI description to mock up"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "hive_muse_naming",
        "description": "Get naming suggestions for variables, functions, classes, etc. using Muse.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What the thing does or represents"},
                "context": {"type": "string", "description": "Context: variable, function, class, project, or api_endpoint", "default": "variable"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "hive_muse_brainstorm",
        "description": "Brainstorm ideas for a topic using Muse.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to brainstorm about"},
                "num_ideas": {"type": "integer", "description": "Number of ideas to generate", "default": 5},
            },
            "required": ["topic"],
        },
    },
    # ── Coda extended tools ──
    {
        "name": "hive_coda_changelog",
        "description": "Generate a changelog from a diff using Coda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff_text": {"type": "string", "description": "Diff text to generate changelog from"},
            },
            "required": ["diff_text"],
        },
    },
    {
        "name": "hive_coda_diff",
        "description": "Summarize a diff in human-readable form using Coda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff_text": {"type": "string", "description": "Diff text to summarize"},
            },
            "required": ["diff_text"],
        },
    },
    {
        "name": "hive_coda_meeting",
        "description": "Extract structured meeting notes from a transcript using Coda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "transcript": {"type": "string", "description": "Meeting transcript to process"},
            },
            "required": ["transcript"],
        },
    },
    # ── Aegis extended tools ──
    {
        "name": "hive_aegis_threat",
        "description": "Perform STRIDE threat modeling on a system using Aegis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "system_description": {"type": "string", "description": "System description to threat model"},
            },
            "required": ["system_description"],
        },
    },
    {
        "name": "hive_aegis_fuzz",
        "description": "Generate fuzzing / edge-case inputs for code using Aegis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to generate fuzzing inputs for"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "hive_aegis_surface",
        "description": "Map the attack surface of an application using Aegis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code_or_description": {"type": "string", "description": "Code or description to analyze"},
            },
            "required": ["code_or_description"],
        },
    },
    # ── Apis extended tools ──
    {
        "name": "hive_apis_contract",
        "description": "Validate an API contract/spec using Apis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_spec": {"type": "string", "description": "API specification to validate"},
            },
            "required": ["api_spec"],
        },
    },
    {
        "name": "hive_apis_loadtest",
        "description": "Generate a load test script for a URL using Apis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL to load-test"},
                "scenario": {"type": "string", "description": "Test scenario: basic, spike, endurance, stress", "default": "basic"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "hive_apis_mock",
        "description": "Generate a mock server from an API spec using Apis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_spec": {"type": "string", "description": "API specification to generate mock server for"},
            },
            "required": ["api_spec"],
        },
    },
]


# ─── Resource Definitions ──────────────────────────────────────────

PERSONA_NAMES = ["oracle", "forge", "sentinel", "debug", "muse", "coda", "aegis", "apis"]


# ─── MCP Server ────────────────────────────────────────────────────

class HiveMCPServer:
    """MCP server using JSON-RPC 2.0 over stdio with Content-Length framing."""

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

        self.session_id = str(uuid.uuid4())[:8]
        self.db.save_session(self.session_id)
        self.memory.set_session(self.session_id)
        self._start_time = time.time()

    # ── JSON-RPC helpers ──

    def _jsonrpc_response(self, id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": id, "result": result}

    def _jsonrpc_error(self, id: Any, code: int, message: str,
                       data: Any = None) -> dict:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": id, "error": err}

    # ── Protocol handlers ──

    def handle_initialize(self, id: Any, params: dict) -> dict:
        return self._jsonrpc_response(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": "hive-engine",
                "version": "0.3.0",
            },
        })

    def handle_tools_list(self, id: Any, params: dict) -> dict:
        return self._jsonrpc_response(id, {"tools": TOOLS})

    def handle_resources_list(self, id: Any, params: dict) -> dict:
        """Return current provider config and persona status as resources."""
        provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
        ladder = router.LADDERS.get(provider, {})

        resources = [
            {
                "uri": "hive://config/provider",
                "name": "Current Provider Configuration",
                "description": f"Active provider: {provider}",
                "mimeType": "application/json",
            },
            {
                "uri": "hive://status/personas",
                "name": "Persona Status",
                "description": "Status of all 8 HIVE personas",
                "mimeType": "application/json",
            },
        ]
        return self._jsonrpc_response(id, {"resources": resources})

    def handle_resources_read(self, id: Any, params: dict) -> dict:
        """Read a specific resource by URI."""
        uri = params.get("uri", "")

        if uri == "hive://config/provider":
            provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
            ladder = router.LADDERS.get(provider, {})
            content = json.dumps({
                "provider": provider,
                "ladder": {str(k): v for k, v in ladder.items()},
                "available_providers": list(router.LADDERS.keys()),
                "tier_map": router.TIER_MAP,
            }, indent=2)
            return self._jsonrpc_response(id, {
                "contents": [{"uri": uri, "mimeType": "application/json", "text": content}]
            })

        elif uri == "hive://status/personas":
            personas_info = {}
            provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
            ladder = router.LADDERS.get(provider, {})
            for p in PERSONA_NAMES:
                tier = router.TIER_MAP.get(p, 2)
                personas_info[p] = {
                    "tier": tier,
                    "model": ladder.get(tier, "N/A"),
                    "status": "ready",
                }
            content = json.dumps(personas_info, indent=2)
            return self._jsonrpc_response(id, {
                "contents": [{"uri": uri, "mimeType": "application/json", "text": content}]
            })

        return self._jsonrpc_error(id, -32602, f"Unknown resource URI: {uri}")

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

    # ── Tool dispatch ──

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
        elif name == "hive_status":
            return self._get_status()
        elif name == "hive_switch_provider":
            return self._switch_provider(args["provider"])
        else:
            raise ValueError(f"Unknown tool: {name}")

    def _get_status(self) -> dict[str, Any]:
        """Build comprehensive status report."""
        provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
        ladder = router.LADDERS.get(provider, {})

        # Persona info
        personas: dict[str, Any] = {}
        for p in PERSONA_NAMES:
            tier = router.TIER_MAP.get(p, 2)
            personas[p] = {
                "tier": tier,
                "model": ladder.get(tier, "N/A"),
                "status": "ready",
            }

        # Memory stats
        mem_stats = self.memory.get_stats()
        db_stats = self.db.get_stats()

        return {
            "provider": {
                "name": provider,
                "ladder": {str(k): v for k, v in ladder.items()},
                "available": list(router.LADDERS.keys()),
            },
            "personas": personas,
            "memory": {
                "working_turns": mem_stats.get("working_size", 0),
                "compressed_anchors": mem_stats.get("compressed_anchors", 0),
                "archival_turns": mem_stats.get("archival_size", 0),
                "total_turns_ram": mem_stats.get("total_turns", 0),
            },
            "database": db_stats,
            "session": {
                "id": self.session_id,
                "uptime_seconds": int(time.time() - self._start_time),
            },
        }

    def _switch_provider(self, provider: str) -> dict[str, Any]:
        """Switch the active LLM provider."""
        provider = provider.strip().lower()
        if provider not in router.LADDERS:
            return {
                "success": False,
                "error": f"Unknown provider: {provider}",
                "available": list(router.LADDERS.keys()),
            }
        os.environ["HIVE_PROVIDER"] = provider
        ladder = router.LADDERS[provider]
        return {
            "success": True,
            "provider": provider,
            "ladder": {str(k): v for k, v in ladder.items()},
        }

    # ── Request routing ──

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
        elif method == "resources/list":
            return self.handle_resources_list(id, params)
        elif method == "resources/read":
            return self.handle_resources_read(id, params)
        elif method == "ping":
            return self._jsonrpc_response(id, {})
        else:
            if id is not None:
                return self._jsonrpc_error(id, -32601, f"Method not found: {method}")
            return None  # ignore unknown notifications

    # ── Stdio transport with Content-Length framing ──

    def _write_message(self, data: dict) -> None:
        """Write a JSON-RPC message with Content-Length header."""
        body = json.dumps(data)
        body_bytes = body.encode("utf-8")
        header = f"Content-Length: {len(body_bytes)}\r\n\r\n"
        sys.stdout.buffer.write(header.encode("utf-8"))
        sys.stdout.buffer.write(body_bytes)
        sys.stdout.buffer.flush()

    def _read_message(self) -> dict | None:
        """Read a JSON-RPC message. Supports both Content-Length framing and bare JSON lines."""
        # Read a line from stdin
        line = sys.stdin.buffer.readline()
        if not line:
            return None  # EOF

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            return None

        # Check if this is a Content-Length header
        if line_str.startswith("Content-Length:"):
            length = int(line_str.split(":", 1)[1].strip())
            # Read until we get the empty line separator
            while True:
                separator = sys.stdin.buffer.readline()
                sep_str = separator.decode("utf-8", errors="replace").strip()
                if sep_str == "":
                    break
            # Read exactly `length` bytes
            body_bytes = b""
            while len(body_bytes) < length:
                chunk = sys.stdin.buffer.read(length - len(body_bytes))
                if not chunk:
                    break
                body_bytes += chunk
            body = body_bytes.decode("utf-8", errors="replace")
            return json.loads(body)
        else:
            # Try to parse as bare JSON (backwards compatibility)
            try:
                return json.loads(line_str)
            except json.JSONDecodeError:
                return None

    def run(self) -> None:
        """Main stdio loop: read JSON-RPC from stdin, write to stdout."""
        while True:
            try:
                request = self._read_message()
                if request is None:
                    # Check if stdin is closed
                    if sys.stdin.buffer.closed:
                        break
                    continue

                response = self.handle_request(request)
                if response is not None:
                    self._write_message(response)

            except json.JSONDecodeError:
                continue
            except Exception:
                traceback.print_exc(file=sys.stderr)
                continue

        self.db.close()


def main() -> None:
    server = HiveMCPServer()
    server.run()


if __name__ == "__main__":
    main()
