"""Public locale metadata API."""
from fastapi import APIRouter

from utils.locale_utils import DEFAULT_LOCALE, LOCALE_CATALOG


router = APIRouter(prefix='/api/locales', tags=['locales'])


@router.get('')
async def list_locales():
    """Return the product locales clients may expose and persist."""
    return {
        'default_locale': DEFAULT_LOCALE,
        'locales': LOCALE_CATALOG,
    }
