"""
Tests for api/badge_generator.py
Constitutional Hash: 608508a9bd224290

Comprehensive coverage of all branches in the badge SVG generator:
  - _score_to_color: all 5 color threshold branches
  - _score_label: percentage formatting at various values
  - generate_badge_svg: defaults, custom args, score clamping, XML escaping,
    width calculations, and SVG structural correctness.
"""

import pytest

from enhanced_agent_bus.api.badge_generator import (
    LOWEST_SCORE_COLOR,
    SCORE_COLORS,
    TEXT_CHAR_WIDTH,
    TEXT_PADDING,
    _score_label,
    _score_to_color,
    generate_badge_svg,
)

# ---------------------------------------------------------------------------
# Module-level constant sanity checks
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_score_colors_is_tuple(self):
        assert isinstance(SCORE_COLORS, tuple)

    def test_score_colors_has_four_entries(self):
        assert len(SCORE_COLORS) == 4

    def test_score_colors_thresholds_descending(self):
        thresholds = [t for t, _ in SCORE_COLORS]
        assert thresholds == sorted(thresholds, reverse=True)

    def test_lowest_score_color_is_red(self):
        assert LOWEST_SCORE_COLOR == "#e05d44"

    def test_text_char_width_positive(self):
        assert TEXT_CHAR_WIDTH > 0

    def test_text_padding_positive(self):
        assert TEXT_PADDING > 0


# ---------------------------------------------------------------------------
# _score_to_color
# ---------------------------------------------------------------------------


class TestScoreToColor:
    """All five branches: >=0.9, >=0.7, >=0.5, >=0.3, <0.3 (fallthrough)."""

    def test_score_1_0_returns_bright_green(self):
        assert _score_to_color(1.0) == "#4c1"

    def test_score_0_9_returns_bright_green(self):
        assert _score_to_color(0.9) == "#4c1"

    def test_score_0_95_returns_bright_green(self):
        assert _score_to_color(0.95) == "#4c1"

    def test_score_just_below_0_9_returns_yellow_green(self):
        assert _score_to_color(0.89) == "#a3c51c"

    def test_score_0_7_returns_yellow_green(self):
        assert _score_to_color(0.7) == "#a3c51c"

    def test_score_0_8_returns_yellow_green(self):
        assert _score_to_color(0.8) == "#a3c51c"

    def test_score_just_below_0_7_returns_yellow(self):
        assert _score_to_color(0.69) == "#dfb317"

    def test_score_0_5_returns_yellow(self):
        assert _score_to_color(0.5) == "#dfb317"

    def test_score_0_6_returns_yellow(self):
        assert _score_to_color(0.6) == "#dfb317"

    def test_score_just_below_0_5_returns_orange(self):
        assert _score_to_color(0.49) == "#fe7d37"

    def test_score_0_3_returns_orange(self):
        assert _score_to_color(0.3) == "#fe7d37"

    def test_score_0_4_returns_orange(self):
        assert _score_to_color(0.4) == "#fe7d37"

    def test_score_just_below_0_3_returns_red(self):
        assert _score_to_color(0.29) == LOWEST_SCORE_COLOR

    def test_score_0_0_returns_red(self):
        assert _score_to_color(0.0) == LOWEST_SCORE_COLOR

    def test_score_0_1_returns_red(self):
        assert _score_to_color(0.1) == LOWEST_SCORE_COLOR

    def test_score_negative_returns_red(self):
        # Negative values fall through all thresholds → red
        assert _score_to_color(-0.5) == LOWEST_SCORE_COLOR

    def test_score_colors_tuple_values_match(self):
        # Verify each threshold value exactly maps to its declared color.
        for threshold, expected_color in SCORE_COLORS:
            assert _score_to_color(threshold) == expected_color


# ---------------------------------------------------------------------------
# _score_label
# ---------------------------------------------------------------------------


class TestScoreLabel:
    def test_score_0_returns_0_percent(self):
        assert _score_label(0.0) == "0%"

    def test_score_1_0_returns_100_percent(self):
        assert _score_label(1.0) == "100%"

    def test_score_0_5_returns_50_percent(self):
        assert _score_label(0.5) == "50%"

    def test_score_0_333_truncates(self):
        # int(0.333 * 100) == 33
        assert _score_label(0.333) == "33%"

    def test_score_0_999_truncates(self):
        # int(0.999 * 100) == 99
        assert _score_label(0.999) == "99%"

    def test_score_0_01_returns_1_percent(self):
        assert _score_label(0.01) == "1%"

    def test_label_ends_with_percent(self):
        assert _score_label(0.75).endswith("%")

    def test_label_contains_integer_only(self):
        label = _score_label(0.75)
        assert label == "75%"


# ---------------------------------------------------------------------------
# generate_badge_svg — defaults
# ---------------------------------------------------------------------------


class TestGenerateBadgeSvgDefaults:
    def test_returns_string(self):
        svg = generate_badge_svg()
        assert isinstance(svg, str)

    def test_default_label_acgs_present(self):
        svg = generate_badge_svg()
        assert "ACGS" in svg

    def test_default_score_1_0_shows_100_percent(self):
        svg = generate_badge_svg()
        assert "100%" in svg

    def test_default_is_valid_svg_open_tag(self):
        svg = generate_badge_svg()
        assert svg.startswith("<svg")

    def test_default_closes_svg_tag(self):
        svg = generate_badge_svg()
        assert svg.strip().endswith("</svg>")

    def test_svg_contains_title_element(self):
        svg = generate_badge_svg()
        assert "<title>" in svg and "</title>" in svg

    def test_svg_contains_linearGradient(self):
        svg = generate_badge_svg()
        assert "linearGradient" in svg

    def test_svg_contains_clipPath(self):
        svg = generate_badge_svg()
        assert "clipPath" in svg

    def test_svg_height_20(self):
        svg = generate_badge_svg()
        assert 'height="20"' in svg

    def test_svg_role_img(self):
        svg = generate_badge_svg()
        assert 'role="img"' in svg

    def test_svg_aria_label_present(self):
        svg = generate_badge_svg()
        assert "aria-label=" in svg

    def test_svg_font_verdana(self):
        svg = generate_badge_svg()
        assert "Verdana" in svg


# ---------------------------------------------------------------------------
# generate_badge_svg — custom label, score, message
# ---------------------------------------------------------------------------


class TestGenerateBadgeSvgCustomArgs:
    def test_custom_label_appears_in_svg(self):
        svg = generate_badge_svg(label="Coverage")
        assert "Coverage" in svg

    def test_custom_score_0_changes_color(self):
        svg = generate_badge_svg(score=0.0)
        assert LOWEST_SCORE_COLOR in svg

    def test_custom_score_0_9_bright_green(self):
        svg = generate_badge_svg(score=0.9)
        assert "#4c1" in svg

    def test_custom_message_overrides_score_label(self):
        svg = generate_badge_svg(message="passing")
        assert "passing" in svg
        # The score label "100%" must not appear in the text content.
        # (The linearGradient uses y2="100%" which is an attribute, not score text.)
        # Check that the title element does not contain the score label.
        assert "<title>ACGS: passing</title>" in svg
        assert "<title>ACGS: 100%</title>" not in svg

    def test_empty_message_falls_back_to_score_label(self):
        # Empty string is falsy; should fall back to score label
        svg = generate_badge_svg(score=0.75, message="")
        assert "75%" in svg

    def test_none_message_falls_back_to_score_label(self):
        svg = generate_badge_svg(score=0.75, message=None)
        assert "75%" in svg

    def test_score_0_7_shows_yellow_green_color(self):
        svg = generate_badge_svg(score=0.7)
        assert "#a3c51c" in svg

    def test_score_0_5_shows_yellow_color(self):
        svg = generate_badge_svg(score=0.5)
        assert "#dfb317" in svg

    def test_score_0_3_shows_orange_color(self):
        svg = generate_badge_svg(score=0.3)
        assert "#fe7d37" in svg

    def test_score_0_1_shows_red_color(self):
        svg = generate_badge_svg(score=0.1)
        assert LOWEST_SCORE_COLOR in svg


# ---------------------------------------------------------------------------
# generate_badge_svg — score clamping
# ---------------------------------------------------------------------------


class TestGenerateBadgeSvgScoreClamping:
    def test_score_greater_than_1_clamped_to_1(self):
        svg_over = generate_badge_svg(score=1.5)
        svg_one = generate_badge_svg(score=1.0)
        # Both should produce identical output
        assert svg_over == svg_one

    def test_score_less_than_0_clamped_to_0(self):
        svg_under = generate_badge_svg(score=-0.5)
        svg_zero = generate_badge_svg(score=0.0)
        assert svg_under == svg_zero

    def test_score_2_still_shows_100_percent(self):
        svg = generate_badge_svg(score=2.0)
        assert "100%" in svg

    def test_score_minus_1_shows_red(self):
        svg = generate_badge_svg(score=-1.0)
        assert LOWEST_SCORE_COLOR in svg

    def test_score_exactly_1_not_clamped(self):
        # Should not change; max(0.0, min(1.0, 1.0)) == 1.0
        svg = generate_badge_svg(score=1.0)
        assert "100%" in svg

    def test_score_exactly_0_not_clamped(self):
        svg = generate_badge_svg(score=0.0)
        assert "0%" in svg


# ---------------------------------------------------------------------------
# generate_badge_svg — XML special character escaping
# ---------------------------------------------------------------------------


class TestGenerateBadgeSvgXmlEscaping:
    def test_ampersand_in_label_is_escaped(self):
        svg = generate_badge_svg(label="A&B")
        assert "&amp;" in svg
        assert "A&B" not in svg  # raw ampersand must not appear

    def test_less_than_in_label_is_escaped(self):
        svg = generate_badge_svg(label="a<b")
        assert "&lt;" in svg
        assert "a<b" not in svg

    def test_greater_than_in_label_is_escaped(self):
        svg = generate_badge_svg(label="a>b")
        assert "&gt;" in svg
        assert "a>b" not in svg

    def test_ampersand_in_message_is_escaped(self):
        svg = generate_badge_svg(message="Q&A")
        assert "&amp;" in svg
        assert "Q&A" not in svg

    def test_less_than_in_message_is_escaped(self):
        svg = generate_badge_svg(message="x<y")
        assert "&lt;" in svg

    def test_greater_than_in_message_is_escaped(self):
        svg = generate_badge_svg(message="x>y")
        assert "&gt;" in svg

    def test_combined_special_chars_all_escaped(self):
        svg = generate_badge_svg(label="A&B", message="<ok>")
        assert "&amp;" in svg
        assert "&lt;" in svg
        assert "&gt;" in svg

    def test_plain_text_not_double_escaped(self):
        svg = generate_badge_svg(label="ACGS", message="ok")
        assert "&amp;" not in svg


# ---------------------------------------------------------------------------
# generate_badge_svg — width calculations
# ---------------------------------------------------------------------------


class TestGenerateBadgeSvgWidthCalculations:
    def test_width_attribute_present(self):
        svg = generate_badge_svg(label="A", score=1.0)
        assert "width=" in svg

    def test_longer_label_produces_larger_width(self):
        svg_short = generate_badge_svg(label="A")
        svg_long = generate_badge_svg(label="ACGS-Constitutional-Governance")

        # Extract the first width="..." value from each SVG
        def extract_total_width(s: str) -> float:
            import re

            m = re.search(r'<svg[^>]+width="([^"]+)"', s)
            assert m is not None, "width not found in SVG"
            return float(m.group(1))

        assert extract_total_width(svg_long) > extract_total_width(svg_short)

    def test_total_width_matches_calculation(self):
        import re

        label = "Test"
        msg = "75%"
        svg = generate_badge_svg(label=label, score=0.75)
        expected_label_w = len(label) * TEXT_CHAR_WIDTH + TEXT_PADDING
        expected_msg_w = len(msg) * TEXT_CHAR_WIDTH + TEXT_PADDING
        expected_total = expected_label_w + expected_msg_w
        m = re.search(r'<svg[^>]+width="([^"]+)"', svg)
        assert m is not None
        assert float(m.group(1)) == pytest.approx(expected_total)

    def test_custom_message_affects_width(self):
        import re

        def extract_total_width(s: str) -> float:
            m = re.search(r'<svg[^>]+width="([^"]+)"', s)
            assert m is not None
            return float(m.group(1))

        svg_short_msg = generate_badge_svg(label="ACGS", score=1.0, message="ok")
        svg_long_msg = generate_badge_svg(label="ACGS", score=1.0, message="all systems nominal")
        assert extract_total_width(svg_long_msg) > extract_total_width(svg_short_msg)


# ---------------------------------------------------------------------------
# generate_badge_svg — SVG structural elements
# ---------------------------------------------------------------------------


class TestGenerateBadgeSvgStructure:
    def test_svg_contains_three_rects_in_clip_group(self):
        svg = generate_badge_svg()
        assert svg.count("<rect") >= 3

    def test_svg_contains_four_text_elements(self):
        svg = generate_badge_svg()
        assert svg.count("<text") == 4

    def test_svg_aria_hidden_on_shadow_texts(self):
        svg = generate_badge_svg()
        assert svg.count('aria-hidden="true"') == 2

    def test_title_element_contains_label_and_message(self):
        svg = generate_badge_svg(label="Gov", message="passing")
        assert "<title>Gov: passing</title>" in svg

    def test_aria_label_contains_label_and_message(self):
        svg = generate_badge_svg(label="Gov", message="passing")
        assert 'aria-label="Gov: passing"' in svg

    def test_msg_color_rect_uses_score_color(self):
        svg = generate_badge_svg(score=0.9)
        assert f'fill="{_score_to_color(0.9)}"' in svg

    def test_label_rect_fill_dark_gray(self):
        svg = generate_badge_svg()
        assert 'fill="#555"' in svg

    def test_gradient_rect_uses_url_s(self):
        svg = generate_badge_svg()
        assert 'fill="url(#s)"' in svg

    def test_xmlns_attribute_present(self):
        svg = generate_badge_svg()
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
