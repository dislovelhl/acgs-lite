"""
ACGS-2 PII Detection Engine
Constitutional Hash: cdd01ef066bc6cf2

Advanced PII (Personally Identifiable Information) detection engine with:
- 25+ regex patterns for common PII types
- Confidence scoring based on pattern strength and context
- Automatic classification tier assignment
- Batch processing support
- GDPR/CCPA compliance mapping
"""

import hashlib
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from src.core.shared.types import JSONDict, JSONList

from .data_classification import (
    CONSTITUTIONAL_HASH,
    ClassificationResult,
    DataClassificationTier,
    PIICategory,
    PIIDetection,
    classify_by_pii_categories,
    get_compliance_frameworks,
    get_tier_requirements,
)

# ============================================================================
# PII Pattern Definitions
# ============================================================================


@dataclass
class PIIPattern:
    """Definition of a PII detection pattern."""

    name: str
    category: PIICategory
    pattern: re.Pattern
    base_confidence: float = 0.8
    description: str = ""
    examples: list[str] = field(default_factory=list)


# Compile patterns for performance
PII_PATTERNS: list[PIIPattern] = [
    # Personal Identifiers
    PIIPattern(
        name="ssn_us",
        category=PIICategory.PERSONAL_IDENTIFIERS,
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        base_confidence=0.95,
        description="US Social Security Number",
        examples=["123-45-6789"],
    ),
    PIIPattern(
        name="ssn_uk_nino",
        category=PIICategory.PERSONAL_IDENTIFIERS,
        pattern=re.compile(r"\b[A-Z]{2}\d{6}[A-Z]\b", re.IGNORECASE),
        base_confidence=0.90,
        description="UK National Insurance Number",
        examples=["AB123456C"],
    ),
    PIIPattern(
        name="passport_number",
        category=PIICategory.PERSONAL_IDENTIFIERS,
        pattern=re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
        base_confidence=0.75,
        description="Passport Number",
    ),
    PIIPattern(
        name="drivers_license",
        category=PIICategory.PERSONAL_IDENTIFIERS,
        pattern=re.compile(r"\b[A-Z]{1,2}\d{5,8}[A-Z]?\b"),
        base_confidence=0.70,
        description="Driver's License Number",
    ),
    # Contact Information
    PIIPattern(
        name="email",
        category=PIICategory.CONTACT_INFO,
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        base_confidence=0.95,
        description="Email Address",
        examples=["user@example.com"],
    ),
    PIIPattern(
        name="phone_us",
        category=PIICategory.CONTACT_INFO,
        pattern=re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        base_confidence=0.85,
        description="US Phone Number",
        examples=["+1 (555) 123-4567", "555-123-4567"],
    ),
    PIIPattern(
        name="phone_international",
        category=PIICategory.CONTACT_INFO,
        pattern=re.compile(r"\b\+\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"),
        base_confidence=0.80,
        description="International Phone Number",
        examples=["+44 20 1234 5678"],
    ),
    PIIPattern(
        name="address_us",
        category=PIICategory.CONTACT_INFO,
        pattern=re.compile(
            r"\b\d{1,5}\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct)\.?\s*,?\s*[\w\s]+,?\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?\b",
            re.IGNORECASE,
        ),
        base_confidence=0.85,
        description="US Street Address",
    ),
    PIIPattern(
        name="zip_code_us",
        category=PIICategory.CONTACT_INFO,
        pattern=re.compile(r"\b\d{5}(?:-\d{4})?\b"),
        base_confidence=0.60,  # Lower confidence - could be other 5-digit numbers
        description="US ZIP Code",
    ),
    # Financial Information
    PIIPattern(
        name="credit_card",
        category=PIICategory.FINANCIAL,
        pattern=re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b"
        ),
        base_confidence=0.95,
        description="Credit Card Number (Visa, MC, Amex, Discover)",
    ),
    PIIPattern(
        name="credit_card_formatted",
        category=PIICategory.FINANCIAL,
        pattern=re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
        base_confidence=0.90,
        description="Formatted Credit Card Number",
    ),
    PIIPattern(
        name="bank_account_us",
        category=PIICategory.FINANCIAL,
        pattern=re.compile(r"\b\d{8,17}\b"),  # US bank account numbers
        base_confidence=0.50,  # Low confidence - many false positives
        description="Bank Account Number",
    ),
    PIIPattern(
        name="iban",
        category=PIICategory.FINANCIAL,
        pattern=re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"),
        base_confidence=0.90,
        description="International Bank Account Number (IBAN)",
    ),
    PIIPattern(
        name="routing_number",
        category=PIICategory.FINANCIAL,
        pattern=re.compile(r"\b0[0-9]{8}\b|[1-2][0-9]{8}\b|3[0-2][0-9]{7}\b"),
        base_confidence=0.70,
        description="US Bank Routing Number",
    ),
    # Health Information
    PIIPattern(
        name="icd10_code",
        category=PIICategory.HEALTH,
        pattern=re.compile(r"\b[A-Z]\d{2}(?:\.\d{1,4})?\b"),
        base_confidence=0.75,
        description="ICD-10 Diagnosis Code",
    ),
    PIIPattern(
        name="npi_number",
        category=PIICategory.HEALTH,
        pattern=re.compile(r"\b\d{10}\b"),  # NPI is exactly 10 digits
        base_confidence=0.50,  # Low confidence without context
        description="National Provider Identifier",
    ),
    PIIPattern(
        name="dea_number",
        category=PIICategory.HEALTH,
        pattern=re.compile(r"\b[A-Z]{2}\d{7}\b"),
        base_confidence=0.80,
        description="DEA Registration Number",
    ),
    # Location Data
    PIIPattern(
        name="ip_address_v4",
        category=PIICategory.LOCATION,
        pattern=re.compile(
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
        ),
        base_confidence=0.90,
        description="IPv4 Address",
        examples=["192.168.1.1", "10.0.0.1"],
    ),
    PIIPattern(
        name="ip_address_v6",
        category=PIICategory.LOCATION,
        pattern=re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"),
        base_confidence=0.90,
        description="IPv6 Address",
    ),
    PIIPattern(
        name="coordinates",
        category=PIICategory.LOCATION,
        pattern=re.compile(
            r"\b-?(?:90(?:\.0+)?|[1-8]?\d(?:\.\d+)?),\s*-?(?:180(?:\.0+)?|(?:1[0-7]\d|\d{1,2})(?:\.\d+)?)\b"
        ),
        base_confidence=0.85,
        description="GPS Coordinates (lat, long)",
    ),
    # Biometric Identifiers
    PIIPattern(
        name="mac_address",
        category=PIICategory.BIOMETRIC,
        pattern=re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),
        base_confidence=0.85,
        description="MAC Address (device identifier)",
    ),
    # Behavioral
    PIIPattern(
        name="uuid",
        category=PIICategory.BEHAVIORAL,
        pattern=re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
        ),
        base_confidence=0.60,  # Could be legitimate system UUIDs
        description="UUID (potential tracking identifier)",
    ),
    PIIPattern(
        name="cookie_session",
        category=PIICategory.BEHAVIORAL,
        pattern=re.compile(
            r"\b(?:session[_-]?id|sid|sess)[=:]\s*[A-Za-z0-9+/=]{16,}\b", re.IGNORECASE
        ),
        base_confidence=0.80,
        description="Session Cookie/ID",
    ),
]

# Field name patterns that indicate PII
FIELD_NAME_INDICATORS: dict[PIICategory, list[re.Pattern]] = {
    PIICategory.PERSONAL_IDENTIFIERS: [
        re.compile(r"\b(?:ssn|social_?security|national_?id|passport|license)\b", re.IGNORECASE),
        re.compile(r"\b(?:first_?name|last_?name|full_?name|middle_?name)\b", re.IGNORECASE),
        re.compile(r"\b(?:dob|date_?of_?birth|birth_?date|birthday)\b", re.IGNORECASE),
    ],
    PIICategory.CONTACT_INFO: [
        re.compile(r"\b(?:email|e_?mail|email_?address)\b", re.IGNORECASE),
        re.compile(r"\b(?:phone|telephone|mobile|cell|fax)\b", re.IGNORECASE),
        re.compile(r"\b(?:address|street|city|state|zip|postal|country)\b", re.IGNORECASE),
    ],
    PIICategory.FINANCIAL: [
        re.compile(r"\b(?:credit_?card|cc_?num|card_?number|cvv|cvc)\b", re.IGNORECASE),
        re.compile(r"\b(?:bank_?account|account_?number|routing|iban)\b", re.IGNORECASE),
        re.compile(r"\b(?:salary|income|wage|tax|ssn)\b", re.IGNORECASE),
    ],
    PIICategory.HEALTH: [
        re.compile(r"\b(?:medical|health|diagnosis|condition|treatment)\b", re.IGNORECASE),
        re.compile(r"\b(?:prescription|medication|drug|allergy)\b", re.IGNORECASE),
        re.compile(r"\b(?:insurance|policy|claim|npi|dea)\b", re.IGNORECASE),
    ],
    PIICategory.LOCATION: [
        re.compile(r"\b(?:ip_?address|ip|location|geo|lat|lon|coordinates)\b", re.IGNORECASE),
        re.compile(r"\b(?:device_?id|mac_?address|imei)\b", re.IGNORECASE),
    ],
    PIICategory.BIOMETRIC: [
        re.compile(r"\b(?:fingerprint|biometric|face|facial|retina|voice)\b", re.IGNORECASE),
        re.compile(r"\b(?:dna|genetic|blood_?type)\b", re.IGNORECASE),
    ],
}

# ============================================================================
# PII Detector Class
# ============================================================================


class PIIDetector:
    """
    Advanced PII detection engine with confidence scoring and batch processing.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        patterns: list[PIIPattern] | None = None,
        min_confidence: float = 0.5,
        enable_field_analysis: bool = True,
        enable_context_boosting: bool = True,
    ):
        """
        Initialize PII detector.

        Args:
            patterns: Custom patterns (uses defaults if None)
            min_confidence: Minimum confidence threshold for detections
            enable_field_analysis: Analyze field names for PII indicators
            enable_context_boosting: Boost confidence based on context
        """
        self.patterns = patterns or PII_PATTERNS
        self.min_confidence = min_confidence
        self.enable_field_analysis = enable_field_analysis
        self.enable_context_boosting = enable_context_boosting
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def detect(
        self,
        data: JSONDict | str | JSONList,
        field_path: str = "$",
    ) -> list[PIIDetection]:
        """
        Detect PII in data structure.

        Args:
            data: Data to analyze (dict, list, or string)
            field_path: JSON path prefix for detection results

        Returns:
            List of PII detections
        """
        detections = self._detect_raw(data, field_path)
        return self._deduplicate_detections(detections)

    def _detect_raw(self, data: JSONDict | str | JSONList, field_path: str) -> list[PIIDetection]:
        """Collect raw detections without deduplication/filtering pass."""
        if isinstance(data, dict):
            return self._detect_in_mapping(data, field_path)
        if isinstance(data, list):
            return self._detect_in_sequence(data, field_path)
        if isinstance(data, str):
            return self._detect_in_string(data, field_path)
        return []

    def _detect_in_mapping(self, data: JSONDict, field_path: str) -> list[PIIDetection]:
        """Detect PII in dictionary-like payloads."""
        detections: list[PIIDetection] = []
        for key, value in data.items():
            current_path = f"{field_path}.{key}"
            detections.extend(self._field_name_detections(key, current_path))
            detections.extend(self._detect_value(value, current_path))
        return detections

    def _detect_in_sequence(self, data: JSONList, field_path: str) -> list[PIIDetection]:
        """Detect PII in list-like payloads."""
        detections: list[PIIDetection] = []
        for idx, item in enumerate(data):
            current_path = f"{field_path}[{idx}]"
            detections.extend(self._detect_value(item, current_path))
        return detections

    def _field_name_detections(self, field_name: str, field_path: str) -> list[PIIDetection]:
        """Run field-name indicator checks when enabled."""
        if not self.enable_field_analysis:
            return []
        return self._detect_from_field_name(field_name, field_path)

    def _detect_value(self, value: object, field_path: str) -> list[PIIDetection]:
        """Detect PII in a nested value node."""
        if isinstance(value, (dict, list, str)):
            return self._detect_raw(value, field_path)
        return []

    def _detect_in_string(self, text: str, field_path: str) -> list[PIIDetection]:
        """Detect PII patterns in a string."""
        detections: list[PIIDetection] = []

        for pattern in self.patterns:
            matches = pattern.pattern.findall(text)
            if matches:
                confidence = self._calculate_confidence(
                    pattern=pattern,
                    match_count=len(matches),
                    text_length=len(text),
                    field_path=field_path,
                )

                if confidence >= self.min_confidence:
                    # Hash the first match for traceability
                    sample_hash = hashlib.sha256(str(matches[0]).encode()).hexdigest()[:16]

                    detections.append(
                        PIIDetection(
                            category=pattern.category,
                            confidence=confidence,
                            field_path=field_path,
                            matched_pattern=pattern.name,
                            sample_value_hash=sample_hash,
                        )
                    )

        return detections

    def _detect_from_field_name(self, field_name: str, field_path: str) -> list[PIIDetection]:
        """Detect PII indicators from field names."""
        detections: list[PIIDetection] = []

        for category, patterns in FIELD_NAME_INDICATORS.items():
            for pattern in patterns:
                if pattern.search(field_name):
                    detections.append(
                        PIIDetection(
                            category=category,
                            confidence=0.70,  # Field name indication is moderate confidence
                            field_path=field_path,
                            matched_pattern=f"field_name:{pattern.pattern}",
                            sample_value_hash=None,
                        )
                    )
                    break  # One match per category per field

        return detections

    def _calculate_confidence(
        self,
        pattern: PIIPattern,
        match_count: int,
        text_length: int,
        field_path: str,
    ) -> float:
        """Calculate detection confidence with context boosting."""
        confidence = pattern.base_confidence

        # Boost for multiple matches (up to 10%)
        if match_count > 1:
            confidence += min(0.10, match_count * 0.02)

        # Context boosting from field path
        if self.enable_context_boosting:
            field_indicators = FIELD_NAME_INDICATORS.get(pattern.category, [])
            for indicator in field_indicators:
                if indicator.search(field_path):
                    confidence += 0.10
                    break

        # Penalty for very short text (potential false positive)
        if text_length < 10:
            confidence -= 0.10

        return min(1.0, max(0.0, confidence))

    def _deduplicate_detections(
        self,
        detections: list[PIIDetection],
    ) -> list[PIIDetection]:
        """Deduplicate detections, keeping highest confidence per field/category."""
        seen: dict[tuple[str, PIICategory], PIIDetection] = {}

        for detection in detections:
            key = (detection.field_path, detection.category)
            if key not in seen or detection.confidence > seen[key].confidence:
                if detection.confidence >= self.min_confidence:
                    seen[key] = detection

        return list(seen.values())

    def classify(
        self,
        data: JSONDict | str | JSONList,
        tenant_id: str | None = None,
    ) -> ClassificationResult:
        """
        Detect PII and classify data tier.

        Args:
            data: Data to analyze
            tenant_id: Optional tenant identifier

        Returns:
            ClassificationResult with tier and detections
        """
        detections = self.detect(data)
        categories = {d.category for d in detections}

        # Determine tier based on categories
        if not detections:
            tier = DataClassificationTier.INTERNAL
            overall_confidence = 0.0
        else:
            tier = classify_by_pii_categories(list(categories))
            overall_confidence = sum(d.confidence for d in detections) / len(detections)

        # Get tier requirements
        requirements = get_tier_requirements(tier)

        # Get applicable frameworks
        frameworks = list(get_compliance_frameworks(list(categories)))

        return ClassificationResult(
            tier=tier,
            pii_detections=detections,
            pii_categories=categories,
            overall_confidence=overall_confidence,
            recommended_retention_days=requirements.get("default_retention_days", 365),
            applicable_frameworks=frameworks,
            requires_encryption=requirements.get("encryption_required", False),
            requires_audit_logging=requirements.get("audit_logging_required", False),
        )

    def detect_batch(
        self,
        items: list[JSONDict],
        item_id_field: str = "id",
    ) -> dict[str, ClassificationResult]:
        """
        Batch process multiple items for PII detection and classification.

        Args:
            items: List of data items to process
            item_id_field: Field name to use as item identifier

        Returns:
            Dictionary mapping item IDs to ClassificationResults
        """
        results: dict[str, ClassificationResult] = {}

        for item in items:
            item_id = str(item.get(item_id_field, str(uuid.uuid4())))
            results[item_id] = self.classify(item)

        return results

    def scan_generator(
        self,
        items: Iterator[JSONDict],
    ) -> Iterator[tuple[JSONDict, ClassificationResult]]:
        """
        Generator for streaming PII detection.

        Args:
            items: Iterator of data items

        Yields:
            Tuples of (original_item, classification_result)
        """
        for item in items:
            result = self.classify(item)
            yield (item, result)

    def get_statistics(
        self,
        results: list[ClassificationResult],
    ) -> JSONDict:
        """
        Generate statistics from classification results.

        Args:
            results: List of classification results

        Returns:
            Statistics dictionary
        """
        tier_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        framework_counts: dict[str, int] = {}
        total_detections = 0
        avg_confidence = 0.0

        for result in results:
            tier = result.tier.value if hasattr(result.tier, "value") else str(result.tier)
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

            for detection in result.pii_detections:
                cat = (
                    detection.category.value
                    if hasattr(detection.category, "value")
                    else str(detection.category)
                )
                category_counts[cat] = category_counts.get(cat, 0) + 1
                total_detections += 1
                avg_confidence += detection.confidence

            for framework in result.applicable_frameworks:
                fw = framework.value if hasattr(framework, "value") else str(framework)
                framework_counts[fw] = framework_counts.get(fw, 0) + 1

        if total_detections > 0:
            avg_confidence /= total_detections

        return {
            "total_items": len(results),
            "total_detections": total_detections,
            "average_confidence": round(avg_confidence, 3),
            "tier_distribution": tier_counts,
            "category_distribution": category_counts,
            "framework_coverage": framework_counts,
            "items_requiring_encryption": sum(1 for r in results if r.requires_encryption),
            "items_requiring_audit": sum(1 for r in results if r.requires_audit_logging),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# ============================================================================
# Singleton Instance
# ============================================================================

_detector_instance: PIIDetector | None = None


def get_pii_detector(
    min_confidence: float = 0.5,
    enable_field_analysis: bool = True,
) -> PIIDetector:
    """Get or create the singleton PIIDetector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = PIIDetector(
            min_confidence=min_confidence,
            enable_field_analysis=enable_field_analysis,
        )
    return _detector_instance


def reset_pii_detector() -> None:
    """Reset the singleton instance (for testing)."""
    global _detector_instance
    _detector_instance = None


# ============================================================================
# Convenience Functions
# ============================================================================


def detect_pii(
    data: JSONDict | str | JSONList,
    min_confidence: float = 0.5,
) -> list[PIIDetection]:
    """
    Convenience function to detect PII in data.

    Args:
        data: Data to analyze
        min_confidence: Minimum confidence threshold

    Returns:
        List of PII detections
    """
    detector = get_pii_detector(min_confidence=min_confidence)
    return detector.detect(data)


def classify_data(
    data: JSONDict | str | JSONList,
    tenant_id: str | None = None,
) -> ClassificationResult:
    """
    Convenience function to classify data.

    Args:
        data: Data to classify
        tenant_id: Optional tenant identifier

    Returns:
        ClassificationResult
    """
    detector = get_pii_detector()
    return detector.classify(data, tenant_id=tenant_id)


__all__ = [
    "CONSTITUTIONAL_HASH",
    "FIELD_NAME_INDICATORS",
    # Constants
    "PII_PATTERNS",
    # Classes
    "PIIDetector",
    "PIIPattern",
    "classify_data",
    # Convenience functions
    "detect_pii",
    # Singleton
    "get_pii_detector",
    "reset_pii_detector",
]
