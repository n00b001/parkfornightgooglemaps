"""
Normalizer module.

Normalizes scraped place/review data, translates text to English,
and builds lookup tables (place types, services, activities).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from translator import translate_text  # type: ignore[import-not-found]

logger = logging.getLogger("pipeline")


def _str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def pick_or_translate(descriptions: dict[str, str]) -> dict[str, Any]:
    """Given {lang: text}, produce {default, _original}."""
    originals = {lang: (text or "").strip() for lang, text in descriptions.items()}
    lang_priority = ["en", "fr", "de", "es", "it", "nl"]

    english_text = ""
    for lang in lang_priority:
        candidate = originals.get(lang, "")
        if candidate:
            if lang == "en":
                english_text = candidate
            else:
                english_text = translate_text(candidate)
            break

    if not english_text:
        for text in originals.values():
            if text:
                english_text = translate_text(text)
                break

    return {
        "default": english_text,
        "_original": {k: v for k, v in originals.items() if v},
    }


def normalize_place(place: dict) -> dict | None:
    """Normalize a single place record."""
    place_id = int(place.get("id", 0))
    if not place_id:
        return None

    title = _str(place.get("title"))
    name = _str(place.get("name"))

    # Descriptions
    raw_descriptions: dict[str, str] = place.get("descriptions") or {}
    if not isinstance(raw_descriptions, dict):
        raw_descriptions = {}
    top_level_desc = _str(place.get("description"))
    if top_level_desc and "en" not in raw_descriptions:
        raw_descriptions.setdefault("en", top_level_desc)
    descriptions = pick_or_translate(raw_descriptions)

    # Type
    raw_type = place.get("type", {})
    if isinstance(raw_type, dict):
        type_code = raw_type.get("code", "")
        type_label = raw_type.get("label", "")
    else:
        type_code = str(raw_type)
        type_label = ""

    # Address
    raw_address = place.get("address", {})
    if not isinstance(raw_address, dict):
        raw_address = {}
    address = {
        "street": _str(raw_address.get("street")),
        "city": _str(raw_address.get("city")),
        "zipcode": _str(raw_address.get("zipcode") or raw_address.get("code_postal")),
        "country": _str(raw_address.get("country")),
        "country_iso": _str(raw_address.get("country_iso")),
    }

    # Pricing
    raw_pricing = place.get("pricing", {})
    if not isinstance(raw_pricing, dict):
        raw_pricing = {}
    pricing: dict[str, str] = {}
    for key in ("parking", "services"):
        value = _str(raw_pricing.get(key)).lower()
        mapping = {"gratuit": "free", "payant": "paid", "sur demande": "on request"}
        if value in mapping:
            value = mapping[value]
        elif value and value not in ("free", "paid", "on request"):
            translated = translate_text(value)
            if translated.lower() != value:
                value = translated.lower()
        pricing[key] = value

    # Access
    raw_access = place.get("access", {})
    if not isinstance(raw_access, dict):
        raw_access = {}
    access = {
        "public": bool(place.get("is_public") or raw_access.get("public") in (True, "1", 1)),
        "height_limit": _str(raw_access.get("height_limit")),
        "parking_places": _str(raw_access.get("parking_places")),
    }

    # Contact
    raw_contact = place.get("contact", {})
    if not isinstance(raw_contact, dict):
        raw_contact = {}
    contact = {
        "phone": _str(raw_contact.get("phone")),
        "email": _str(raw_contact.get("email")),
        "website": _str(raw_contact.get("website")),
        "video": _str(raw_contact.get("video")),
    }

    # Services & Activities
    services = place.get("services") or []
    activities = place.get("activities") or []
    if not isinstance(services, list):
        services = []
    if not isinstance(activities, list):
        activities = []

    # Photos
    photos = place.get("photos") or []
    if not isinstance(photos, list):
        photos = []
    normalized_photos: list[dict] = []
    for photo in photos:
        if not isinstance(photo, dict):
            continue
        normalized_photos.append(
            {
                "id": str(photo.get("id", "")),
                "numero": photo.get("numero"),
                "path_thumb": photo.get("path_thumb") or photo.get("url_thumb", ""),
                "path_large": photo.get("path_large") or photo.get("url_large", ""),
            }
        )

    # Owner
    raw_owner = place.get("owner", {})
    if not isinstance(raw_owner, dict):
        raw_owner = {}

    return {
        "id": place_id,
        "title": title,
        "name": name,
        "descriptions": descriptions,
        "latitude": float(place.get("latitude") or 0),
        "longitude": float(place.get("longitude") or 0),
        "type_code": type_code,
        "type_label": type_label,
        "address": address,
        "pricing": pricing,
        "access": access,
        "contact": contact,
        "services": services,
        "activities": activities,
        "photos": normalized_photos,
        "rating": float(place["rating"]) if place.get("rating") is not None else None,
        "review_count": int(place.get("review_count") or 0),
        "photo_count": int(place.get("photo_count") or len(normalized_photos)),
        "visit_count": int(place.get("visit_count") or 0),
        "is_public": access["public"],
        "is_protected_nature": bool(place.get("is_protected_nature")),
        "is_top_list": bool(place.get("is_top_list")),
        "online_booking": bool(place.get("online_booking")),
        "owner_username": _str(raw_owner.get("username")),
        "owner_user_id": _str(raw_owner.get("user_id")),
        "owner_vehicle_type": _str(raw_owner.get("vehicle_type")),
        "created_at": _str(place.get("created_at")),
        "closed_at": _str(place.get("closed_at")),
        "scraped_at": _str(place.get("scraped_at")),
    }


def normalize_review(review: dict) -> dict | None:
    """Normalize a single review record."""
    review_id = review.get("id")
    if not review_id:
        return None

    place_id = int(review.get("place_id", 0))
    if not place_id:
        return None

    raw_text = _str(review.get("text"))
    if raw_text:
        translated = translate_text(raw_text)
        review_text = {"default": translated, "_original": raw_text}
    else:
        review_text = {"default": "", "_original": ""}

    author = review.get("author", {})
    if not isinstance(author, dict):
        author = {}
    author_data = {
        "name": _str(author.get("name")),
        "id": _str(author.get("id")),
        "vehicle_type": _str(author.get("vehicle_type")),
    }

    social = review.get("social", {})
    if not isinstance(social, dict):
        social = {}

    return {
        "id": str(review_id),
        "place_id": place_id,
        "rating": int(review.get("rating") or 0),
        "text": review_text,
        "author": author_data,
        "social": {
            "website": _str(social.get("website")),
            "facebook": _str(social.get("facebook")),
            "twitter": _str(social.get("twitter")),
            "instagram": _str(social.get("instagram")),
        },
        "created_at": _str(review.get("created_at")),
        "scraped_at": _str(review.get("scraped_at")),
    }


def build_place_types(places: list[dict]) -> list[dict]:
    """Extract unique place types."""
    seen: dict[str, dict] = {}
    for place in places:
        code = place.get("type_code", "")
        label = place.get("type_label", "")
        if code and code not in seen:
            seen[code] = {"code": code, "english_name": label or code}
    return list(seen.values())


def build_services(places: list[dict]) -> list[dict]:
    """Extract unique service codes."""
    seen: dict[str, dict] = {}
    for place in places:
        for svc in place.get("services", []):
            if isinstance(svc, dict):
                code = svc.get("code", "")
                label = svc.get("label", "")
                if code and code not in seen:
                    seen[code] = {"code": code, "label": label or code}
    return list(seen.values())


def build_activities(places: list[dict]) -> list[dict]:
    """Extract unique activity codes."""
    seen: dict[str, dict] = {}
    for place in places:
        for act in place.get("activities", []):
            if isinstance(act, dict):
                code = act.get("code", "")
                label = act.get("label", "")
                if code and code not in seen:
                    seen[code] = {"code": code, "label": label or code}
    return list(seen.values())


def build_vehicle_types(places: list[dict], reviews: list[dict]) -> list[dict]:
    """Extract unique vehicle type codes."""
    seen: dict[str, dict] = {}
    for place in places:
        vt = place.get("owner_vehicle_type", "")
        if vt and vt not in seen:
            seen[vt] = {"code": vt}
    for review in reviews:
        author = review.get("author", {})
        if isinstance(author, dict):
            vt = author.get("vehicle_type", "")
            if vt and vt not in seen:
                seen[vt] = {"code": vt}
    return list(seen.values())
