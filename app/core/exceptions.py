class AthleticAnalysisError(Exception):
    """Excepcion base de la aplicacion."""


class InvalidVideoFormatError(AthleticAnalysisError):
    pass


class VideoTooLargeError(AthleticAnalysisError):
    pass


class VideoProcessingError(AthleticAnalysisError):
    pass


class AnalysisNotFoundError(AthleticAnalysisError):
    pass


class AthleteNotFoundError(AthleticAnalysisError):
    pass


class TestNotFoundError(AthleticAnalysisError):
    pass


class VideoNotFoundError(AthleticAnalysisError):
    pass


class MetricsNotFoundError(AthleticAnalysisError):
    pass


class InvalidCredentialsError(AthleticAnalysisError):
    pass
