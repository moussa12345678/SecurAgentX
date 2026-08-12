from cli.tui_design import color_lerp, format_bytes


def test_color_lerp_interpolates_hex_colors_with_fractional_channels():
    assert color_lerp("#000000", "#ffffff", 0.5) == "#7f7f7f"
    assert color_lerp("#abc", "#123456", 0.0) == "#aabbcc"


def test_format_bytes_preserves_fractional_scaling_without_mutating_input_type():
    assert format_bytes(1024) == "1.0KB"
    assert format_bytes(1536) == "1.5KB"
