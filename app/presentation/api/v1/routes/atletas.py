import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.athlete_dto import AthleteCreateDTO, AthleteResponseDTO, AthleteUpdateDTO
from app.application.use_cases.create_athlete import CreateAthlete
from app.application.use_cases.get_athlete import GetAthlete
from app.application.use_cases.list_athletes import ListAthletes
from app.core.database import get_db_session
from app.core.timezone import format_local
from app.domain.entities.user import User
from app.domain.services.athlete_code import athlete_code, athlete_id_from_code
from app.infrastructure.database.models.analysis_model import AnalysisModel
from app.infrastructure.database.models.athlete_model import AthleteModel
from app.infrastructure.database.models.metrics_model import MetricsModel
from app.infrastructure.database.models.test_model import TestModel
from app.infrastructure.database.models.video_model import VideoModel
from app.infrastructure.database.repositories.athlete_repository_impl import SqlAlchemyAthleteRepository
from app.presentation.api.v1.dependencies import get_current_user
from app.presentation.api.v1.ownership import get_user_timezone, require_owned_athlete, user_id

router = APIRouter(prefix="/api/v1/atletas", tags=["atletas"])


@router.post("", response_model=AthleteResponseDTO, status_code=201)
async def create_athlete(
    data: AthleteCreateDTO,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AthleteResponseDTO:
    repository = SqlAlchemyAthleteRepository(session)
    athlete = await CreateAthlete(repository).execute(data, owner_user_id=user_id(current_user))
    return AthleteResponseDTO.model_validate(athlete)


@router.get("", response_model=list[AthleteResponseDTO])
async def list_athletes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=50),
    group_name: str | None = Query(default=None, max_length=80),
    is_active: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[AthleteResponseDTO]:
    query = select(AthleteModel).where(AthleteModel.owner_user_id == user_id(current_user))
    if q:
        term = f"%{q.strip()}%"
        code_id = athlete_id_from_code(q)
        filters = [AthleteModel.identification.ilike(term), AthleteModel.email.ilike(term)]
        if code_id is not None:
            filters.append(AthleteModel.id == code_id)
        query = query.where(or_(*filters))
    if category:
        query = query.where(AthleteModel.category == category)
    if group_name:
        query = query.where(AthleteModel.group_name == group_name)
    if is_active is not None:
        query = query.where(AthleteModel.is_active.is_(is_active))
    models = (
        await session.execute(query.order_by(AthleteModel.id).offset(skip).limit(limit))
    ).scalars().all()
    ids = [model.id for model in models]
    test_counts = {}
    if ids:
        test_counts = dict(
            (
                await session.execute(
                    select(TestModel.athlete_id, func.count(TestModel.id))
                    .where(TestModel.athlete_id.in_(ids))
                    .group_by(TestModel.athlete_id)
                )
            ).all()
        )
    return [
        AthleteResponseDTO.model_validate(model).model_copy(
            update={"test_count": test_counts.get(model.id, 0)}
        )
        for model in models
    ]


@router.get("/groups")
async def list_athlete_groups(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, list[str]]:
    owner_id = user_id(current_user)
    categories = (
        await session.execute(
            select(AthleteModel.category)
            .where(AthleteModel.owner_user_id == owner_id, AthleteModel.category.is_not(None))
            .distinct()
            .order_by(AthleteModel.category)
        )
    ).scalars().all()
    groups = (
        await session.execute(
            select(AthleteModel.group_name)
            .where(AthleteModel.owner_user_id == owner_id, AthleteModel.group_name.is_not(None))
            .distinct()
            .order_by(AthleteModel.group_name)
        )
    ).scalars().all()
    return {"categories": categories, "groups": groups}


@router.get("/export")
async def export_athletes(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    athletes = (
        await session.execute(
            select(AthleteModel)
            .where(AthleteModel.owner_user_id == user_id(current_user))
            .order_by(AthleteModel.id)
        )
    ).scalars().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["id", "code", "identification", "email", "age", "gender", "category", "group_name", "is_active"]
    )
    for athlete in athletes:
        writer.writerow(
            [
                athlete.id, athlete_code(athlete.id), athlete.identification,
                athlete.email or "", athlete.age, athlete.gender, athlete.category or "",
                athlete.group_name or "", athlete.is_active,
            ]
        )
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="atletas.csv"'},
    )


@router.get("/export/completo")
async def export_full_report(
    format: str = Query(default="xlsx", pattern="^(xlsx|csv)$"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Descargable general: todos los atletas de la cuenta con los datos de
    cada prueba analizada y sus metricas. Las fechas van en la zona horaria
    elegida en Configuracion."""
    owner_id = user_id(current_user)
    tz_name = await get_user_timezone(session, owner_id)
    athletes = (
        await session.execute(
            select(AthleteModel).where(AthleteModel.owner_user_id == owner_id).order_by(AthleteModel.id)
        )
    ).scalars().all()
    rows = (
        await session.execute(
            select(AthleteModel.id, TestModel, VideoModel, AnalysisModel, MetricsModel)
            .join(TestModel, TestModel.athlete_id == AthleteModel.id)
            .outerjoin(VideoModel, VideoModel.test_id == TestModel.id)
            .outerjoin(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
            .outerjoin(MetricsModel, MetricsModel.analysis_id == AnalysisModel.id)
            .where(AthleteModel.owner_user_id == owner_id)
            .order_by(AthleteModel.id, TestModel.created_at)
        )
    ).all()

    athlete_headers = [
        "ID", "C?digo", "Documento", "Correo", "Edad", "Género", "Categoría", "Grupo", "Estado",
        "Pruebas", "Análisis completados", "Velocidad promedio media (m/s)", "Mejor velocidad máxima (m/s)",
    ]
    test_headers = [
        "ID atleta", "C?digo atleta", "Documento", "Edad", "Género", "Categoría", "Grupo", "Código prueba", "Fecha y hora",
        "Distancia (m)", "Tipo de prueba", "Técnica", "Video", "Análisis", "Estado",
        "Velocidad promedio (m/s)", "Velocidad máxima (m/s)", "Longitud de zancada (m)", "Cadencia (pasos/s)",
        "Postura (%)",
    ]
    by_athlete: dict[int, list] = {}
    for athlete_id, test, video, analysis, metrics in rows:
        by_athlete.setdefault(athlete_id, []).append((test, video, analysis, metrics))

    athlete_rows: list[list] = []
    test_rows: list[list] = []
    for athlete in athletes:
        entries = by_athlete.get(athlete.id, [])
        done = [metrics for _, _, _, metrics in entries if metrics is not None]
        athlete_rows.append(
            [
                athlete.id, athlete_code(athlete.id), athlete.identification, athlete.email or "",
                athlete.age, athlete.gender, athlete.category or "", athlete.group_name or "",
                "Activo" if athlete.is_active else "Inactivo",
                len({test.id for test, _, _, _ in entries}), len(done),
                round(sum(m.average_speed for m in done) / len(done), 2) if done else "",
                round(max(m.maximum_speed for m in done), 2) if done else "",
            ]
        )
        base = [
            athlete.id, athlete_code(athlete.id), athlete.identification, athlete.age,
            athlete.gender, athlete.category or "", athlete.group_name or "",
        ]
        if not entries:
            test_rows.append(base + [""] * (len(test_headers) - len(base)))
        for test, video, analysis, metrics in entries:
            test_rows.append(
                base
                + [
                    f"PRU-{test.id:05d}", format_local(test.created_at, tz_name), test.distance, test.test_type,
                    test.technique, video.original_filename if video else "", analysis.id if analysis else "",
                    analysis.status if analysis else test.status,
                    round(metrics.average_speed, 2) if metrics else "",
                    round(metrics.maximum_speed, 2) if metrics else "",
                    round(metrics.stride_length, 2) if metrics else "",
                    round(metrics.cadence, 2) if metrics else "",
                    round(metrics.posture_score, 1) if metrics else "",
                ]
            )

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(test_headers)
        writer.writerows(test_rows)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="atletas-analizados.csv"'},
        )

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Atletas"
    summary.append(athlete_headers)
    for row in athlete_rows:
        summary.append(row)
    detail = workbook.create_sheet("Pruebas y métricas")
    detail.append(test_headers)
    for row in test_rows:
        detail.append(row)
    for sheet in (summary, detail):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            width = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 40)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="atletas-analizados.xlsx"'},
    )


@router.post("/import", status_code=201)
async def import_athletes(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El CSV supera el límite de 10 MB")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        required = {"first_name", "last_name", "identification", "age", "gender"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise HTTPException(
                status_code=422,
                detail={"message": "Faltan columnas obligatorias", "required": sorted(required)},
            )
        models = []
        seen_ids: set[str] = set()
        errors = []
        for line, row in enumerate(reader, start=2):
            try:
                data = AthleteCreateDTO.model_validate(row)
                if data.identification in seen_ids:
                    raise ValueError("Documento repetido dentro del archivo")
                seen_ids.add(data.identification)
                models.append(
                    AthleteModel(
                        first_name=data.first_name,
                        last_name=data.last_name,
                        identification=data.identification,
                        email=data.email,
                        age=data.age,
                        gender=data.gender,
                        category=data.category,
                        group_name=data.group_name,
                        owner_user_id=user_id(current_user),
                    )
                )
            except (ValueError, TypeError) as exc:
                errors.append({"line": line, "error": str(exc)})
        if errors:
            raise HTTPException(status_code=422, detail={"message": "El CSV contiene filas inválidas", "errors": errors[:50]})
        if not models:
            raise HTTPException(status_code=422, detail="El archivo no contiene atletas")
        session.add_all(models)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Uno o más documentos ya existen") from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="El archivo debe estar codificado en UTF-8") from exc
    return {"imported": len(models)}


@router.get("/{athlete_id}/metrics")
@router.get("/{athlete_id}/metricas", include_in_schema=False)
async def athlete_metrics(
    athlete_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    await require_owned_athlete(session, athlete_id, user_id(current_user))
    rows = (
        await session.execute(
            select(TestModel, MetricsModel, AnalysisModel)
            .outerjoin(VideoModel, VideoModel.test_id == TestModel.id)
            .outerjoin(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
            .outerjoin(MetricsModel, MetricsModel.analysis_id == AnalysisModel.id)
            .where(TestModel.athlete_id == athlete_id)
            .order_by(TestModel.created_at)
        )
    ).all()
    history = [
        {
            "test_id": test.id,
            "date": test.created_at,
            "distance": test.distance,
            "status": analysis.status if analysis else test.status,
            "analysis_id": analysis.id if analysis else None,
            "average_speed": metrics.average_speed if metrics else None,
            "maximum_speed": metrics.maximum_speed if metrics else None,
            "stride_length": metrics.stride_length if metrics else None,
            "cadence": metrics.cadence if metrics else None,
            "posture_score": metrics.posture_score if metrics else None,
        }
        for test, metrics, analysis in rows
    ]
    completed = [row for row in history if row["average_speed"] is not None]
    return {
        "athlete_id": athlete_id,
        "total_tests": len(history),
        "average_speed": (
            sum(row["average_speed"] for row in completed) / len(completed) if completed else None
        ),
        "best_speed": max((row["maximum_speed"] for row in completed), default=None),
        "history": history,
    }


@router.get("/{athlete_id}", response_model=AthleteResponseDTO)
async def get_athlete(
    athlete_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AthleteResponseDTO:
    await require_owned_athlete(session, athlete_id, user_id(current_user))
    repository = SqlAlchemyAthleteRepository(session)
    athlete = await GetAthlete(repository).execute(athlete_id)
    return AthleteResponseDTO.model_validate(athlete)


@router.put("/{athlete_id}", response_model=AthleteResponseDTO)
async def update_athlete(
    athlete_id: int,
    data: AthleteUpdateDTO,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AthleteResponseDTO:
    model = await require_owned_athlete(session, athlete_id, user_id(current_user))
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    try:
        await session.commit()
        await session.refresh(model)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="El documento ya está registrado") from exc
    return AthleteResponseDTO.model_validate(model)


@router.delete("/{athlete_id}", status_code=204)
async def deactivate_athlete(
    athlete_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    model = await require_owned_athlete(session, athlete_id, user_id(current_user))
    model.is_active = False
    await session.commit()
