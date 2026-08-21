"""Modular score-sheet OCR: preprocessing → OCR engine → table reconstruction →
post-processing/validation → a structured, cell-level extraction for human review.

Nothing here writes to permanent score records; the pipeline only produces a
reviewable extraction (see utils/ocr/pipeline.py). PaddleOCR is the primary
engine (utils/ocr/paddle_engine.py) but the reconstruction and post-processing
(reconstruct.py, postprocess.py) are engine-agnostic pure functions that operate
on OCR *tokens* — so they are unit-testable without the heavy OCR runtime.
"""
