import setuptools


setuptools.setup(
     name="reglo_icc_pump",
     version="0.1.0",
     python_requires=">=3.6",
     install_requires=['pyserial'],  # TODO figure out min version
     py_modules=["reglo_icc_pump"],
     )
