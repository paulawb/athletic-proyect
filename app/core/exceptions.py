class AthleticAnalysisError(Exception):
    """Excepcion base de la aplicacion."""


class InvalidVideoFormatError(AthleticAnalysisError):
    pass


class VideoTooLargeError(AthleticAnalysisError):
    pass


class VideoProcessingError(AthleticAnalysisError):
    pass


class AnalysisNoLongerActiveError(ValueError):
    """El analisis ya no esta en PENDING/PROCESSING: lo eliminaron, se marco
    como fallido por inactividad o ya termino. Quien lo procesa debe parar
    sin volver a escribir su estado. Hereda de ValueError para conservar el
    contrato anterior de update_progress (ValueError si no existe)."""


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
