"""Modular score-sheet OCR: preprocessing → OCR engine → table reconstruction →
post-processing/validation → a structured, cell-level extraction for human review.

Nothing here writes to permanent score records; the pipeline only produces a
reviewable extraction (see utils/ocr/pipeline.py). Tesseract produces the OCR
*tokens* (utils/ocr/tesseract_engine.py), but the reconstruction and
post-processing (reconstruct.py, postprocess.py) are engine-agnostic pure
functions that operate on those tokens — so they are unit-testable without any
OCR runtime, and Claude vision (which returns a structured table directly)
bypasses them.
"""
