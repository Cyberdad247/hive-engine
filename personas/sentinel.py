"""Sentinel persona -- Tier 1 security reviewer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from core import router
from personas.base import Persona


@dataclass
class SecurityFinding:
    """A single security finding."""
    issue: str
    severity: str  # low, medium, high, critical
    line_hint: str = ""
    recommendation: str = ""


@dataclass
class SecurityAssessment:
    """Complete security assessment result."""
    findings: list[SecurityFinding] = field(default_factory=list)
    overall_risk: str = "low"  # low, medium, high, critical
    summary: str = ""
    passed: bool = True


class Sentinel(Persona):
    """Security reviewer persona. Analyzes code for vulnerabilities.

    Read-only: cannot write files.
    """

    name = "sentinel"
    model_tier = 1
    allowed_tools = {"read_file"}
    system_prompt = (
        "You are Sentinel, the HIVE Engine security reviewer. "
        "Analyze code for security vulnerabilities. Return a JSON object with:\n"
        "- findings: list of {issue, severity, line_hint, recommendation}\n"
        "  severity is one of: low, medium, high, critical\n"
        "- overall_risk: low/medium/high/critical\n"
        "- summary: one-line summary\n"
        "- passed: boolean (true if no high/critical findings)\n\n"
        "Output valid JSON only. No markdown fences."
    )

    def process(self, prompt: str, **kwargs: Any) -> SecurityAssessment:
        """Analyze file content for security issues.

        Args:
            prompt: The file content or code to review.
            **kwargs: Extra args (e.g., file_path for context).

        Returns:
            SecurityAssessment with findings and overall risk.
        """
        file_path = kwargs.pop("file_path", None)
        system = kwargs.pop("system_prompt", self.system_prompt)

        review_prompt = prompt
        if file_path:
            review_prompt = f"File: {file_path}\n\n{prompt}"

        response = router.route(
            self.name,
            review_prompt,
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

        # Parse the response into a SecurityAssessment
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(response[start:end])
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        findings = []
        for f in data.get("findings", []):
            if isinstance(f, dict):
                findings.append(SecurityFinding(
                    issue=f.get("issue", "Unknown"),
                    severity=f.get("severity", "medium"),
                    line_hint=f.get("line_hint", ""),
                    recommendation=f.get("recommendation", ""),
                ))

        overall_risk = data.get("overall_risk", "medium")
        passed = data.get("passed", not any(
            f.severity in ("high", "critical") for f in findings
        ))

        return SecurityAssessment(
            findings=findings,
            overall_risk=overall_risk,
            summary=data.get("summary", "Review complete."),
            passed=passed,
        )

    # -- helper to parse JSON from LLM responses --------------------------

    def _parse_json(self, response: str) -> dict:
        """Extract and parse JSON from an LLM response string."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(response[start:end])
                except json.JSONDecodeError:
                    return {}
            return {}

    # -- new skills --------------------------------------------------------

    def scan_dependencies(self, requirements_text: str, **kwargs: Any) -> Dict[str, Any]:
        """Scan dependency manifest content for vulnerable or risky packages.

        Args:
            requirements_text: Raw text of a requirements.txt or package.json.
            **kwargs: Extra args forwarded to the router.

        Returns:
            Dict with keys ``findings`` (list of dicts with package, severity,
            issue, recommendation), ``overall_risk``, and ``summary``.
        """
        system = (
            "You are Sentinel, the HIVE Engine security reviewer. "
            "You are scanning a dependency manifest (requirements.txt or package.json). "
            "Check every listed package for:\n"
            "- Known CVEs or security advisories\n"
            "- Typosquatting (names very similar to popular packages)\n"
            "- Unmaintained or abandoned packages\n"
            "- Packages that request excessive permissions or have suspicious install scripts\n\n"
            "Return a JSON object with:\n"
            '- findings: list of {package: str, severity: "low"|"medium"|"high"|"critical", '
            "issue: str, recommendation: str}\n"
            '- overall_risk: "low"|"medium"|"high"|"critical"\n'
            "- summary: one-line summary of the scan\n\n"
            "Output valid JSON only. No markdown fences."
        )

        response = router.route(
            self.name,
            f"Scan the following dependency manifest:\n\n{requirements_text}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)
        data = self._parse_json(response)

        findings: List[Dict[str, str]] = []
        for f in data.get("findings", []):
            if isinstance(f, dict):
                findings.append({
                    "package": f.get("package", "unknown"),
                    "severity": f.get("severity", "medium"),
                    "issue": f.get("issue", ""),
                    "recommendation": f.get("recommendation", ""),
                })

        return {
            "findings": findings,
            "overall_risk": data.get("overall_risk", "low"),
            "summary": data.get("summary", "Dependency scan complete."),
        }

    def owasp_checklist(self, code: str, app_type: str = "web", **kwargs: Any) -> Dict[str, Any]:
        """Check code against the OWASP Top 10 2021 categories.

        Args:
            code: Source code to evaluate.
            app_type: Application type hint (e.g. ``"web"``, ``"api"``).
            **kwargs: Extra args forwarded to the router.

        Returns:
            Dict with keys ``checks`` (list of dicts with owasp_id, category,
            status, details), ``score`` (0-100), and ``summary``.
        """
        system = (
            "You are Sentinel, the HIVE Engine security reviewer. "
            "Systematically evaluate the provided code against every OWASP Top 10 2021 category:\n"
            "A01:2021 Broken Access Control\n"
            "A02:2021 Cryptographic Failures\n"
            "A03:2021 Injection\n"
            "A04:2021 Insecure Design\n"
            "A05:2021 Security Misconfiguration\n"
            "A06:2021 Vulnerable and Outdated Components\n"
            "A07:2021 Identification and Authentication Failures\n"
            "A08:2021 Software and Data Integrity Failures\n"
            "A09:2021 Security Logging and Monitoring Failures\n"
            "A10:2021 Server-Side Request Forgery\n\n"
            "Return a JSON object with:\n"
            '- checks: list of {owasp_id: str, category: str, status: "pass"|"fail"|"warning", '
            "details: str}\n"
            "- score: integer 0-100 (100 = all pass)\n"
            "- summary: one-line summary\n\n"
            "Output valid JSON only. No markdown fences."
        )

        response = router.route(
            self.name,
            f"Application type: {app_type}\n\nCode to review:\n\n{code}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)
        data = self._parse_json(response)

        checks: List[Dict[str, str]] = []
        for c in data.get("checks", []):
            if isinstance(c, dict):
                checks.append({
                    "owasp_id": c.get("owasp_id", ""),
                    "category": c.get("category", ""),
                    "status": c.get("status", "warning"),
                    "details": c.get("details", ""),
                })

        return {
            "checks": checks,
            "score": int(data.get("score", 0)),
            "summary": data.get("summary", "OWASP checklist review complete."),
        }

    def compliance_check(
        self, code: str, standard: str = "general", **kwargs: Any
    ) -> Dict[str, Any]:
        """Check code against a compliance standard.

        Args:
            code: Source code to evaluate.
            standard: One of ``"gdpr"``, ``"hipaa"``, ``"pci-dss"``, or
                ``"general"`` (best practices).
            **kwargs: Extra args forwarded to the router.

        Returns:
            Dict with keys ``standard``, ``findings`` (list of dicts with
            requirement, status, details), ``compliant`` (bool), and
            ``summary``.
        """
        system = (
            "You are Sentinel, the HIVE Engine security reviewer. "
            f"Evaluate the provided code for compliance with the '{standard}' standard. "
            "Check the following areas as they apply to the standard:\n"
            "- Data handling and storage practices\n"
            "- Logging and audit trails\n"
            "- Encryption of data at rest and in transit\n"
            "- Access controls and authentication\n"
            "- Data retention and deletion policies\n"
            "- Consent and privacy requirements (GDPR)\n"
            "- Protected health information safeguards (HIPAA)\n"
            "- Cardholder data protection (PCI-DSS)\n\n"
            "Return a JSON object with:\n"
            f'- standard: "{standard}"\n'
            "- findings: list of {requirement: str, "
            'status: "compliant"|"non_compliant"|"needs_review", details: str}\n'
            "- compliant: boolean (true only if zero non_compliant findings)\n"
            "- summary: one-line summary\n\n"
            "Output valid JSON only. No markdown fences."
        )

        response = router.route(
            self.name,
            f"Compliance standard: {standard}\n\nCode to review:\n\n{code}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)
        data = self._parse_json(response)

        findings: List[Dict[str, str]] = []
        for f in data.get("findings", []):
            if isinstance(f, dict):
                findings.append({
                    "requirement": f.get("requirement", ""),
                    "status": f.get("status", "needs_review"),
                    "details": f.get("details", ""),
                })

        compliant = data.get(
            "compliant",
            not any(f["status"] == "non_compliant" for f in findings),
        )

        return {
            "standard": standard,
            "findings": findings,
            "compliant": bool(compliant),
            "summary": data.get("summary", "Compliance review complete."),
        }
