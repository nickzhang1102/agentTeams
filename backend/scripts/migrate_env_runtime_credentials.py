"""Import legacy runtime credentials and optionally remove them from ``.env``.

Existing database values win. ``--cleanup-env`` removes legacy lines only after
the transaction commits and a fresh database session verifies usable values.
"""

from __future__ import annotations

import os
import argparse
import re
import tempfile
from pathlib import Path

from config import Config
from db import SessionLocal
from models import LLMModel, SystemConfig


LEGACY_ENV_KEYS = frozenset({
    'LLM_API_KEY',
    'LLM_BASE_URL',
    'LLM_MODEL',
    'LLM_MAX_TOKENS',
    'GRAPHIFY_LLM_API_KEY',
    'GRAPHIFY_LLM_BASE_URL',
    'GRAPHIFY_LLM_MODEL',
    'EXA_API_KEY',
    'TAVILY_API_KEY',
})

_ENV_ASSIGNMENT = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=')


def _legacy_value(key: str) -> str:
    return (os.environ.get(key) or '').strip()


def _verify_database(legacy_values: dict[str, str]) -> None:
    """Refuse cleanup unless every legacy runtime credential has a DB home."""
    session = SessionLocal()
    try:
        model = (
            session.query(LLMModel)
            .filter(LLMModel.is_enabled == True)
            .order_by(LLMModel.is_default.desc(), LLMModel.sort_order, LLMModel.id)
            .first()
        )
        if any(legacy_values.get(key) for key in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL')):
            if not model or not model.api_key or not model.base_url:
                raise RuntimeError('Database does not contain a usable enabled LLM model')

        for key in ('EXA_API_KEY', 'TAVILY_API_KEY'):
            if not legacy_values.get(key):
                continue
            row = session.query(SystemConfig).filter_by(key=key).first()
            if row is None or not row.value:
                raise RuntimeError(f'Database setting {key} is not configured')
    finally:
        session.close()


def _remove_legacy_env_lines(env_path: Path) -> list[str]:
    """Atomically remove managed legacy keys without exposing their values."""
    original = env_path.read_text(encoding='utf-8')
    kept_lines = []
    removed = []
    for line in original.splitlines(keepends=True):
        match = _ENV_ASSIGNMENT.match(line)
        if match and match.group(1) in LEGACY_ENV_KEYS:
            removed.append(match.group(1))
        else:
            kept_lines.append(line)

    if not removed:
        return []

    with tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        newline='',
        dir=env_path.parent,
        prefix=f'.{env_path.name}.',
        suffix='.tmp',
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.writelines(kept_lines)

    try:
        os.replace(temp_path, env_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return sorted(set(removed))


def main(*, cleanup_env: bool = False, env_path: Path | None = None) -> None:
    legacy_values = {key: _legacy_value(key) for key in LEGACY_ENV_KEYS}
    session = SessionLocal()
    imported = []
    try:
        if not session.query(LLMModel).first():
            api_key = _legacy_value('LLM_API_KEY')
            base_url = _legacy_value('LLM_BASE_URL')
            model_id = _legacy_value('LLM_MODEL')
            if api_key and base_url and model_id:
                session.add(LLMModel(
                    model_id=model_id,
                    display_name=model_id,
                    base_url=base_url,
                    api_key=api_key,
                    max_output_tokens=int(_legacy_value('LLM_MAX_TOKENS') or 16384),
                    is_enabled=True,
                    is_default=True,
                ))
                imported.append('LLM model')

        for key, description in (
            ('EXA_API_KEY', 'Exa Web Search API Key'),
            ('TAVILY_API_KEY', 'Tavily Web Search API Key'),
        ):
            value = _legacy_value(key)
            row = session.query(SystemConfig).filter_by(key=key).first()
            if value and (row is None or not row.value):
                if row is None:
                    session.add(SystemConfig(key=key, value=value, description=description))
                else:
                    row.value = value
                imported.append(key)

        session.commit()
        if imported:
            print('Imported: ' + ', '.join(imported))
        else:
            print('Nothing imported; database values already exist or legacy values are empty.')
    finally:
        session.close()

    _verify_database(legacy_values)
    print('Database verification passed.')

    if cleanup_env:
        target = env_path or (Path(__file__).resolve().parents[1] / '.env')
        if not target.exists():
            print(f'No .env file found at {target}; nothing to clean.')
            return
        removed = _remove_legacy_env_lines(target)
        print('Removed legacy .env keys: ' + (', '.join(removed) if removed else 'none'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--cleanup-env',
        action='store_true',
        help='atomically remove legacy runtime keys after database verification',
    )
    parser.add_argument('--env-file', type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    main(cleanup_env=args.cleanup_env, env_path=args.env_file)
