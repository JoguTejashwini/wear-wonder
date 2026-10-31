"""Outfit styling package for Wear & Wonder."""
from app.styling.outfit_generator import generate_outfit_proposals
from app.styling.outfit_service import (
    approve_all_outfits,
    approve_single_outfit,
    edit_outfit,
    reject_single_outfit,
)
from app.styling.outfit_validator import (
    VALIDATION_DIMENSIONS,
    check_outfit_distinctness,
    validate_outfit_record,
)

__all__ = [
    "generate_outfit_proposals",
    "edit_outfit",
    "approve_single_outfit",
    "reject_single_outfit",
    "approve_all_outfits",
    "validate_outfit_record",
    "check_outfit_distinctness",
    "VALIDATION_DIMENSIONS",
]
