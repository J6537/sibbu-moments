"""Duenner Wrapper um die OpenAI Responses API mit Retry/Backoff.

Angelehnt an das Retry-Muster des bestehenden Content_Agent
(Medienprojekte/_intern/openai_client.py), aber eigenstaendig implementiert
-- kein Import aus dem fremden, nur lesend zu verwendenden Content_Agent-Repo.
"""

import time

from openai import (
    OpenAI,
    APIConnectionError,
    InternalServerError,
    RateLimitError,
)

from . import config

TRANSIENTE_FEHLER = (APIConnectionError, RateLimitError, InternalServerError)

_client = None


class MissingApiKeyError(RuntimeError):
    pass


def get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client

    api_key = config.resolve_openai_api_key()
    if not api_key:
        raise MissingApiKeyError(
            "Kein OpenAI-API-Key gefunden. Setze die Umgebungsvariable "
            f"{config.OPENAI_API_KEY_ENV} oder lege {config.LOCAL_ENV_FILE} "
            f"mit '{config.OPENAI_API_KEY_ENV}=...' an (nicht versioniert)."
        )

    _client = OpenAI(api_key=api_key)
    return _client


def call_responses(**kwargs):
    """Ruft client.responses.create(**kwargs) mit Retry/Backoff bei
    transienten Fehlern auf."""
    client = get_client()
    letzter_fehler = None

    for versuch in range(1, config.OPENAI_MAX_VERSUCHE + 1):
        try:
            return client.responses.create(**kwargs)
        except TRANSIENTE_FEHLER as fehler:
            letzter_fehler = fehler
            if versuch == config.OPENAI_MAX_VERSUCHE:
                break
            index = min(versuch - 1, len(config.OPENAI_WARTEZEITEN_SEKUNDEN) - 1)
            wartezeit = config.OPENAI_WARTEZEITEN_SEKUNDEN[index]
            print(f"OpenAI-Aufruf fehlgeschlagen (Versuch {versuch}/{config.OPENAI_MAX_VERSUCHE}): {fehler}")
            print(f"Erneuter Versuch in {wartezeit}s...")
            time.sleep(wartezeit)

    raise letzter_fehler


def json_schema_format(name: str, schema: dict, strict: bool = True) -> dict:
    """Baut den 'text'-Parameter fuer strukturierte JSON-Ausgaben ueber die
    Responses API (OpenAI Structured Outputs)."""
    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "schema": schema,
            "strict": strict,
        }
    }
