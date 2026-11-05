import abc


class ControllerAbstract(abc.ABC):

    # Subclasses can override to declare which priorities they handle.
    # Defaults to all priorities for backward compatibility.
    ACTIVE_PRIORITIES = (0, 1, 2)

    def __init__(self, controlledObj, Settings, dssInstance, ElmObjectList, dssSolver):
        """Abstract class CONSTRUCTOR."""
        pass

    @abc.abstractmethod
    def Update(self,  Priority, Time, UpdateResults):
        pass

    @abc.abstractmethod
    def Name(self):
        pass

    @abc.abstractmethod
    def ControlledElement(self):
        pass

    @abc.abstractmethod
    def debugInfo(self):
        pass