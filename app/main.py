import os
import io
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from fastapi import File, UploadFile
from googleapiclient.http import MediaIoBaseUpload


# Load environment variables
load_dotenv()

app = FastAPI()

# Google Drive setup
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

if not SERVICE_ACCOUNT_FILE or not FOLDER_ID:
    raise RuntimeError(
        "Missing GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_DRIVE_FOLDER_ID in .env")

SCOPES = ["https://www.googleapis.com/auth/drive"]

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
drive_service = build("drive", "v3", credentials=creds)


@app.get("/")
def root():
    return {"message": "Hello from FastAPI + Google Drive!"}

# listing files in a specific folder with optional filtering by file extension


@app.get("/files")
def list_files(extension: str = Query(None, description="File extension filter, e.g. pdf")):
    """
    List files in the shared folder by extension.
    Example: /files?extension=pdf
    """
    query = f"'{FOLDER_ID}' in parents and trashed = false"
    if extension:
        query += f" and name contains '.{extension}'"

    results = drive_service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, mimeType, modifiedTime)",
    ).execute()

    files = results.get("files", [])
    return {"count": len(files), "files": files}

# download a file by its ID


@app.get("/download/{file_id}")
def download_file(file_id: str):
    """
    Download a file from Google Drive by ID.
    Example: /download/123ABC456XYZ
    """
    try:
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        fh.seek(0)
        file = drive_service.files().get(fileId=file_id, fields="name").execute()
        filename = file.get("name")

        return StreamingResponse(
            fh,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# upload a file to the shared folder


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file to the Google Drive folder.
    Example: POST /upload with form-data key 'file'
    """
    try:
        # Read file content
        file_content = await file.read()
        fh = io.BytesIO(file_content)

        # Prepare metadata
        file_metadata = {
            "name": file.filename,
            "parents": [FOLDER_ID]
        }

        # Upload file
        media = MediaIoBaseUpload(fh, mimetype=file.content_type)
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name"
        ).execute()

        return {"id": uploaded_file.get("id"), "name": uploaded_file.get("name")}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# delete a file by its ID


@app.delete("/delete/{file_id}")
def delete_file(file_id: str):
    """
    Delete a file from Google Drive by its ID.
    Example: DELETE /delete/123ABC
    """
    try:
        drive_service.files().delete(fileId=file_id).execute()
        return {"message": f"File {file_id} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# rename a file by its ID
@app.patch("/rename/{file_id}")
def rename_file(file_id: str, new_name: str = Query(..., description="New file name")):
    """
    Rename a file in Google Drive by its ID.
    Example: PATCH /rename/123ABC?new_name=newfile.pdf
    """
    try:
        updated_file = drive_service.files().update(
            fileId=file_id,
            body={"name": new_name},
            fields="id, name"
        ).execute()
        return {"id": updated_file["id"], "new_name": updated_file["name"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
