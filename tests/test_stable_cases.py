import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_stable_cases", ROOT / "src" / "build_stable_cases.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_stability_controls_are_idempotent():
    source = "&HEAD CHID='x'/\n&TIME T_END=100./\n&SURF ID='fuel', HRRPUA=200., RAMP_Q='Q'/\n"
    text = MODULE.patch_time(source)
    text, changed = MODULE.patch_combustion_ramp(text)
    text = MODULE.patch_solver(text)
    assert changed == 1
    assert "DT=0.002" in text
    assert "CFL_MAX=0.5" in text
    assert "&TIME T_END=100., DT=0.002/" in text
    assert "&MISC CHECK_HT=.TRUE., CFL_MAX=0.5/" in text
    assert "TAU_Q=10.0" in text
    assert "RAMP_Q" not in text
    assert "&CLIP" in text and "&PRES" in text


def test_nonburning_surface_is_not_given_tau_q():
    text, changed = MODULE.patch_combustion_ramp("&SURF ID='wall', COLOR='GRAY'/")
    assert changed == 0
    assert "TAU_Q" not in text
