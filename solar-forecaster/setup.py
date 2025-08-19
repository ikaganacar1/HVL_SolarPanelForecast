from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy
import os

# NumPy API warning'ini düzelt
define_macros = [("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]

# Extension'ları tanımla
extensions = [
    Extension(
        name="battery_simulation",  # Modül adı
        sources=["battery_simulation.pyx"],  # Kaynak dosya
        include_dirs=[numpy.get_include()],
        define_macros=define_macros,
        extra_compile_args=['-O3', '-ffast-math'],  # Optimizasyon bayrakları
        language='c'
    ),
    Extension(
        name="data_processing",
        sources=["data_processing.pyx"],
        include_dirs=[numpy.get_include()],
        define_macros=define_macros,
        extra_compile_args=['-O3', '-ffast-math'],
        language='c'
    )
]

setup(
    name="solar_optimization",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'boundscheck': False,
            'wraparound': False,
            'initializedcheck': False,
            'cdivision': True,
            'language_level': 3
        }
    ),
    zip_safe=False,
)