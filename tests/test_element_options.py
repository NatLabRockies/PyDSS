from pydss.element_options import ElementOptions


def test_element_options__list_options():
    options = ElementOptions()
    assert options.is_option_valid("Lines", "Currents", "phase_terminal")
    assert not options.is_option_valid("Lines", "Currents", "bad")


def test_element_options__is_option_valid():
    options = ElementOptions()
    assert options.list_options("Lines", "Currents") == ["phase_terminal"]
    assert options.list_options("Lines", "NormalAmps") == []
