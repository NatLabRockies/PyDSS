import numpy as np
import math


def form_yprim(values):
    dimension = int(math.sqrt(len(values) / 2))
    yprim = np.array([[complex(0, 0)] * dimension] * dimension)
    for row in range(dimension):
        for column in range(dimension):
            yprim[row][column] = complex(
                values[dimension * row * 2 + 2 * column],
                values[dimension * row * 2 + 2 * column + 1],
            )
    return yprim


def form_yprim_2(values):
    dimension = int(math.sqrt(len(values) / 2))
    real = np.array(values[0::2]).reshape((dimension, dimension))
    imag = np.array(values[1::2]).reshape((dimension, dimension))
    return real + 1j * imag


def get_yprime_matrix(dss_objects):
    elements = dss_objects["Lines"] + dss_objects["Transformers"]
    n_elements = len(elements)
    np.array([[complex(0, 0)] * 2 * n_elements] * 2 * n_elements)


globals()["form_Yprim"] = form_yprim
globals()["form_Yprim_2"] = form_yprim_2
globals()["get_Yprime_Matrix"] = get_yprime_matrix
