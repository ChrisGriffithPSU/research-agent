"""Root pytest configuration for lightweight deterministic tests."""

from __future__ import annotations

import enum
import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Load .env before any test runs
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def pytest_configure(config: pytest.Config) -> None:
    """Register project markers."""
    config.addinivalue_line("markers", "integration: in-process integration tests")
    config.addinivalue_line("markers", "e2e: in-process end-to-end tests")


def _module_available(name: str) -> bool:
    """Return True when import metadata exists without raising errors."""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _install_docling_stub() -> None:
    if "docling" in sys.modules or _module_available("docling"):
        return

    docling = types.ModuleType("docling")
    converter = types.ModuleType("docling.document_converter")
    datamodel = types.ModuleType("docling.datamodel")
    base_models = types.ModuleType("docling.datamodel.base_models")
    pipeline_options = types.ModuleType("docling.datamodel.pipeline_options")

    class _FakeConverted:
        class _Document:
            @staticmethod
            def export_to_dict() -> dict:
                return {"text": "stub"}

        document = _Document()

    class DocumentConverter:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def convert(self, _url: str) -> _FakeConverted:
            return _FakeConverted()

    class InputFormat(enum.Enum):
        PDF = "pdf"

    class PdfPipelineOptions:
        def __init__(self) -> None:
            self.do_ocr = False
            self.do_table_structure = False
            self.table_structure_options = types.SimpleNamespace(do_cell_matching=False)

    setattr(converter, "DocumentConverter", DocumentConverter)
    setattr(base_models, "InputFormat", InputFormat)
    setattr(pipeline_options, "PdfPipelineOptions", PdfPipelineOptions)

    sys.modules["docling"] = docling
    sys.modules["docling.document_converter"] = converter
    sys.modules["docling.datamodel"] = datamodel
    sys.modules["docling.datamodel.base_models"] = base_models
    sys.modules["docling.datamodel.pipeline_options"] = pipeline_options


_install_docling_stub()
