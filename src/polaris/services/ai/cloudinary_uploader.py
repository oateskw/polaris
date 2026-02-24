"""Cloudinary upload utility for hosting videos with correct Content-Type headers."""

from pathlib import Path


def upload_to_cloudinary(local_path: Path, resource_type: str = "video") -> str:
    """Upload a file to Cloudinary and return the secure URL."""
    import cloudinary
    import cloudinary.uploader
    from polaris.config import get_settings

    settings = get_settings()
    if not settings.is_cloudinary_configured:
        raise ValueError("Cloudinary credentials not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in your .env file.")

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
    )

    result = cloudinary.uploader.upload(
        str(local_path),
        resource_type=resource_type,
        folder="polaris",
    )
    return result["secure_url"]
