"""Validation test for PvVoltageRideThru controller.

Captures Generator kW and kvar time-series from a voltage ride-through
simulation and compares against a saved baseline.  Use this to validate
that refactored (batch) controller implementations produce identical results.

Usage:
    # Step 1: Generate baseline (run once with the original controller)
    pytest tests/test_pv_ride_through_validation.py::test_pv_ride_through_save_baseline -s

    # Step 2: After refactoring, validate against baseline
    pytest tests/test_pv_ride_through_validation.py::test_pv_ride_through_validate -s
"""

import json
from pathlib import Path

import numpy as np
import pytest

from pydss.pydss_project import PyDssProject
from pydss.pydss_results import PyDssResults

BASE_PATH = Path(__file__).parent.absolute()
PROJECT_PATH = BASE_PATH / "data" / "controllers"
BASELINE_FILE = BASE_PATH / "data" / "pv_ride_through_baseline.json"


def _run_and_get_results():
    """Run voltage ride-through simulation and return Generator kW/kvar dataframes."""
    project = PyDssProject.load_project(
        PROJECT_PATH,
        simulation_file="simulation_pv_ride_through.toml",
    )
    project.run()

    results = PyDssResults(PROJECT_PATH)
    scenario = results.scenarios[0]

    powers_df = scenario.get_full_dataframe("Generators", "Powers")
    kw_df = powers_df.apply(lambda c: c.map(lambda v: v.real) if c.dtype == complex else c)
    kvar_df = powers_df.apply(lambda c: c.map(lambda v: v.imag) if c.dtype == complex else c)

    return kw_df, kvar_df


def test_pv_ride_through_save_baseline():
    """Run simulation and save results as the reference baseline."""
    kw_df, kvar_df = _run_and_get_results()

    baseline = {
        "kw_columns": list(kw_df.columns),
        "kw_values": kw_df.values.tolist(),
        "kvar_columns": list(kvar_df.columns),
        "kvar_values": kvar_df.values.tolist(),
        "kw_index": [str(t) for t in kw_df.index],
    }

    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)

    print(f"\nBaseline saved to {BASELINE_FILE}")
    print(f"  Generators: {len(kw_df.columns)}")
    print(f"  Timesteps: {len(kw_df)}")
    print(f"  kW range: [{kw_df.values.min():.4f}, {kw_df.values.max():.4f}]")
    print(f"  kvar range: [{kvar_df.values.min():.4f}, {kvar_df.values.max():.4f}]")


def test_pv_ride_through_validate():
    """Run simulation and compare against saved baseline."""
    if not BASELINE_FILE.exists():
        pytest.skip(f"No baseline file found at {BASELINE_FILE}. Run test_pv_ride_through_save_baseline first.")

    with open(BASELINE_FILE) as f:
        baseline = json.load(f)

    kw_df, kvar_df = _run_and_get_results()

    # Check columns match
    assert list(kw_df.columns) == baseline["kw_columns"], "Generator names changed"
    assert list(kvar_df.columns) == baseline["kvar_columns"], "Generator names changed"

    # Check shape
    baseline_kw = np.array(baseline["kw_values"])
    baseline_kvar = np.array(baseline["kvar_values"])
    assert kw_df.shape == baseline_kw.shape, (
        f"Shape mismatch: got {kw_df.shape}, expected {baseline_kw.shape}"
    )

    # Compare values
    kw_diff = np.abs(kw_df.values - baseline_kw)
    kvar_diff = np.abs(kvar_df.values - baseline_kvar)

    kw_max_diff = kw_diff.max()
    kvar_max_diff = kvar_diff.max()

    print(f"\n  Max kW difference:   {kw_max_diff:.2e}")
    print(f"  Max kvar difference: {kvar_max_diff:.2e}")

    atol = 1e-6
    if kw_max_diff > atol:
        idx = np.unravel_index(kw_diff.argmax(), kw_diff.shape)
        col_name = kw_df.columns[idx[1]]
        print(f"  Worst kW diff at step {idx[0]}, generator '{col_name}': "
              f"got {kw_df.values[idx]:.6f}, expected {baseline_kw[idx]:.6f}")

    if kvar_max_diff > atol:
        idx = np.unravel_index(kvar_diff.argmax(), kvar_diff.shape)
        col_name = kvar_df.columns[idx[1]]
        print(f"  Worst kvar diff at step {idx[0]}, generator '{col_name}': "
              f"got {kvar_df.values[idx]:.6f}, expected {baseline_kvar[idx]:.6f}")

    np.testing.assert_allclose(kw_df.values, baseline_kw, atol=atol,
                               err_msg="kW values differ from baseline")
    np.testing.assert_allclose(kvar_df.values, baseline_kvar, atol=atol,
                               err_msg="kvar values differ from baseline")
    print("  PASSED: Results match baseline within tolerance")
