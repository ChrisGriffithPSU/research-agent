"""Smoke imports for primary application modules."""


def test_import_core_modules() -> None:
    import src.scheduler  # noqa: F401
    import src.shared.messaging.consumer  # noqa: F401
    import src.shared.messaging.publisher  # noqa: F401
    import src.workers.paper_triage.worker  # noqa: F401
    import src.workers.pdf_parser.worker  # noqa: F401
    import src.workers.concept_generator.worker  # noqa: F401
    import src.workers.experiment_exploder.worker  # noqa: F401
    import src.workers.notifier.slack_worker  # noqa: F401
    import workers.kimi_worker.runner  # noqa: F401
