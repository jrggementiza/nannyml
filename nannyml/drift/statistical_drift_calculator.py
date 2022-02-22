#  Author:   Niels Nuyttens  <niels@nannyml.com>
#
#  License: Apache Software License 2.0

"""Statistical drift calculation using `Kolmogorov-Smirnov` and `chi2-contingency` tests."""
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, ks_2samp

from nannyml.chunk import Chunk
from nannyml.drift._base import BaseDriftCalculator
from nannyml.metadata import ModelMetadata

ALERT_THRESHOLD_P_VALUE = 0.05


class StatisticalDriftCalculator(BaseDriftCalculator):
    """A drift calculator that relies on statistics to detect drift."""

    def __init__(self, model_metadata: ModelMetadata, features: List[str] = None):
        """Constructs a new StatisticalDriftCalculator.

        Parameters
        ----------
        model_metadata: ModelMetadata
            Metadata for the model whose data is to be processed.
        features: List[str], default=None
            An optional list of feature names to use during drift calculation. None by default, in this case
            all features are used during calculation.
        """
        super(StatisticalDriftCalculator, self).__init__(model_metadata, features)

        self._reference_data = None

    def _fit(self, reference_data: pd.DataFrame):
        self._reference_data = reference_data.copy(deep=True)

    def _calculate_drift(
        self,
        chunks: List[Chunk],
    ) -> pd.DataFrame:
        # Get lists of categorical <-> categorical features
        categorical_column_names = [f.column_name for f in self.model_metadata.categorical_features]
        continuous_column_names = [f.column_name for f in self.model_metadata.continuous_features]

        res = pd.DataFrame()
        # Calculate chunk-wise drift statistics.
        # Append all into resulting DataFrame indexed by chunk key.
        for chunk in chunks:
            chunk_drift: Dict[str, Any] = {
                'key': chunk.key,
                'start_index': chunk.start_index,
                'end_index': chunk.end_index,
                'start_date': chunk.start_datetime,
                'end_date': chunk.end_datetime,
                'partition': 'analysis' if chunk.is_transition else chunk.partition,
            }

            present_categorical_column_names = list(set(chunk.data.columns) & set(categorical_column_names))
            for column in present_categorical_column_names:
                statistic, p_value, _, _ = chi2_contingency(
                    pd.concat(
                        [
                            self._reference_data[column].value_counts(),  # type: ignore
                            chunk.data[column].value_counts(),
                        ],
                        axis=1,
                    )
                )
                chunk_drift[f'{column}_chi2'] = [statistic]
                chunk_drift[f'{column}_p_value'] = [np.round(p_value, decimals=3)]
                chunk_drift[f'{column}_alert'] = [p_value < ALERT_THRESHOLD_P_VALUE]

            present_continuous_column_names = list(set(chunk.data.columns) & set(continuous_column_names))
            for column in present_continuous_column_names:
                statistic, p_value = ks_2samp(self._reference_data[column], chunk.data[column])  # type: ignore
                chunk_drift[f'{column}_dstat'] = [statistic]
                chunk_drift[f'{column}_p_value'] = [np.round(p_value, decimals=3)]
                chunk_drift[f'{column}_alert'] = [p_value < ALERT_THRESHOLD_P_VALUE]

            res = res.append(pd.DataFrame(chunk_drift))

        res = res.reset_index(drop=True)
        res.attrs['nml_drift_calculator'] = __name__
        return res
