"""pytest fixtures and options, and utilities for tests support."""

import logging
import math
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

import pytest


def pytest_addoption(parser):
    """Add CLI args to pytest tests."""
    parser.addoption(
        "--keep-tmp-hms-model",
        action="store_true",
        default=False,
        help="Avoid deleting the temporary HMS model dir after the test run.",
    )


@pytest.fixture(scope="session")
def local_data_out_path():
    """Return a Path object pointing to data/out/ relative to conftest.py's parent (relative this file's parent)."""
    return Path(__file__).resolve().parent / "data" / "out"


class ComparisonError(Exception):
    """Raised when comparing two instances of ScalarComp when values are not close within tolerance."""


@dataclass
class Scalar:
    """Labeled scalar value."""

    param_label: str  # e.g. "FLOW" or "PRECIP-INC"
    stat_label: str  # e.g. "value", "mean", "min", "max", "sum"
    quantity: int | float


class ScalarComp:
    """Compare dictionaries of scalar results. Log differences. Assert equality with tolerance.

    Raises ComparisonError when comparisons are out of tolerance.
    Otherwise raises RuntimeError in most cases.
    """

    def __init__(self, comp_label: str, data: list[Scalar]) -> None:
        """Initialize and validate labeled results."""
        self._errors: list[Exception] = []

        self.comp_label = comp_label
        self.data = data
        self._validate_self()

    def compare_with_tolerance(self, other: "ScalarComp", tol_rel: float, tol_abs: float) -> None:
        """Compare self.data vs other.data. Log differences. Raise ComparisonError when tolerances are exceeded.

        Parameters
        ----------
        other : ScalarComp
            Other instance of ScalarComp to compare against the ScalarComp of self.data.
        tol_rel : float
            Allowed relative difference. Decimal, e.g. 0.05 allows 5% difference.
        tol_abs : float
            Allowed absolute difference.
        """
        # Validate args
        if not isinstance(other, ScalarComp):
            self._append_error(TypeError(f"Expected other to be a ScalarComp, got type {type(other)}"))
        for tolerance in (tol_rel, tol_abs):
            if not isinstance(tolerance, Real) or not math.isfinite(tolerance) or tolerance < 0:
                self._append_error(ValueError(f"Tolerances must be finite and non-negative, but got: {tolerance}"))
        self._raise_errors()
        if tol_rel >= 0.50:
            logging.warning(
                f"tol_rel={tol_rel} is high. It should represent a decimal value, not a percentage value. Did you mean {tol_rel / 100}?"
            )

        # Validate self and other in isolation
        self._validate_self()
        other._validate_self()

        # Validate that self and other are comparable
        if self.comp_label.strip() == other.comp_label.strip():
            self._append_error(ValueError(f"self.comp_label cannot be equal to other.comp_label: {self.comp_label}"))
        original_scalars = sorted(self.data, key=lambda scalar: (scalar.param_label, scalar.stat_label))
        other_scalars = sorted(other.data, key=lambda scalar: (scalar.param_label, scalar.stat_label))
        if len(original_scalars) != len(other_scalars):
            self._append_error(ValueError(f"Scalar counts differ: {len(original_scalars)} != {len(other_scalars)}."))
        self._raise_errors()

        # Do the comparison math
        for i, (scalar_orig, scalar_other) in enumerate(zip(original_scalars, other_scalars)):
            label_pair_orig = (scalar_orig.param_label, scalar_orig.stat_label)
            label_pair_other = (scalar_other.param_label, scalar_other.stat_label)
            if label_pair_orig != label_pair_other:
                self._append_error(
                    ValueError(f"Scalar labels differ at i={i}: {label_pair_orig} != {label_pair_other}.")
                )
                continue

            val_orig = scalar_orig.quantity
            val_other = scalar_other.quantity
            diff_raw = abs(val_other - val_orig)
            diff_rel = diff_raw / abs(val_orig) if val_orig != 0 else (0.0 if diff_raw == 0 else math.inf)
            message = f"Comparison: {self.comp_label!r} vs {other.comp_label!r}: {label_pair_orig[0]}.{label_pair_orig[1]}: {val_orig:.4f} vs {val_other:.4f}. diff_rel~{diff_rel:.2%}. diff_raw~{diff_raw:.4f}."
            logging.info(message)
            if diff_raw > tol_abs or diff_rel > tol_rel:
                self._append_error(ComparisonError(message))
        self._raise_errors()

        if tol_rel >= 0.50:
            logging.warning(
                f"tol_rel={tol_rel} is high. It should represent a decimal value, not a percentage value. Did you mean {tol_rel / 100}?"
            )

    @property
    def _scalar_label_pairs(self) -> list[tuple[str, str]]:
        """Return a list of (param_label, stat_label) tuples associated with the scalars."""
        label_pairs: list[tuple[str, str]] = []
        for scalar in self.data:
            if not isinstance(scalar, Scalar):
                self._append_error(TypeError(f"Expected elements of self.data to be type Scalar, got {type(scalar)}"))
            label_pairs.append((scalar.param_label, scalar.stat_label))
        return label_pairs

    def _validate_self(self) -> None:
        """Validate the label and nested numeric data."""
        if not isinstance(self.comp_label, str) or not self.comp_label.strip():
            self._append_error(ValueError(f"label must be a non-empty string, but got: {self.comp_label!r}"))
        if not isinstance(self.data, list):
            self._append_error(TypeError(f"Expected data to be a list of Scalar, got {type(self.data)}"))
        self._raise_errors()

        label_pairs = self._scalar_label_pairs
        labelpair2count: dict[tuple[str, str], int] = {pair: label_pairs.count(pair) for pair in label_pairs}
        for pair, count in labelpair2count.items():
            if count > 1:
                self._append_error(ValueError(f"Duplicate label pair {pair} found {count} times."))
        self._raise_errors()

    def _append_error(self, error: Exception) -> None:
        logging.error("%s", error)
        self._errors.append(error)

    def _raise_errors(self) -> None:
        """Raise errors. If all errors are type ComparisonError, then raise that type so it can be handled. Otherwise raise RuntimeError."""
        if self._errors:
            logging.error(f"{len(self._errors)} errors.")
            exception_types = {type(error) for error in self._errors}
            exc_type = ComparisonError if exception_types == {ComparisonError} else RuntimeError
            raise exc_type(self._errors)
