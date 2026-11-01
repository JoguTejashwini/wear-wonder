"""Wear & Wonder Stage 6 Publishing & Scheduling Package."""
from app.publishing.metadata_generator import (
    generate_publishing_metadata,
)
from app.publishing.youtube_publisher import (
    check_youtube_auth_status,
    publish_to_youtube,
)
from app.publishing.instagram_publisher import (
    check_instagram_auth_status,
    publish_to_instagram,
)
from app.publishing.publishing_service import (
    get_or_create_publishing_record,
    import_assembled_video,
    import_custom_thumbnail,
    set_master_image_as_thumbnail,
    update_publishing_metadata,
    refresh_publishing_metadata,
    approve_and_schedule_video,
    record_manual_publication,
)

__all__ = [
    "generate_publishing_metadata",
    "check_youtube_auth_status",
    "publish_to_youtube",
    "check_instagram_auth_status",
    "publish_to_instagram",
    "get_or_create_publishing_record",
    "import_assembled_video",
    "import_custom_thumbnail",
    "set_master_image_as_thumbnail",
    "update_publishing_metadata",
    "refresh_publishing_metadata",
    "approve_and_schedule_video",
    "record_manual_publication",
]
