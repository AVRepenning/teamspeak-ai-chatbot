"""Queue activity notices and enforce official sources for Danish weather."""
import json
import os
import re
from pathlib import Path
import uuid
import time
from urllib.parse import urlsplit

STATE_DIR = Path(os.getenv("SKYNET_STATE_DIR", "/home/dammeserver/skynet-ts6/runtime"))

_WEATHER_TERMS = re.compile(
    r"\b(?:weather|vejret?|vejrudsigt(?:en)?|forecast|temperatur(?:en)?|temperature|"
    r"nedbør|precipitation|rainfall|regn)\b",
    re.IGNORECASE,
)
_DANMARK_TERMS = re.compile(
    r"\b(?:denmark|danmark|københavn|copenhagen|næstved|naestved|aarhus|århus|"
    r"aalborg|ålborg|odense|esbjerg|randers|kolding|horsens|vejle|roskilde|herning|"
    r"silkeborg|helsingør|helsingor|hillerød|hillerod|fredericia|køge|koege|holbæk|"
    r"holbaek|sønderborg|sonderborg|viborg|ringsted)\b",
    re.IGNORECASE,
)
_WEATHER_TURNS: dict[str, bool] = {}
_ALLOWED_WEATHER_HOSTS = ("dmi.dk", "met.no", "yr.no")


def guard_weather_sources(tool_name="", args=None, turn_id="", task_id="", session_id="", **_):
    """Force Danish-weather searches to DMI and keep extraction on official providers."""
    if not isinstance(args, dict):
        return None
    turn_key = str(turn_id or task_id or session_id or "")
    if tool_name == "web_search":
        query = " ".join(str(args.get("query", "")).split())
        is_danish_weather = bool(_WEATHER_TERMS.search(query) and _DANMARK_TERMS.search(query))
        if not is_danish_weather:
            if turn_key:
                _WEATHER_TURNS.pop(turn_key, None)
            return None
        already_searched_dmi = bool(_WEATHER_TURNS.get(turn_key)) if turn_key else False
        if turn_key:
            _WEATHER_TURNS[turn_key] = True
            if len(_WEATHER_TURNS) > 256:
                _WEATHER_TURNS.pop(next(iter(_WEATHER_TURNS)))
        fallback_domain = None
        lower_query = query.casefold()
        if "met.no" in lower_query or "met norway" in lower_query:
            fallback_domain = "met.no"
        elif "yr.no" in lower_query:
            fallback_domain = "yr.no"
        if fallback_domain and already_searched_dmi:
            cleaned = re.sub(r"\bsite:[^\s]+\s*", "", query, flags=re.IGNORECASE).strip()
            return {"action": "modify", "args": {**args, "query": f"site:{fallback_domain} {cleaned}".strip()}}
        cleaned = re.sub(r"\bsite:[^\s]+\s*", "", query, flags=re.IGNORECASE).strip()
        return {"action": "modify", "args": {**args, "query": f"site:dmi.dk {cleaned}".strip()}}

    if tool_name == "web_extract" and turn_key in _WEATHER_TURNS:
        supplied = args.get("urls")
        urls = supplied if isinstance(supplied, list) else ([supplied] if isinstance(supplied, str) else [])
        allowed = []
        for value in urls:
            parsed = urlsplit(str(value))
            host = (parsed.hostname or "").lower()
            if parsed.scheme in {"http", "https"} and any(
                host == domain or host.endswith("." + domain) for domain in _ALLOWED_WEATHER_HOSTS
            ):
                allowed.append(value)
        if not allowed:
            return {
                "action": "block",
                "message": "For Danish weather, use DMI first; only MET Norway or Yr are approved fallbacks.",
            }
        if allowed != urls:
            return {"action": "modify", "args": {**args, "urls": allowed}}
    return None


def notify(tool_name="", args=None, result=None, **_):
    if tool_name not in {"memory", "skill_manage", "web_search", "web_extract"} or not isinstance(args, dict):
        return
    try:
        outcome = json.loads(result) if isinstance(result, str) else result
    except (ValueError, TypeError):
        return
    if not isinstance(outcome, dict):
        return
    if tool_name == "web_search":
        hits = outcome.get("data", {}).get("web", []) if isinstance(outcome.get("data"), dict) else []
        query = " ".join(str(args.get("query", "")).split())[:100]
        if not hits or not query or outcome.get("error"):
            return
        event = {"kind": "web_search", "query": query}
    elif tool_name == "web_extract":
        results = outcome.get("results")
        if not isinstance(results, list):
            return
        hosts = []
        for item in results:
            if not isinstance(item, dict) or item.get("error") or not item.get("content"):
                continue
            url = urlsplit(str(item.get("url", "")))
            if url.scheme in {"http", "https"} and url.hostname and url.hostname not in hosts:
                hosts.append(url.hostname[:100])
        if not hosts:
            return
        event = {"kind": "web_extract", "hosts": hosts[:4]}
    elif outcome.get("success") is not True or outcome.get("staged"):
        return
    elif tool_name == "memory":
        kind = "memory"
        action = args.get("action", "batch")
        if action not in {"add", "replace", "remove", "batch"}:
            return
        name = ""
    else:
        kind = "skill"
        operations = args.get("operations")
        if not isinstance(operations, list) or not operations:
            return
        action = operations[0].get("action", "")
        name = operations[0].get("name", "")
        if action not in {"create", "patch", "write_file", "remove_file", "delete"} or not name:
            return
    if tool_name in {"memory", "skill_manage"}:
        event = {"kind": kind, "action": action, "name": str(name)[:64]}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    token = f"{time.time_ns():019d}-{uuid.uuid4().hex}"
    temporary = STATE_DIR / (".notify-" + token)
    destination = STATE_DIR / ("notify-" + token + ".json")
    try:
        temporary.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def register(ctx):
    ctx.register_hook("pre_tool_call", guard_weather_sources)
    ctx.register_hook("post_tool_call", notify)
