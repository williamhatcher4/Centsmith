from typing import List
from pydantic import BaseModel, field_validator

from app.models.user_settings import SYSTEM_CATEGORIES

ALL_PAGE_SLUGS: frozenset[str] = frozenset(
    {"/", "/inbox", "/personal-inbox", "/transactions", "/spending", "/exports", "/statements"}
)


class UserSettingsOut(BaseModel):
    personal_categories: List[str]
    hidden_pages: List[str]

    model_config = {"from_attributes": True}


class UserSettingsUpdate(BaseModel):
    personal_categories: List[str]
    hidden_pages: List[str]

    @field_validator("personal_categories")
    @classmethod
    def validate_categories(cls, value: List[str]) -> List[str]:
        cleaned = [c.strip() for c in value]
        seen: set[str] = set()
        for cat in cleaned:
            if not cat:
                raise ValueError("Category names cannot be empty")
            if len(cat) > 80:
                raise ValueError(f"Category name exceeds 80 characters: '{cat[:30]}'")
            lower = cat.lower()
            if lower in seen:
                raise ValueError(f"Duplicate category: '{cat}'")
            seen.add(lower)
        missing = SYSTEM_CATEGORIES - set(cleaned)
        if missing:
            raise ValueError(
                f"System categories cannot be removed: {', '.join(sorted(missing))}"
            )
        return cleaned

    @field_validator("hidden_pages")
    @classmethod
    def validate_hidden_pages(cls, value: List[str]) -> List[str]:
        for page in value:
            if page not in ALL_PAGE_SLUGS:
                raise ValueError(f"Unknown page slug: '{page}'")
        if set(value) >= ALL_PAGE_SLUGS:
            raise ValueError("At least one page must remain visible")
        return list(dict.fromkeys(value))  # deduplicate, preserve order
