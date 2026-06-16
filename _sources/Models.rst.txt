Data models
+++++++++++

Simulation input models
************************

.. autopydantic_model:: pydss.simulation_input_models.SnapshotTimePointSelectionConfigModel

.. autopydantic_model:: pydss.simulation_input_models.ScenarioPostProcessModel

.. autopydantic_model:: pydss.simulation_input_models.ScenarioModel

.. autopydantic_model:: pydss.simulation_input_models.ProjectModel

.. autopydantic_model:: pydss.simulation_input_models.ExportsModel

.. autopydantic_model:: pydss.simulation_input_models.FrequencyModel

.. autopydantic_model:: pydss.simulation_input_models.HelicsModel

.. autopydantic_model:: pydss.simulation_input_models.LoggingModel

.. autopydantic_model:: pydss.simulation_input_models.MonteCarloModel

.. autopydantic_model:: pydss.simulation_input_models.ProfilesModel

.. autopydantic_model:: pydss.simulation_input_models.ReportBaseModel

.. autopydantic_model:: pydss.simulation_input_models.CapacitorStateChangeCountReportModel

.. autopydantic_model:: pydss.simulation_input_models.FeederLossesReportModel

.. autopydantic_model:: pydss.simulation_input_models.FeederLossesReportModel

.. autopydantic_model:: pydss.simulation_input_models.PvClippingReportModel

.. autopydantic_model:: pydss.simulation_input_models.PvCurtailmentReportModel

.. autopydantic_model:: pydss.simulation_input_models.RegControlTapNumberChangeCountsReportModel

.. autopydantic_model:: pydss.simulation_input_models.ThermalMetricsReportModel

.. autopydantic_model:: pydss.simulation_input_models.VoltageMetricsReportModel

.. autopydantic_model:: pydss.simulation_input_models.ReportsModel

.. autopydantic_model:: pydss.simulation_input_models.SimulationSettingsModel

Scenario setup models
************************

.. autopydantic_model:: pydss.controllers.ControllerBaseModel

.. autopydantic_model:: pydss.controllers.PvControllerModel


Thermal metrics models
**********************

.. autopydantic_model:: pydss.thermal_metrics.ThermalMetricsBaseModel

.. autopydantic_model:: pydss.thermal_metrics.ThermalMetricsModel

.. autopydantic_model:: pydss.thermal_metrics.ThermalMetricsSummaryModel

.. autopydantic_model:: pydss.thermal_metrics.SimulationThermalMetricsModel

Voltage metrics models
**********************

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetricsBaseModel

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetric1

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetric2

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetric3

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetric4

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetric5

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetric5

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetricsSummaryModel

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetricsModel

.. autopydantic_model:: pydss.node_voltage_metrics.VoltageMetricsByBusTypeModel

.. autopydantic_model:: pydss.node_voltage_metrics.SimulationVoltageMetricsModel


Feeder metrics models
**********************

.. autopydantic_model:: pydss.reports.feeder_losses.FeederLossesMetricsModel

.. autopydantic_model:: pydss.reports.feeder_losses.SimulationFeederLossesMetricsModel


HELICS interface models
************************

.. autopydantic_model:: pydss.helics_interface.Subscription

.. autopydantic_model:: pydss.helics_interface.Publication

.. autopydantic_model:: pydss.helics_interface.Subscriptions

.. autopydantic_model:: pydss.helics_interface.Publications