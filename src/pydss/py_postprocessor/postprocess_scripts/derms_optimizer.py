from pydss.py_postprocessor.py_postprocess_abstract import AbstractPostprocess
from pydss.py_postprocessor.postprocess_scripts.derms_optimizer_helper_modules.opt_funcs import (
    Derms,
    linear_powerflow_model,
)
from scipy.sparse import lil_matrix
import scipy.sparse.linalg as sp
import scipy.sparse as sparse
from scipy import stats
import pandas as pd
from math import sqrt
import numpy as np
import os


class DermsOptimizer(AbstractPostprocess):
    REQUIRED_INPUT_FIELDS_AND_DEFAULTS = {
        "control_flag": True,
        "control_all_flag": True,
        "num_DERMS": 1,
        "Vlower": 0.955,
        "Vupper": 1.038,
        "coeff_p": 0.0005,
        "coeff_q": 0.000001,
        "stepsize_xp": 1,
        "stepsize_xq": 5,
        "stepsize_mu": 10,
        "opf_iteration": 60,
        "max_iterations": 50,
        "time_trigger_sec": 900,
        "measurements_noises_flag": True,
        "implementation_mode": "Voltage triggered",
        "Distributions": {
            "Vmes": ["norm", [0.0, 0.01]],
            "Imes": ["norm", [0.0, 0.01]],
        },
    }

    IMPLEMENTATION_MODES = ["Continuous", "Voltage triggered", "Time triggered", "Off"]

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
        """Constructor method"""
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
        self.options = {**self.REQUIRED_INPUT_FIELDS_AND_DEFAULTS, **inputs}
        self.Settings = simulation_settings
        self.Objects = dss_objects_by_class

        self.dss_solver = dss_solver
        self.dss = dss_instance
        self.logger = logger
        self.logger.info("Creating DERMS Optimizer module")

        self.rootPath = simulation_settings["Project"]["Project Path"]
        self.dssPath = os.path.join(
            self.rootPath, simulation_settings["Project"]["Active Project"], "DSSfiles"
        )

        self.Buses = []
        self.BusDistance = []
        self.Vbase_allnode = []

        self.initialize_optimizer()
        self.ExportCSVfiles = True
        self.sim_start = False
        self.DERMS_trigger_fail_count = 0
        self.DERMS_trigger_count = 0
        self.DERMS_trigger_success_count = 0

        p_vdata = self.get_de_rdata()

        assert self.options["implementation_mode"] in self.IMPLEMENTATION_MODES, (
            "valid implementation modes are ()".fomrmat(self.IMPLEMENTATION_MODES)
        )
        self.derms_controller = Derms(
            p_vdata,
            self.controlbus,
            self.controlelem,
            self.BEcapacity,
            self.nodes[self.nSlack :],
            self.BEname,
        )

    def initialize_optimizer(self):
        self.dss.utils.run_command("calcV")
        self.nodes = self.dss.Circuit.YNodeOrder()
        self.nNodes = len(self.nodes)

        self.Slack = self.Objects["Vsources"]["Vsource.source"]
        self.nSlack = int(self.Slack.get_value("phases"))

        for node in self.nodes:
            node = node.lower()
            bus, phase_info = node.split(".", 1)
            self.Vbase_allnode.append(self.Objects["Buses"][bus].get_variable("kVBase") * 1000)
            self.BusDistance.append(self.Objects["Buses"][bus].get_variable("Distance"))

        for x in self.nodes:
            b_name = x.split(".")[0]
            if b_name not in self.Buses:
                self.Buses.append(b_name)
        self.nBus = len(self.Buses)

        y00, y01, y10, y11, y11_sparse, y11_inv, ybus = self.extract_impednce_matrix()
        self.get_branch_info()

        self.dss_solver.Solve()
        v1, v1_pu = self.get_voltage__yorder()

        cap_names = self.dss.Capacitors.AllNames()
        ",".join(cap_names)

        load_data = self.get_elem_data(
            "Loads",
            [
                "Name",
                "kV",
                "kW",
                "pf",
                "phase",
                "bus",
                "phases",
                "VoltagesMagAng",
                "Powers",
                "conn",
            ],
        )
        sum([L["kW"] for L in load_data])
        # Do we want profile implementation here or a dedicatied profile manager?

        self.PVSystem = self.get_elem_data(
            "Generators", ["Name", "bus", "busFull", "phase", "kVA", "kW", "phases", "conn"]
        )
        self.pv_system_1phase = self.convert_3phase_pv_to_1phase_pv(self.PVSystem)
        self.PVSystem_1phaseDF = pd.DataFrame(self.pv_system_1phase)
        if self.options["control_flag"]:
            p_vlocation = []
            len(self.pv_system_1phase)
            node_index_with_pv = []
            pv_inverter_size = []
            for pv in self.pv_system_1phase:
                allpvbus = pv["bus"].split(".")
                p_vlocation.append(allpvbus[0])
                if len(allpvbus) == 1:
                    allpvbus = allpvbus + ["1", "2", "3"]
                for ii in range(len(allpvbus) - 1):
                    pvbus = allpvbus[0] + "." + allpvbus[ii + 1]
                    node_index_with_pv.append(self.nodes.index(pvbus.upper()))
                pv_inverter_size.append(float(pv["kVA"]) / (len(allpvbus) - 1))

            self.get_elem_data("Capacitors", ["Name", "bus", "phase", "phases", "kV", "kvar"])
            pq_load, pq_pv, pq_node, qcap = self.calc_node_pq()

            if self.options["control_all_flag"]:
                self.controlbus = self.nodes[self.nSlack :]
            else:
                self.controlbus = self.get_contol_buses(["Generators", "Capacitors"])

            self.controlelem = []
            self.mu0 = [
                np.zeros(len(self.controlbus)),
                np.zeros(len(self.controlbus)),
                np.zeros(len(self.controlelem)),
            ]

            self.power_flow_data = linear_powerflow_model(
                y00, y01, y10, y11_inv, [], v1, self.nSlack
            )

            self.stepsize_control = [
                self.options["stepsize_xp"],
                self.options["stepsize_xq"],
                self.options["stepsize_mu"],
            ]
            self.vlimit = [self.options["Vupper"], self.options["Vlower"]]
        return

    def calc_node_pq(self):
        pq_load = self.get_pq_by_class("Loads")
        pq_pv = self.get_pq_by_class("Generators")
        pq_cap = self.get_pq_by_class("Capacitors")
        qcap = pq_cap.imag
        pq_node = -pq_load + pq_pv - 1j * np.array(qcap)  # power injection
        return pq_load, pq_pv, pq_node, qcap

    def get_pq_by_class(self, class_name):
        p = [0] * len(self.nodes)
        q = [0] * len(self.nodes)
        for name, obj in self.Objects[class_name].items():
            power = obj.get_value("Powers")
            bus = obj.get_value("BusNames")[0]
            nodes = bus.split(".")[1:] if len(bus.split(".")[1:]) else [1, 2, 3]

            for i, ii in enumerate(nodes):
                node_name = "{}.{}".format(bus.split(".")[0], ii)
                index = self.nodes.index(node_name.upper())
                p[index] = power[2 * i]
                q[index] = power[2 * i + 1]
        pq = np.array(p) + 1j * np.array(q)
        return pq

    def get_elem_data(self, element_class, properties):
        data = []
        for name, obj in self.Objects[element_class].items():
            datum = {}
            for ppty in properties:
                if ppty == "bus":
                    datum[ppty] = obj.get_value("BusNames")[0].split(".")[0]
                elif ppty == "phase":
                    phases = obj.get_value("BusNames")[0].split(".")[1:]
                    datum[ppty] = phases if len(phases) else [1, 2, 3]
                elif ppty == "busFull":
                    datum[ppty] = obj.get_value("BusNames")[0]
                else:
                    datum[ppty] = obj.get_value(ppty)
            data.append(datum)
        return data

    def convert_3phase_pv_to_1phase_pv(self, pv_systems):
        # convert multi-phase PV into multiple 1-phase PVs for control implementation purpose
        pv_system_1phase = []
        for pv in pv_systems:
            for i, ii in enumerate(pv["phase"]):
                pv_perphase = {}
                pv_perphase["Name"] = pv["Name"]  # +'_node'+bus[ii+1]
                pv_perphase["bus"] = pv["bus"] + "." + ii
                pv_perphase["kW"] = pv["kW"] / pv["phases"]
                pv_perphase["kVA"] = pv["kVA"] / pv["phases"]
                pv_system_1phase.append(pv_perphase)
        return pv_system_1phase

    def get_incidence_matrix(self):
        # self.dss.utils.run_command('solve mode=fault') dont think this is needed. May be wrong
        ybranch_prim, branch_node_incidence, n_neutral, record_index = self.construct__yprime()
        current_coeff_matrix = np.dot(ybranch_prim, branch_node_incidence)
        current_coeff_matrix = current_coeff_matrix[record_index, :-n_neutral]
        branch_node_incidence = branch_node_incidence[record_index, :-n_neutral]
        return current_coeff_matrix, branch_node_incidence, current_coeff_matrix

    def extract_impednce_matrix(self):
        y = self.dss.Circuit.SystemY()
        ybus = self.to_complex(y)
        y00 = ybus[0 : self.nSlack, 0 : self.nSlack]
        y01 = ybus[0 : self.nSlack, self.nSlack :]
        y10 = ybus[self.nSlack :, 0 : self.nSlack]
        y11 = ybus[self.nSlack :, self.nSlack :]
        y11_sparse = lil_matrix(y11)
        y11_sparse = y11_sparse.tocsr()
        a_sps = sparse.csc_matrix(y11)
        lu_obj = sp.splu(a_sps)
        y11_inv = lu_obj.solve(np.eye(self.nNodes - self.nSlack))
        return y00, y01, y10, y11, y11_sparse, y11_inv, ybus

    def get_voltage__yorder(self):
        temp__vbus = self.dss.Circuit.YNodeVArray()
        voltage = [complex(0, 0)] * self.nNodes
        for ii in range(self.nNodes):
            voltage[ii] = complex(temp__vbus[ii * 2], temp__vbus[ii * 2 + 1])
        voltage_pu = list(map(lambda x: abs(x[0]) / x[1], zip(voltage, self.Vbase_allnode)))
        return voltage, voltage_pu

    def to_complex(self, values):
        ydim = int(sqrt(len(values) / 2))
        yreal = np.array(values[0::2]).reshape((ydim, ydim))
        yimag = np.array(values[1::2]).reshape((ydim, ydim))
        ycmplx = yreal + 1j * yimag
        return ycmplx

    def construct__yprime(self):
        ybranch_prim = np.array(
            [[complex(0, 0)] * 2 * self.nBarnchElements] * 2 * self.nBarnchElements
        )
        branch_node_incidence = np.zeros(
            [2 * self.nBarnchElements, self.nNodes + 422]
        )  # TODO fix hard coded 422 for Green, 104 for Diamond

        record_index = []
        n_neutral = 0
        start_no = 0
        count = 0

        temp__all_node_names = self.dss.Circuit.YNodeOrder()
        for elem_name, elm_obj in self.branchElements.items():
            values = elm_obj.get_value("YPrim")
            yprim = self.to_complex(values)
            buses = [ii.split(".")[0] for ii in elm_obj.get_value("BusNames")]
            nodes = elm_obj.get_value("NodeOrder")
            n_phases = int(len(nodes) / 2)
            n_neutral += nodes.count(0)
            for ii in range(n_phases):
                from_node = buses[0] + "." + str(nodes[ii])
                to_node = buses[1] + "." + str(nodes[ii + n_phases])
                if nodes[ii] == 0:
                    temp__all_node_names.append(from_node.upper())
                if nodes[ii + n_phases] == 0:
                    temp__all_node_names.append(to_node.upper())
                from_node_index = temp__all_node_names.index(from_node.upper())
                to_node_index = temp__all_node_names.index(to_node.upper())
                branch_node_incidence[2 * count + ii, from_node_index] = 1
                branch_node_incidence[2 * count + n_phases + ii, to_node_index] = 1
                record_index.append(2 * count + ii)
            count = count + n_phases
            end_no = start_no + 2 * n_phases
            ybranch_prim[start_no:end_no, start_no:end_no] = yprim
            start_no = end_no

        return ybranch_prim, branch_node_incidence, n_neutral, record_index

    def get_contol_buses(self, class_names):
        controlbus = []
        for class_name in class_names:
            for elm in self.get_elem_data(class_name, ["bus", "phases"]):
                for phase in elm["phases"]:
                    controlbus.append("{}.{}".format(elm["bus"], phase))
        return controlbus

    @staticmethod
    def _get_required_input_fields():
        return {}

    def get_branch_info(self):
        self.branchElements = {**self.Objects["Lines"], **self.Objects["Transformers"]}
        self.nBarnchElements = len(self.branchElements)
        self.BEindex = []
        self.BEcapacity = []
        self.BEname = []

        for elm_name, elm_obj in self.branchElements.items():
            n_terms = elm_obj.get_value("NumTerminals")
            nodes = elm_obj.get_value("NodeOrder")
            n_phases = int(len(nodes) / n_terms)
            self.BEindex.append(list(range(n_phases)))
            for ii in range(n_phases):
                self.BEcapacity.append(elm_obj.get_value("NormalAmps"))
                self.BEname.append("{}.{}".format(elm_name, nodes[ii]))

    def get_de_rdata(self):
        data = self.get_elem_data(
            "Generators", ["Name", "busFull", "phase", "kVA", "kW", "phases", "conn"]
        )
        data = pd.DataFrame(data)
        data.index = data["Name"]
        p_vdata = {
            "pvName": [],
            "pvLocation": [],
            "bus": [],
            "pvSize": [],
            "inverterSize": [],
        }
        for pv1_p in self.PVSystem_1phaseDF["Name"].tolist():
            pv = data.loc[pv1_p]
            p_vdata["pvName"].append(pv["Name"])
            p_vdata["bus"].append(pv["busFull"])
            p_vdata["pvSize"].append(pv["kW"])
            p_vdata["inverterSize"].append(pv["kVA"])
            for b in self.buses(pv):
                if b.upper() not in p_vdata["pvLocation"]:
                    p_vdata["pvLocation"].append(b.upper())
                    break
        return p_vdata

    def buses(self, pv):
        bus = pv["busFull"].split(".")
        if len(bus) == 1:
            bus += ["1", "2", "3"]
        return [f"{bus[0]}.{i}" for i in bus[1:]]

    def run(self, step, step_max, simulation=None):
        """Induces and removes a fault as the simulation runs as per user defined settings."""
        self.logger.info("Running DERMS optimization module")
        opt_iter = 0

        # Really bad codeing form
        mu0 = [
            [0 for x in range(len(self.controlbus))],
            [0 for x in range(len(self.controlbus))],
            [0 for x in range(len(self.controlelem))],
        ]

        p_vmax = [pv["kW"] if pv["kW"] < pv["kVA"] else pv["kVA"] for pv in self.pv_system_1phase]

        while opt_iter < self.options["max_iterations"]:
            self.dss_solver.reSolve()
            p_vlocation, p_vpower, vmes, imes = self.dermsController.monitor(
                self._dssInstance, self.Objects, self.PVSystem_1phaseDF
            )
            self.logger.info("Voltage measurements: {}".format(len(vmes)))
            self.logger.info("Maximum voltage: {}".format(max(vmes)))

            if self.options["measurements_noises_flag"]:
                dist_name, dist_params = self.options["Distributions"]["Vmes"]
                dist = getattr(stats, dist_name)
                vmes = vmes + dist.rvs(*dist_params, size=len(vmes))
                dist_name, dist_params = self.options["Distributions"]["Imes"]
                dist = getattr(stats, dist_name)
                imes = imes + dist.rvs(*dist_params, size=len(imes))

            if self.options["implementation_mode"] == "Continuous":
                derms_trigger = 1
            elif self.options["implementation_mode"] == "Voltage triggered":
                if max(vmes) > self.options["Vupper"] or min(vmes) < self.options["Vlower"]:
                    derms_trigger = 1
                    # TODO: Should DERMS trigger count be in this if statement?
                elif (
                    max(vmes) <= self.options["Vupper"]
                    and min(vmes) >= self.options["Vlower"]
                    and opt_iter >= 1
                ):
                    derms_trigger = 0
                    self.DERMS_trigger_count += 1
                    self.DERMS_trigger_success_count += 1
                    self.logger.info("DERMS OPF successfully triggered, maxV: {}".fotmat(max(vmes)))
                    break
                else:
                    derms_trigger = 0
            elif self.options["implementation_mode"] == "Time triggered":
                # TODO: Is step * stepsize_sim >= time_mode_resolution required? Is the idea to ensure that the controller does not run on the first iteration?
                if (
                    step > 0
                    and self.dss_solver.GetTotalSeconds() % self.options["time_trigger_sec"] == 0
                ):
                    derms_trigger = 1
                else:
                    derms_trigger = 0
            elif self.options["implementation_mode"] == "Off":
                derms_trigger = 0

            if derms_trigger == 1:
                [x1, mu1] = self.dermsController.control(
                    self.power_flow_data,
                    self.options,
                    self.stepsize_control,
                    mu0,
                    self.vlimit,
                    p_vpower,
                    imes,
                    vmes,
                    p_vmax,
                )
                # ------ apply the setpoint ------
                n_pv_1_phs = len(self.pv_system_1phase)
                for pv in self.PVSystem:
                    idx = [
                        i for i, x in enumerate(self.pv_system_1phase) if x["Name"] == pv["Name"]
                    ]
                    self.Objects["Generators"][pv["Name"]].SetParameter(
                        "kW", sum([x1[ii] for ii in idx])
                    )
                    self.Objects["Generators"][pv["Name"]].SetParameter(
                        "kvar", sum([x1[ii + n_pv_1_phs] for ii in idx])
                    )

                mu0 = mu1
                # resV_record.append(max(Vmes))
                opt_iter = opt_iter + 1
                if max(vmes) <= self.options["Vupper"] and min(vmes) >= self.options["Vlower"]:
                    self.DERMS_trigger_count += 1
                    self.DERMS_trigger_success_count += 1
                    self.logger.info("DERMS OPF successfully triggered")
                    break
            elif derms_trigger == 0:
                # TODO: Is this piece of code required?
                # for pv in self.PVSystem:
                #     PVgen = float(pv['kW']) * PVshape[
                #         int((present_step - 1) * stepsize_sim / data_resolution + 3600 / data_resolution * startH)]
                #     if PVgen > float(pv["kVA"]):
                #         PVgen = float(pv["kVA"])
                #     dss.run_command('edit ' + str(pv["name"]) + ' kW=' + str(PVgen) + ' pf=' + str(pf_auto))
                break
            if opt_iter == self.options["max_iterations"]:
                self.DERMS_trigger_count += 1
                if max(vmes) > self.options["Vupper"] or min(vmes) < self.options["Vlower"]:
                    self.DERMS_trigger_fail_count += 1
                    self.logger.warning("DERMS OPF triggered and failed")

            opt_iter += 1
        # step-=1 # uncomment the line if the post process needs to rerun for the same point in time
        return step

    def get_preoptimization_results(self):
        return
