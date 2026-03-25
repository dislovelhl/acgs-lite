from __future__ import annotations


class GraphCheckVerifier:
    def __init__(self, db_type: str = "mock") -> None:
        self.db_type = db_type

    async def verify_entities(self, content: str) -> dict[str, object]:
        results: list[dict[str, str]] = []
        lowered = content.lower()
        for token in ["supply chain", "asia", "risk"]:
            if token in lowered:
                results.append({"entity": token, "status": "grounded"})
        if not results:
            results.append({"entity": "content", "status": "unknown"})
        return {
            "is_valid": any(item["status"] == "grounded" for item in results),
            "results": results,
        }
