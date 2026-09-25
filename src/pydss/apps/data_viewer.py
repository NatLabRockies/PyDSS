import ast
import copy
import os
import re
import sys
from importlib.util import find_spec

import ipywidgets as widgets
import pandas as pd
from IPython.display import display

if find_spec("plotly") is None:
    print("plotly is required to run the DataViewer. Please run 'pip install plotly'")
    sys.exit(1)


from pydss.pydss_results import PyDssResults


class DataViewer:
    """Provides a UI for viewing pydss results."""

    DEFAULTS = {
        "project_path": os.environ.get("PYDSS_PROJECT_PATH"),
    }

    def __init__(self, **kwargs):
        pd.options.plotting.backend = "plotly"
        self._results = None
        self._project_path = None
        self._scenario = None
        self._scenario_names = [""]
        self._element_classes = [""]
        self._element_props = [""]
        self._timestamps = None
        self._df = None
        self._defaults = copy.deepcopy(self.DEFAULTS)
        if kwargs:
            self._defaults.update(kwargs)
        self._make_widgets()
        self._display_widgets()
        if self._project_path_text.value != "":
            self._on_load_project_click(None)
        self._first_plot = True

    @property
    def results(self):
        """Return the current PyDssResults object."""
        return self._results

    @property
    def scenarios(self):
        """Return the current PyDssScenarioResults objects."""
        return self._results.scenarios

    @property
    def df(self):
        """Return the current DataFrame."""
        return self._df

    def _make_widgets(self):
        self._main_label = widgets.HTML("<b>Pydss Data Viewer</b>")
        text_layout_long = widgets.Layout(width="400px")
        text_layout_med = widgets.Layout(width="200px")
        text_layout_short = widgets.Layout(width="100px")
        button_layout = widgets.Layout(width="200px")
        path = "" if self._defaults["project_path"] is None else self._defaults["project_path"]
        self._project_path_text = widgets.Text(
            path,
            description="Project Path",
            layout=text_layout_long,
            placeholder="pydss_projects/project1/",
        )
        self._load_project_btn = widgets.Button(description="Load project", layout=button_layout)
        self._load_project_btn.on_click(self._on_load_project_click)
        self._scenario_label = widgets.HTML("Scenario", layout=text_layout_med)
        self._elem_class_label = widgets.HTML("Element Class", layout=text_layout_med)
        self._elem_prop_label = widgets.HTML("Element Property", layout=text_layout_med)
        self._prop_available_options_label = widgets.HTML("Options")
        self._prop_options_label = widgets.HTML("Element Property Options", layout=text_layout_med)
        self._num_elems_label = widgets.HTML("Number of Elements", layout=text_layout_med)
        self._elem_regex_label = widgets.HTML("Element Name Regex", layout=text_layout_med)
        self._start_time_label = widgets.HTML("Start Time", layout=text_layout_med)
        self._end_time_label = widgets.HTML("End Time", layout=text_layout_med)
        self._resolution_label = widgets.HTML("Resolution", layout=text_layout_med)
        self._moving_avg_cb = widgets.Checkbox(
            value=False, description="Moving Average", disabled=True
        )
        self._window_label = widgets.HTML("Moving Average Window", layout=text_layout_med)
        self._window_text = widgets.Text(value="4")
        self._scenario_dd = widgets.Dropdown(
            options=self._scenario_names,
            value=self._scenario_names[0],
            disabled=True,
        )
        self._scenario_dd.observe(self._on_scenario_change, names="value")
        self._elem_class_dd = widgets.Dropdown(
            options=self._element_classes,
            value=self._element_classes[0],
            disabled=True,
        )
        self._elem_class_dd.observe(self._on_elem_class_change, names="value")
        self._elem_prop_dd = widgets.Dropdown(
            options=self._element_props,
            value=self._element_props[0],
            disabled=True,
        )
        self._elem_prop_dd.observe(self._on_elem_prop_change, names="value")
        self._prop_available_options_text = widgets.Text(disabled=True)
        self._prop_options_text = widgets.Text(disabled=True)
        self._num_elems_text = widgets.Text(disabled=True)
        self._elem_regex_text = widgets.Text(disabled=True, placeholder="p1udt.*")
        self._elem_names_select = widgets.SelectMultiple(
            options=[""],
            value=[""],
            rows=5,
            description="Elements",
            disabled=True,
        )
        self._start_time_text = widgets.Text(disabled=True)
        self._end_time_text = widgets.Text(disabled=True)
        self._resolution_text = widgets.Text(disabled=True)
        self._load_dataframe_btn = widgets.Button(
            description="Load DataFrame",
            layout=button_layout,
            disabled=True,
            tooltip="Load DataFrame into `app.df`",
        )
        self._load_dataframe_btn.on_click(self._on_load_dataframe_click)
        self._plot_btn = widgets.Button(description="Plot", layout=button_layout)
        self._plot_btn.on_click(self._on_plot_click)
        self._aggregation_label = widgets.HTML("Aggregation", layout=text_layout_short)
        self._aggregation_dd = widgets.Dropdown(
            options=["None", "Min/Mean/Max", "Sum"],
            value="None",
            disabled=True,
        )
        self._real_only_cb = widgets.Checkbox(
            value=True, description="Exclude imaginary parts", disabled=True
        )
        self._reset_btn = widgets.Button(description="Reset", layout=button_layout)
        self._reset_btn.on_click(self._on_reset_click)
        self._plot_output = widgets.Output()

    def _display_widgets(self):
        box = widgets.VBox(
            (
                self._main_label,
                widgets.HBox((self._load_project_btn, self._project_path_text)),
                widgets.HBox((self._scenario_label, self._scenario_dd)),
                widgets.HBox((self._elem_class_label, self._elem_class_dd)),
                widgets.HBox(
                    (
                        self._elem_prop_label,
                        self._elem_prop_dd,
                        self._prop_available_options_label,
                        self._prop_available_options_text,
                    )
                ),
                widgets.HBox((self._prop_options_label, self._prop_options_text)),
                widgets.HBox(
                    (
                        widgets.VBox(
                            (
                                widgets.HBox((self._num_elems_label, self._num_elems_text)),
                                widgets.HBox((self._elem_regex_label, self._elem_regex_text)),
                            )
                        ),
                        self._elem_names_select,
                    )
                ),
                widgets.HBox(
                    (
                        widgets.VBox(
                            (
                                widgets.HBox((self._start_time_label, self._start_time_text)),
                                widgets.HBox((self._end_time_label, self._end_time_text)),
                                widgets.HBox((self._resolution_label, self._resolution_text)),
                            ),
                        ),
                        widgets.VBox(
                            (
                                self._moving_avg_cb,
                                widgets.HBox((self._window_label, self._window_text)),
                            )
                        ),
                    )
                ),
                widgets.HBox(
                    (
                        self._plot_btn,
                        self._load_dataframe_btn,
                        self._aggregation_label,
                        self._aggregation_dd,
                        self._real_only_cb,
                    )
                ),
                self._reset_btn,
            )
        )
        display(box)

    def _enable_project_actions(self):
        self._elem_class_dd.disabled = False
        self._elem_prop_dd.disabled = False
        self._prop_options_text.disabled = False
        self._load_dataframe_btn.disabled = False
        self._plot_btn.disabled = False
        self._scenario_dd.disabled = False
        self._aggregation_dd.disabled = False
        self._real_only_cb.disabled = False
        self._elem_regex_text.disabled = False
        self._elem_names_select.disabled = False
        self._start_time_text.disabled = False
        self._end_time_text.disabled = False
        self._moving_avg_cb.disabled = False
        self._assign_widgets()

    def _assign_widgets(self):
        self._scenario_names[:] = [x.name for x in self._results.scenarios]
        self._scenario_dd.options = self._scenario_names
        self._scenario_dd.value = self._scenario_names[0]
        self._on_elem_class_change(None)
        self._on_elem_prop_change(None)

    def _on_scenario_change(self, _):
        self._scenario = [x for x in self._results.scenarios if x.name == self._scenario_dd.value][
            0
        ]
        self._element_classes[:] = self._scenario.list_element_classes()
        self._elem_class_dd.options = self._element_classes
        self._elem_class_dd.value = self._element_classes[0]

    def _on_elem_class_change(self, _):
        elem_class = self._elem_class_dd.value
        self._element_props[:] = self._scenario.list_element_properties(elem_class)
        self._elem_prop_dd.options = self._element_props
        if self._element_props:
            self._elem_prop_dd.value = self._element_props[0]
        elem_names = self._scenario.list_element_names(elem_class)
        elem_names.insert(0, "All")
        self._elem_names_select.options = elem_names
        self._elem_names_select.value = [elem_names[0]]
        self._num_elems_text.value = str(len(elem_names))

    def _on_elem_prop_change(self, _):
        elem_class = self._elem_class_dd.value
        elem_prop = self._elem_prop_dd.value
        options = self._scenario.list_element_property_options(elem_class, elem_prop)
        self._prop_available_options_text.value = ", ".join(options)
        self._prop_options_text.value = ""
        self._prop_options_text.placeholder = ", ".join(f"{x}='X'" for x in options)
        self._elem_regex_text.value = ""

    def _on_load_project_click(self, _):
        path = self._project_path_text.value
        if path == "":
            print("Project Path cannot be empty.", file=sys.stderr)
            return

        self._results = PyDssResults(path)
        self._timestamps = self._results.scenarios[0].get_timestamps()
        self._start_time_text.value = str(self._timestamps.iloc[0])
        self._end_time_text.value = str(self._timestamps.iloc[-1])
        self._resolution_text.value = str(self._timestamps.iloc[1] - self._timestamps.iloc[0])
        self._enable_project_actions()

    def _filter_dataframe_by_time(self):
        filter_required = False
        start_time = pd.Timestamp(self._start_time_text.value)
        end_time = pd.Timestamp(self._end_time_text.value)
        p_start = self._timestamps.iloc[0]
        p_end = self._timestamps.iloc[-1]
        if start_time < p_start or start_time > p_end:
            print(
                f"Error: start_time={start_time} must be between {p_start} and {p_end}",
                file=sys.stderr,
            )
            raise BadInputError("invalid start time")
        if start_time != p_start:
            filter_required = True
        if end_time > p_end or end_time < p_start:
            print(
                f"Error: end_time={end_time} must be between {p_start} and {p_end}",
                file=sys.stderr,
            )
            raise BadInputError("invalid end time")
        if end_time != p_end:
            filter_required = True

        if filter_required:
            self._df = self._df.loc[start_time:end_time, :]

    def _filter_dataframe_by_elem_names(self):
        value = self._elem_names_select.value
        if value != ("All",):
            values = set(value)
            columns = [
                x for x in self._df.columns if self._scenario.get_name_from_column(x) in values
            ]
            self._df = self._df[columns]

    def _filter_dataframe_by_elem_regex(self):
        regex_str = self._elem_regex_text.value
        if regex_str != "":
            regex = re.compile(rf"{regex_str}")
            columns = [x for x in self._df.columns if regex.search(x) is not None]
            self._df = self._df[columns]

    def _get_elem_property_options(self):
        options = {}
        options_text = self._prop_options_text.value.strip()
        if options_text != "":
            for option_pair in options_text.split(","):
                fields = option_pair.split("=")
                if len(fields) != 2:
                    print(
                        f"Invalid option pair: '{option_pair}'. Must be 'option=value'",
                        file=sys.stderr,
                    )
                    return
                key = fields[0].strip()
                val = fields[1].strip()
                options[key] = ast.literal_eval(val)
        return options

    def _assign_dataframe(self):
        elem_class = self._elem_class_dd.value
        elem_prop = self._elem_prop_dd.value
        real_only = self._real_only_cb.value

        self._df = self._scenario.get_full_dataframe(
            elem_class,
            elem_prop,
            real_only=real_only,
            **self._get_elem_property_options(),
        )
        try:
            self._filter_dataframe_by_time()
        except BadInputError:
            return

        self._filter_dataframe_by_elem_names()
        self._filter_dataframe_by_elem_regex()

        if self._aggregation_dd.value == "Min/Mean/Max":
            columns = list(self._df.columns)
            self._df["Max"] = self._df.max(axis=1)
            self._df["Mean"] = self._df.mean(axis=1)
            self._df["Min"] = self._df.min(axis=1)
            self._df.drop(columns=columns, inplace=True)
        elif self._aggregation_dd.value == "Sum":
            columns = list(self._df.columns)
            self._df["Sum"] = self._df.sum(axis=1)
            self._df.drop(columns=columns, inplace=True)
        else:
            assert self._aggregation_dd.value == "None"

        if self._moving_avg_cb.value:
            try:
                window = int(self._window_text.value)
            except Exception:
                print(f"window size {self._window_text.value} must be an integer")
                return
            self._df = self._df.rolling(window=window).mean()

    def _on_load_dataframe_click(self, _):
        self._assign_dataframe()

    def _on_plot_click(self, _):
        if self._first_plot:
            # This is a hack. Not sure why, but the first plot isn't displayed unless I do this.
            display(self._plot_output)
            self._plot_output.clear_output()
            self._first_plot = False

        self._assign_dataframe()
        title = f"{self._elem_class_dd.value} {self._elem_prop_dd.value}"
        # Potential bug: pandas reports a warning about a fragmented dataframe as a result of
        # plotly code whenever the dataframe has more than 100 columns.
        # Seems to be caused by plotly but am not sure.
        fig = self._df.plot(title=title)
        with self._plot_output:
            fig.show()
        display(self._plot_output)
        self._plot_output.clear_output(wait=True)
        # TODO: Something about this function is incorrect.
        # The notebook accumulates blank space every time it is called.

    def _on_reset_click(self, _):
        self._plot_output.clear_output()
        for val in self.__dict__.values():
            if isinstance(val, widgets.Widget):
                val.close_all()
        self._make_widgets()
        self._display_widgets()
        self._enable_project_actions()
        self._first_plot = True


class BadInputError(Exception):
    """Raise on bad user input."""
