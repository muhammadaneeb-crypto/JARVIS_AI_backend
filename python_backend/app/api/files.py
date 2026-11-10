
"""JARVIS AI - Phase 6 File Management API."""

import csv
import io
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from docx import Document
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from xml.sax.saxutils import escape

from app.core.config import settings
from app.core.security import verify_token
from app.services import session as sessions
from app.services.supabase_client import (
    SupabaseClient,
    get_client,
)


router = APIRouter(
    prefix="/files",
    tags=["File Management"],
    dependencies=[Depends(verify_token)],
)


# =========================================================
# CONFIGURATION
# =========================================================

FILES_BUCKET = os.getenv(
    "SUPABASE_FILES_BUCKET",
    "jarvis-files",
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".py",
    ".pdf",
    ".docx",
    ".xlsx",
    ".xlsm",
    ".log",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".py",
    ".log",
}


# =========================================================
# REQUEST MODELS
# =========================================================

class FileReadRequest(BaseModel):
    storage_path: str = Field(
        min_length=3,
        max_length=500,
    )


class DocumentGenerateRequest(BaseModel):
    title: str = Field(
        default="JARVIS Document",
        min_length=1,
        max_length=150,
    )

    content: str = Field(
        min_length=1,
        max_length=200000,
    )


class ExcelGenerateRequest(BaseModel):
    title: str = Field(
        default="JARVIS Spreadsheet",
        min_length=1,
        max_length=150,
    )

    headers: list[str] = Field(
        min_length=1,
        max_length=100,
    )

    rows: list[list[str | int | float | bool | None]] = Field(
        default_factory=list,
        max_length=10000,
    )


# =========================================================
# AUTHENTICATION
# =========================================================

def get_user_session(client: SupabaseClient):
    """Require a valid Supabase user session."""

    session = sessions.require_session(client)

    user_id = session.user.get("id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="User ID not found in session.",
        )

    return session, str(user_id)


# =========================================================
# FILE HELPERS
# =========================================================

def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from a filename."""

    name = Path(filename).name
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    name = name.strip("._")

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename.",
        )

    return name[:150]


def validate_storage_path(
    storage_path: str,
    user_id: str,
) -> str:
    """Allow access only to the current user's storage folder."""

    path = storage_path.replace("\\", "/").strip("/")

    parts = path.split("/")

    if (
        len(parts) < 2
        or parts[0] != user_id
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only access your own files.",
        )

    extension = Path(parts[-1]).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file extension.",
        )

    return path


def get_storage_headers(access_token: str) -> dict:
    """Build authenticated Supabase Storage headers."""

    return {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {access_token}",
    }


def get_storage_url(storage_path: str) -> str:
    """Create a safely encoded Supabase Storage URL."""

    encoded_bucket = quote(FILES_BUCKET, safe="")
    encoded_path = quote(storage_path, safe="/")

    return (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/{encoded_bucket}/{encoded_path}"
    )


def check_storage_configuration():
    """Check required Supabase settings."""

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured.",
        )


async def storage_request(
    method: str,
    storage_path: str,
    access_token: str,
    content: bytes | None = None,
    content_type: str | None = None,
):
    """Make an authenticated Supabase Storage request."""

    check_storage_configuration()

    headers = get_storage_headers(access_token)

    if content_type:
        headers["Content-Type"] = content_type

    if method == "POST":
        headers["x-upsert"] = "false"

    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            response = await http.request(
                method=method,
                url=get_storage_url(storage_path),
                headers=headers,
                content=content,
            )

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="File not found.",
            )

        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=403,
                detail="Supabase denied access to this file. Check Storage policies.",
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Supabase Storage request failed.",
                    "status_code": response.status_code,
                    "response": response.text[:1000],
                },
            )

        return response

    except HTTPException:
        raise

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Supabase Storage request timed out.",
        )

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Storage connection error: {str(exc)}",
        )


# =========================================================
# FILE TEXT EXTRACTION
# =========================================================

def extract_file_text(
    file_bytes: bytes,
    extension: str,
) -> str:
    """Extract readable text from supported file formats."""

    try:
        if extension in TEXT_EXTENSIONS:
            text = file_bytes.decode(
                "utf-8-sig",
                errors="replace",
            )

            if extension == ".json":
                try:
                    return json.dumps(
                        json.loads(text),
                        indent=2,
                        ensure_ascii=False,
                    )
                except json.JSONDecodeError:
                    return text

            if extension == ".csv":
                rows = csv.reader(io.StringIO(text))
                return "\n".join(
                    " | ".join(row)
                    for row in rows
                )

            return text

        if extension == ".pdf":
            reader = PdfReader(io.BytesIO(file_bytes))

            return "\n\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

        if extension == ".docx":
            document = Document(io.BytesIO(file_bytes))

            return "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
            )

        if extension in (".xlsx", ".xlsm"):
            workbook = load_workbook(
                io.BytesIO(file_bytes),
                read_only=True,
                data_only=True,
            )

            output = []

            for sheet in workbook.worksheets:
                output.append(f"Sheet: {sheet.title}")

                for row in sheet.iter_rows(values_only=True):
                    output.append(
                        " | ".join(
                            "" if value is None else str(value)
                            for value in row
                        )
                    )

            workbook.close()

            return "\n".join(output)

        raise HTTPException(
            status_code=400,
            detail="This file format cannot be read.",
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract file content: {str(exc)}",
        )


# =========================================================
# POST /files/upload
# =========================================================

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    client: SupabaseClient = Depends(get_client),
):
    """Upload a private file to the user's Supabase folder."""

    session, user_id = get_user_session(client)

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    filename = sanitize_filename(file.filename)
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Unsupported file type.",
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            },
        )

    file_bytes = await file.read(MAX_FILE_SIZE + 1)

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Empty files are not allowed.",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Maximum file size is 10 MB.",
        )

    storage_path = f"{user_id}/{filename}"

    content_type = (
        file.content_type or "application/octet-stream"
    )

    response = await storage_request(
        method="POST",
        storage_path=storage_path,
        access_token=session.access_token,
        content=file_bytes,
        content_type=content_type,
    )

    return {
        "status": "success",
        "message": "File uploaded successfully.",
        "filename": filename,
        "storage_path": storage_path,
        "size_bytes": len(file_bytes),
        "content_type": content_type,
        "storage_status": response.status_code,
    }


# =========================================================
# POST /files/read
# =========================================================

@router.post("/read")
async def read_file(
    body: FileReadRequest,
    client: SupabaseClient = Depends(get_client),
):
    """Download and extract text from the user's private file."""

    session, user_id = get_user_session(client)

    storage_path = validate_storage_path(
        body.storage_path,
        user_id,
    )

    response = await storage_request(
        method="GET",
        storage_path=storage_path,
        access_token=session.access_token,
    )

    file_bytes = response.content

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File is too large to read.",
        )

    extension = Path(storage_path).suffix.lower()

    content = extract_file_text(
        file_bytes,
        extension,
    )

    return {
        "status": "success",
        "filename": Path(storage_path).name,
        "storage_path": storage_path,
        "content": content,
        "characters": len(content),
    }


# =========================================================
# DOCUMENT GENERATION HELPERS
# =========================================================

def make_download_response(
    file_bytes: bytes,
    filename: str,
    media_type: str,
):
    """Return generated file as a downloadable response."""

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Content-Length": str(len(file_bytes)),
        },
    )


# =========================================================
# POST /files/generate/pdf
# =========================================================

@router.post("/generate/pdf")
async def generate_pdf(
    body: DocumentGenerateRequest,
    client: SupabaseClient = Depends(get_client),
):
    """Generate and download a PDF document."""

    get_user_session(client)

    buffer = io.BytesIO()

    try:
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=body.title,
        )

        styles = getSampleStyleSheet()

        story = [
            Paragraph(
                escape(body.title),
                styles["Title"],
            ),
            Spacer(1, 20),
        ]

        for paragraph in body.content.splitlines():
            if paragraph.strip():
                story.append(
                    Paragraph(
                        escape(paragraph),
                        styles["BodyText"],
                    )
                )
                story.append(Spacer(1, 8))

        document.build(story)

        return make_download_response(
            buffer.getvalue(),
            "jarvis_document.pdf",
            "application/pdf",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(exc)}",
        )


# =========================================================
# POST /files/generate/docx
# =========================================================

@router.post("/generate/docx")
async def generate_docx(
    body: DocumentGenerateRequest,
    client: SupabaseClient = Depends(get_client),
):
    """Generate and download a Word document."""

    get_user_session(client)

    try:
        document = Document()

        document.add_heading(
            body.title,
            level=0,
        )

        for paragraph in body.content.splitlines():
            document.add_paragraph(paragraph)

        buffer = io.BytesIO()
        document.save(buffer)

        return make_download_response(
            buffer.getvalue(),
            "jarvis_document.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Word generation failed: {str(exc)}",
        )


# =========================================================
# POST /files/generate/xlsx
# =========================================================

@router.post("/generate/xlsx")
async def generate_xlsx(
    body: ExcelGenerateRequest,
    client: SupabaseClient = Depends(get_client),
):
    """Generate and download an Excel workbook."""

    get_user_session(client)

    if any(len(row) > 100 for row in body.rows):
        raise HTTPException(
            status_code=400,
            detail="A row cannot contain more than 100 columns.",
        )

    try:
        workbook = Workbook()
        worksheet = workbook.active

        worksheet.title = "JARVIS Data"

        worksheet.append(body.headers)

        for row in body.rows:
            worksheet.append(row)

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for column_cells in worksheet.columns:
            max_length = max(
                (
                    len(str(cell.value))
                    for cell in column_cells
                    if cell.value is not None
                ),
                default=10,
            )

            worksheet.column_dimensions[
                column_cells[0].column_letter
            ].width = min(max_length + 2, 40)

        buffer = io.BytesIO()
        workbook.save(buffer)

        return make_download_response(
            buffer.getvalue(),
            "jarvis_spreadsheet.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Excel generation failed: {str(exc)}",
        )
