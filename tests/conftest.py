"""Root pytest configuration for lightweight deterministic tests."""

from __future__ import annotations

import enum
import importlib.util
import sys
import types
from pathlib import Path

import pytest


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


def _install_kaos_stub() -> None:
    if "kaos.path" in sys.modules or _module_available("kaos.path"):
        return

    kaos = types.ModuleType("kaos")
    kaos_path = types.ModuleType("kaos.path")

    class KaosPath(str):
        @staticmethod
        def cwd() -> "KaosPath":
            return KaosPath(str(Path.cwd()))

    setattr(kaos_path, "KaosPath", KaosPath)
    sys.modules["kaos"] = kaos
    sys.modules["kaos.path"] = kaos_path


def _install_kimi_sdk_stub() -> None:
    if "kimi_agent_sdk" in sys.modules or _module_available("kimi_agent_sdk"):
        return

    kimi = types.ModuleType("kimi_agent_sdk")

    class RunCancelled(Exception):
        pass

    class TextPart:
        def __init__(self, text: str = "") -> None:
            self.text = text

    class ToolCallPart:
        pass

    class ToolResult:
        pass

    class ApprovalRequest:
        def __init__(self, action: str = "", description: str = "", sender: str = "") -> None:
            self.action = action
            self.description = description
            self.sender = sender
            self.display: list[object] = []
            self.resolved_with: str | None = None

        def resolve(self, decision: str) -> None:
            self.resolved_with = decision

    class Session:
        @staticmethod
        async def create(*args, **kwargs):
            return Session()

        def prompt(self, _prompt: str, merge_wire_messages: bool = False):
            async def _gen():
                if False:
                    yield None

            return _gen()

        def cancel(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            await self.close()

    setattr(kimi, "RunCancelled", RunCancelled)
    setattr(kimi, "TextPart", TextPart)
    setattr(kimi, "ToolCallPart", ToolCallPart)
    setattr(kimi, "ToolResult", ToolResult)
    setattr(kimi, "ApprovalRequest", ApprovalRequest)
    setattr(kimi, "Session", Session)
    sys.modules["kimi_agent_sdk"] = kimi


def _install_source_model_stub() -> None:
    if "src.shared.models.source" in sys.modules or _module_available("src.shared.models.source"):
        return

    module = types.ModuleType("src.shared.models.source")

    class SourceType(str, enum.Enum):
        ARXIV = "arxiv"
        KAGGLE = "kaggle"
        HUGGINGFACE = "huggingface"
        OTHER = "other"

    class ProcessingStatus(str, enum.Enum):
        FETCHED = "fetched"
        PROCESSED = "processed"
        FAILED = "failed"

    setattr(module, "SourceType", SourceType)
    setattr(module, "ProcessingStatus", ProcessingStatus)
    sys.modules["src.shared.models.source"] = module


_install_docling_stub()
_install_kaos_stub()
_install_kimi_sdk_stub()
_install_source_model_stub()
