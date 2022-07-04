#  Author:   Niels Nuyttens  <niels@nannyml.com>
#
#  License: Apache Software License 2.0

"""Implementation of the Data Reconstruction Drift Calculator."""

import pandas as pd
import plotly.graph_objects as go

from nannyml.base import AbstractCalculator, AbstractCalculatorResult
from nannyml.exceptions import InvalidArgumentsException
from nannyml.plots._step_plot import _step_plot


class DataReconstructionDriftCalculatorResult(AbstractCalculatorResult):
    """Contains the results of the data reconstruction drift calculation and adds functionality like plotting."""

    def __init__(self, results_data: pd.DataFrame, calculator: AbstractCalculator):
        super().__init__(results_data)

        from . import DataReconstructionDriftCalculator

        if not isinstance(calculator, DataReconstructionDriftCalculator):
            raise RuntimeError(
                f"{calculator.__class__.__name__} is not an instance of type " f"DataReconstructionDriftCalculator"
            )
        self.calculator = calculator

    @property
    def calculator_name(self) -> str:
        return "multivariate_data_reconstruction_feature_drift"

    def plot(self, kind: str = 'drift', plot_reference: bool = False, *args, **kwargs) -> go.Figure:
        """Renders a line plot of the ``reconstruction_error`` of the data reconstruction drift calculation results.

        Chunks are set on a time-based X-axis by using the period containing their observations.
        Chunks of different periods (``reference`` and ``analysis``) are represented using different colors and
        a vertical separation if the drift results contain multiple periods.

        The different plot kinds that are available:

        - ``drift``: plots drift per :class:`~nannyml.chunk.Chunk` for a chunked data set.

        Returns
        -------
        fig: plotly.graph_objects.Figure
            A ``Figure`` object containing the requested drift plot. Can be saved to disk or shown rendered on screen
            using ``fig.show()``.

        Examples
        --------
        >>> import nannyml as nml
        >>> ref_df, ana_df, _ = nml.load_synthetic_binary_classification_dataset()
        >>> metadata = nml.extract_metadata(ref_df, model_type=nml.ModelType.CLASSIFICATION_BINARY)
        >>> drift_calc = nml.DataReconstructionDriftCalculator(model_metadata=metadata, chunk_period='W')
        >>> drift_calc.fit(ref_df)
        >>> drifts = drift_calc.calculate(ana_df)
        >>> # create the data reconstruction drift plot and display it
        >>> drifts.plot(kind='drift').show()
        """
        if kind == 'drift':
            return _plot_drift(self.data, self.calculator, plot_reference)
        else:
            raise InvalidArgumentsException(
                f"unknown plot kind '{kind}'. "
                f"Please provide on of: ['feature_drift', 'feature_distribution', "
                f"'prediction_drift', 'prediction_distribution']."
            )

    # @property
    # def plots(self) -> Dict[str, go.Figure]:
    #     return {'multivariate_feature_drift': _plot_drift(self.data)}


def _plot_drift(data: pd.DataFrame, calculator, plot_reference: bool) -> go.Figure:
    plot_period_separator = plot_reference

    data['period'] = 'analysis'

    if plot_reference:
        reference_results = calculator.previous_reference_results
        reference_results['period'] = 'reference'
        data = pd.concat([reference_results, data], ignore_index=True)

    fig = _step_plot(
        table=data,
        metric_column_name='reconstruction_error',
        chunk_column_name='key',
        drift_column_name='alert',
        lower_threshold_column_name='lower_threshold',
        upper_threshold_column_name='upper_threshold',
        hover_labels=['Chunk', 'Reconstruction error', 'Target data'],
        title='Data Reconstruction Drift',
        y_axis_title='Reconstruction Error',
        v_line_separating_analysis_period=plot_period_separator,
    )

    return fig
