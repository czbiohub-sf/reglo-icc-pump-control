# reglo-icc-pump-control
This is a Python driver for controlling Masterflex Ismatec Reglo ICC digital peristaltic pumps. It is designed with the USB interface in mind (use with the RS-232 interface is currently untested).

This project is not affiliated with Avantor.

## API documentation
Refer to the docstrings or compiled documentation for API usage information. 

The API documentation is built using Sphinx. To view the docs as HTML, run `make html` from the `docs/` subdirectory, then open `docs/html/_build/index.html` in a web browser. Other formats are available as well; run `make` with no arguments for a list.

The content of the usage example from the documentation can also be found directly at `docs/usage_example.py`.

## Requirements
The `reglo_icc_pump` package requires:
- Python >= 3.6
- `pyserial` >= 3.5 (earlier versions may work, not tested).

Building the documentation additionally requires `sphinx` and GNU Make.

## Installation
Activate a virtual environment if desired, then, from the root of this source distribution, run:
```
pip install .
```

## Support
This repository is maintained by Greg Courville of the Bioengineering Platform at Chan Zuckerberg Biohub San Francisco.
