import toml
import sys
import os
import typer


def run_pydss(
    pydss_path: str = typer.Option(r"C:\Users\alatif\Desktop\pydss_test"),
    sim_path: str = typer.Option(
        r"C:\Users\alatif\Desktop\pydss_test\examples\external_interfaces\Python_example"
    ),
    sim_file: str = typer.Option(r"simulation.toml"),
):
    sys.path.append(pydss_path)
    sys.path.append(os.path.join(pydss_path, "pydss"))
    file1 = open(os.path.join(sim_path, sim_file), "r")
    text = file1.read()
    sim_args = toml.loads(text)
    from pydss import instance

    a = instance()
    dss_instance = a.create_dss_instance(sim_args)
    for t in range(5):
        x = {"Load.mpx000635970": {"kW": 7.28}}
        results = dss_instance.RunStep(t, x)
        print(results["Load.mpx000635970"]["Powers"]["E"]["value"])
    dss_instance.ResultContainer.ExportResults()
    dss_instance.DeleteInstance()
    del a


if __name__ == "__main__":
    typer.run(run_pydss)
