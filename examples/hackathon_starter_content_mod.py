"""
ACGS Hackathon Starter: Content Moderation API
===============================================
A REST API that validates user-generated content against constitutional
rules before publishing. Uses GovernanceEngine directly for fast validation.

Usage:
    pip install acgs-lite fastapi uvicorn
    python hackathon_starter_content_mod.py

Then test:
    curl -X POST http://localhost:8000/validate \
      -H "Content-Type: application/json" \
      -d '{"content": "Check out this great product!", "author": "user123"}'

No API keys required.
"""

from datetime import datetime, timezone

from acgs_lite import Constitution, GovernanceEngine
from acgs_lite.audit import AuditLog

# --- Step 1: Define content moderation rules ---
MODERATION_RULES = """
rules:
  - id: NO_HATE_SPEECH
    text: Content must not contain hate speech or discriminatory language
    severity: critical
    keywords: ["hate", "slur", "discriminate"]

  - id: NO_SPAM
    text: Content must not be spam or unsolicited advertising
    severity: low
    keywords: ["buy now", "limited offer", "click here", "free money"]

  - id: NO_PII_SHARING
    text: Users must not share personal information publicly
    severity: critical
    keywords: ["my phone number is", "my address is", "my SSN"]
    patterns: ["\\\\b\\\\d{3}[-.\\\\s]?\\\\d{3}[-.\\\\s]?\\\\d{4}\\\\b"]

  - id: NO_EXTERNAL_LINKS
    text: Limit external links to prevent phishing
    severity: low
    keywords: ["http://", "https://", "www."]

  - id: MIN_QUALITY
    text: Content must be substantive (not just emoji or single words)
    severity: low
    keywords: ["lol", "ok", "hi", "yo"]
"""


def validate_content(content: str, author: str) -> dict:
    """Validate content against moderation rules. Returns structured result."""
    constitution = Constitution.from_yaml_str(MODERATION_RULES)
    audit = AuditLog()
    engine = GovernanceEngine(constitution, audit_log=audit, strict=False)

    result = engine.validate(content, agent_id=author)

    response = {
        "content": content,
        "author": author,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "approved": result.valid,
        "violations": [],
        "warnings": [],
    }

    for v in result.violations:
        entry = {"rule_id": v.rule_id, "severity": str(v.severity), "message": v.rule_text}
        if v.severity.value == "critical":
            response["violations"].append(entry)
        else:
            response["warnings"].append(entry)

    response["action"] = "PUBLISH" if result.valid else "BLOCK"
    return response


def main() -> None:
    print("=== Content Moderation Demo ===\n")

    test_posts = [
        ("Check out this great product review!", "user123"),
        ("BUY NOW! Limited offer! Click here for free money!", "spammer42"),
        ("My phone number is 555-123-4567, call me!", "naive_user"),
        ("I really enjoyed this article about gardening.", "gardener99"),
        ("Visit https://phishing-site.com for deals", "sketchy_link"),
        ("Hi", "low_effort"),
    ]

    for content, author in test_posts:
        result = validate_content(content, author)
        status = "APPROVED" if result["approved"] else "BLOCKED"
        print(f'[{status}] @{author}: "{content}"')
        if result["violations"]:
            for v in result["violations"]:
                print(f"  violation: [{v['rule_id']}] {v['message']}")
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"  warning:   [{w['rule_id']}] {w['message']}")
        print()

    # --- Optional: FastAPI server ---
    print("--- To run as API server: ---")
    print("Add FastAPI routes and run with: uvicorn hackathon_starter_content_mod:app")


# --- Optional FastAPI app (uncomment if you have fastapi installed) ---
try:
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI(title="ACGS Content Moderation API")

    class ContentRequest(BaseModel):
        content: str
        author: str = "anonymous"

    @app.post("/validate")
    def api_validate(req: ContentRequest) -> dict:
        return validate_content(req.content, req.author)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "engine": "acgs-lite"}

except ImportError:
    pass  # FastAPI not installed, CLI-only mode


if __name__ == "__main__":
    main()
