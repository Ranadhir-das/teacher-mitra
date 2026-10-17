from pathlib import Path
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError


def validate_upload(upload):
    """Inspect bytes instead of trusting the browser's MIME type or filename."""
    suffix = Path(upload.name).suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise ValidationError("Upload a PDF, PNG or JPEG file.")
    if not upload.size or upload.size > settings.DOCUMENT_MAX_UPLOAD_SIZE:
        raise ValidationError("Upload a non-empty file no larger than 10 MB.")
    upload.seek(0)
    try:
        if suffix == ".pdf":
            if not upload.read(8).startswith(b"%PDF-"):
                raise ValidationError("The file is not a PDF.")
            upload.seek(max(0, upload.size - 1024))
            if b"%%EOF" not in upload.read():
                raise ValidationError("The PDF is incomplete.")
            return "application/pdf"
        with Image.open(upload) as image:
            expected = "PNG" if suffix == ".png" else "JPEG"
            if image.format != expected:
                raise ValidationError("Image content does not match its extension.")
            image.verify()
        return "image/png" if suffix == ".png" else "image/jpeg"
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("Upload a valid, safely sized image.") from exc
    finally:
        upload.seek(0)
