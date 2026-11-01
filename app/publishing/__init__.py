"""Wear & Wonder Stage 6 Publishing & Metadata Package."""
from app.publishing.metadata_generator import (
    generate_publishing_metadata,
    get_recommended_thumbnail,
)
from app.publishing.publishing_service import (
    get_or_create_publishing_record,
    refresh_publishing_metadata,
    update_publishing_metadata,
    set_recommended_thumbnail_choice,
    save_and_approve_publishing_package,
    import_assembled_video,
    import_custom_thumbnail,
    set_master_image_as_thumbnail,
    approve_and_schedule_video,
    record_manual_publication,
)
from app.publishing.youtube_publisher import (
    check_youtube_auth_status,
    publish_to_youtube,
)
from app.publishing.instagram_publisher import (
    check_instagram_auth_status,
    publish_to_instagram,
)

__all__ = [
    "generate_publishing_metadata",
    "get_recommended_thumbnail",
    "get_or_create_publishing_record",
    "refresh_publishing_metadata",
    "update_publishing_metadata",
    "set_recommended_thumbnail_choice",
    "save_and_approve_publishing_package",
    "import_assembled_video",
    "import_custom_thumbnail",
    "set_master_image_as_thumbnail",
    "approve_and_schedule_video",
    "record_manual_publication",
    "check_youtube_auth_status",
    "publish_to_youtube",
    "check_instagram_auth_status",
    "publish_to_instagram",
]
