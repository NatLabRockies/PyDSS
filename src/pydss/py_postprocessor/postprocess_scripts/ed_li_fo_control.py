# **Authors: ksedzro@ieee.org**


# Additional packages
import os
import math
import numbers
import pandas as pd
import opendssdirect as dss
import numpy as np
from pydss.py_postprocessor.py_postprocess_abstract import AbstractPostprocess

# from pydss.exceptions import InvalidParameter, OpenDssConvergenceError
from pydss.utils.timing_utils import timed_info


# to get xfmr information
def get_transformer_info():
    """
    Gather transformer information
    """
    xfmr_name = dss.Transformers.Name()
    xfmr_data_dict = {
        "name": xfmr_name,
        "num_phases": dss.Properties.Value("Phases"),
        "num_wdgs": dss.Transformers.NumWindings(),
        "kva": [],
        "conn": [],
        "kv": [],
    }
    for wdgs in range(xfmr_data_dict["num_wdgs"]):
        dss.Transformers.Wdg(wdgs + 1)
        xfmr_data_dict["kva"].append(float(dss.Properties.Value("kva")))
        xfmr_data_dict["kv"].append(float(dss.Properties.Value("kv")))
        xfmr_data_dict["conn"].append(dss.Properties.Value("conn"))
    return xfmr_data_dict


def get_g(r_value):
    """
    Get conductance values from resistance values
    """
    return float(str(r_value[0]).split("|")[0]) ** (-1)


#
@timed_info
def compute_electric_distance(bus_phases=None):
    """
    This method computes electric distance matrix
    """
    lines = dss.utils.lines_to_dataframe()
    column_list = [c.strip().lower() for c in lines.columns]
    lines.columns = column_list
    lines["phases"] = pd.to_numeric(lines["phases"])

    if bus_phases is not None:
        lines = lines.loc[lines["phases"] == bus_phases, ["bus1", "bus2", "rmatrix"]].copy()

    lines["g"] = lines["rmatrix"].apply(get_g)
    busall = np.unique((list(lines["bus1"]) + list(lines["bus2"])))
    dis_gmat_df = pd.DataFrame(0, index=busall, columns=busall)

    for line in lines.index:
        dis_gmat_df.loc[lines.loc[line, "bus1"], lines.loc[line, "bus2"]] = -lines.loc[line, "g"]
        dis_gmat_df.loc[lines.loc[line, "bus2"], lines.loc[line, "bus1"]] = -lines.loc[line, "g"]

    for bus in busall:
        dis_gmat_df.loc[bus, bus] = -sum(dis_gmat_df.loc[bus, :])

    dis_rmat_df = pd.DataFrame(
        np.linalg.pinv(np.array(dis_gmat_df)),
        index=dis_gmat_df.index,
        columns=dis_gmat_df.columns,
    )

    dismat_df = pd.DataFrame(0, index=busall, columns=busall)
    for bus_i in dis_gmat_df.index:
        for bus_j in dis_gmat_df.columns:
            dismat_df.loc[bus_i, bus_j] = (
                dis_rmat_df.loc[bus_i, bus_i]
                + dis_rmat_df.loc[bus_j, bus_j]
                - dis_rmat_df.loc[bus_i, bus_j]
                - dis_rmat_df.loc[bus_j, bus_i]
            )

    return dismat_df


def choose_zone_radius(dismat_df):
    """
    Selects a zone radius value that makes sense
    """
    avg_distance = np.mean(np.array(dismat_df))
    std_distance = np.std(np.array(dismat_df))
    dispersion_factor = std_distance / avg_distance
    k = -0.8  # zone_radius calibration factor bounded by the inverse of the dispersion factor
    if abs(k) > 1 / dispersion_factor:
        k = -0.8 / dispersion_factor  # to avoid negative zone radius
    zone_thr = round(avg_distance + k * std_distance, 4)
    return avg_distance, std_distance, dispersion_factor, zone_thr


def string_attribute_parser(att, line):
    """
    Parses attribute value from a line string
    """
    if att.lower() in line.lower():
        return line.lower().split(att.lower() + "=")[1].split()[0]
    else:
        return None


def parse_pv_scenario(file_path, min_lifo_pv_size):
    """
    Extracts from a PV deployment scenario, parameter information into a dataframe.
    Sample syntax: PV_dict, PV_dataframe = parse_pv_scenario(deployment_path + deployment_name)
    """

    p_vsys_dict = dict()
    attribute_list = [
        "phases",
        "bus1",
        "kV",
        "irradiance",
        "Pmpp",
        "pf",
        "conn",
        "kVA",
        "%cutin",
        "%cutout",
        "Vmaxpu",
    ]

    if os.path.exists(file_path):
        with open(file_path, "r") as depfile:
            for line in depfile.readlines():
                pvname = line.split("PVSystem.")[1].split()[0].lower()
                p_vsys_dict[pvname] = dict()
                p_vsys_dict[pvname]["pvname"] = pvname
                for att in attribute_list:
                    p_vsys_dict[pvname][att] = string_attribute_parser(att, line)
    else:
        flag = dss.PVsystems.First()

        while flag > 0:
            pvname = dss.PVsystems.Name().lower()
            p_vsys_dict[pvname] = dict()
            p_vsys_dict[pvname]["pvname"] = pvname

            for att in attribute_list:
                if att in [
                    "kV",
                    "irradiance",
                    "Pmpp",
                    "pf",
                    "kVA",
                    "%cutin",
                    "%cutout",
                    "Vmaxpu",
                ]:
                    p_vsys_dict[pvname][att] = float(dss.Properties.Value(att))
                else:
                    p_vsys_dict[pvname][att] = dss.Properties.Value(att)

            flag = dss.PVsystems.Next()

    return p_vsys_dict, pd.DataFrame.from_dict(p_vsys_dict, "index")


def get_monitored_line_dataframe(phase_info=3):
    """
    Sample syntax:
    monitored_lines = get_monitored_line_dataframe()
    """
    lines = dss.utils.lines_to_dataframe()
    column_list = [c.strip().lower() for c in lines.columns]
    lines.columns = column_list
    lines["phases"] = pd.to_numeric(lines["phases"])
    if phase_info != 3:
        monitored_lines = lines
    else:
        monitored_lines = lines.loc[lines["phases"] == 3, ["bus1", "bus2", "rmatrix"]].copy()

    return monitored_lines


@timed_info
def check_line_overloads(monitored_lines):
    """
    Checks line overloads
    """
    # monitored_lines = get_monitored_line_dataframe()
    ovrl = None

    overloaded_line_dict = dict()
    affected_buses = set()
    dss.Circuit.SetActiveClass("Line")
    flag = dss.ActiveClass.First()
    while flag > 0:
        line_name = dss.CktElement.Name()
        line_limit = dss.CktElement.NormalAmps()
        raw_current = dss.CktElement.Currents()
        line_current = [math.sqrt(i**2 + j**2) for i, j in zip(raw_current[::2], raw_current[1::2])]
        ldg = max(line_current) / float(line_limit)

        if ldg > 1.0:
            overloaded_line_dict[line_name] = ldg * 100
            affected_buses.add(dss.CktElement.BusNames()[0])

            affected_buses.add(dss.CktElement.BusNames()[1])

        flag = dss.ActiveClass.Next()

    if affected_buses:
        ovrl = pd.DataFrame.from_dict(overloaded_line_dict, "index")
        ovrl.columns = ["%normal"]

    affected_buses = list(affected_buses)

    return ovrl, affected_buses


def form_pvzones(affected_buses, dismat_df, zone_thr):
    """
    Builds PV zones
    """
    # #print('Affected buses:', affected_buses)
    ohmy = dismat_df.loc[affected_buses, :].copy()
    zone = list()
    for col in ohmy.columns:
        if min(ohmy.loc[:, col]) <= zone_thr:
            zone.append(col)

    return zone


class EdLifoControl(AbstractPostprocess):
    """
    Electric distance last-in First-out curtailment based PV output control
    """

    REQUIRED_INPUT_FIELDS = [
        "curtailment_size",
        "electrical_distance_file_path",
        "zone_option",
        "zone_threshold",
        "fixed_pv_path",
        "lifo_pv_path",
        "lifo_min_pv_size",
        "user_lifo_pv_list",
    ]

    def __init__(
        self,
        project,
        scenario,
        inputs,
        dss_instance,
        dss_solver,
        dss_objects,
        dss_objects_by_class,
        simulation_settings,
        logger,
    ):
        """
        Constructor method
        """
        super().__init__(
            project,
            scenario,
            inputs,
            dss_instance,
            dss_solver,
            dss_objects,
            dss_objects_by_class,
            simulation_settings,
            logger,
        )
        dss = dss_instance

        if isinstance(self.config["curtailment_size"], numbers.Number):
            self.curtailment_size = self.config["curtailment_size"]
        else:
            self.curtailment_size = 5

        self.electrical_distance_file_path = self.config["electrical_distance_file_path"]

        if not os.path.exists(self.electrical_distance_file_path):
            self.electrical_distance_file_path = os.path.join(
                self.config["Inputs"], "edistance.csv"
            )
            self.dismat_df = compute_electric_distance()
            self.dismat_df.to_csv(self.electrical_distance_file_path)

        else:
            self.dismat_df = pd.read_csv(self.electrical_distance_file_path, index_col=0)

        (
            self.avg_distance,
            self.std_distance,
            self.dispersion_factor,
            self.zone_threshold,
        ) = choose_zone_radius(self.dismat_df)
        self.zone_option = self.config["zone_option"]

        if isinstance(self.config["zone_threshold"], numbers.Number):
            self.zone_threshold = self.config["zone_threshold"]

        if os.path.exists(self.config["fixed_pv_path"]):
            self.fixed_pv_path = self.config["fixed_pv_path"]
        else:
            self.fixed_pv_path = ""

        if os.path.exists(self.config["lifo_pv_path"]):
            self.lifo_pv_path = self.config["lifo_pv_path"]
        else:
            self.lifo_pv_path = ""

        self.lifo_min_pv_size = self.config["lifo_min_pv_size"]
        self.user_lifo_pv_list = self.config["user_lifo_pv_list"]
        self.pvdict, self.pvdf = parse_pv_scenario(self.lifo_pv_path, self.lifo_min_pv_size)
        self.pvdf3 = self.pvdf[self.pvdf["phases"] == "3"].copy()
        self.export_path = os.path.join(self.config["Outputs"])
        self.monitored_lines = get_monitored_line_dataframe("all")
        self.pctpmpp_step = 5
        self.curtail_option = "%Pmpp"  # can be 'kva' or '%Pmpp', default='%Pmpp'

        self.curtailment_record = {}
        self.pvbus_voltage_record = {}
        self.total_init_kW_deployed = 0
        self.total_kW_curtailed = 0
        self.total_kVA_curtailed = 0
        self.poa_lifo_ordered_pv_list = []
        self.init_power_PV = []
        self.total_kW_output = 0
        self.init_net_power_PV = 0
        self.zone = []
        self.overloads_df = pd.DataFrame()
        self.affected_buses = ()
        self.init_pctpmpp = {}
        self.init_kVA = {}
        self.comment = "Welcome to edLiFo! \n"
        self.pvbus_voltage = dict()
        self.solution_status = -1
        self.my_lifo_list = []
        self.pvs_df = dss.utils.pvsystems_to_dataframe()
        self.has_converged = True
        self.error = ""
        self.PV_kW_curtailed = {}
        self.PV_curtailed = {}

    def get_lifo_ordered_list(self):
        """
        Get the last-in first-in ordered PV list
        """
        self.pvs_df = dss.utils.pvsystems_to_dataframe()

        ordered_pv_df = self.pvs_df.sort_values(["Idx"], ascending=False)

        if not self.user_lifo_pv_list:
            self.poa_lifo_ordered_pv_list = list(ordered_pv_df.index)
            if list(self.pvdf3.phases):
                self.poa_lifo_ordered_pv_list = [
                    p for p in self.poa_lifo_ordered_pv_list if p in list(self.pvdf3.index)
                ]
        else:
            self.poa_lifo_ordered_pv_list = self.user_lifo_pv_list

    def record_curtailment(self, pv_sys):
        """
        Records PV curtailments
        """
        dss.Circuit.SetActiveElement(f"PVSystem.{pv_sys}")

        avail_power = [
            float(x["Pmpp"]) * float(dss.Properties.Value("irradiance"))
            for k, x in self.pvdict.items()
            if pv_sys == k
        ][0]
        power_pv = dss.CktElement.Powers()
        net_power_pv = sum(power_pv[::2])
        net_kvar_pv = sum(power_pv[1::2])
        self.PV_kW_curtailed[pv_sys + "Ref"] = self.init_net_power_PV
        self.PV_kW_curtailed[pv_sys + "Actual"] = net_power_pv
        self.PV_kW_curtailed[pv_sys + "NetCurt"] = self.init_net_power_PV - net_power_pv
        self.PV_kW_curtailed[pv_sys + "PctCurt"] = (
            100 * abs(self.init_net_power_PV - net_power_pv) / max(1, abs(avail_power))
        )
        self.PV_kW_curtailed[pv_sys + "kVarActual"] = net_kvar_pv

        self.total_kVA_curtailed += self.PV_curtailed[pv_sys]
        self.total_kW_curtailed += self.PV_kW_curtailed[pv_sys + "NetCurt"]
        self.total_init_kW_deployed += self.PV_kW_curtailed[pv_sys + "Ref"]
        self.total_kW_output += net_power_pv
        self.logger.info(f"Total curtailment for PVSystem.{pv_sys}: {self.total_kVA_curtailed}")

        which_bus = dss.Properties.Value("bus1")
        dss.Circuit.SetActiveBus(which_bus)

        self.pvbus_voltage[pv_sys] = dss.Bus.puVmagAngle()[::2]

    @timed_info
    def solve_overloads(self):
        """
        Uses the LiFo logic to solve line and transformer overloads
        """
        for pv_sys in self.my_lifo_list:
            dss.Circuit.SetActiveClass("PVsystems")

            if not dss.Circuit.SetActiveElement(f"PVSystem.{pv_sys}") > 0:
                self.logger.info(f"Cannot find the PV system {pv_sys}")
                self.logger.info(
                    f"Active element index: {dss.Circuit.SetActiveElement(f'PVSystem.{pv_sys}')}"
                )

            else:
                dss.Circuit.SetActiveElement(f"PVSystem.{pv_sys}")
                self.init_power_PV = dss.CktElement.Powers()
                self.init_net_power_PV = sum(self.init_power_PV[::2])
                if dss.Properties.Value("%Pmpp") == "":
                    self.init_pctpmpp[pv_sys] = 100
                    oldpctpmpp = 100
                    dss.run_command(f"Edit PVSystem.{pv_sys} %Pmpp=100")
                else:
                    self.init_pctpmpp[pv_sys] = float(dss.Properties.Value("%Pmpp"))
                    self.init_kVA[pv_sys] = float(dss.Properties.Value("kVA"))
                    oldpctpmpp = self.init_pctpmpp[pv_sys]

            while (
                self.affected_buses and self.pvs_df.loc[pv_sys, "kVARated"] > 0 and oldpctpmpp > 0
            ):
                """
                This while loop breaks the above conditions or when all PVs are curtailed,
                i.e., oldpctpmpp==0
                """

                dss.Circuit.SetActiveElement(f"PVSystem.{pv_sys}")

                if self.curtail_option == "%Pmpp":
                    self.logger.info(f"Old %Pmpp: {oldpctpmpp}")
                    newpctpmpp = max(oldpctpmpp - self.pctpmpp_step, 0)

                    dss.run_command(f"Edit PVSystem.{pv_sys} %Pmpp={newpctpmpp}")
                    if newpctpmpp == 0:
                        kvarlimit = 0
                        dss.run_command(f"Edit PVSystem.{pv_sys} kvarLimit={kvarlimit}")
                    npc = float(dss.Properties.Value("%Pmpp"))
                    self.logger.info(f"New %Pmpp: {npc}")
                    self.PV_kW_curtailed[pv_sys + "%Pmpp"] = newpctpmpp
                else:
                    self.PV_curtailed[pv_sys] += min(
                        self.curtailment_size, self.pvs_df.loc[pv_sys, "kVARated"]
                    )
                    new_k_va = max(self.pvs_df.loc[pv_sys, "kVARated"] - self.curtailment_size, 0)
                    dss.run_command(f"Edit PVSystem.{pv_sys} kVA={new_k_va}")

                dss.run_command("_SolvePFlow")

                self.overloads_df, self.affected_buses = check_line_overloads(self.monitored_lines)
                self.pvs_df = dss.utils.pvsystems_to_dataframe()

                if self.curtail_option == "%Pmpp":
                    oldpctpmpp = newpctpmpp
                    if self.affected_buses and oldpctpmpp == 0:
                        self.comment = f"{pv_sys} is fully curtailed but overloads still exist!"

                elif self.curtail_option == "kva":
                    if (
                        self.affected_buses
                        and max(self.pvs_df.loc[self.poa_lifo_ordered_pv_list, "kVARated"]) == 0
                    ):
                        self.comment = (
                            "All PV systems have been curtailed, but overloads still exist!"
                        )

                if not self.affected_buses:
                    self.solution_status = 1
                    self.comment = "Overload Solved!"
                    self.logger.info(self.comment)

                    break

            self.record_curtailment(pv_sys)

        # Setting pmpps back to their original values
        if self.init_kVA != {}:
            for pv_sys in self.my_lifo_list:
                inipctpmpp = self.init_pctpmpp[pv_sys]
                inikva = self.init_kVA[pv_sys]
                dss.run_command(f"Edit PVSystem.{pv_sys} %Pmpp={inipctpmpp} kVA={inikva}")

    def get_curtailment_candidates(self):
        """
        Finds PV units that can be be candidates for curtailment
        """
        lifo_pv_list = []
        for pv in self.poa_lifo_ordered_pv_list:
            if self.user_lifo_pv_list is None:
                if self.pvdf3.loc[pv, "bus1"] in self.zone:
                    lifo_pv_list.append(pv)
            else:
                dss.Circuit.SetActiveElement("PVSystem." + str(pv))
                bus1 = dss.Properties.Value("bus1")
                if bus1 in self.zone:
                    lifo_pv_list.append(pv)

        lifo_pv_list = list(lifo_pv_list)
        if self.zone and not lifo_pv_list:
            self.comment = f"No PV system found in the vicinity (radius={self.zone_threshold}) of the thermal overload"
            # #print(comment)

        if self.zone_option == "Yes" and lifo_pv_list:
            self.my_lifo_list = lifo_pv_list + [
                x for x in self.poa_lifo_ordered_pv_list if x not in lifo_pv_list
            ]

        else:
            self.my_lifo_list = self.poa_lifo_ordered_pv_list

    def poa_curtail(self):
        """
        Executes curtailment decisions
        """
        sol = dss.Solution
        dss.run_command("set stepsize=0")
        dss.run_command("BatchEdit PVSystem.* VarFollowInverter=True")
        self.get_lifo_ordered_list()

        self.PV_curtailed = dict()
        self.PV_kW_curtailed = dict()
        self.pvbus_voltage = dict()
        self.solution_status = -1
        self.comment = "RAS"
        total_k_va_deployed = self.pvs_df["kVARated"].sum()
        self.total_init_kW_deployed = 0
        # #print("Total PV KVA deployed: ",total_kVA_deployed)
        self.total_kVA_curtailed = 0
        self.total_kW_curtailed = 0
        self.total_kW_output = 0
        pct_k_w_curtailment = 0

        for pv_sys in self.poa_lifo_ordered_pv_list:
            # pv_sys_n = remove_pen(pv_sys)
            self.PV_curtailed[pv_sys] = 0
            self.pvbus_voltage[pv_sys] = []
            # PV_kW_curtailed[pv_sys_n] = 0
            self.PV_kW_curtailed[pv_sys + "NetCurt"] = 0
            self.PV_kW_curtailed[pv_sys + "kWCurt"] = 0
            self.PV_kW_curtailed[pv_sys + "PctCurt"] = 0
            self.PV_kW_curtailed[pv_sys + "%Pmpp"] = 100

        self.overloads_df, self.affected_buses = check_line_overloads(self.monitored_lines)
        self.logger.info(f"Number of buses affected: {len(self.affected_buses)}")

        self.zone = []

        if self.affected_buses:
            self.zone = form_pvzones(self.affected_buses, self.dismat_df, self.zone_threshold)
            # #print('zone length:',len(zone))

        else:
            self.logger.info("No monitored line affected")

        self.get_curtailment_candidates()

        self.solution_status = 0

        if self.pvs_df.loc[self.poa_lifo_ordered_pv_list, "kVARated"].max() == 0:
            self.comment = "No PV system found!"
            self.logger.info(self.comment)
            number_ol = len(self.overloads_df)
            self.logger.info(f"There are {number_ol} persisting overloads")

        elif self.my_lifo_list:
            self.init_pctpmpp = {}
            self.init_kVA = {}
            self.init_net_power_PV = 0
            self.init_power_PV = []

            self.solve_overloads()

        if self.solution_status == -1:
            self.comment = "No need to curtail!"

        if max(self.PV_curtailed.keys(), key=(lambda k: self.PV_curtailed[k])) == 0:
            self.comment = "Deployment passed without curtailment!"
            # #print(comment)
            self.solution_status == 0

        self.PV_curtailed["Comment"] = self.comment
        pct_curtailment = self.total_kVA_curtailed * 100 / max(1, total_k_va_deployed)
        self.PV_curtailed["Pct_curtailment"] = pct_curtailment

        pct_k_w_curtailment = (
            abs(self.total_kW_curtailed) * 100 / max(1, abs(self.total_init_kW_deployed))
        )
        self.PV_kW_curtailed["Pct_kW_curtailment"] = pct_k_w_curtailment
        self.PV_kW_curtailed["Total_PV_kW_deployed"] = self.total_init_kW_deployed
        self.PV_kW_curtailed["Total_PV_kW_curtailed"] = self.total_kW_curtailed
        self.PV_kW_curtailed["Total_PV_kW_output"] = self.total_kW_output

        self.PV_kW_curtailed["Comment"] = self.comment
        # #print("Done with 1 poa loop:", Pct_curtailment)

        self.logger.info(f"kW Curtailed: {self.PV_kW_curtailed}")
        self.has_converged = sol.Converged()
        self.error = sol.Convergence()
        # This error is fake for now, find how to get this from Opendssdirect

    def run(self, step, step_max, simulation=None):
        """
        Runs edLiFo
        """

        self.logger.info("Running edLiFo control")
        self.poa_curtail()

        self.curtailment_record[step] = self.PV_kW_curtailed
        self.pvbus_voltage_record[step] = self.pvbus_voltage

        has_converged = self.has_converged
        error = self.error
        # This error is fake for now, find how to get this from Opendssdirect

        # step-=1 # uncomment the line if the post process needs to rerun for the same point in time
        return step, has_converged, error

    def _get_required_input_fields(self):
        return self.REQUIRED_INPUT_FIELDS

    @timed_info
    def finalize(self):

        df1 = pd.DataFrame.from_dict(self.curtailment_record, "index")
        curtailment_report = os.path.join(
            self.export_path,
            f"curtailment_report_{str(self.zone_threshold)}_{self.zone_option}_{self.curtail_option}.csv",
        )
        df1.to_csv(curtailment_report)

        df2 = pd.DataFrame.from_dict(self.pvbus_voltage_record, "index")
        voltage_report = os.path.join(
            self.export_path,
            f"pvbus_voltage_report_{str(self.zone_threshold)}_{self.zone_option}_{self.curtail_option}.csv",
        )
        df2.to_csv(voltage_report)
