ELEMENT_FIELDS = {
    "Lines": [
        {
            "names": ["Currents", "Powers", "Voltages", "PhaseLosses"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": [
                "SeqVoltages",
                "SeqPowers",
                "SeqCurrents",
                "VoltagesMagAng",
                "CurrentsMagAng",
            ],
            "options": ["phase_terminal", "mag_ang"],
        },
        {
            "names": ["Losses", "NormalAmps"],
            "options": [],
        },
    ],
    "Transformers": [
        {
            "names": ["Currents", "Powers", "Voltages", "PhaseLosses"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": [
                "SeqVoltages",
                "SeqPowers",
                "SeqCurrents",
                "VoltagesMagAng",
                "CurrentsMagAng",
            ],
            "options": ["phase_terminal", "mag_ang"],
        },
        {
            "names": ["taps", "maxtap", "mintap", "numtaps", "kv", "kva"],
            "options": [
                "wdg",
            ],
        },
        {
            "names": ["Losses", "NormalAmps", "tap"],
            "options": [],
        },
    ],
    "Generators": [
        {
            "names": ["Currents", "Powers", "Voltages", "PhaseLosses"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": [
                "SeqVoltages",
                "SeqPowers",
                "SeqCurrents",
                "VoltagesMagAng",
                "CurrentsMagAng",
            ],
            "options": ["phase_terminal", "mag_ang"],
        },
    ],
    "PVSystems": [
        {
            "names": ["Currents", "Powers", "Voltages", "PhaseLosses"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": [
                "SeqVoltages",
                "SeqPowers",
                "SeqCurrents",
                "VoltagesMagAng",
                "CurrentsMagAng",
            ],
            "options": ["phase_terminal", "mag_ang"],
        },
        {
            "names": ["Pmpp"],
            "options": [],
        },
    ],
    "Loads": [
        {
            "names": ["Currents", "Powers", "Voltages", "PhaseLosses"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": [
                "SeqVoltages",
                "SeqPowers",
                "SeqCurrents",
                "VoltagesMagAng",
                "CurrentsMagAng",
            ],
            "options": ["phase_terminal", "mag_ang"],
        },
    ],
    "Storages": [
        {
            "names": ["Currents", "Powers", "Voltages", "PhaseLosses"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": [
                "SeqVoltages",
                "SeqPowers",
                "SeqCurrents",
                "VoltagesMagAng",
                "CurrentsMagAng",
            ],
            "options": ["phase_terminal", "mag_ang"],
        },
    ],
    "Capacitors": [
        {
            "names": ["Currents", "Powers", "Voltages", "PhaseLosses"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": [
                "SeqVoltages",
                "SeqPowers",
                "SeqCurrents",
                "VoltagesMagAng",
                "CurrentsMagAng",
            ],
            "options": ["phase_terminal", "mag_ang"],
        },
        {
            "names": ["states", "open", "close"],
            "options": [],
        },
    ],
    "Meters": [
        {
            "names": ["AllocFactors"],
            "options": [
                "phase_terminal",
            ],
        }
    ],
    "Buses": [
        {
            "names": ["CplxSeqVoltages", "Voc", "Voltages", "puVLL", "PuVoltage"],
            "options": [
                "phase_terminal",
            ],
        },
        {
            "names": ["SeqVoltages", "VMagAngle", "SeqCurrents", "puVmagAngle"],
            "options": ["phase_terminal", "mag_ang"],
        },
        {
            "names": ["Distance"],
            "options": [],
        },
    ],
    "Circuits": [
        {
            "names": ["TotalPower", "LineLosses", "Losses", "SubstationLosses"],
            "options": [],
        }
    ],
}
