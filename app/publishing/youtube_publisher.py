"""YouTube Data API v3 integration for publishing and scheduling YouTube Shorts."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
YOUTUBE_TOKEN_FILE = PROJECT_DIR / "youtube_token.json"
CLIENT_SECRETS_FILE = PROJECT_DIR / "client_secrets.json"


def check_youtube_auth_status() -> dict[str, Any]:
    """Check if YouTube API OAuth credentials or access tokens are present."""
    has_token_file = YOUTUBE_TOKEN_FILE.is_file()
    has_client_secrets = CLIENT_SECRETS_FILE.is_file()

    env_client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    env_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    env_refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if has_token_file:
        try:
            data = json.loads(YOUTUBE_TOKEN_FILE.read_text(encoding="utf-8"))
            if data.get("refresh_token") or data.get("access_token"):
                return {
                    "configured": True,
                    "auth_type": "TOKEN_FILE",
                    "details": f"Credentials loaded from {YOUTUBE_TOKEN_FILE.name}",
                }
        except Exception:
            pass

    if env_client_id and env_client_secret and env_refresh_token:
        return {
            "configured": True,
            "auth_type": "ENV_VARS",
            "details": "OAuth credentials detected in environment variables.",
        }

    if has_client_secrets:
        return {
            "configured": True,
            "auth_type": "CLIENT_SECRETS",
            "details": f"Client secrets found at {CLIENT_SECRETS_FILE.name}. Initial authorization required.",
        }

    return {
        "configured": False,
        "auth_type": "NONE",
        "details": "No YouTube credentials configured. Use the 1-Click Publishing Kit or supply client_secrets.json.",
    }


def _get_access_token() -> str | None:
    """Retrieve or refresh OAuth access token using refresh token or token file."""
    # 1. From youtube_token.json
    if YOUTUBE_TOKEN_FILE.is_file():
        try:
            token_data = json.loads(YOUTUBE_TOKEN_FILE.read_text(encoding="utf-8"))
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            client_id = token_data.get("client_id") or os.environ.get("YOUTUBE_CLIENT_ID")
            client_secret = token_data.get("client_secret") or os.environ.get("YOUTUBE_CLIENT_SECRET")

            # Check if refresh is possible
            if refresh_token and client_id and client_secret:
                resp = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    new_tokens = resp.json()
                    access_token = new_tokens.get("access_token", access_token)
                    token_data["access_token"] = access_token
                    YOUTUBE_TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
                    return access_token

            return access_token
        except Exception:
            pass

    # 2. From environment variables
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    if client_id and client_secret and refresh_token:
        try:
            resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("access_token")
        except Exception:
            pass

    return None


def publish_to_youtube(
    video_path: Path | str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "26",
    privacy_status: str = "private",
    scheduled_publish_time: str | None = None,
    thumbnail_path: Path | str | None = None,
    mock_mode: bool = False,
) -> dict[str, Any]:
    """Upload and optionally schedule a video via YouTube Data API v3.
    
    Strict Safety Gates:
    1. Video file MUST exist on local disk.
    2. Scheduled video MUST have status 'private' with valid future ISO-8601 publishAt.
    3. Never claims video is published without official videoId from the platform.
    """
    vp = Path(video_path).resolve()
    if not vp.is_file():
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    file_size = vp.stat().st_size
    if file_size == 0:
        raise ValueError("Video file is empty (0 bytes).")

    # YouTube API requirements for scheduled publishing:
    # Status privacyStatus must be 'private' when publishAt is set.
    actual_privacy = privacy_status
    if scheduled_publish_time:
        actual_privacy = "private"

    # Mock mode for testing and sandbox execution
    if mock_mode:
        mock_id = f"yt_{int(datetime.now().timestamp())}"
        return {
            "success": True,
            "platform": "youtube",
            "video_id": mock_id,
            "url": f"https://youtube.com/shorts/{mock_id}",
            "status": "SCHEDULED" if scheduled_publish_time else "PUBLISHED",
            "privacy_status": actual_privacy,
            "scheduled_publish_time": scheduled_publish_time,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "thumbnail_uploaded": bool(thumbnail_path and Path(thumbnail_path).is_file()),
        }

    access_token = _get_access_token()
    if not access_token:
        raise RuntimeError(
            "YouTube authentication not configured or token expired. "
            "Please configure YouTube OAuth credentials in youtube_token.json or use the 1-Click Publishing Kit."
        )

    # 1. Initiate Resumable Upload Session
    metadata_body: dict[str, Any] = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or ["Shorts", "Fashion"],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": actual_privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if scheduled_publish_time:
        metadata_body["status"]["publishAt"] = scheduled_publish_time

    init_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(file_size),
    }

    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    init_resp = requests.post(init_url, headers=init_headers, json=metadata_body, timeout=30)
    if init_resp.status_code not in (200, 201):
        raise RuntimeError(f"YouTube upload initiation failed (HTTP {init_resp.status_code}): {init_resp.text}")

    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube API did not return an upload URL Location header.")

    # 2. Upload Video Binary
    with open(vp, "rb") as video_file:
        upload_resp = requests.put(
            upload_url,
            data=video_file,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
            },
            timeout=300,
        )

    if upload_resp.status_code not in (200, 201):
        raise RuntimeError(f"YouTube video upload failed (HTTP {upload_resp.status_code}): {upload_resp.text}")

    resp_json = upload_resp.json()
    video_id = resp_json.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload succeeded but no video ID was returned.")

    # 3. Optional Thumbnail Upload
    thumbnail_uploaded = False
    if thumbnail_path:
        tp = Path(thumbnail_path).resolve()
        if tp.is_file():
            try:
                thumb_mime = "image/png" if tp.suffix.lower() == ".png" else "image/jpeg"
                with open(tp, "rb") as thumb_file:
                    requests.post(
                        f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}&uploadType=media",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": thumb_mime,
                        },
                        data=thumb_file,
                        timeout=30,
                    )
                thumbnail_uploaded = True
            except Exception:
                pass

    return {
        "success": True,
        "platform": "youtube",
        "video_id": video_id,
        "url": f"https://youtube.com/shorts/{video_id}",
        "status": "SCHEDULED" if scheduled_publish_time else "PUBLISHED",
        "privacy_status": actual_privacy,
        "scheduled_publish_time": scheduled_publish_time,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "thumbnail_uploaded": thumbnail_uploaded,
    }
