class EpicBoxError(Exception):
    """The base class for custom exceptions raised by epicboxie."""


class DockerError(EpicBoxError):
    """An error occurred with the underlying docker system."""
