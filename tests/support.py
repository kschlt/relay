"""Shared helpers for the contract suite."""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures")
SCHEMA_PATH = os.path.join(
    REPO_ROOT, "schema", "intake-envelope-v1.schema.json"
)


def load_fixture(relative_path):
    with open(os.path.join(FIXTURE_ROOT, relative_path), "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_manifest():
    return load_fixture("manifest.json")


def fixture_files(subdirectory):
    directory = os.path.join(FIXTURE_ROOT, subdirectory)
    return sorted(
        "%s/%s" % (subdirectory, name)
        for name in os.listdir(directory)
        if name.endswith(".json")
    )


def a_valid_envelope():
    """A conforming envelope, safe for a test to mutate."""
    return load_fixture("valid/meeting-structural.json")
