"""
utils/sanitize.py

Utility functions and mixins for sanitizing user input to prevent XSS and unsafe HTML.
"""

import bleach
from pydantic import BaseModel, field_validator
from pydantic_core.core_schema import FieldValidationInfo

# Define what HTML tags and attributes (if any) you want to allow.
ALLOWED_TAGS = []  # e.g., ["b", "i", "u", "em", "strong"] if you want minimal formatting
ALLOWED_ATTRIBUTES = {}
ALLOWED_STYLES = []


def sanitize_text(user_input: str, max_length: int = 500) -> str:
    """
    Clean user input to prevent XSS and enforce length limits.
    """
    if not user_input:
        return ""

    trimmed = user_input[:max_length]

    cleaned = bleach.clean(
        trimmed,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True
    )

    return cleaned.strip()


class SanitizedModel(BaseModel):
    """
    Base model mixin that automatically sanitizes all string fields,
    except for sensitive ones like passwords.
    Extend this in your Pydantic schemas.
    """

    @field_validator("*", mode="before")
    def sanitize_all_strings(cls, v, info: FieldValidationInfo):
        if isinstance(v, str):
            # Skip sanitization for password fields
            if info.field_name == "password":
                return v
            return sanitize_text(v, max_length=1000)
        return v
