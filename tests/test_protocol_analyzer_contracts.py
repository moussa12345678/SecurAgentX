from tools.protocol_analyzer import ProtocolAnalyzer, ProtocolType


def test_binary_analysis_keeps_pattern_list_and_report_counters_typed_at_runtime():
    analyzer = ProtocolAnalyzer()

    analysis = analyzer._analyze_binary(b"\x00\x00\x00\x00PK\x03\x04", ProtocolType.UNKNOWN_BINARY)

    assert analysis["common_patterns"] == ["null_padding", "zip_file"]
    assert analyzer.generate_report()["protocol_distribution"] == {}
    assert analyzer.generate_report()["severity_distribution"] == {}
