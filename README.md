[![Pytest](https://github.com/NatLabRockies/PyDSS/actions/workflows/pull_request_tests.yml/badge.svg)](https://github.com/NatLabRockies/PyDSS/actions/workflows/pull_request_tests.yml) • [![Upload to PyPi](https://github.com/NatLabRockies/PyDSS/actions/workflows/python-publish.yml/badge.svg)](https://github.com/NatLabRockies/PyDSS/actions/workflows/python-publish.yml) • [![deploy-docs](https://github.com/NatLabRockies/PyDSS/actions/workflows/gh-pages.yml/badge.svg)](https://github.com/NatLabRockies/PyDSS/actions/workflows/gh-pages.yml) • ![PyPI - Downloads](https://img.shields.io/pypi/dm/NREL-pydss) • [![GitHub issues](https://img.shields.io/github/issues/NatLabRockies/PyDSS)](https://github.com/NatLabRockies/PyDSS/issues) • [![License](https://img.shields.io/github/license/NatLabRockies/PyDSS)](https://github.com/NatLabRockies/PyDSS/blob/master/LICENSE) • [![PyPI Downloads](https://static.pepy.tech/personalized-badge/nrel-pydss?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/nrel-pydss)

# PyDSS

**PyDSS** is a high-level Python interface for [OpenDSS](https://www.epri.com/pages/sa/opendss) that extends its organizational, analytical, and co-simulation capabilities. It is built on top of [OpenDSSDirect.py](https://pypi.org/project/OpenDSSDirect.py/).

**Documentation:** [https://natlabrockies.github.io/PyDSS/](https://natlabrockies.github.io/PyDSS/index.html)

## Key Features

- **Custom Control Algorithms** — Define Python-based controllers for any circuit element, executed at each simulation time step. 13 built-in controllers are included (PV, storage, motor stall, fault, transformer, thermostat, and more).
- **HELICS Co-simulation** — Integrate with external simulators via the [HELICS](https://github.com/GMLC-TDC/HELICS) framework for cyber-physical co-simulation studies.
- **Scenario Management** — Run multiple scenarios on a shared OpenDSS model with independent controllers, exports, and post-processing.
- **Flexible Data Export** — Export results to HDF5 or CSV with per-element filtering, regex-based selection, moving averages, and group aggregation.
- **Automated Reports** — Generate reports for voltage metrics, thermal metrics, PV clipping/curtailment, capacitor switching, tap changes, and feeder losses.
- **Monte Carlo Studies** — Built-in support for running Monte Carlo simulations with profile management.
- **Extension Architecture** — Plugin system for custom controllers, post-processing scripts, and report types.

## Installation

Install in a conda virtual environment (recommended):

```bash
conda create -n pydss python=3.11
conda activate pydss
pip install NREL-pydss
```

## Quick Start

```bash
# Create a project with two scenarios
pydss create-project --project=my-project --scenarios="scenario1,scenario2" --path=./projects

# Copy your OpenDSS files into projects/my-project/DSSfiles/
# Set dss_file in projects/my-project/simulation.toml

# Run all scenarios
pydss run ./projects/my-project
```

## Python API

```python
from pydss.pydss_project import PyDssProject

# Run a project
PyDssProject.run_project("./projects/my-project")

# Access results
from pydss.pydss_results import PyDssResults
results = PyDssResults("./projects/my-project")
scenario = results.scenarios[0]
df = scenario.get_dataframe("Lines", "Currents", "Line.pvl_112")
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `pydss create-project` | Create a new project with scenarios |
| `pydss run` | Run all scenarios in a project |
| `pydss export` | Convert HDF5 results to CSV |
| `pydss controllers` | Manage the controller registry |
| `pydss edit-scenario` | Modify scenario configuration |
| `pydss reports` | Generate analysis reports |

Run `pydss --help` for full usage details.

## License

BSD 3-Clause. See [LICENSE](LICENSE) for details.

