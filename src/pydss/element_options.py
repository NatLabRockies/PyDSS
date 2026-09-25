"""Stores the options available for element classes and properties."""

from loguru import logger

from pydss.element_fields import ELEMENT_FIELDS


class ElementOptions:
    """Stores the options available for element classes and properties."""

    def __init__(self, data=None):
        if data is None:
            data = ELEMENT_FIELDS
        self._element_classes = {}
        for elem_class, option_combos in data.items():
            options = {}
            for option_combo in option_combos:
                for prop in option_combo["names"]:
                    assert prop not in options
                    options[prop] = option_combo["options"]
            self._element_classes[elem_class] = options

    def is_option_valid(self, element_class, prop, option):
        """Returns True if the option is valid for the class and property.

        Returns
        -------
        True

        """
        return option in self.list_options(element_class, prop)

    def list_options(self, element_class, prop):
        """List the options available for a class and property.

        Returns
        -------
        list

        """
        if element_class not in self._element_classes:
            logger.debug("class=%s is not stored", element_class)
            return []
        if prop not in self._element_classes[element_class]:
            logger.debug("class=%s property=%s is not stored", element_class, prop)
            return []
        return self._element_classes[element_class][prop][:]
