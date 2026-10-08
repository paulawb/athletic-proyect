# Athletic Analysis — Backend

Backend del trabajo de grado *"Sistema de análisis de vídeo basado en drones
autónomos para la evaluación de variables de desempeño en carreras de
velocidad"*. El proyecto usa FastAPI, PostgreSQL, autenticación JWT y procesa
video con OpenCV y MediaPipe para estimar pose y calcular métricas.

## Arquitectura

Arquitectura Limpia en 4 capas, con las dependencias apuntando siempre hacia
adentro:

```
presentation  →  application (casos de uso)  →  domain  ←  infrastructure
```

- **`app/domain/`** — entidades (dataclasses puras) e interfaces
  (`ABC`) de repositorios y servicios. No importa FastAPI ni SQLAlchemy.
- **`app/application/`** — casos de uso: orquestan el dominio a través de
  las interfaces. No conocen SQLAlchemy ni FastAPI directamente.
- **`app/infrastructure/`** — implementaciones concretas: modelos y
  repositorios SQLAlchemy, `BackgroundTasksRunner`, etc.
- **`app/presentation/`** — routers de FastAPI. Traducen HTTP a llamadas al
  caso de uso correspondiente; no contienen lógica de negocio.
- **`app/core/`** — configuración, conexión a base de datos, logging,
  excepciones y utilidades de seguridad (hash de contraseñas, JWT) sin
  acoplamiento a un framework.

Los atletas pertenecen a la cuenta que los crea; las pruebas, videos y
análisis se consultan a través de ese propietario. Los registros anteriores
a esta separación se conservan sin propietario y no aparecen en las cuentas.
Los informes generados persisten en PostgreSQL; videos y archivos subidos a
la biblioteca usan el almacenamiento local configurado para el servicio.

## Qué incluye

**Fase 1 — Arquitectura, FastAPI, PostgreSQL, auth**
- Estructura completa del proyecto y las interfaces de dominio para todas
  las entidades del modelo de datos (`Athlete`, `Test`, `Video`, `Analysis`,
  `Metrics`, `FrameMetrics`), listas para implementarse en las fases 4-7.
- Conexión async a PostgreSQL (SQLAlchemy 2.x + asyncpg) y migraciones con
  Alembic.
- Autenticación JWT (`POST /api/v1/auth/token`, `GET /api/v1/auth/me`) con
  hashing de contraseñas vía bcrypt.
- `GET /health` para verificar que el servicio está arriba.

**Fase 2 — CRUD de atletas y pruebas**
- `POST /api/v1/atletas`, `GET /api/v1/atletas`, `GET /api/v1/atletas/{id}`.
- `POST /api/v1/pruebas`, `GET /api/v1/pruebas` (con filtro opcional
  `?athlete_id=`). `CreateTest` valida que el atleta exista antes de crear
  la prueba.

**Fase 3 — Carga y almacenamiento de video**
- `POST /api/v1/pruebas/{test_id}/video` — sube el video de una prueba.
  Escribe a disco en streaming (1 MB por lectura, nunca carga el archivo
  completo en memoria) y aborta si se supera `MAX_VIDEO_SIZE_MB` a mitad
  de la escritura, sin terminar de guardar un archivo que ya sabemos que
  se va a rechazar.
- Validaciones: extensión (`.mp4`/`.mov`), tipo de contenido, archivo
  vacío y video corrupto (se verifica abriéndolo con OpenCV y confirmando
  que tiene al menos un fotograma legible).
- Al validar, extrae y persiste los metadatos reales del video: `fps`,
  `duración`, `resolución` y `total de fotogramas`.
- `GET /api/v1/pruebas/{test_id}/video` y `GET /api/v1/videos/{video_id}`
  para consultar lo cargado.
- `LocalVideoStorage` implementa la interfaz `VideoStorage` guardando en
  `storage/videos/`; `S3VideoStorage` podrá reemplazarla después sin tocar
  el caso de uso. `OpenCVFrameProcessor.get_video_metadata()` es lo que se
  usa aquí; `iterate_frames()` (mismo archivo) queda listo para la Fase 4.
- Todos los endpoints nuevos requieren el token JWT de la Fase 1.
- Migración `0004` (videos), encadenada a la `0003`.

Pruebas unitarias con repositorios/almacenamiento/estimador en memoria
(seguridad, autenticación, atletas, pruebas y carga de video) — ninguna
requiere Postgres ni `cv2` instalado; más la prueba de integración del
health check.

**Fase 4 — Procesamiento cuadro por cuadro con OpenCV**
- Recorre el video con `FrameProcessor.iterate_frames()`, cuadro por
  cuadro y sin cargarlo completo en memoria (sección 8). Reporta avance
  (`processed_frames`/`total_frames`/`progress_percentage`) cada 10
  cuadros para no golpear la base de datos en cada uno.
- `GET /api/v1/analisis` y `GET /api/v1/analisis/{id}` para listar y
  consultar el estado (`PENDING → PROCESSING → COMPLETED/FAILED`). Si un
  cuadro falla a mitad de camino, el análisis queda `FAILED` con
  `error_message` y conserva cuántos cuadros sí se procesaron.
- En esta fase corría de forma síncrona dentro del request; la Fase 8 lo
  mueve detrás de `TaskRunner` (ver más abajo) sin tocar la lógica del
  recorrido cuadro por cuadro en sí.
- Migración `0005` (analyses), encadenada a la `0004`.

**Fase 5 — MockPoseEstimator**
- `MockPoseEstimator` implementa `PoseEstimator` (sección 9): no analiza el
  contenido real del cuadro, devuelve un esqueleto de 9 puntos (nariz,
  hombros, caderas, rodillas, tobillos) que oscila según el número de
  cuadro, para que `MetricsCalculator` (Fase 6) tenga datos con forma de
  ciclo de carrera en vez de puntos fijos sin sentido.
- `ProcessVideoFrames` ahora llama a `pose_estimator.estimate(frame, frame_number)`
  dentro del mismo recorrido cuadro por cuadro de la Fase 4, y deja los
  resultados disponibles en `use_case.pose_results` — livianos comparado
  con los cuadros de video en sí, así que acumularlos en memoria durante
  el recorrido no repite el problema que `iterate_frames()` evita.
- Deliberadamente **no** calcula ninguna métrica todavía con esos
  resultados (Fase 6) ni los persiste (Fase 7): esta fase solo prueba que
  la estimación de pose está conectada al pipeline.
- `MediaPipePoseEstimator`/`YOLOPoseEstimator` (Fase 9) reemplazarán a
  `MockPoseEstimator` después sin que `ProcessVideoFrames` cambie.

**Fase 6 — MetricsCalculator con datos simulados**
- `BasicMetricsCalculator` implementa `MetricsCalculator` (sección 10) con
  fórmulas reales de cinemática (desplazamiento/tiempo), corriendo sobre
  los datos simulados de `MockPoseEstimator`:
  - **Velocidad** (promedio/máxima): sigue el punto medio de las caderas
    cuadro a cuadro, lo convierte de píxeles a metros y divide por el
    tiempo entre cuadros.
  - **Cadencia**: cuenta los apoyos (máximos locales de la altura del
    tobillo en píxeles — recuerda que el eje de la imagen crece hacia
    abajo) y los divide por la duración total.
  - **Longitud de zancada**: distancia recorrida por la cadera entre dos
    apoyos consecutivos.
  - **Postura**: heurística geométrica de alineación nariz-hombros-cadera
    (no un modelo biomecánico real todavía — sección 10 lo deja para la
    Fase 10).
- `PoseEstimationResult` ahora incluye `timestamp` (lo adjunta
  `ProcessVideoFrames` con el tiempo real que ya traía
  `FrameProcessor.iterate_frames()`), porque calcular velocidad real
  requiere desplazamiento **y** tiempo, no solo posición.
- Calibración (sección 11) simplificada: `pixels_per_meter = ancho_del_video / distancia_de_la_prueba`,
  asumiendo un plano fijo sin corrección de perspectiva. No es una
  calibración real — eso, junto con el cálculo biomecánico real, es la
  Fase 10.
- `ProcessVideoFrames` calcula las métricas al terminar el recorrido y las
  deja en `use_case.metrics_result`, además de persistirlas (ver Fase 7).
- Pruebas con datos sintéticos controlados (velocidad constante conocida,
  oscilación de tobillo con apoyos predecibles, alineación perfecta vs.
  desalineada) para verificar las fórmulas en sí, además de las pruebas de
  integración del pipeline completo.

**Fase 7 — Persistencia de métricas**
- `MetricsCalculator` ahora tiene un segundo método, `calculate_frame_metrics()`,
  que devuelve el mismo cálculo desglosado cuadro por cuadro (posición,
  velocidad instantánea, fase de zancada, postura) en vez del agregado —
  necesario para poblar `FRAME_METRICS` (sección 6), no solo `METRICS`.
  `BasicMetricsCalculator` comparte los mismos helpers internos entre
  ambos métodos para no duplicar fórmulas.
- `ProcessVideoFrames` persiste `Metrics` (una fila por análisis) y
  `FrameMetrics` (una fila por cuadro, insertadas por lote con
  `bulk_create` — nunca fila por fila) justo después de calcularlas.
- `GET /api/v1/analisis/{id}/metricas` (sección 14-15): devuelve las
  métricas ya persistidas. 404 si el análisis no existe, o si existe pero
  todavía no tiene métricas (sigue `PENDING`/`PROCESSING`, o terminó
  `FAILED`).
- Decisión que tomé sin preguntarte, por ser de bajo riesgo: no expuse un
  endpoint para leer `FrameMetrics` todavía (no estaba en tu lista de
  endpoints); queda persistido y listo para cuando la Fase 11
  (reportes y gráficos) lo necesite.

**Fase 8 — Procesamiento asíncrono**
- `POST /api/v1/analisis` (body: `{"video_id": <id>}`) ahora responde
  **de inmediato** (`202 Accepted`, sección 16) con
  `{"analysis_id": ..., "status": "PENDING", "message": "..."}`, en vez de
  esperar a que termine todo el procesamiento (secciones 12-13). Para ver
  el avance hay que sondear `GET /api/v1/analisis/{id}` hasta que
  `status` sea `COMPLETED` o `FAILED`, y entonces pedir
  `GET /api/v1/analisis/{id}/metricas`.
- Partí `ProcessVideoFrames` en dos casos de uso: `CreateAnalysis` (valida
  el video y crea el `Analysis` en `PENDING` — instantáneo, corre dentro
  del request) y `ProcessVideoFrames` (el recorrido cuadro por cuadro
  completo — se encola con `TaskRunner.enqueue()` y corre después de
  responder).
- `BackgroundTasksRunner` (ya definida desde la Fase 1) es la
  implementación académica con `fastapi.BackgroundTasks`. Detalle
  importante de FastAPI que dejé documentado en el propio router: las
  dependencias con `yield` (como la sesión de base de datos) se cierran
  **después** de que las tareas en segundo plano terminan, no antes — por
  eso la misma sesión se puede reutilizar de forma segura dentro de la
  tarea encolada.
- Encontré (y resolví) la limitación que la Fase 1 ya había señalado:
  "una tarea CPU-bound larga puede degradar la capacidad de respuesta de
  otras peticiones si no se delega a un threadpool". `ProcessVideoFrames`
  ahora avanza el iterador de cuadros con `asyncio.to_thread()`, así que
  la lectura bloqueante de OpenCV no monopoliza el único hilo del event
  loop mientras procesa un video largo. Sigue siendo el mismo proceso que
  la API (no escala a varios workers, no sobrevive un reinicio, no tiene
  reintentos) — eso solo lo resuelve una migración real a Celery/RQ,
  fuera del alcance de esta fase.
- `AnalysisResponseDTO` (el de `GET`) ya no incluye `metrics_preview`:
  ya no tiene sentido con el flujo asíncrono — el dato real y siempre
  correcto es `GET /api/v1/analisis/{id}/metricas`.

**Fase 9 — Integración de modelo real de pose**
- `MediaPipePoseEstimator` implementa `PoseEstimator` (sección 9) con el
  modelo **Pose Landmarker** de MediaPipe — un detector real, no
  simulado. Usa la API de **Tasks** (`mediapipe.tasks.python.vision`);
  Google retiró la API "Solutions" anterior (`mp.solutions.pose.Pose`) en
  mediapipe 0.10+, así que verifiqué la sintaxis vigente antes de escribir
  el código en vez de asumir la que tenía en memoria.
- Nuevo contrato compartido en el dominio: `KeypointName` (enum) reemplaza
  los strings sueltos ("left_hip", etc.) que antes vivían duplicados en
  `MockPoseEstimator` y `BasicMetricsCalculator`. Ahora ambos —y
  `MediaPipePoseEstimator`— importan el mismo vocabulario, así que un
  typo en una implementación nueva ya no podría romper el cálculo de
  métricas en silencio.
- `PoseEstimator` ganó un método `close()` con implementación por
  defecto (no-op). `MediaPipePoseEstimator` lo sobreescribe para liberar
  el modelo correctamente; `ProcessVideoFrames` lo llama siempre en un
  `finally`, sin saber cuál implementación concreta recibió.
- Como un modelo real sí puede tardar de verdad por cuadro (a diferencia
  del Mock), `ProcessVideoFrames` ahora delega también la llamada a
  `pose_estimator.estimate()` a `asyncio.to_thread()` — el mismo
  tratamiento que ya le dábamos a la lectura de OpenCV desde la Fase 8.
- `POSE_ESTIMATOR_BACKEND` (`.env`) usa `mediapipe` por defecto para
  detectar personas en el video real. `mock` solo sirve para pruebas
  visuales y genera puntos artificiales; no debe usarse para analizar
  atletas.
- La variante `full` de Pose Landmarker es la predeterminada para priorizar
  la detección frente a la rapidez de `lite`. MediaPipe descarta puntos con
  confianza menor a `0.5` y poses sin una geometría coherente de torso y
  piernas; `MEDIAPIPE_MIN_PRESENCE_CONFIDENCE` controla el umbral global
  (por defecto `0.65`) para reducir falsos positivos.
- El modelo (`.task`, unos MB) no se versiona: `scripts/download_pose_model.py`
  lo descarga a `MEDIAPIPE_MODEL_PATH`. `MediaPipePoseEstimator` da un
  error claro si falta, en vez de un traceback críptico de MediaPipe.
- El proyecto usa el modelo preentrenado publicado por MediaPipe; no es un
  modelo entrenado específicamente con los videos de esta tesis. La calidad
  depende del encuadre, iluminación, resolución, oclusiones y perspectiva.
- Decisión de privacidad que tomé sin preguntarte: fijé `mediapipe==0.10.21`
  en vez de una versión más reciente, porque versiones posteriores
  agregaron telemetría hacia servidores de Google. Dado que este sistema
  procesa video de atletas —algunos menores, según las categorías de tus
  maquetas—, prefiero no introducir esas llamadas de red sin que lo
  decidas explícitamente. Si no te preocupa, podés subir de versión.
- `Dockerfile` y `docker-compose.yml` actualizados: librerías de sistema
  que MediaPipe suele necesitar sobre Debian "slim", y un volumen para
  `models/` igual que ya existía para `storage/`.

**Fase 10 — Cálculo real de métricas biomecánicas y calibración real**
- Cambio de diseño en el dominio: `CoordinateCalibrator.pixel_to_world()`
  ya no recibe un `CameraCalibration` (dos escalares) en cada llamada —
  ahora es *stateful*: cada implementación calcula su transformación una
  sola vez en el constructor (necesario para una homografía real, que no
  cabe en dos números). `MetricsCalculator.calculate()` recibe el
  calibrador en vez del valor de calibración.
- `LinearCoordinateCalibrator`: formaliza como implementación real de
  `CoordinateCalibrator` la escala lineal simple que ya usábamos desde la
  Fase 6 (correcta solo si la cámara mira perpendicular al suelo).
- `HomographyCoordinateCalibrator` (nuevo, sección 11): usa
  `cv2.getPerspectiveTransform`/`cv2.perspectiveTransform` con 4 puntos de
  referencia — corrige perspectiva de verdad, a diferencia de la escala
  lineal. Sin puntos reales de una toma específica todavía (eso requeriría
  una forma de marcarlos, manual o con marcadores físicos — ninguna de las
  dos entra en esta fase), `from_frame_corners()` construye uno por
  defecto asumiendo que el cuadro completo es la vista de un rectángulo de
  `distancia_de_la_prueba × ancho_de_carril` — el mismo supuesto
  simplificado de siempre, pero corriendo sobre el mecanismo correcto:
  en cuanto haya puntos reales, mejora la precisión sin tocar
  `MetricsCalculator` ni `ProcessVideoFrames`.
- `BiomechanicalMetricsCalculator` (nuevo): mejora las dos fórmulas que en
  `BasicMetricsCalculator` (Fase 6) eran heurísticas simples:
  - **Postura**: en vez de solo alineación horizontal, calcula el ángulo
    real de inclinación del tronco (vector cadera→hombro contra la
    vertical) y lo compara contra ~45°, la referencia general de
    literatura de entrenamiento para la fase de impulso de una salida de
    tacos. Se mide en píxeles a propósito, no en metros — es una medida de
    *ángulo* (invariante a escala), y solo tiene sentido si la cámara
    tiene un componente lateral sobre el atleta, un supuesto distinto (y
    compatible) del que usa `CoordinateCalibrator` para la distancia a lo
    largo de la pista.
  - **Cadencia/zancada**: detecta apoyos mediante el cruce por cero de la
    velocidad vertical del tobillo (positiva a negativa), una técnica
    estándar de detección de eventos de marcha, más robusta a ruido
    puntual que comparar 3 posiciones consecutivas (Fase 6).
  - Ninguna de las dos es un modelo biomecánico certificado ni reemplaza
    una evaluación profesional — están documentadas como heurísticas
    razonables, no como verdad clínica.
- `METRICS_CALCULATOR_BACKEND` (`basic`/`biomechanical`) y
  `CALIBRATION_BACKEND` (`linear`/`homography`) en `.env` eligen la
  implementación sin tocar código, mismo patrón que
  `POSE_ESTIMATOR_BACKEND` desde la Fase 9.
- `ProcessVideoFrames` ahora recibe una *fábrica* de calibrador
  (`CalibratorFactory`), no una instancia: el calibrador depende de datos
  propios del video (ancho/alto) y la prueba (distancia), que solo se
  conocen dentro del caso de uso — la fábrica la arma el router, que sí
  conoce las implementaciones concretas de infraestructura.

**Fase 11 — Reportes y gráficos**
- `GET /api/v1/analisis/{id}/reporte` (sección 23): devuelve un PDF
  descargable con atleta, fecha, video, la tabla de métricas, un **gráfico
  real de velocidad durante la prueba** (a partir de `FrameMetrics`) y,
  si el atleta tiene pruebas anteriores completadas, una tabla y un
  gráfico de **tendencia de velocidad promedio** entre pruebas. Mismo
  criterio 404 que `/metricas`: si el análisis no existe o todavía no
  tiene métricas.
- Nuevo puerto `ReportGenerator` (dominio) + `PdfReportGenerator`
  (infraestructura, con `reportlab` para el documento y `matplotlib`
  para los gráficos, incrustados como imagen). La sección 23 permitía
  dejar PDF para después si complicaba la primera versión; llegados a
  la Fase 11, con `Metrics` y `FrameMetrics` ya persistidos desde la
  Fase 7, se implementa completo.
- `GenerateAnalysisReport` (nuevo caso de uso) arma los datos del informe
  cruzando `Analysis` → `Video` → `Test` → `Athlete`, y arma la
  comparación buscando, para cada prueba anterior del mismo atleta, su
  análisis completado más reciente y sus métricas — una prueba anterior
  sin video, sin análisis completado o sin métricas simplemente no aporta
  un punto de comparación (no es un error).
- Los informes PDF, Excel y CSV se generan con los registros que pertenecen
  a la cuenta autenticada. Sus archivos quedan guardados en PostgreSQL para
  que se puedan volver a descargar aunque Render reinicie el servicio. La
  interfaz usa `GET /api/v1/reports`, `POST /api/v1/reports/generate` y las
  rutas de descarga/eliminación de informes.
- `AnalysisRepository` ganó `list_by_video_id()`, necesario para encontrar
  el análisis más reciente de una prueba anterior.

**Ajustes de cuentas y gestión**
- La migración `0014` asocia atletas nuevos con la cuenta que los crea; las
  consultas de atletas, pruebas, videos, análisis, métricas y exportaciones
  respetan ese propietario. Los registros previos sin propietario se
  conservan, pero no se muestran en las cuentas.
- El registro solo admite el rol docente. Las cuentas existentes con rol
  estudiante se convierten a docente al ejecutar la migración.
- Los informes generados pertenecen a su cuenta y se guardan en PostgreSQL.
  Los recursos y referencias de la Biblioteca continúan siendo compartidos
  entre cuentas autenticadas; los archivos subidos a la Biblioteca usan
  almacenamiento local y pueden requerir almacenamiento persistente para
  sobrevivir reinicios de Render.
- Se retiró la sección y las rutas de configuración institucional. La sesión
  se cierra automáticamente al expirar el token o cuando la API responde 401.
  Al ejecutar `0014`, también se eliminan las configuraciones institucionales
  antiguas de la tabla `settings`.

**Lo que NO incluye todavía**: migración a Celery/RQ real ni una forma de
marcar puntos de calibración reales sobre una toma específica. Las tareas
de video siguen ejecutándose dentro del proceso del backend y el cálculo
de métricas sigue siendo una aproximación 2D, no una evaluación clínica.

## Cómo correrlo

### Con Docker (recomendado)

```bash
cp .env.example .env
# edita .env y define un JWT_SECRET_KEY real
docker compose up --build
```

La API queda en `http://localhost:8000` y la documentación interactiva en
`http://localhost:8000/docs` (generada automáticamente por FastAPI/OpenAPI).

Corre las migraciones dentro del contenedor:

```bash
docker compose exec backend alembic upgrade head
```

Crea el primer usuario desde la opción «Crear cuenta» de la pantalla de acceso.
También puedes crear usuarios desde el servidor:

```bash
docker compose exec backend python -m scripts.create_admin \
  entrenador@institucion.edu "Contrasena123" "Nombre Apellido"
```

Para usar el modelo real de pose en vez del simulado (Fase 9), descarga el
modelo y cambia una variable de entorno:

```bash
docker compose exec backend python -m scripts.download_pose_model full
# .env ya configura POSE_ESTIMATOR_BACKEND=mediapipe
docker compose restart backend
```

### Local (sin Docker)

Requiere Python 3.12+ y un PostgreSQL corriendo.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ajusta DATABASE_URL y JWT_SECRET_KEY
alembic upgrade head
python -m scripts.create_admin entrenador@institucion.edu "Contrasena123" "Nombre Apellido"
uvicorn app.main:app --reload
```

### Interfaz web

La aplicación React se ejecuta por separado del backend. Primero aplica la
migración nueva (`alembic upgrade head`) y deja la API disponible en el puerto
8000. Luego, en otra terminal:

```bash
cd frontend
npm install
npm run dev
```

Abre `http://127.0.0.1:5173`, crea una cuenta desde la pantalla de acceso o
inicia sesión con una cuenta existente.
La aplicación web y la API deben permanecer ejecutándose en sus respectivas
terminales. También se permite `http://localhost:5173` para acceder a la web.
Copia `frontend/.env.example` a `frontend/.env.local` si quieres configurar
otra dirección para la API. Ese archivo local está excluido de Git.

### Instalar en un celular (PWA)

La interfaz se puede instalar desde el navegador del celular como una PWA,
sin Play Store ni instalar un APK. Para publicarla o instalarla en otro
dispositivo, necesita una dirección HTTPS pública; `127.0.0.1` solo apunta al
propio celular y no sirve para conectarse al backend de tu computador.

Antes de generar la versión pública, configura la URL HTTPS de la API y crea
el paquete web:

```powershell
cd frontend
$env:VITE_API_URL = "https://api.tu-dominio.com"
npm run build
```

Publica el contenido de `frontend/dist` en un servicio web HTTPS con soporte
para aplicaciones SPA (las rutas deben devolver `index.html`). Configura la
API para permitir mediante CORS el origen HTTPS de la aplicación. No publiques
la app mientras `VITE_API_URL` apunte a `127.0.0.1`.

- **Android:** abre la dirección HTTPS en Chrome y elige «Instalar aplicación»
  o «Añadir a pantalla de inicio».
- **iPhone/iPad:** abre la dirección HTTPS en Safari, toca Compartir y elige
  «Añadir a pantalla de inicio».

La PWA guarda en caché solo el shell estático para abrir la interfaz; no guarda
en caché respuestas privadas de la API ni videos. Para iniciar sesión y
procesar videos se necesita conexión y un backend público activo. El backend,
PostgreSQL, almacenamiento persistente de videos y modelo de pose también
deben desplegarse en un servidor; publicar solo `frontend/dist` no basta.
En Android, Capacitor sirve el frontend desde `https://localhost`; ese origen
debe estar permitido en `CORS_ORIGINS` del backend para que el APK pueda llamar
a la API.

### APK instalable en Android

El proyecto incluye un contenedor Android con Capacitor. El APK contiene la
interfaz, pero **no** incluye la API ni la base de datos: el teléfono necesita
internet y una URL HTTPS pública para usar todas las funciones. Primero
despliega el backend (por ejemplo, con el Blueprint de Render) y ten a mano la
URL pública que Render asigne al servicio.

La forma más sencilla de obtener el APK es usar el flujo **Crear APK Android**
de GitHub Actions. Publica primero estos cambios en GitHub; luego abre la
pestaña **Actions**, elige **Crear APK Android**, pulsa **Run workflow** y
escribe la URL HTTPS pública cuando se solicite. Al terminar, descarga
`athletic-analysis-android-apk` en **Artifacts**. El archivo estará disponible
durante 7 días.

También se puede compilar localmente. En Windows, instala Android Studio y sus
componentes Android SDK. Después, en PowerShell:

```powershell
cd frontend
npm install
$env:VITE_API_URL = "https://tu-servicio.onrender.com"
npm run android:sync
npm run android:open
```

En Android Studio, espera la sincronización de Gradle y selecciona **Build >
Build Bundle(s) / APK(s) > Build APK(s)**. El APK de prueba queda en
`frontend/android/app/build/outputs/apk/debug/app-debug.apk`. Copia ese archivo
al celular Android e instálalo; el teléfono puede pedir autorización para
instalar aplicaciones procedentes de esa fuente. Este APK de depuración sirve
para pruebas y sustentación, no es una versión firmada de distribución
comercial. Cada vez que cambie la URL o el frontend, vuelve a compilar el APK
con la URL actualizada.

### Despliegue integrado en Render

El archivo `render.yaml` define una API que también sirve la interfaz compilada
en el mismo dominio HTTPS. Así el celular usa una sola dirección para la PWA y
la API. La configuración actual es una **demo gratuita temporal**: no incluye
disco persistente, guarda videos y el modelo en almacenamiento temporal y limita
la carga a 100 MB. Los videos pueden desaparecer al reiniciarse, suspenderse o
desplegarse el servicio.

Render suspende el servicio web gratuito tras 15 minutos sin tráfico y puede
tardar alrededor de un minuto en volver a responder. PostgreSQL gratuito tiene
un límite de 1 GB y expira a los 30 días. Hay 14 días adicionales para
actualizarlo; después Render elimina la base y sus datos. No tiene copias de
seguridad.
El servicio web gratuito tiene 512 MB de RAM, por lo que el procesamiento de
video con MediaPipe puede reiniciarse si supera la memoria disponible. Esta
configuración sirve para probar la interfaz y el flujo, no para conservar
información ni para uso institucional.

Para un despliegue de uso continuo se necesitará un plan de pago y almacenamiento
persistente. Revisa los precios y las condiciones actuales de Render antes de
crear recursos o agregar un método de pago.

Render necesita que el código esté en un repositorio GitHub conectado a la
cuenta. Esta carpeta local no se publica automáticamente. Cuando el repositorio
esté disponible, en Render elige **New + > Blueprint**, conecta el repositorio
y confirma los recursos de `render.yaml`. El primer arranque descarga el modelo
de pose y aplica las migraciones de la base de datos. El modelo se descargará
de nuevo cuando el almacenamiento temporal se pierda. Luego abre la URL HTTPS
que Render muestra para el servicio y usa las instrucciones de instalación
anteriores en cada celular. Antes de cargar datos reales, ten en cuenta los
límites y la caducidad de la demo gratuita descritos arriba.

Para este despliegue, Docker compila la web junto con la API. `.dockerignore`
excluye `.env`, videos locales, modelos y dependencias locales: no subas secretos
ni videos de atletas al repositorio. La base Render se crea vacía; los usuarios
y datos de tu PostgreSQL local no se copian automáticamente.

El registro valida formato de correo y teléfono, crea la cuenta y abre la
sesión inmediatamente. No se envían códigos SMS ni enlaces de confirmación.
Los cargos disponibles son `Docente` y `Estudiante`.

La API agrega `GET /api/v1/dashboard/stats`, reportes en
`/api/v1/reports`, recursos en `/api/v1/library/resources` y preferencias en
`/api/v1/settings`. Para recursos cargados e informes generados, los archivos se
guardan en `storage/biblioteca` y `storage/informes`.

## Pruebas

Las pruebas unitarias no requieren base de datos (usan un repositorio en
memoria y utilidades puras). La prueba de integración del health check
tampoco toca Postgres.

```bash
pip install -r requirements.txt
pytest
```

## Migraciones (Alembic)

```bash
alembic revision -m "descripcion del cambio"   # crea una migración nueva
alembic upgrade head                            # aplica migraciones pendientes
```

## Variables de entorno

Ver `.env.example`. Ninguna se hardcodea en el código; `Settings`
(`app/core/config.py`) las carga desde el entorno o `.env`.

## Roadmap (fases 1-12, todas completas)

| Fase | Alcance | ¿Dónde está? |
|------|---------|--------------|
| 1 | Arquitectura limpia 4 capas + FastAPI + PostgreSQL async | `app/core`, `app/domain`, `app/infrastructure`, `app/presentation` |
| 2 | Modelos de BD y Alembic (users, athletes, tests, videos, analyses, metrics+frame_metrics) | `app/infrastructure/database/models/`, `alembic/versions/0001` a `0007` |
| 3 | Almacenamiento local de videos (streaming, validación de extensión/tamaño) | `app/infrastructure/video/local_video_storage.py`, `app/infrastructure/video/opencv_frame_processor.py` |
| 4 | JWT + bcrypt (auth) | `app/core/security.py`, `app/presentation/api/v1/routes/auth.py` |
| 5 | CRUD atletas y pruebas | `app/presentation/api/v1/routes/atletas.py`, `pruebas.py` |
| 6 | Pipeline de análisis: pose estimation + métricas básicas + calibrador lineal | `app/domain/services/`, `app/infrastructure/vision/`, `app/infrastructure/metrics/` |
| 7 | Persistencia de métricas y frame_metrics (bulk insert) | `app/infrastructure/database/repositories/metrics_repository_impl.py`, `frame_metrics_repository_impl.py` |
| 8 | Análisis asíncrono (202 Accepted + polling de progreso) | `app/presentation/api/v1/routes/analisis.py`, `app/infrastructure/tasks/background_tasks_runner.py` |
| 9 | Backends configurables de pose estimator (mock/mediapipe) | `POSE_ESTIMATOR_BACKEND` en `.env` |
| 10 | Calibrador de homografía + métricas biomecánicas | `HomographyCoordinateCalibrator`, `BiomechanicalMetricsCalculator` |
| 11 | Informe en PDF con reportlab + gráficos matplotlib | `app/infrastructure/reports/pdf_report_generator.py`, `GenerateAnalysisReport` |
| 12 | **Optimización y pruebas de carga** (esta fase) | Ver abajo |

## Fase 12: optimización y pruebas de carga

### Optimizaciones aplicadas

1. **Connection pool** (`app/core/database.py`): `pool_size=10`, `max_overflow=20`,
   `pool_timeout=30`, `pool_pre_ping=True`, `pool_recycle=3600`. Evita crear/cerrar
   conexiones por cada request.

2. **Índices en BD** (migración `0007`): `ix_analyses_status`,
   `ix_analyses_video_completed`, `ix_analyses_completed_at`. Aceleran el
   listado general, el polling de progreso y la consulta del informe
   ("análisis completado más reciente de un video").

3. **`update_progress` con RETURNING** (`analysis_repository_impl.py`):
   el UPDATE y el SELECT del registro actualizado se combinan en una sola
   query. La versión anterior hacía `session.get()` (SELECT) antes del UPDATE.

4. **`update_progress_batch`**: UPDATE liviano (solo `processed_frames`,
   sin SELECT ni RETURNING). `ProcessVideoFrames` lo llama cada 10 cuadros
   para reportar progreso sin golpear la BD con una query pesada por cada
   cuadro. El cambio de estado a COMPLETED/FAILED llega por `update_progress`
   al terminar.

5. **Endpoint combinado** `POST /api/v1/analisis/procesar-video`
   (Fase 12): sube el video y encola el análisis en una sola request,
   evitando dos round-trips y dos subidas de archivo.

### Pruebas de carga (Locust)

Archivo: `locustfile.py`. Define dos clases de usuario:
- `HealthUser`: solo `GET /health` (capa de FastAPI/uvicorn).
- `AnalystUser`: autenticado, mezcla listados, polling, upload y enqueue
  (incluido el endpoint combinado).

Ejecución:
```bash
locust -f locustfile.py --host=http://localhost:8000 --users 10 --spawn-rate 2 -t 60s
```
Las credenciales del admin se leen de `LOCUST_ADMIN_EMAIL` /
`LOCUST_ADMIN_PASSWORD` (para no hardcodear secrets).

### Verificación

```bash
pytest                       # 73/73 pasadas (unit + 1 integración)
python -c "from app.main import app"   # sin errores de importación
```

## Próximos pasos (fuera de alcance del roadmap 1-12)

1. Una forma de marcar los 4 puntos de referencia reales de una toma
   específica (manual sobre el video, o marcadores físicos detectados
   automáticamente en la pista) para que `HomographyCoordinateCalibrator`
   deje de usar el supuesto por defecto y calibre con datos reales.
2. Un endpoint de lectura para `FrameMetrics` en sí (no solo dentro del
   PDF), si el frontend necesita graficarlos directamente; y formatos de
   informe adicionales (Excel/CSV) implementando `ReportGenerator`.
3. Migrar `BackgroundTasksRunner` a Celery + Redis si el volumen de
   análisis lo justifica (el contrato `TaskRunner` ya está listo para
   ese cambio).
