import numpy as np
import math
import csv


def linear_powerflow_model(y00, y01, y10, y11_inv, i_coeff, v1, slack_no):
    # voltage linearlization
    v1_conj = np.conj(v1[slack_no:])
    v1_conj_inv = 1 / v1_conj
    coeff_v = y11_inv * v1_conj_inv
    coeff_v_p = coeff_v
    coeff_v_q = -1j * coeff_v
    coeff__vm = -np.dot(y11_inv, np.dot(y10, v1[:slack_no]))

    # voltage magnitude linearization
    m = coeff__vm
    m_inv = 1 / coeff__vm
    coeff__vmag_k = abs(m)
    a = (np.multiply(coeff_v.transpose(), m_inv)).transpose()
    coeff__vmag_p = (np.multiply(a.real.transpose(), coeff__vmag_k)).transpose()
    coeff__vmag_q = (np.multiply((-1j * a).real.transpose(), coeff__vmag_k)).transpose()

    # current linearization
    if len(i_coeff):
        coeff_i_p = np.dot(i_coeff[:, slack_no:], coeff_v_p)
        coeff_i_q = np.dot(i_coeff[:, slack_no:], coeff_v_q)
        coeff_i_const = np.dot(i_coeff[:, slack_no:], coeff__vm) + np.dot(
            i_coeff[:, :slack_no], v1[:slack_no]
        )
    else:
        coeff_i_p = []
        coeff_i_q = []
        coeff_i_const = []

    # =========================================Yiyun's Notes===========================================#
    # Output relations: Vmag = coeff_Vmag_P * Pnode + coeff_Vmag_Q * Qnode + coeff_Vm
    #                      I = coeff_I_P * Pnode + coeff_I_Q * Qnode + coeff_I_const (complex value)
    # ================================================================================================#

    return (
        coeff_v_p,
        coeff_v_q,
        coeff__vm,
        coeff__vmag_p,
        coeff__vmag_q,
        coeff__vmag_k,
        coeff_i_p,
        coeff_i_q,
        coeff_i_const,
    )


def validate_linear_model(coeff__vp, coeff__vq, coeff__vm, pq_node, slack_number):
    v_cal = (
        coeff__vm
        + np.dot(coeff__vp, np.array([np.real(ii) * 1000 for ii in pq_node[slack_number:]]))
        + np.dot(coeff__vq, np.array([np.imag(ii) * 1000 for ii in pq_node[slack_number:]]))
    )
    v_cal_1 = coeff__vm + np.dot(coeff__vp, np.conj(pq_node[slack_number:] * 1000))
    # coeff_Vp*Pnode + coeff_Vq*Qnode + coeff_Vm

    # =========================================Yiyun's Notes===========================================#
    # 1000 should be the S base
    # =================================================================================================#

    return [v_cal, v_cal_1]


def check_vi_correct(
    v1,
    pq_node,
    slack_number,
    coeff_v,
    coeff__vm,
    coeff__vmag_p,
    coeff__vmag_q,
    coeff__vmag_k,
    y10,
    y11,
    coeff_i_p,
    coeff_i_q,
    coeff_i_const,
    i_coeff,
):
    v1_linear = np.dot(coeff_v, np.conj(pq_node[slack_number:] * 1000)) + coeff__vm
    v1_linear = list(v1_linear)
    vdiff = list(
        map(lambda x: abs(x[0] - x[1]) / abs(x[0]) * 100, zip(v1[slack_number:], v1_linear))
    )
    with open("voltage_diff.csv", "w") as f:
        csvwriter = csv.writer(f)
        csvwriter.writerow(vdiff)
    f.close()

    v1_mag_linear = (
        np.dot(coeff__vmag_p, (pq_node[slack_number:] * 1000).real)
        + np.dot(coeff__vmag_q, (pq_node[slack_number:] * 1000).imag)
        + coeff__vmag_k
    )
    v1_mag_linear = list(v1_mag_linear)
    vdiff = list(
        map(
            lambda x: abs(abs(x[0]) - x[1]) / abs(x[0]) * 100, zip(v1[slack_number:], v1_mag_linear)
        )
    )
    with open("voltageMag_diff.csv", "w") as f:
        csvwriter = csv.writer(f)
        csvwriter.writerow(vdiff)
    f.close()

    # get Ibus
    ibus = list(
        map(
            lambda x: (x[0] * 1000 / x[1]).conjugate(),
            zip(list(pq_node)[slack_number:], v1[slack_number:]),
        )
    )
    ibus_cal_0 = np.dot(y10, v1[0:slack_number])
    ibus_cal_1 = np.dot(y11, v1[slack_number:])
    ibus_cal = list(map(lambda x: x[0] + x[1], zip(ibus_cal_0, ibus_cal_1)))
    idiff = list(map(lambda x: abs(x[0] - x[1]), zip(ibus, ibus_cal)))
    with open("currentBus_diff.csv", "w") as f:
        csvwriter = csv.writer(f)
        csvwriter.writerow(idiff)
    f.close()

    # get Ibranch
    ibranch = np.dot(i_coeff, v1)
    ibranch_cal = np.dot(i_coeff[:, slack_number:], v1_linear) + np.dot(
        i_coeff[:, 0:slack_number], v1[:slack_number]
    )
    ibranch_diff = list(map(lambda x: abs(x[0] - x[1]), zip(ibranch, ibranch_cal)))
    with open("current_diff.csv", "w") as f:
        csvwriter = csv.writer(f)
        csvwriter.writerow(ibranch_diff)
    f.close()


def cost_fun(
    x,
    dual_upper,
    dual_lower,
    v1_pu,
    ppv_max,
    coeff_p,
    coeff_q,
    npv,
    control_bus_index,
    vupper,
    vlower,
    dual_current,
    thermal_limit,
    i1_mag,
):
    # cost_function = coeff_p*(Pmax-P)^2+coeff_q*Q^2+dual_upper*(v1-1.05)+dual_lower*(0.95-v1)
    f1 = 0
    for ii in range(npv):
        f1 = (
            f1
            + coeff_p * (ppv_max[ii] - x[ii]) * (ppv_max[ii] - x[ii])
            + coeff_q * x[ii + npv] * x[ii + npv]
        )
    # f = f1 + np.dot(dual_upper,(np.array(v1_pu)[control_bus_index]-Vupper)) + np.dot(dual_lower,(Vlower-np.array(v1_pu)[control_bus_index]))
    v_evaluate = [v1_pu[ii] for ii in control_bus_index]
    f2 = (
        f1
        + np.dot(dual_upper, np.array([max(ii - vupper, 0) for ii in v_evaluate]))
        + np.dot(dual_lower, np.array([max(vlower - ii, 0) for ii in v_evaluate]))
    )
    f3 = np.dot(
        dual_current,
        np.array(
            [
                max(ii, 0)
                for ii in list(map(lambda x: x[0] * x[0] - x[1] * x[1], zip(i1_mag, thermal_limit)))
            ]
        ),
    )
    f = f2 + f3

    # =========================================Yiyun's Notes===========================================#
    # f1 is the quadratic PV curtailment plus quadratic reactive power injection
    # f2 is the Lagrangian term for voltage violations and line current violations
    # ===> Note the "control_bus_index" might be the index for measurement sensitivity analysis
    # =================================================================================================#

    return [f1, f]


def pv_cost_fun_gradient(x, coeff_p, coeff_q, pmax):
    grad = np.zeros(len(x))
    for ii in range(int(len(x) / 2)):
        grad[ii] = -2 * coeff_p * (pmax[ii] * 1000 - x[ii] * 1000)
        grad[ii + int(len(x) / 2)] = 2 * coeff_q * x[ii + int(len(x) / 2)] * 1000
        # grad[ii + int(len(x) / 2)] = 0

    # =========================================Yiyun's Notes===========================================#
    # x is the decision vector [P,Q]
    # =================================================================================================#

    return grad


def voltage_constraint_gradient(
    all_node_names, node_with_pv, dual_upper, dual_lower, coeff__vmag_p, coeff__vmag_q
):
    node_noslackbus = all_node_names
    node_noslackbus[0:3] = []

    # =========================================Yiyun's Notes===========================================#
    # remove the slack bus
    # =================================================================================================#

    grad_upper = np.matrix([0] * len(node_noslackbus) * 2).transpose()
    grad_lower = np.matrix([0] * len(node_noslackbus) * 2).transpose()
    count = 0
    for node in node_noslackbus:
        if node in node_with_pv:
            grad_upper[count] = dual_upper.transpose() * coeff__vmag_p[:, count]
            grad_upper[count + len(node_noslackbus)] = (
                dual_upper.transpose() * coeff__vmag_q[:, count]
            )
            grad_lower[count] = -dual_lower.transpose() * coeff__vmag_p[:, count]
            grad_lower[count + len(node_noslackbus)] = (
                -dual_lower.transpose() * coeff__vmag_q[:, count]
            )
        count = count + 1
    return [grad_upper, grad_lower]


def current_constraint_gradient(
    all_node_names, node_with_pv, dual_upper, coeff__imag_p, coeff__imag_q
):
    node_noslackbus = all_node_names
    node_noslackbus[0:3] = []
    grad_upper = np.matrix([0] * len(node_noslackbus) * 2).transpose()
    count = 0
    for node in node_noslackbus:
        if node in node_with_pv:
            grad_upper[count] = dual_upper.transpose() * coeff__imag_p[:, count]
            grad_upper[count + len(node_noslackbus)] = (
                dual_upper.transpose() * coeff__imag_q[:, count]
            )
        count = count + 1
    return grad_upper

    # =========================================Yiyun's Notes===========================================#
    # PV_costFun_gradient,  voltage_constraint_gradient, current_constraint_gradient and project_PV..
    # ... are set up for updating the PV decision variables in eq(10)
    # =================================================================================================#


def voltage_constraint(v1_mag):
    g = v1_mag - 1.05
    g.append(0.95 - v1_mag)
    return g


def current_constraint(i1_mag, imax):
    g = []
    g.append(i1_mag - imax)

    # =========================================Yiyun's Notes===========================================#
    # assume single directional power flow
    # voltage_constraint, current_constraint, and project_dualvariable are set up for updating the dual...
    # ... variables in eq (11)
    # =================================================================================================#

    return g


def project_dualvariable(mu):
    for ii in range(len(mu)):
        mu[ii] = max(mu[ii], 0)

    # =========================================Yiyun's Notes===========================================#
    # If the corresponding constraints in primal problem is in canonical form, then dual variable is >=0
    # =================================================================================================#

    return mu


def project_pv(x, pmax, sinv):
    qavailable = 0
    pavailable = 0
    num = len(sinv)
    for ii in range(num):
        if x[ii] > pmax[ii]:
            x[ii] = pmax[ii]
        elif x[ii] < 0:
            x[ii] = 0

        if sinv[ii] > x[ii]:
            qmax = math.sqrt(sinv[ii] * sinv[ii] - x[ii] * x[ii])
        else:
            qmax = 0
        if x[ii + num] > qmax:
            x[ii + num] = qmax
        # elif x[ii + num] < 0:
        #     x[ii + num] = 0
        elif x[ii + num] < -qmax:
            x[ii + num] = -qmax

        pavailable = pavailable + pmax[ii]
        qavailable = qavailable + qmax
    return [x, pavailable, qavailable]


def dual_update(mu, coeff_mu, constraint):
    mu_new = mu + coeff_mu * constraint
    mu_new = project_dualvariable(mu_new)

    # =========================================Yiyun's Notes===========================================#
    # normal way for update Lagrangian variable is by the sub-gradient of cost function
    # Here is the equation (11) in the draft paper
    # =================================================================================================#

    return mu_new


def matrix_cal_for_sub_power(v0, y00, y01, y11, v1_noload):
    diag_v0 = np.matrix([[complex(0, 0)] * 3] * 3)
    diag_v0[0, 0] = v0[0]
    diag_v0[1, 1] = v0[1]
    diag_v0[2, 2] = v0[2]
    k = diag_v0 * y01.conj() * np.linalg.inv(y11.conj())
    g = (
        diag_v0 * y00.conj() * np.matrix(v0).transpose().conj()
        + diag_v0 * y01.conj() * v1_noload.conj()
    )
    return [k, g]


def sub_power_pq(v1, pq_node, k, g):
    diag_v1 = np.matrix([[complex(0, 0)] * len(v1)] * len(v1))
    for ii in range(len(v1)):
        diag_v1[ii, ii] = v1[ii]
    m = k * np.linalg.inv(diag_v1)
    mr = m.real
    mi = m.imag
    p0 = g.real + (mr.dot(pq_node.real) * 1000 - mi.dot(pq_node.imag) * 1000)
    q0 = g.imag + (mr.dot(pq_node.imag) * 1000 + mi.dot(pq_node.real) * 1000)

    p0 = p0 / 1000
    q0 = q0 / 1000  # convert to kW/kVar

    # =========================================Yiyun's Notes===========================================#
    # Power injection at substation/feeder head
    # =================================================================================================#

    return [p0, q0, m]


def sub_cost_fun_gradient(x, sub_ref, coeff_sub, sub_measure, m, node_with_pv):
    grad_a = np.matrix([0] * len(x)).transpose()
    grad_b = np.matrix([0] * len(x)).transpose()
    grad_c = np.matrix([0] * len(x)).transpose()

    mr = m.real
    mi = m.imag
    count = 0
    for node in node_with_pv:
        grad_a[count] = -mr[0, int(node)]
        grad_b[count] = -mr[1, int(node)]
        grad_c[count] = -mr[2, int(node)]

        grad_a[count + len(node_with_pv)] = mi[0, int(node)]
        grad_b[count + len(node_with_pv)] = mi[1, int(node)]
        grad_c[count + len(node_with_pv)] = mi[2, int(node)]

        count = count + 1

    res = coeff_sub * (
        (sub_measure[0] - sub_ref[0]) * 1000 * grad_a
        + (sub_measure[1] - sub_ref[1]) * 1000 * grad_b
        + (sub_measure[2] - sub_ref[2]) * 1000 * grad_c
    )
    res = res / 1000

    return res


def projection(x, xmax, xmin):
    for ii in range(len(x)):
        if x.item(ii) > xmax[ii]:
            x[ii] = xmax[ii]
        if x.item(ii) < xmin[ii]:
            x[ii] = xmin[ii]
    return x


class Derms:
    def __init__(
        self, pv_data, controlbus, controlelem, controlelem_limit, sub_node_names, sub_elem_names
    ):
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # PV_name: names of all PVs in the zone
        # PV_size: sizes of all PVs in the zone
        # PV_location: busnames of all PVs in the zone
        # controlbus: names of all controlled nodes
        # sub_node_names: names of all nodes in the zone
        # sub_node_names "include" controlbus
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        self.PV_name = pv_data["pvName"]
        self.PV_location = pv_data["pvLocation"]
        self.PV_size = pv_data["pvSize"]
        self.inverter_size = pv_data["inverterSize"]
        self.control_bus = controlbus

        sub_node_names = [ii.upper() for ii in sub_node_names]
        self.controlbus_index = [
            sub_node_names.index(ii.upper()) for ii in controlbus
        ]  # control bus index in the sub system (number)
        # here
        p_vbus_index = []
        for bus in self.PV_location:
            temp = bus.split(".")
            if len(temp) == 1:
                temp = temp + ["1", "2", "3"]
            for ii in range(len(temp) - 1):
                p_vbus_index.append(sub_node_names.index((temp[0] + "." + temp[ii + 1]).upper()))

        # =========================================Yiyun's Notes===========================================#
        # adding .1 .2 .3 following the number to recognize the three phases.
        # =================================================================================================#
        self.p_vbus_index = p_vbus_index
        self.control_elem = controlelem
        self.controlelem_limit = controlelem_limit
        self.controlelem_index = [
            sub_elem_names.index(ii) for ii in controlelem
        ]  # control branches index in the sub system (number)

    def monitor(self, dss, dss_objects, pv_system_1phase):
        p_vpowers = []
        for pv in pv_system_1phase["Name"].tolist():
            n_phases = dss_objects["Generators"][pv].get_value("phases")
            power = dss_objects["Generators"][pv].get_value("Powers")
            p_vpowers.append([sum(power[::2]) / n_phases, sum(power[1::2]) / n_phases])
        p_vpowers = np.asarray(p_vpowers)

        vmes = []
        for bus in self.control_bus:
            bus_name = bus.split(".")[0].lower()
            vmag = dss_objects["Buses"][bus_name].get_value("puVmagAngle")[::2]
            allbusnode = dss.Bus.nodes()
            phase = bus.split(".")[1]
            index = allbusnode.index(int(phase))
            vnode = vmag[index]
            vmes.append(vnode)

        imes = []
        for elem in self.control_elem:
            class_name = elem.split(".")[0] + "s"
            currents = dss_objects[class_name][elem].get_value("CurrentsMagAng")[::2][
                :3
            ]  # TODO: Why is there a hardcoded [:3] ?
            imes.append(currents)

        return [self.PV_location, p_vpowers, vmes, imes]

    def control(
        self,
        linear_pf_coeff,
        options,
        stepsize,
        mu0,
        vlimit,
        p_vpower,
        imes,
        vmes,
        pv__pmax_forecast,
    ):
        coeff_p = options["coeff_p"]
        coeff_q = options["coeff_q"]

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # linear_PF_coeff is the linear power flow model coefficients for the zone, and linear power flow model
        #                coefficients are the result vector from function "linear_powerflow_model"
        # coeff_p, coeff_q are constant coefficients in PV cost function
        # stepsize is a vector of stepsize constants
        # mu0 is the dual variable from last time step: mu_Vmag_upper0, mu_Vmag_lower0, mu_I0
        # Vlimit is the allowed voltage limit: Vupper and Vlower
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        p_vname = self.PV_name
        npv = len(p_vname)
        x0 = np.zeros(2 * npv)
        for ii in range(npv):
            x0[ii] = -p_vpower[ii][0]  # in kW
            x0[ii + npv] = -p_vpower[ii][1]  # in kVar

        # coeff_V_P = linear_PF_coeff[0]
        # coeff_V_Q = linear_PF_coeff[1]
        # coeff_Vm = linear_PF_coeff[2]
        coeff__vmag_p = linear_pf_coeff[3]
        coeff__vmag_q = linear_pf_coeff[4]
        # coeff_Vmag_k = linear_PF_coeff[5]
        coeff_i_p = linear_pf_coeff[6]
        coeff_i_q = linear_pf_coeff[7]
        # coeff_I_const = linear_PF_coeff[8]
        stepsize_xp = stepsize[0]
        stepsize_xq = stepsize[1]
        stepsize_mu = stepsize[2]
        vupper = vlimit[0]
        vlower = vlimit[1]

        controlbus_index = self.controlbus_index
        p_vbus_index = self.p_vbus_index
        controlelem_index = self.controlelem_index
        pv_inverter_size = self.inverter_size
        imes_limit = self.controlelem_limit

        mu__vmag_upper0 = mu0[0]
        mu__vmag_lower0 = mu0[1]
        mu_i0 = mu0[2]

        p_vcost_fun_gradient = pv_cost_fun_gradient(x0, coeff_p, coeff_q, pv__pmax_forecast)

        vmag_upper_gradient = np.concatenate(
            (
                np.dot(
                    coeff__vmag_p[
                        np.ix_([ii for ii in controlbus_index], [ii for ii in p_vbus_index])
                    ].transpose(),
                    mu__vmag_upper0,
                ),
                np.dot(
                    coeff__vmag_q[
                        np.ix_([ii for ii in controlbus_index], [ii for ii in p_vbus_index])
                    ].transpose(),
                    mu__vmag_upper0,
                ),
            ),
            axis=0,
        )
        vmag_lower_gradient = np.concatenate(
            (
                np.dot(
                    coeff__vmag_p[
                        np.ix_([ii for ii in controlbus_index], [ii for ii in p_vbus_index])
                    ].transpose(),
                    mu__vmag_lower0,
                ),
                np.dot(
                    coeff__vmag_q[
                        np.ix_([ii for ii in controlbus_index], [ii for ii in p_vbus_index])
                    ].transpose(),
                    mu__vmag_lower0,
                ),
            ),
            axis=0,
        )

        vmag_gradient = vmag_upper_gradient - vmag_lower_gradient
        if len(mu_i0) > 0:
            temp_real = mu_i0 * np.array(imes.real)
            temp_imag = mu_i0 * np.array(imes.imag)

            i_gradient_real = np.concatenate(
                (
                    np.dot(
                        coeff_i_p[
                            np.ix_([ii for ii in controlelem_index], [ii for ii in p_vbus_index])
                        ].real.transpose(),
                        temp_real,
                    ),
                    np.dot(
                        coeff_i_q[
                            np.ix_([ii for ii in controlelem_index], [ii for ii in p_vbus_index])
                        ].real.transpose(),
                        temp_real,
                    ),
                ),
                axis=0,
            )
            i_gradient_imag = np.concatenate(
                (
                    np.dot(
                        coeff_i_p[
                            np.ix_([ii for ii in controlelem_index], [ii for ii in p_vbus_index])
                        ].imag.transpose(),
                        temp_imag,
                    ),
                    np.dot(
                        coeff_i_q[
                            np.ix_([ii for ii in controlelem_index], [ii for ii in p_vbus_index])
                        ].imag.transpose(),
                        temp_imag,
                    ),
                ),
                axis=0,
            )
            i_gradient = 2 * i_gradient_real + 2 * i_gradient_imag
        else:
            i_gradient = 0

        gradient = p_vcost_fun_gradient + vmag_gradient + i_gradient / 1000

        # compute x1, mu1
        x1 = np.concatenate(
            [x0[:npv] - stepsize_xp * gradient[:npv], x0[npv:] - stepsize_xq * gradient[npv:]]
        )
        [x1, pmax_all_pv, qmax_all_pv] = project_pv(x1, pv__pmax_forecast, pv_inverter_size)
        x1 = np.array([round(ii, 5) for ii in x1])

        mu__vmag_lower1 = mu__vmag_lower0 + stepsize_mu * (vlower - np.array(vmes))
        mu__vmag_upper1 = mu__vmag_upper0 + stepsize_mu * (np.array(vmes) - vupper)
        mu__vmag_lower1 = project_dualvariable(mu__vmag_lower1)
        mu__vmag_upper1 = project_dualvariable(mu__vmag_upper1)
        if mu_i0:
            mu_i1 = mu_i0 + stepsize_mu / 300 * np.array(
                list(map(lambda x: x[0] * x[0] - x[1] * x[1], zip(imes, imes_limit)))
            )
            mu_i1 = project_dualvariable(mu_i1)
        else:
            mu_i1 = mu_i0
        mu1 = [mu__vmag_upper1, mu__vmag_lower1, mu_i1]
        # =========================================Yiyun's Notes===========================================#
        # Each time of calling DERMS.control, it is a one step update of PV real and reactive power outputs
        # =================================================================================================#

        return [x1, mu1]
