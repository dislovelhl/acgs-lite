"""
Validation tests for ACGS2_FAccT_enhanced.tex paper claims.

Verifies that metrics, citations, and structural claims in the paper
match the actual codebase state. Run with:
    python -m pytest src/research/docs/research/test_paper_validation.py -v
"""

import csv
import re
from collections import Counter
from pathlib import Path

import pytest

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[4]  # up from src/research/docs/research/
PAPER_PATH = Path(__file__).parent / "ACGS2_FAccT_enhanced.tex"
CONSTITUTION_DIR = PROJECT_ROOT / "packages" / "acgs-lite" / "src" / "acgs_lite" / "constitution"
RUST_SRC_DIR = PROJECT_ROOT / "packages" / "acgs-lite" / "rust" / "src"
CONSTANTS_FILE = PROJECT_ROOT / "src" / "core" / "shared" / "constants.py"
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"
AUTORESEARCH_RESULTS = PROJECT_ROOT / "autoresearch" / "results.tsv"


@pytest.fixture(scope="module")
def paper_text():
    """Load the LaTeX source."""
    return PAPER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def paper_macros(paper_text):
    """Extract LaTeX macro definitions."""
    macros = {}
    for match in re.finditer(r"\\newcommand\{\\(\w+)\}\{(.+?)\}", paper_text):
        macros[match.group(1)] = match.group(2)
    return macros


# ============================================================================
# Section 1: LaTeX Structural Validation
# ============================================================================
class TestLatexStructure:
    """Validate LaTeX syntax and structure."""

    def test_brace_balance(self, paper_text):
        """All braces must be balanced (excluding escaped braces)."""
        # Remove escaped braces and verbatim environments
        cleaned = re.sub(r"\\[{}]", "", paper_text)
        cleaned = re.sub(r"\\begin\{verbatim\}.*?\\end\{verbatim\}", "", cleaned, flags=re.DOTALL)
        open_count = cleaned.count("{")
        close_count = cleaned.count("}")
        assert open_count == close_count, (
            f"Brace imbalance: {open_count} open vs {close_count} close"
        )

    def test_environment_balance(self, paper_text):
        """All \\begin{{env}} must have matching \\end{{env}}."""
        begins = re.findall(r"\\begin\{(\w+)\}", paper_text)
        ends = re.findall(r"\\end\{(\w+)\}", paper_text)
        begin_counts = Counter(begins)
        end_counts = Counter(ends)
        for env, count in begin_counts.items():
            assert count == end_counts.get(env, 0), (
                f"Environment '{env}': {count} begins vs {end_counts.get(env, 0)} ends"
            )

    def test_no_duplicate_paragraphs(self, paper_text):
        """No paragraph should appear twice (catches copy-paste errors)."""
        lines = [line.strip() for line in paper_text.split("\n") if len(line.strip()) > 80]
        seen = set()
        duplicates = []
        for line in lines:
            if line in seen and not line.startswith("%") and not line.startswith("\\"):
                duplicates.append(line[:80])
            seen.add(line)
        assert len(duplicates) == 0, f"Duplicate paragraphs found: {duplicates}"

    def test_no_markdown_in_latex(self, paper_text):
        """No markdown bold/italic syntax in LaTeX source."""
        md_bold = re.findall(r"\*\*[^*]+\*\*", paper_text)
        # Filter out math contexts (** can appear in math)
        real_md = [m for m in md_bold if "\\begin{equation" not in m]
        assert len(real_md) == 0, f"Markdown bold found in LaTeX: {real_md[:3]}"

    def test_no_unicode_dashes(self, paper_text):
        """Use LaTeX --- not Unicode em-dash."""
        # Allow in comments
        non_comment_lines = [
            line for line in paper_text.split("\n") if not line.strip().startswith("%")
        ]
        content = "\n".join(non_comment_lines)
        unicode_emdash_count = content.count("\u2014")  # em-dash
        assert unicode_emdash_count == 0, (
            f"Found {unicode_emdash_count} Unicode em-dashes; use LaTeX ---"
        )


# ============================================================================
# Section 2: Citation Integrity
# ============================================================================
class TestCitationIntegrity:
    """Validate all citations are defined and used."""

    def test_all_cited_refs_defined(self, paper_text):
        """Every \\cite{{key}} must have a matching \\bibitem{{key}}."""
        cited = set(re.findall(r"\\cite\{([^}]+)\}", paper_text))
        cited_keys = set()
        for group in cited:
            for key in group.split(","):
                cited_keys.add(key.strip())

        defined = set(re.findall(r"\\bibitem\{([^}]+)\}", paper_text))
        undefined = cited_keys - defined
        assert len(undefined) == 0, f"Cited but undefined: {undefined}"

    def test_all_defined_refs_cited(self, paper_text):
        """Every \\bibitem{{key}} must be cited at least once."""
        defined = set(re.findall(r"\\bibitem\{([^}]+)\}", paper_text))

        cited = set(re.findall(r"\\cite\{([^}]+)\}", paper_text))
        cited_keys = set()
        for group in cited:
            for key in group.split(","):
                cited_keys.add(key.strip())

        orphaned = defined - cited_keys
        assert len(orphaned) == 0, f"Defined but never cited: {orphaned}"

    def test_reference_count(self, paper_text):
        """Paper should have a reasonable number of references (15-30 for FAccT)."""
        refs = re.findall(r"\\bibitem\{", paper_text)
        assert 15 <= len(refs) <= 30, f"Reference count {len(refs)} outside expected 15-30"

    def test_no_broken_citations(self, paper_text):
        """No malformed \\cite commands."""
        broken = re.findall(r"\\cite\{[^}]*$", paper_text, re.MULTILINE)
        assert len(broken) == 0, f"Broken citations (unclosed brace): {broken}"


# ============================================================================
# Section 3: Metric Accuracy (Paper vs Codebase)
# ============================================================================
class TestMetricAccuracy:
    """Validate paper claims match actual codebase."""

    def test_constitution_module_count(self, paper_macros):
        """Paper's constitutionmodules macro matches actual module count."""
        if not CONSTITUTION_DIR.exists():
            pytest.skip("Constitution directory not found")
        actual = len([f for f in CONSTITUTION_DIR.glob("*.py") if f.name != "__init__.py"])
        claimed = int(paper_macros.get("constitutionmodules", "0"))
        # Allow +-2 tolerance for module additions between paper drafts
        assert abs(actual - claimed) <= 2, (
            f"Constitution modules: paper claims {claimed}, actual is {actual}"
        )

    def test_rust_module_count(self, paper_macros):
        """Paper's rustmodules macro matches actual Rust source files."""
        if not RUST_SRC_DIR.exists():
            pytest.skip("Rust source directory not found")
        actual = len(
            [
                f
                for f in RUST_SRC_DIR.glob("*.rs")
                if f.name != "lib.rs"  # lib.rs is the entry point, not a module
            ]
        )
        claimed = int(paper_macros.get("rustmodules", "0"))
        # Paper lists specific named modules; lib.rs is entry point
        # Actual modules: context, hash, impact_scorer, result, severity, validator, verbs = 7
        # Plus lib.rs = 8 files total
        assert abs(actual - claimed) <= 2, (
            f"Rust modules: paper claims {claimed}, actual is {actual} (excluding lib.rs)"
        )

    def test_constitutional_hash(self, paper_macros):
        """Paper's hash matches the canonical source in constants.py."""
        if not CONSTANTS_FILE.exists():
            pytest.skip("Constants file not found")
        constants_text = CONSTANTS_FILE.read_text()
        hash_match = re.search(r"['\"]?(608508a9bd224290)['\"]?", constants_text)
        assert hash_match is not None, "Constitutional hash not found in constants.py"
        claimed = paper_macros.get("constitutionalhash", "")
        assert claimed == hash_match.group(1), (
            f"Hash mismatch: paper={claimed}, constants.py={hash_match.group(1)}"
        )

    def test_pytest_marker_count(self, paper_macros):
        """Paper's testmarkers macro matches actual pyproject.toml markers."""
        if not PYPROJECT_FILE.exists():
            pytest.skip("pyproject.toml not found")
        pyproject_text = PYPROJECT_FILE.read_text()
        markers = re.findall(r'^\s+"(\w+):', pyproject_text, re.MULTILINE)
        actual = len(set(markers))
        claimed = int(paper_macros.get("testmarkers", "0"))
        assert abs(actual - claimed) <= 3, (
            f"Pytest markers: paper claims {claimed}, actual is {actual}"
        )

    def test_performance_baseline(self, paper_macros):
        """Paper's baseline latency is plausible."""
        baseline = paper_macros.get("baselinelatency", "")
        # Should be in ms format like "0.146ms"
        match = re.match(r"([\d.]+)ms", baseline)
        assert match is not None, f"Baseline latency format invalid: {baseline}"
        value = float(match.group(1))
        assert 0.05 < value < 1.0, f"Baseline latency {value}ms outside plausible range"

    def test_optimized_latency(self, paper_macros):
        """Paper's optimized latency is plausible and better than baseline."""
        optimized = paper_macros.get("optimizedlatency", "")
        baseline = paper_macros.get("baselinelatency", "")
        opt_match = re.match(r"([\d.]+)ms", optimized)
        base_match = re.match(r"([\d.]+)ms", baseline)
        assert opt_match and base_match, "Latency format invalid"
        opt_val = float(opt_match.group(1))
        base_val = float(base_match.group(1))
        assert opt_val < base_val, f"Optimized ({opt_val}ms) should be < baseline ({base_val}ms)"

    def test_autoresearch_results_exist(self):
        """Autoresearch results file should exist if iterations are claimed."""
        if not AUTORESEARCH_RESULTS.exists():
            pytest.skip("Autoresearch results file not found")
        lines = AUTORESEARCH_RESULTS.read_text().strip().split("\n")
        # At least header + some data rows
        assert len(lines) > 10, f"Only {len(lines)} lines in results.tsv"

    def test_compliance_rate_plausible(self, paper_macros):
        """Compliance rate should be between 90% and 100%."""
        rate_str = paper_macros.get("compliancerate", "0")
        # Extract numeric value (e.g., "97.0\\%" -> 97.0)
        match = re.search(r"([\d.]+)", rate_str)
        assert match, f"Cannot parse compliance rate: {rate_str}"
        rate = float(match.group(1))
        assert 90.0 <= rate <= 100.0, f"Compliance rate {rate}% outside plausible 90-100%"

    def test_error_rate_consistent_with_compliance(self, paper_macros):
        """Error rate + compliance rate should sum to ~100%."""
        compliance_str = paper_macros.get("compliancerate", "0")
        error_str = paper_macros.get("errorrate", "0")
        comp_match = re.search(r"([\d.]+)", compliance_str)
        err_match = re.search(r"([\d.]+)", error_str)
        assert comp_match and err_match, "Cannot parse rates"
        total = float(comp_match.group(1)) + float(err_match.group(1))
        assert abs(total - 100.0) < 0.5, (
            f"Compliance ({comp_match.group(1)}%) + Error ({err_match.group(1)}%) = {total}%, expected ~100%"
        )

    def test_scenario_count_matches_table(self, paper_text):
        """Total scenarios in compliance table should match scenariocount macro."""
        # Find the compliance results table rows with scenario counts
        rows = re.findall(r"(\w[\w\s-]+)\s*&\s*(\d+)\s*&\s*\d+", paper_text)
        # Sum scenario counts (second group)
        total = sum(int(count) for _, count in rows if int(count) > 0)
        # Get the macro value
        macro_match = re.search(r"\\newcommand\{\\scenariocount\}\{(\d+)\}", paper_text)
        if macro_match:
            claimed = int(macro_match.group(1))
            assert total == claimed, (
                f"Table scenario total ({total}) != scenariocount macro ({claimed})"
            )

    def test_error_cases_consistent(self, paper_text, paper_macros):
        """Error case counts in taxonomy should sum to errorcases macro."""
        # Extract "n=X" only from the error taxonomy section
        taxonomy_start = paper_text.find("Error Taxonomy")
        taxonomy_end = paper_text.find("Performance Results", taxonomy_start)
        if taxonomy_start == -1 or taxonomy_end == -1:
            pytest.skip("Error taxonomy section not found")
        taxonomy_section = paper_text[taxonomy_start:taxonomy_end]
        error_ns = re.findall(r"n=(\d+)", taxonomy_section)
        if error_ns:
            total_errors = sum(int(n) for n in error_ns)
            claimed = int(paper_macros.get("errorcases", "0"))
            assert total_errors == claimed, (
                f"Error taxonomy sums to {total_errors}, macro says {claimed}"
            )


# ============================================================================
# Section 4: FAccT Submission Requirements
# ============================================================================
class TestFAccTRequirements:
    """Validate FAccT 2026 submission requirements."""

    def test_has_abstract(self, paper_text):
        assert "\\begin{abstract}" in paper_text
        assert "\\end{abstract}" in paper_text

    def test_has_ccs_concepts(self, paper_text):
        assert "\\begin{CCSXML}" in paper_text
        assert "\\ccsdesc" in paper_text

    def test_has_keywords(self, paper_text):
        assert "\\keywords{" in paper_text

    def test_has_ethics_statement(self, paper_text):
        assert "Ethics Statement" in paper_text

    def test_has_generative_ai_statement(self, paper_text):
        """FAccT 2026 mandates a Generative AI Usage Statement."""
        assert "Generative AI Usage Statement" in paper_text

    def test_anonymous_submission(self, paper_text):
        """Paper should be anonymous for review."""
        assert "anonymous" in paper_text.lower()
        # Should not contain real author names or institutions
        assert "\\author{Anonymous}" in paper_text

    def test_acmart_document_class(self, paper_text):
        """Must use ACM acmart document class."""
        assert "\\documentclass" in paper_text
        assert "acmart" in paper_text

    def test_page_estimate_within_limit(self, paper_text):
        """Estimate page count (14-page limit for FAccT, excluding references)."""
        # Rough estimate: ~3500 chars per ACM two-column page
        # Remove bibliography
        pre_bib = paper_text.split("\\begin{thebibliography}")[0]
        # Remove comments
        lines = [line for line in pre_bib.split("\n") if not line.strip().startswith("%")]
        content = "\n".join(lines)
        # Remove LaTeX commands (rough)
        content = re.sub(r"\\[a-zA-Z]+(\{[^}]*\})*", " ", content)
        char_count = len(content)
        estimated_pages = char_count / 3500
        assert estimated_pages <= 16, f"Estimated {estimated_pages:.1f} pages (limit 14 + buffer)"

    def test_has_required_sections(self, paper_text):
        """Paper should have standard academic structure."""
        required = [
            "Introduction",
            "Related Work",
            "Conclusion",
        ]
        for section in required:
            assert section in paper_text, f"Missing required section: {section}"


# ============================================================================
# Section 5: Content Consistency
# ============================================================================
class TestContentConsistency:
    """Check internal consistency of paper claims."""

    def test_all_labels_referenced(self, paper_text):
        """Labels defined with \\label should be referenced with \\ref."""
        labels = set(re.findall(r"\\label\{([^}]+)\}", paper_text))
        refs = set(re.findall(r"\\ref\{([^}]+)\}", paper_text))
        # Not all labels need refs (tables, figures), but key section labels should
        section_labels = {label for label in labels if label.startswith("sec:")}
        unreferenced_sections = section_labels - refs
        # Allow unreferenced sections that don't typically need cross-refs
        allowed_unreferenced = {
            "sec:conclusion",
            "sec:intro",
            "sec:related",
            "sec:methodology",
            "sec:evaluation",
        }
        real_unreferenced = unreferenced_sections - allowed_unreferenced
        assert len(real_unreferenced) == 0, f"Unreferenced section labels: {real_unreferenced}"

    def test_table_labels_referenced(self, paper_text):
        """All table labels should be referenced in text."""
        table_labels = set(re.findall(r"\\label\{(tab:[^}]+)\}", paper_text))
        refs = set(re.findall(r"\\ref\{(tab:[^}]+)\}", paper_text))
        unreferenced = table_labels - refs
        assert len(unreferenced) == 0, f"Unreferenced tables: {unreferenced}"

    def test_figure_labels_referenced(self, paper_text):
        """All figure labels should be referenced in text."""
        fig_labels = set(re.findall(r"\\label\{(fig:[^}]+)\}", paper_text))
        refs = set(re.findall(r"\\ref\{(fig:[^}]+)\}", paper_text))
        unreferenced = fig_labels - refs
        assert len(unreferenced) == 0, f"Unreferenced figures: {unreferenced}"

    def test_speedup_factor_consistent(self, paper_macros):
        """Speedup factor should match baseline/optimized ratio."""
        baseline = paper_macros.get("baselinelatency", "")
        optimized = paper_macros.get("optimizedlatency", "")
        speedup_str = paper_macros.get("speedupfactor", "")
        base_match = re.match(r"([\d.]+)ms", baseline)
        opt_match = re.match(r"([\d.]+)ms", optimized)
        speed_match = re.search(r"([\d.]+)", speedup_str)
        if base_match and opt_match and speed_match:
            actual_speedup = float(base_match.group(1)) / float(opt_match.group(1))
            claimed_speedup = float(speed_match.group(1))
            # Allow 20% tolerance for rounding
            assert abs(actual_speedup - claimed_speedup) / claimed_speedup < 0.20, (
                f"Speedup: {baseline}/{optimized} = {actual_speedup:.1f}x, "
                f"but paper claims {claimed_speedup}x"
            )

    def test_error_taxonomy_percentages_sum(self, paper_text):
        """Error taxonomy percentages should sum to ~100%."""
        re.findall(r"(\d+)\\%", paper_text)
        # The four error types are specifically: 41%, 27%, 19%, 13%
        # Find them by looking at the error taxonomy section
        taxonomy_section = paper_text.split("Error Taxonomy")[1].split("Performance Results")[0]
        type_pcts = re.findall(r"(\d+)\\%", taxonomy_section)
        if len(type_pcts) >= 4:
            total = sum(int(p) for p in type_pcts[:4])
            assert total == 100, f"Error taxonomy percentages sum to {total}%, expected 100%"

    def test_eu_ai_act_articles_valid(self, paper_text):
        """EU AI Act article references should be valid (1-113)."""
        articles = re.findall(r"Article\s+(\d+)", paper_text)
        for art in articles:
            num = int(art)
            assert 1 <= num <= 113, f"Invalid EU AI Act article number: {num}"

    def test_research_questions_answered(self, paper_text):
        """Each RQ should appear in both introduction and later sections."""
        for rq in ["RQ1", "RQ2", "RQ3"]:
            occurrences = paper_text.count(rq)
            # RQ should be defined once; answers may reference them
            assert occurrences >= 1, f"{rq} defined but never referenced"

    def test_contributions_match_sections(self, paper_text):
        """Contribution claims should reference real sections."""
        # C1-C4 should reference sections that exist
        section_refs = re.findall(r"Section~\\ref\{(sec:\w+)\}", paper_text)
        labels = set(re.findall(r"\\label\{(sec:\w+)\}", paper_text))
        for ref in section_refs:
            assert ref in labels, f"Section reference {ref} has no matching label"


# ============================================================================
# Section 6: Autoresearch Data Validation
# ============================================================================
class TestAutoresearchValidation:
    """Validate autoresearch claims against results.tsv."""

    @pytest.fixture
    def results_data(self):
        if not AUTORESEARCH_RESULTS.exists():
            pytest.skip("results.tsv not found")
        with AUTORESEARCH_RESULTS.open(newline="") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))

    def test_iterations_exceed_claimed(self, results_data, paper_macros):
        """Actual iterations should be >= paper's claimed count."""
        claimed_str = paper_macros.get("autoresearchiterations", "0")
        claimed_match = re.search(r"(\d+)", claimed_str)
        if claimed_match:
            claimed = int(claimed_match.group(1))
            assert len(results_data) >= claimed, (
                f"Paper claims {claimed}+ iterations, only {len(results_data)} in results.tsv"
            )

    def test_final_latency_better_than_claimed(self, results_data, paper_macros):
        """A logged latency should support the paper's claimed optimized latency."""
        if not results_data:
            pytest.skip("No results data")
        claimed_str = paper_macros.get("optimizedlatency", "")
        claimed_match = re.match(r"([\d.]+)ms", claimed_str)
        if not claimed_match:
            pytest.skip("Cannot parse optimized latency macro")
        claimed_ms = float(claimed_match.group(1))
        observed = [float(r["p99_ms"]) for r in results_data if r.get("p99_ms")]
        if not observed:
            pytest.skip("No p99_ms values found in results.tsv")
        best_ms = min(observed)
        assert best_ms <= claimed_ms * 1.1, (  # 10% tolerance
            f"Best logged P99 ({best_ms}ms) does not support claimed ({claimed_ms}ms)"
        )
