#  Author:   Niels Nuyttens  <niels@nannyml.com>
#
#  License: Apache Software License 2.0
from typing import Dict, Protocol, Union  # noqa: TYP001

import pandas as pd
from plotly.graph_objs import Figure


class Result(Protocol):
    """the data that was calculated or estimated"""

    data: pd.DataFrame

    """all available plots"""
    plots: Dict[str, Figure]

    """name of the calculator that created it"""
    calculator_name: str


class Calculator(Protocol):
    def fit(self, reference_data: pd.DataFrame, *args, **kwargs):
        """Fits the calculator on reference data."""

    def calculate(self, data: pd.DataFrame, *args, **kwargs):
        """Perform a calculation based on analysis data."""


class Estimator(Protocol):
    def fit(self, reference_data: pd.DataFrame, *args, **kwargs):
        """Fits the estimator on reference data."""

    def estimate(self, data: pd.DataFrame, *args, **kwargs) -> Result:
        """Perform an estimation based on analysis data."""


ModelOutputsType = Union[str, Dict[str, str]]
