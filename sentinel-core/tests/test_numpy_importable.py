"""Smoke tests: numpy + PyYAML must be importable in the sentinel-core image.

Per project memory `project_dockerfile_deps`: a Python dep needs to land in
BOTH pyproject.toml AND Dockerfile, or the container restart-loops on
ModuleNotFoundError. This regression test fires if either ships without
the other.
"""


def test_numpy_importable():
    import numpy

    assert numpy.__version__


def test_yaml_importable():
    import yaml

    assert yaml.__version__
