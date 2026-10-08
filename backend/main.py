import io
import json
import os
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
from botocore.client import Config
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:4566")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "test")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT_URL,
    region_name=REGION,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    config=Config(signature_version="s3v4"),
)

app = FastAPI(title="LocalStack S3 Explorer", version="1.1.0")


class BucketRequest(BaseModel):
    name: str


class TextFileRequest(BaseModel):
    content: str


class FolderRequest(BaseModel):
    prefix: str


def safe_key(key: str) -> str:
    key = key.strip().lstrip("/")
    if not key or key.endswith("/"):
        raise HTTPException(400, "Informe uma chave de arquivo válida.")
    if ".." in key or "\\" in key:
        raise HTTPException(400, "Chave inválida.")
    return key


def safe_prefix(prefix: str) -> str:
    prefix = prefix.strip().lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    if ".." in prefix or "\\" in prefix:
        raise HTTPException(400, "Prefixo de pasta inválido.")
    return prefix


def handle_s3_error(exc: Exception) -> None:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    if code in {"NoSuchBucket", "NoSuchKey", "404"}:
        raise HTTPException(404, "Recurso não encontrado.")
    if code in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
        raise HTTPException(409, "O recurso já existe.")
    raise HTTPException(500, str(exc))


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health():
    try:
        s3.list_buckets()
        return {"status": "ok", "endpoint": ENDPOINT_URL}
    except Exception as exc:
        raise HTTPException(503, f"LocalStack S3 indisponível: {exc}")


@app.get("/api/buckets")
def list_buckets():
    try:
        response = s3.list_buckets()
        buckets = []
        for bucket in response.get("Buckets", []):
            name = bucket["Name"]
            try:
                paginator = s3.get_paginator("list_objects_v2")
                count = 0
                size = 0
                for page in paginator.paginate(Bucket=name):
                    contents = page.get("Contents", [])
                    count += len(contents)
                    size += sum(item.get("Size", 0) for item in contents)
            except Exception:
                count, size = 0, 0
            buckets.append({
                "name": name,
                "created": bucket.get("CreationDate").isoformat() if bucket.get("CreationDate") else None,
                "objects": count,
                "size": size,
            })
        return buckets
    except Exception as exc:
        handle_s3_error(exc)


@app.post("/api/buckets")
def create_bucket(payload: BucketRequest):
    name = payload.name.strip().lower()
    if len(name) < 3 or len(name) > 63:
        raise HTTPException(400, "O nome do bucket deve ter entre 3 e 63 caracteres.")
    try:
        s3.create_bucket(Bucket=name)
        return {"message": "Bucket criado.", "name": name}
    except Exception as exc:
        handle_s3_error(exc)


@app.put("/api/buckets/{old_name}")
def rename_bucket(old_name: str, payload: BucketRequest):
    new_name = payload.name.strip().lower()
    if not new_name or new_name == old_name:
        raise HTTPException(400, "Informe um novo nome para o bucket.")
    try:
        s3.create_bucket(Bucket=new_name)
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=old_name):
            for item in page.get("Contents", []):
                key = item["Key"]
                body = s3.get_object(Bucket=old_name, Key=key)["Body"].read()
                s3.put_object(Bucket=new_name, Key=key, Body=body)
        s3.delete_bucket(Bucket=old_name)
        return {"message": "Bucket atualizado.", "name": new_name}
    except Exception as exc:
        handle_s3_error(exc)


@app.delete("/api/buckets/{name}")
def delete_bucket(name: str):
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=name):
            for item in page.get("Contents", []):
                s3.delete_object(Bucket=name, Key=item["Key"])
        s3.delete_bucket(Bucket=name)
        return {"message": "Bucket excluído."}
    except Exception as exc:
        handle_s3_error(exc)


@app.get("/api/buckets/{bucket}/objects")
def list_objects(bucket: str, prefix: str = ""):
    prefix = safe_prefix(prefix)
    try:
        response = s3.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            Delimiter="/",
        )

        folders = [
            item["Prefix"]
            for item in response.get("CommonPrefixes", [])
            if item.get("Prefix")
        ]

        objects = []
        for item in response.get("Contents", []):
            key = item["Key"]
            if key == prefix:
                continue
            objects.append({
                "key": key,
                "size": item.get("Size", 0),
                "modified": item.get("LastModified").isoformat() if item.get("LastModified") else None,
                "etag": item.get("ETag", "").replace('"', ""),
            })

        return {
            "prefix": prefix,
            "folders": folders,
            "objects": objects,
        }
    except Exception as exc:
        handle_s3_error(exc)


@app.post("/api/buckets/{bucket}/folders")
def create_folder(bucket: str, payload: FolderRequest):
    prefix = safe_prefix(payload.prefix)
    if not prefix:
        raise HTTPException(400, "Informe o caminho da pasta.")

    try:
        s3.put_object(
            Bucket=bucket,
            Key=prefix,
            Body=b"",
            ContentType="application/x-directory",
        )
        return {"message": "Pasta criada.", "prefix": prefix}
    except Exception as exc:
        handle_s3_error(exc)


@app.delete("/api/buckets/{bucket}/folders")
def delete_folder(bucket: str, prefix: str):
    prefix = safe_prefix(prefix)
    if not prefix:
        raise HTTPException(400, "Informe a pasta.")

    try:
        paginator = s3.get_paginator("list_objects_v2")
        deleted = 0

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                s3.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": keys, "Quiet": True},
                )
                deleted += len(keys)

        return {
            "message": "Pasta excluída.",
            "prefix": prefix,
            "deleted": deleted,
        }
    except Exception as exc:
        handle_s3_error(exc)


@app.post("/api/buckets/{bucket}/objects/upload")
async def upload_object(bucket: str, file: UploadFile = File(...), key: str | None = None):
    object_key = safe_key(key or file.filename or "")
    try:
        content = await file.read()
        s3.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
        return {"message": "Arquivo enviado.", "key": object_key}
    except Exception as exc:
        handle_s3_error(exc)


@app.put("/api/buckets/{bucket}/objects/{key:path}")
async def update_object(bucket: str, key: str, file: UploadFile = File(...)):
    object_key = safe_key(key)
    try:
        content = await file.read()
        s3.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
        return {"message": "Arquivo atualizado.", "key": object_key}
    except Exception as exc:
        handle_s3_error(exc)


@app.post("/api/buckets/{bucket}/objects/text")
def create_text_object(bucket: str, payload: TextFileRequest):
    raise HTTPException(400, "Use o campo key no endpoint de criação de arquivo.")


@app.put("/api/buckets/{bucket}/objects-text")
def save_text_object(bucket: str, key: str, payload: TextFileRequest):
    object_key = safe_key(key)
    try:
        s3.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=payload.content.encode("utf-8"),
            ContentType="text/plain",
        )
        return {"message": "Arquivo salvo.", "key": object_key}
    except Exception as exc:
        handle_s3_error(exc)


@app.delete("/api/buckets/{bucket}/objects/{key:path}")
def delete_object(bucket: str, key: str):
    object_key = safe_key(key)
    try:
        s3.delete_object(Bucket=bucket, Key=object_key)
        return {"message": "Arquivo excluído."}
    except Exception as exc:
        handle_s3_error(exc)


@app.get("/api/buckets/{bucket}/objects/{key:path}/download")
def download_object(bucket: str, key: str):
    object_key = safe_key(key)
    try:
        response = s3.get_object(Bucket=bucket, Key=object_key)
        body = response["Body"].read()
        content_type = response.get("ContentType", "application/octet-stream")
        return Response(
            content=body,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{Path(object_key).name}"'},
        )
    except Exception as exc:
        handle_s3_error(exc)


@app.get("/api/buckets/{bucket}/objects/{key:path}/content")
def preview_object(bucket: str, key: str):
    object_key = safe_key(key)
    try:
        response = s3.get_object(Bucket=bucket, Key=object_key)
        body = response["Body"].read()
        filename = Path(object_key).name
        suffix = Path(filename).suffix.lower()

        if suffix in {".txt", ".csv", ".json", ".jsonl"}:
            text = body.decode("utf-8", errors="replace")
            if suffix == ".json":
                try:
                    data = json.loads(text)
                    return JSONResponse({"type": "json", "data": data})
                except json.JSONDecodeError:
                    return JSONResponse({"type": "text", "data": text})
            return JSONResponse({"type": "text", "data": text})

        if suffix == ".parquet":
            df = pd.read_parquet(io.BytesIO(body))
            return JSONResponse({
                "type": "table",
                "columns": df.columns.tolist(),
                "rows": json.loads(df.head(500).to_json(orient="records", date_format="iso")),
                "total_rows": len(df),
            })

        if suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(io.BytesIO(body))
            return JSONResponse({
                "type": "table",
                "columns": df.columns.tolist(),
                "rows": json.loads(df.head(500).to_json(orient="records", date_format="iso")),
                "total_rows": len(df),
            })

        return JSONResponse({
            "type": "binary",
            "message": "Pré-visualização não disponível para este tipo de arquivo.",
            "size": len(body),
        })
    except Exception as exc:
        handle_s3_error(exc)
