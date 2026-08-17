"""Reading metadata and icons out of AppImages."""

from .extractor import ExtractionScratch, extract, extraction_method_available, fallback_name

__all__ = [
    "ExtractionScratch",
    "extract",
    "extraction_method_available",
    "fallback_name",
]
