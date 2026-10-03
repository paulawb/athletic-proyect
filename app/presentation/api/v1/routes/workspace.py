import csv
import io
import re
import uuid
from pathlib import Path
from datetime import date, datetime, time, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, EmailStr, Field, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.entities.user import User
from app.core.phone import normalize_phone

from app.infrastructure.database.models.analysis_model import AnalysisModel
from app.infrastructure.database.models.athlete_model import AthleteModel
from app.infrastructure.database.models.metrics_model import MetricsModel
from app.infrastructure.database.models.test_model import TestModel
from app.infrastructure.database.models.video_model import VideoModel
from app.infrastructure.database.models.workspace_model import (
    GeneratedReportModel,
    LibraryReferenceModel,
    LibraryResourceModel,
    SettingModel,
)
from app.infrastructure.database.models.user_model import UserModel
from app.presentation.api.v1.dependencies import get_current_user
from app.core.security import hash_password, verify_password

router = APIRouter(prefix="/api/v1", tags=["workspace"])
_SETTING_SECTIONS = {"profile", "institution", "privacy", "system"}
class SettingsSectionDTO(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class ReportCreateDTO(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    output_format: Literal["pdf", "xlsx", "csv"] = "pdf"
    template: Literal["monthly", "individual", "group", "trends"] = "individual"
    analysis_id: int | None = Field(default=None, gt=0)
    athlete_ids: list[int] = Field(default_factory=list, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    metrics: list[Literal["average_speed", "maximum_speed", "stride_length", "cadence", "posture_score"]] = Field(
        default_factory=lambda: ["average_speed", "maximum_speed", "stride_length", "cadence", "posture_score"]
    )


class PasswordChangeDTO(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class LibraryReferenceDTO(BaseModel):
    metric: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=30)
    age_range: str = Field(min_length=1, max_length=30)
    low: str = Field(min_length=1, max_length=80)
    average: str = Field(min_length=1, max_length=80)
    high: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=255)


def _user_id(user: User) -> int:
    if user.id is None:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    return user.id


@router.get("/dashboard/stats")
async def dashboard_stats(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    athlete_count = await session.scalar(select(func.count()).select_from(AthleteModel)) or 0
    test_count = await session.scalar(select(func.count()).select_from(TestModel)) or 0
    completed_count = await session.scalar(
        select(func.count(func.distinct(TestModel.id)))
        .select_from(TestModel)
        .join(VideoModel, VideoModel.test_id == TestModel.id)
        .join(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
        .where(func.upper(AnalysisModel.status) == "COMPLETED")
    ) or 0
    processing_count = await session.scalar(
        select(func.count(func.distinct(TestModel.id)))
        .select_from(TestModel)
        .join(VideoModel, VideoModel.test_id == TestModel.id)
        .join(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
        .where(func.upper(AnalysisModel.status).in_(("PROCESSING", "PENDING")))
    ) or 0
    rows = (
        await session.execute(
            select(TestModel, AthleteModel, AnalysisModel, MetricsModel)
            .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
            .outerjoin(VideoModel, VideoModel.test_id == TestModel.id)
            .outerjoin(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
            .outerjoin(MetricsModel, MetricsModel.analysis_id == AnalysisModel.id)
            .order_by(TestModel.created_at.desc())
            .limit(5)
        )
    ).all()
    recent = [
        {
            "test_id": test.id,
            "athlete_name": f"{athlete.first_name} {athlete.last_name}",
            "distance": test.distance,
            "test_type": test.test_type,
            "status": analysis.status if analysis else test.status,
            "average_speed": metrics.average_speed if metrics else None,
            "created_at": test.created_at,
            "analysis_id": analysis.id if analysis else None,
        }
        for test, athlete, analysis, metrics in rows
    ]
    return {
        "total_athletes": athlete_count,
        "total_tests": test_count,
        "completed_tests": completed_count,
        "processing_tests": processing_count,
        "recent_analyses": recent,
    }


@router.get("/settings")
async def get_settings_sections(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(SettingModel).where(SettingModel.user_id == _user_id(current_user))
        )
    ).scalars()
    result = {row.section: row.data for row in rows}
    result.pop("notifications", None)
    first, _, last = current_user.full_name.partition(" ")
    result.setdefault(
        "profile",
        {
            "first_name": first,
            "last_name": last,
            "email": current_user.email,
            "phone": current_user.phone or "",
            "position": current_user.role.capitalize(),
        },
    )
    profile_data = dict(result["profile"])
    result["profile"] = {
        **profile_data,
        "email": current_user.email,
        "phone": current_user.phone or "",
        "position": current_user.role.capitalize(),
    }
    result["privacy"] = {
        "export_format": str(result.get("privacy", {}).get("export_format", "JSON")).upper(),
    }
    system_data = result.get("system", {})
    result["system"] = {
        "timezone": system_data.get("timezone", "America/Bogota"),
        "language": "Español",
    }
    return result


@router.put("/settings/{section}")
async def update_settings_section(
    section: str,
    payload: SettingsSectionDTO,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if section not in _SETTING_SECTIONS:
        raise HTTPException(status_code=404, detail="Sección de configuración desconocida")
    uid = _user_id(current_user)
    data = dict(payload.data)
    setting = await session.scalar(
        select(SettingModel).where(SettingModel.user_id == uid, SettingModel.section == section)
    )
    if section == "profile":
        user = await session.get(UserModel, uid)
        if user is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        first = str(payload.data.get("first_name", "")).strip()
        last = str(payload.data.get("last_name", "")).strip()
        email = payload.data.get("email")
        if email:
            try:
                normalized_email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
            except ValueError as exc:
                await session.rollback()
                raise HTTPException(status_code=422, detail="El correo del perfil no es válido") from exc
            if normalized_email != user.email.lower():
                existing_email = await session.scalar(
                    select(UserModel.id).where(
                        UserModel.id != uid,
                        func.lower(UserModel.email) == normalized_email,
                    )
                )
                if existing_email is not None:
                    raise HTTPException(status_code=409, detail="El correo ya está asociado a otra cuenta")
                user.email = normalized_email
        phone = payload.data.get("phone")
        if phone is not None:
            try:
                user.phone = normalize_phone(str(phone)) if str(phone).strip() else None
            except ValueError as exc:
                await session.rollback()
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        if first or last:
            user.full_name = " ".join(part for part in (first, last) if part)
        role = str(payload.data.get("position", user.role)).strip().lower()
        if role not in {"docente", "estudiante"}:
            raise HTTPException(status_code=422, detail="El cargo debe ser Docente o Estudiante")
        user.role = role
        data["position"] = user.role.capitalize()
        data["email"] = user.email
        data["phone"] = user.phone or ""
    if setting is None:
        setting = SettingModel(user_id=uid, section=section, data=data)
        session.add(setting)
    else:
        setting.data = data
    if section == "profile":
        setting.data = data
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="El correo ya está asociado a otra cuenta") from exc
        return {"section": section, "data": data}
    await session.commit()
    return {"section": section, "data": payload.data}


@router.put("/settings/security/password", status_code=204)
async def change_password(
    payload: PasswordChangeDTO,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    user = await session.get(UserModel, _user_id(current_user))
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    user.hashed_password = hash_password(payload.new_password)
    await session.commit()
    return Response(status_code=204)


@router.get("/settings/export")
async def export_user_data(
    format: Literal["json", "csv"] = Query(default="json"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    athlete_rows = (
        await session.execute(
            select(AthleteModel).order_by(AthleteModel.id)
        )
    ).scalars().all()
    test_rows = (
        await session.execute(
            select(TestModel, MetricsModel)
            .outerjoin(VideoModel, VideoModel.test_id == TestModel.id)
            .outerjoin(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
            .outerjoin(MetricsModel, MetricsModel.analysis_id == AnalysisModel.id)
            .order_by(TestModel.id)
        )
    ).all()
    data = {
        "athletes": [
            {
                "id": athlete.id,
                "first_name": athlete.first_name,
                "last_name": athlete.last_name,
                "identification": athlete.identification,
                "email": athlete.email,
                "age": athlete.age,
                "gender": athlete.gender,
                "category": athlete.category,
                "group_name": athlete.group_name,
                "is_active": athlete.is_active,
            }
            for athlete in athlete_rows
        ],
        "tests": [
            {
                "id": test.id,
                "athlete_id": test.athlete_id,
                "distance": test.distance,
                "test_type": test.test_type,
                "technique": test.technique,
                "status": test.status,
                "created_at": test.created_at.isoformat() if test.created_at else None,
                "metrics": (
                    {
                        "average_speed": metrics.average_speed,
                        "maximum_speed": metrics.maximum_speed,
                        "stride_length": metrics.stride_length,
                        "cadence": metrics.cadence,
                        "posture_score": metrics.posture_score,
                    }
                    if metrics
                    else None
                ),
            }
            for test, metrics in test_rows
        ],
    }
    if format == "json":
        import json

        return Response(
            content=json.dumps(data, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="athletic-analysis-data.json"'},
        )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "test_id", "athlete_id", "distance", "test_type", "technique", "status", "created_at",
            "average_speed", "maximum_speed", "stride_length", "cadence", "posture_score",
        ]
    )
    for item in data["tests"]:
        metrics = item["metrics"] or {}
        writer.writerow(
            [
                item["id"], item["athlete_id"], item["distance"], item["test_type"], item["technique"],
                item["status"], item["created_at"], metrics.get("average_speed"), metrics.get("maximum_speed"),
                metrics.get("stride_length"), metrics.get("cadence"), metrics.get("posture_score"),
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="athletic-analysis-data.csv"'},
    )


@router.post("/settings/institution/logo")
async def upload_institution_logo(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=415, detail="El logo debe ser PNG, JPG o WEBP")
    content = await file.read(5 * 1024 * 1024 + 1)
    if not content or len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El logo debe pesar entre 1 byte y 5 MB")
    directory = Path(get_settings().storage_local_path) / "institucion"
    directory.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{extension}"
    (directory / stored).write_bytes(content)
    uid = _user_id(current_user)
    setting = await session.scalar(
        select(SettingModel).where(SettingModel.user_id == uid, SettingModel.section == "institution")
    )
    data = dict(setting.data) if setting else {}
    data["logo_filename"] = stored
    if setting:
        setting.data = data
    else:
        session.add(SettingModel(user_id=uid, section="institution", data=data))
    await session.commit()
    return {"logo_url": "/api/v1/settings/institution/logo", "filename": stored}


@router.get("/settings/institution/logo")
async def get_institution_logo(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    setting = await session.scalar(
        select(SettingModel).where(
            SettingModel.user_id == _user_id(current_user), SettingModel.section == "institution"
        )
    )
    filename = setting.data.get("logo_filename") if setting else None
    if not filename:
        raise HTTPException(status_code=404, detail="La institución aún no tiene un logo")
    path = Path(get_settings().storage_local_path) / "institucion" / Path(filename).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo del logo no está disponible")
    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[path.suffix.lower()]
    return FileResponse(path, media_type=content_type)


@router.get("/library/resources")
async def list_library_resources(
    resource_type: Literal["video", "document", "reference"] | None = Query(default=None, alias="type"),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if resource_type == "reference":
        rows = (
            await session.execute(
                select(LibraryReferenceModel).order_by(
                    LibraryReferenceModel.metric, LibraryReferenceModel.age_range
                )
            )
        ).scalars()
        return [
            {
                "id": row.id,
                "metric": row.metric,
                "unit": row.unit,
                "age_range": row.age_range,
                "low": row.low,
                "average": row.average,
                "high": row.high,
                "source": row.source,
            }
            for row in rows
        ]
    query = select(LibraryResourceModel)
    if resource_type:
        query = query.where(LibraryResourceModel.resource_type == resource_type)
    rows = (await session.execute(query.order_by(LibraryResourceModel.created_at.desc()))).scalars()
    return [
        {
            "id": row.id,
            "type": row.resource_type,
            "title": row.title,
            "category": row.category,
            "filename": row.original_filename,
            "content_type": row.content_type,
            "size_bytes": row.size_bytes,
            "created_at": row.created_at,
            "download_url": f"/api/v1/library/resources/{row.id}/download",
        }
        for row in rows
    ]


@router.post("/library/references", status_code=status.HTTP_201_CREATED)
async def create_library_reference(
    payload: LibraryReferenceDTO,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    reference = LibraryReferenceModel(**payload.model_dump())
    session.add(reference)
    await session.commit()
    await session.refresh(reference)
    return {"id": reference.id, **payload.model_dump()}


@router.put("/library/references/{reference_id}")
async def update_library_reference(
    reference_id: int,
    payload: LibraryReferenceDTO,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    reference = await session.get(LibraryReferenceModel, reference_id)
    if reference is None:
        raise HTTPException(status_code=404, detail="Referencia no encontrada")
    for field, value in payload.model_dump().items():
        setattr(reference, field, value)
    await session.commit()
    return {"id": reference.id, **payload.model_dump()}


@router.delete("/library/references/{reference_id}", status_code=204)
async def delete_library_reference(
    reference_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> Response:
    reference = await session.get(LibraryReferenceModel, reference_id)
    if reference is None:
        raise HTTPException(status_code=404, detail="Referencia no encontrada")
    await session.delete(reference)
    await session.commit()
    return Response(status_code=204)


@router.post("/library/resources", status_code=status.HTTP_201_CREATED)
async def upload_library_resource(
    resource_type: Literal["video", "document"] = Form(..., alias="type"),
    title: str = Form(..., min_length=1, max_length=200),
    category: str = Form(..., min_length=1, max_length=50),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    extension = Path(file.filename or "").suffix.lower()
    allowed = {".mp4", ".mov"} if resource_type == "video" else {".pdf", ".xlsx", ".docx", ".csv"}
    if extension not in allowed:
        raise HTTPException(status_code=415, detail="Formato de archivo no permitido")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contents) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 100 MB")

    settings = get_settings()
    directory = Path(settings.storage_local_path) / "biblioteca"
    directory.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}{extension}"
    (directory / stored_filename).write_bytes(contents)
    resource = LibraryResourceModel(
        resource_type=resource_type,
        title=title,
        category=category,
        original_filename=Path(file.filename or "recurso").name,
        stored_filename=stored_filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(contents),
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return {
        "id": resource.id,
        "type": resource.resource_type,
        "title": resource.title,
        "category": resource.category,
        "filename": resource.original_filename,
        "size_bytes": resource.size_bytes,
        "created_at": resource.created_at,
        "download_url": f"/api/v1/library/resources/{resource.id}/download",
    }


@router.get("/library/resources/{resource_id}/download")
async def download_library_resource(
    resource_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> FileResponse:
    resource = await session.get(LibraryResourceModel, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    path = Path(get_settings().storage_local_path) / "biblioteca" / resource.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo del recurso no está disponible")
    return FileResponse(path, media_type=resource.content_type, filename=resource.original_filename)


@router.get("/reports")
async def list_reports(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(GeneratedReportModel)
            .where(GeneratedReportModel.user_id == _user_id(current_user))
            .order_by(GeneratedReportModel.created_at.desc())
        )
    ).scalars()
    return [
        {
            "id": row.id,
            "analysis_id": row.analysis_id,
            "name": row.name,
            "format": row.output_format,
            "downloads": row.downloads,
            "parameters": row.parameters,
            "created_at": row.created_at,
            "download_url": f"/api/v1/reports/{row.id}/download",
        }
        for row in rows
    ]


@router.post("/reports/generate", status_code=status.HTTP_201_CREATED)
async def generate_report(
    payload: ReportCreateDTO,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not payload.metrics:
        raise HTTPException(status_code=422, detail="Selecciona al menos una métrica")
    if payload.date_from and payload.date_to and payload.date_from > payload.date_to:
        raise HTTPException(status_code=422, detail="El rango de fechas es inválido")
    query = (
        select(AnalysisModel, TestModel, AthleteModel, MetricsModel)
        .join(VideoModel, VideoModel.id == AnalysisModel.video_id)
        .join(TestModel, TestModel.id == VideoModel.test_id)
        .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
        .join(MetricsModel, MetricsModel.analysis_id == AnalysisModel.id)
        .where(AnalysisModel.status == "COMPLETED")
    )
    if payload.analysis_id:
        query = query.where(AnalysisModel.id == payload.analysis_id)
    if payload.athlete_ids:
        query = query.where(AthleteModel.id.in_(payload.athlete_ids))
    if payload.date_from:
        query = query.where(
            TestModel.created_at
            >= datetime.combine(payload.date_from, time.min, tzinfo=timezone.utc)
        )
    if payload.date_to:
        query = query.where(
            TestModel.created_at
            < datetime.combine(
                date.fromordinal(payload.date_to.toordinal() + 1), time.min, tzinfo=timezone.utc
            )
        )
    rows = (
        await session.execute(query.order_by(TestModel.created_at, AnalysisModel.id).limit(5000))
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No hay resultados que coincidan con los filtros")
    labels = {
        "average_speed": "Velocidad promedio (m/s)",
        "maximum_speed": "Velocidad máxima (m/s)",
        "stride_length": "Longitud de zancada (m)",
        "cadence": "Cadencia (pasos/s)",
        "posture_score": "Postura (0-100)",
    }
    columns = ["Análisis", "Prueba", "Atleta", "Fecha", "Distancia (m)"] + [
        labels[field] for field in payload.metrics
    ]
    values = [
        [
            analysis.id,
            test.id,
            f"{athlete.first_name} {athlete.last_name}",
            test.created_at.strftime("%Y-%m-%d") if test.created_at else "",
            test.distance,
            *[getattr(metrics, field) for field in payload.metrics],
        ]
        for analysis, test, athlete, metrics in rows
    ]
    if payload.output_format == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=0.5 * inch, leftMargin=0.5 * inch)
        table = Table([columns, *values], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d6dbe5")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fa")]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story = [
            Paragraph(payload.name, getSampleStyleSheet()["Title"]),
            Paragraph(f"Plantilla: {payload.template} · Registros: {len(values)}", getSampleStyleSheet()["Normal"]),
            Spacer(1, 0.25 * inch),
            table,
        ]
        document.build(story)
        content = buffer.getvalue()
    elif payload.output_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(values)
        content = output.getvalue().encode("utf-8-sig")
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Resultados"
        sheet.append(columns)
        for row in values:
            sheet.append(row)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        buffer = io.BytesIO()
        workbook.save(buffer)
        content = buffer.getvalue()
    extension = payload.output_format
    stored_filename = f"{uuid.uuid4().hex}.{extension}"
    directory = Path(get_settings().storage_local_path) / "informes"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / stored_filename).write_bytes(content)
    report = GeneratedReportModel(
        user_id=_user_id(current_user),
        analysis_id=payload.analysis_id or rows[0][0].id,
        name=payload.name,
        output_format=payload.output_format,
        stored_filename=stored_filename,
        parameters=payload.model_dump(mode="json", exclude={"name", "output_format"}),
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return {
        "id": report.id,
        "analysis_id": report.analysis_id,
        "name": report.name,
        "format": report.output_format,
        "created_at": report.created_at,
        "download_url": f"/api/v1/reports/{report.id}/download",
    }


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    report = await session.get(GeneratedReportModel, report_id)
    if report is None or report.user_id != _user_id(current_user):
        raise HTTPException(status_code=404, detail="Informe no encontrado")
    path = Path(get_settings().storage_local_path) / "informes" / report.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo del informe no está disponible")
    report.downloads += 1
    await session.commit()
    media_types = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
    }
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", report.name).strip("-") or "informe"
    return FileResponse(
        path,
        media_type=media_types[report.output_format],
        filename=f"{safe_name}.{report.output_format}",
    )
