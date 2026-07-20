from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "case_manifest.json").read_text(encoding="utf-8"))
assert len(manifest["cases"]) == 5
for summary in manifest["cases"]:
    case = summary["case"]
    text = (ROOT / "cases" / case / f"{case}.fds").read_text(encoding="utf-8")
    assert len(re.findall(r"&MESH\b", text)) == 32
    assert set(map(int, re.findall(r"MPI_PROCESS=(\d+)", text))) == set(range(32))
    assert "ID='U04.stl'" not in text
    assert "SPECIFIC_HEAT=0.896" in text
    assert "N_REACTIONS" not in text and not re.search(r"&MATL[\s\S]*?\bA=", text)
    assert "ID='\u7535\u529b\u4f20\u8f93\u5b50\u7cfb\u7edf'" in text and "THICKNESS(1)=1.0E-3" in text
    assert "ID='\u64cd\u7eb5\u5b50\u7cfb\u7edf'" in text and "THICKNESS(1)=2.0E-3" in text
    assert summary["temperature_probes"] == 162
    assert all(summary["probe_counts"].get(f"H{i}", 0) > 0 for i in range(1, 8))
    voxel_vents = re.findall(r"&VENT\s+ID='VF\d+'[\s\S]*?/", text)
    assert len(voxel_vents) == summary["illuminated_vents"]
    for vent in voxel_vents:
        values = [float(value) for value in re.search(r"XB=([^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+)", vent).group(1).split(",")]
        assert sum(abs(values[i] - values[i + 1]) < 1e-9 for i in (0, 2, 4)) == 1
print("validated", len(manifest["cases"]), "cases")
