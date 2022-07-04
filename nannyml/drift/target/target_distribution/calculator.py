#  Author:   Niels Nuyttens  <niels@nannyml.com>
#
#  License: Apache Software License 2.0

"""Module for target distribution monitoring."""
from __future__ import annotations

import warnings
from typing import Dict, Optional

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from nannyml.base import AbstractCalculator
from nannyml.chunk import Chunker
from nannyml.drift.target.target_distribution.result import TargetDistributionResult
from nannyml.exceptions import CalculatorNotFittedException, InvalidArgumentsException

_ALERT_THRESHOLD_P_VALUE = 0.05


class TargetDistributionCalculator(AbstractCalculator):
    """Calculates target distribution for a given dataset."""

    def __init__(
        self,
        y_true: str,
        timestamp_column_name: str,
        chunk_size: int = None,
        chunk_number: int = None,
        chunk_period: str = None,
        chunker: Chunker = None,
    ):
        """Constructs a new TargetDistributionCalculator.

        Parameters
        ----------
        model_metadata: ModelMetadata
            Metadata for the model whose data is to be processed.
        chunk_size: int
            Splits the data into chunks containing `chunks_size` observations.
            Only one of `chunk_size`, `chunk_number` or `chunk_period` should be given.
        chunk_number: int
            Splits the data into `chunk_number` pieces.
            Only one of `chunk_size`, `chunk_number` or `chunk_period` should be given.
        chunk_period: str
            Splits the data according to the given period.
            Only one of `chunk_size`, `chunk_number` or `chunk_period` should be given.
        chunker : Chunker
            The `Chunker` used to split the data sets into a lists of chunks.

        Examples
        --------
        >>> import nannyml as nml
        >>> ref_df, ana_df, _ = nml.load_synthetic_binary_classification_dataset()
        >>> metadata = nml.extract_metadata(ref_df, model_type=nml.ModelType.CLASSIFICATION_BINARY)
        >>> # Create a calculator that will chunk by week
        >>> target_distribution_calc = nml.TargetDistributionCalculator(model_metadata=metadata, chunk_period='W')
        """
        super().__init__(chunk_size, chunk_number, chunk_period, chunker)

        self.y_true = y_true
        self.timestamp_column_name = timestamp_column_name

        self.previous_reference_results: Optional[pd.DataFrame] = None
        self.previous_reference_data: Optional[pd.DataFrame] = None

        # self._reference_targets: pd.Series = None  # type: ignore

        # TODO: determine better min_chunk_size for target distribution
        self._minimum_chunk_size = 300

    def _fit(self, reference_data: pd.DataFrame, *args, **kwargs) -> TargetDistributionCalculator:
        """Fits the calculator to reference data.

        During fitting the reference target data is validated and stored for later use.

        Examples
        --------
        >>> import nannyml as nml
        >>> ref_df, ana_df, _ = nml.load_synthetic_binary_classification_dataset()
        >>> metadata = nml.extract_metadata(ref_df, model_type=nml.ModelType.CLASSIFICATION_BINARY)
        >>> target_distribution_calc = nml.TargetDistributionCalculator(model_metadata=metadata, chunk_period='W')
        >>> # fit the calculator on reference data
        >>> target_distribution_calc.fit(ref_df)
        """
        if reference_data.empty:
            raise InvalidArgumentsException('data contains no rows. Please provide a valid data set.')

        reference_data = reference_data.copy()

        if self.y_true not in reference_data.columns:
            raise InvalidArgumentsException(
                f"target data column '{self.y_true}' is not in data columns: {reference_data.columns}."
            )

        self.previous_reference_data = reference_data
        self.previous_reference_results = self._calculate(reference_data).data

        return self

    def _calculate(self, data: pd.DataFrame, *args, **kwargs):
        """Calculates the target distribution of a binary classifier.

        Requires fitting the calculator on reference data first.

        Parameters
        ----------
        data: pd.DataFrame
            Data for the model, i.e. model inputs, predictions and targets.

        Examples
        --------
        >>> import nannyml as nml
        >>> ref_df, ana_df, _ = nml.load_synthetic_binary_classification_dataset()
        >>> metadata = nml.extract_metadata(ref_df, model_type=nml.ModelType.CLASSIFICATION_BINARY)
        >>> target_distribution_calc = nml.TargetDistributionCalculator(model_metadata=metadata, chunk_period='W')
        >>> target_distribution_calc.fit(ref_df)
        >>> # calculate target distribution
        >>> target_distribution = target_distribution_calc.calculate(ana_df)
        """
        if data.empty:
            raise InvalidArgumentsException('data contains no rows. Please provide a valid data set.')

        data = data.copy()

        if self.y_true not in data.columns:
            raise InvalidArgumentsException(
                f"target data column '{self.y_true}' not found in data columns: {data.columns}."
            )

        data['NML_TARGET_INCOMPLETE'] = data[self.y_true].isna().astype(np.int16)

        # Generate chunks
        # features_and_metadata = NML_METADATA_COLUMNS + ['NML_TARGET_INCOMPLETE']
        chunks = self.chunker.split(
            data,
            columns=[self.y_true, 'NML_TARGET_INCOMPLETE'],
            minimum_chunk_size=self._minimum_chunk_size,
            timestamp_column_name=self.timestamp_column_name,
        )

        # Construct result frame
        if self.previous_reference_data is None:
            raise CalculatorNotFittedException("no reference data known. Did you fit the calculator first?")
        res = pd.DataFrame.from_records(
            [
                {
                    'key': chunk.key,
                    'start_index': chunk.start_index,
                    'end_index': chunk.end_index,
                    'start_date': chunk.start_datetime,
                    'end_date': chunk.end_datetime,
                    'period': 'analysis' if chunk.is_transition else chunk.period,
                    'targets_missing_rate': (
                        chunk.data['NML_TARGET_INCOMPLETE'].sum() / chunk.data['NML_TARGET_INCOMPLETE'].count()
                    ),
                    **_calculate_target_drift_for_chunk(
                        self.previous_reference_data[self.y_true], chunk.data[self.y_true]
                    ),
                }
                for chunk in chunks
            ]
        )

        return TargetDistributionResult(results_data=res, calculator=self)


def _calculate_target_drift_for_chunk(reference_targets: pd.Series, targets: pd.DataFrame) -> Dict:
    statistic, p_value, _, _ = chi2_contingency(
        pd.concat([reference_targets.value_counts(), targets.value_counts()], axis=1).fillna(0)
    )

    is_non_binary_targets = targets.nunique() > 2
    if is_non_binary_targets:
        warnings.warn(
            f"the target column contains {targets.nunique()} unique values. "
            "NannyML cannot provide a value for 'metric_target_drift' "
            "when there are more than 2 unique values. "
            "All 'metric_target_drift' values will be set to np.NAN"
        )

    is_string_targets = targets.dtype in ['object', 'string']
    if is_string_targets:
        warnings.warn(
            "the target column contains non-numerical values. NannyML cannot provide a value for "
            "'metric_target_drift'."
            "All 'metric_target_drift' values will be set to np.NAN"
        )

    return {
        'metric_target_drift': targets.mean() if not (is_non_binary_targets or is_string_targets) else np.NAN,
        'statistical_target_drift': statistic,
        'p_value': p_value,
        'thresholds': _ALERT_THRESHOLD_P_VALUE,
        'alert': p_value < _ALERT_THRESHOLD_P_VALUE,
        'significant': p_value < _ALERT_THRESHOLD_P_VALUE,
    }
