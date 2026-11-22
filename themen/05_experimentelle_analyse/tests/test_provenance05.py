"""Umgebungsangaben ohne Linux-spezifische Pflichtdateien."""

from experimentelle_analyse import provenance


def test_environment_without_proc_cpuinfo_uses_platform_processor(monkeypatch, tmp_path):
    # macOS und Windows besitzen kein /proc/cpuinfo; die Pipeline darf nicht abbrechen.
    monkeypatch.setattr(provenance, "CPUINFO", tmp_path / "fehlt" / "cpuinfo")
    monkeypatch.setattr(provenance.platform, "processor", lambda: "Testprozessor")
    environment = provenance.environment()
    assert environment["cpu"] == "Testprozessor"
    assert environment["clock"]["unit"] == "ns"


def test_environment_reads_model_name_from_cpuinfo(monkeypatch, tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nmodel name\t: Beispiel-CPU 1.0 GHz\n", encoding="utf-8")
    monkeypatch.setattr(provenance, "CPUINFO", cpuinfo)
    monkeypatch.setattr(provenance.platform, "processor", lambda: "Ersatz")
    assert provenance.environment()["cpu"] == "Beispiel-CPU 1.0 GHz"


def test_environment_falls_back_when_cpuinfo_lacks_model_name(monkeypatch, tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nHardware\t: ARM\n", encoding="utf-8")
    monkeypatch.setattr(provenance, "CPUINFO", cpuinfo)
    monkeypatch.setattr(provenance.platform, "processor", lambda: "Ersatz")
    assert provenance.environment()["cpu"] == "Ersatz"
