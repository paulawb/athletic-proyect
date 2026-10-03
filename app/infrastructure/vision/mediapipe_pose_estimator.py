import os

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from app.domain.services.pose_estimator import Keypoint, KeypointName, PoseEstimationResult, PoseEstimator

# Indices fijos del modelo Pose Landmarker de MediaPipe (33 puntos en total;
# tabla publicada por Google, no una constante de la libreria: la API de
# Tasks ya no expone un enum de nombres como la antigua mp.solutions.pose
# .PoseLandmark, asi que mapeamos nosotros mismos los que nos interesan a
# KeypointName -el mismo vocabulario que usa MockPoseEstimator (Fase 5),
# para que BasicMetricsCalculator no tenga que cambiar una linea.
_LANDMARK_INDEX: dict[KeypointName, int] = {
    KeypointName.NOSE: 0,
    KeypointName.LEFT_SHOULDER: 11,
    KeypointName.RIGHT_SHOULDER: 12,
    KeypointName.LEFT_ELBOW: 13,
    KeypointName.RIGHT_ELBOW: 14,
    KeypointName.LEFT_WRIST: 15,
    KeypointName.RIGHT_WRIST: 16,
    KeypointName.LEFT_HIP: 23,
    KeypointName.RIGHT_HIP: 24,
    KeypointName.LEFT_KNEE: 25,
    KeypointName.RIGHT_KNEE: 26,
    KeypointName.LEFT_ANKLE: 27,
    KeypointName.RIGHT_ANKLE: 28,
}


class MediaPipePoseEstimator(PoseEstimator):
    """Primera implementacion real de PoseEstimator (seccion 9), usando el
    modelo Pose Landmarker de MediaPipe.

    Usa la API de Tasks (mediapipe.tasks.python.vision.PoseLandmarker):
    Google retiro la API "Solutions" anterior (mp.solutions.pose.Pose) en
    mediapipe 0.10+, asi que esta es la forma vigente. Traduce los 33
    landmarks normalizados (0..1) del modelo a los KeypointName que
    BasicMetricsCalculator espera, convertidos a pixeles multiplicando por
    el ancho/alto real del cuadro -MockPoseEstimator y esta clase hablan
    exactamente el mismo vocabulario de nombres, por eso ProcessVideoFrames
    y MetricsCalculator no tienen que cambiar una linea al intercambiarlas.

    Requiere el archivo de modelo (.task) descargado localmente:
    ver scripts/download_pose_model.py y MEDIAPIPE_MODEL_PATH en .env.
    """

    def __init__(
        self,
        model_path: str,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"No se encontro el modelo de MediaPipe en '{model_path}'. "
                f"Corre 'python -m scripts.download_pose_model' para descargarlo "
                f"(o ajusta MEDIAPIPE_MODEL_PATH en tu .env)."
            )

        options = mp_vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            min_pose_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)

    def estimate(
        self, frame: np.ndarray, frame_number: int, timestamp_ms: int | None = None
    ) -> PoseEstimationResult:
        height, width = int(frame.shape[0]), int(frame.shape[1])
        # OpenCV entrega los cuadros en BGR; MediaPipe espera RGB (seccion 8).
        rgb_frame = np.ascontiguousarray(frame[:, :, ::-1])
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # VIDEO requiere timestamps en milisegundos, no indices de cuadro.
        # El pipeline recibe el tiempo del video del FrameProcessor.
        result = self._landmarker.detect_for_video(
            mp_image, timestamp_ms if timestamp_ms is not None else frame_number
        )

        if not result.pose_landmarks:
            # Ningun cuerpo detectado en este cuadro (oclusion, fuera de
            # plano, etc.): se devuelve sin puntos. BasicMetricsCalculator ya
            # maneja cuadros sin ciertos keypoints (los salta, no revienta).
            return PoseEstimationResult(frame_number=frame_number, keypoints=[])

        landmarks = result.pose_landmarks[0]  # una sola persona esperada: el atleta en la pista
        keypoints = [
            Keypoint(
                name=name.value,
                x=round(landmarks[index].x * width, 2),
                y=round(landmarks[index].y * height, 2),
                confidence=round(landmarks[index].visibility, 3),
            )
            for name, index in _LANDMARK_INDEX.items()
        ]
        return PoseEstimationResult(frame_number=frame_number, keypoints=keypoints)

    def close(self) -> None:
        self._landmarker.close()
