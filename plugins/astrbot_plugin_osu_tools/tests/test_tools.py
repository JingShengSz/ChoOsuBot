import asyncio
import importlib
import inspect
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import docstring_parser
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
api = importlib.import_module("astrbot_plugin_osu_tools.api")
catalog = importlib.import_module("astrbot_plugin_osu_tools.catalog")
output = importlib.import_module("astrbot_plugin_osu_tools.output")


@pytest.fixture
def registry():
    return catalog.Catalog()


def test_catalogue_unique_permissions(registry):
    assert len(registry.operations) == 120
    assert sum(e["enabled"] for e in registry.operations.values()) == 55
    assert registry.get("getGlobalScores")["path"] == "/scores"
    assert "/playlist/" in registry.get("getPlaylistScores")["path"]
    for entry in registry.operations.values():
        if entry["enabled"]:
            assert entry["method"] == "GET" or entry["id"] == "getBeatmapAttributes"
            assert not set(entry["auth"]) - {"OAuth", "public"}


@pytest.mark.parametrize(
    "operation",
    [
        "createNewPM",
        "sendMessageToChannel",
        "getOwnData",
        "getApiV2Friends",
        "postApiV2Screenshots",
        "revokeCurrentToken",
        "getApiV2ScoresScoreDownload",
    ],
)
def test_account_and_binary_operations_blocked(registry, operation):
    with pytest.raises(catalog.InputError):
        registry.prepare(operation)


@pytest.mark.parametrize(
    "user",
    [
        "../scores",
        "%2e%2e",
        "a?x=1",
        "https://evil.test",
        "user#fragment",
        "foo\\bar",
        "a\n",
    ],
)
def test_path_cannot_escape_endpoint(registry, user):
    with pytest.raises(catalog.InputError):
        registry.prepare("getUser", {"user": user})


def test_optional_username_and_wiki_path(registry):
    assert registry.prepare("getUser", {"user": "@123"})[1] == "/users/%40123"
    assert (
        registry.prepare("getUser", {"user": "@name with space", "mode": "mania"})[1]
        == "/users/%40name%20with%20space/mania"
    )
    assert registry.prepare("getTeam", {"team": "@ABC"})[1] == "/teams/%40ABC"
    assert (
        registry.prepare(
            "getWikiPage", {"locale": "en", "path": "Gameplay/Game_modifier"}
        )[1]
        == "/wiki/en/Gameplay/Game_modifier"
    )


def test_pagination_and_array_encoding(registry):
    params = registry.prepare(
        "getRanking",
        {"mode": "mania", "type": "performance"},
        {"cursor": {"page": 2}, "country": "CN"},
    )[2]
    assert ("cursor[page]", "2") in params
    assert registry.prepare("getUsers", query_params={"ids[]": [1, 2]})[2] == [
        ("ids[]", "1"),
        ("ids[]", "2"),
    ]
    with pytest.raises(catalog.InputError):
        registry.prepare("getUserScores", {"user": 1, "type": "best"}, {"limit": 100})
    with pytest.raises(catalog.InputError):
        registry.prepare("getUser", {"user": 1}, {"access_token": "bad"})


def test_attributes_mod_settings_preserved(registry):
    body = {
        "mods": [{"acronym": "DT", "settings": {"speed_change": 1.2}}],
        "ruleset": "mania",
    }
    op, path, _, actual = registry.prepare(
        "getBeatmapAttributes", {"beatmap": 5111622}, body=body
    )
    assert op["method"] == "POST"
    assert path == "/beatmaps/5111622/attributes"
    assert actual == body
    with pytest.raises(catalog.InputError):
        registry.prepare(
            "getBeatmapAttributes", {"beatmap": 1}, body={"client_secret": "x"}
        )


def test_output_projection_and_bounded_valid_json():
    value = {
        "cursor_string": "NEXT",
        "scores": [{"id": i, "description": "密" * 9000} for i in range(100)],
    }
    text = output.render(value)
    result = json.loads(text)
    assert len(text) <= 24000
    assert result["truncated"]
    assert result["paging"]["cursor_string"] == "NEXT"
    assert output.project(value, "scores.id") == {
        "scores": [{"id": i} for i in range(100)]
    }


@pytest.fixture
def client(tmp_path):
    credential = tmp_path / "synthetic.json"
    credential.write_text(
        json.dumps({"client_id": "12", "client_secret": "SYNTHETIC-SECRET"}),
        encoding="utf-8",
    )
    instance = api.OsuClient(credential)
    return instance


@pytest.mark.asyncio
async def test_cache_and_concurrent_singleflight(client):
    async def http(method, url, **kwargs):
        await asyncio.sleep(0.001)
        if url == api.TOKEN_URL:
            return 200, {"access_token": "TOKEN", "expires_in": 3600}, None
        return 200, {"id": 1}, None

    client._http = AsyncMock(side_effect=http)
    values = await asyncio.gather(
        *(client.query("GET", "/users/1", [], {}) for _ in range(8))
    )
    assert all(v[0] == {"id": 1} for v in values)
    assert client._http.await_count == 2
    assert (await client.query("GET", "/users/1", [], {}))[1] is True
    assert client._http.await_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_401_refresh_once_and_no_secret_echo(client):
    client._http = AsyncMock(
        side_effect=[
            (200, {"access_token": "OLD", "expires_in": 3600}, None),
            (401, {"danger": "SYNTHETIC-SECRET"}, None),
            (200, {"access_token": "NEW", "expires_in": 3600}, None),
            (401, {"danger": "SYNTHETIC-SECRET"}, None),
        ]
    )
    with pytest.raises(api.APIError) as error:
        await client.query("GET", "/users/1", [], {})
    assert client._http.await_count == 4
    assert error.value.status == 401
    assert "SECRET" not in str(error.value)


@pytest.mark.asyncio
async def test_long_retry_after_not_retried_immediately(client):
    client._http = AsyncMock(return_value=(429, None, "120"))
    with pytest.raises(api.APIError) as error:
        await client.query("GET", "/news", [], {}, authenticated=False)
    assert error.value.code == "rate_limited"
    assert client._http.await_count == 1
    with pytest.raises(api.APIError) as error:
        await client.query("GET", "/news", [], {}, authenticated=False)
    assert error.value.code == "rate_limited"
    assert client._http.await_count == 1


@pytest.mark.asyncio
async def test_http_disables_redirects_and_never_reads_error_body(client):
    class Response:
        status = 302

        def __init__(self):
            self.headers = {"Location": "https://elsewhere.test"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @property
        def content(self):
            raise AssertionError("An error response body must not be read")

    calls = []

    class Session:
        closed = False

        def request(self, method, url, **kwargs):
            calls.append(kwargs)
            return Response()

    client._session = Session()
    client._rate_wait = AsyncMock()
    status, data, _ = await client._http(
        "GET", api.API_BASE + "/users/1", token="SECRET"
    )
    assert status == 302 and data is None
    assert calls[0]["allow_redirects"] is False
    assert calls[0]["headers"] == {"Authorization": "Bearer SECRET"}


@pytest.mark.asyncio
async def test_public_endpoint_without_credentials(tmp_path):
    instance = api.OsuClient(tmp_path / "missing.json")
    instance._http = AsyncMock(return_value=(200, {"news_posts": []}, None))
    data, _ = await instance.query("GET", "/news", [], {}, authenticated=False)
    assert data == {"news_posts": []}
    assert instance._http.call_args.kwargs["token"] is None


@pytest.mark.asyncio
async def test_missing_credentials_safe_error(tmp_path):
    instance = api.OsuClient(tmp_path / "PRIVATE_PATH.json")
    with pytest.raises(api.APIError) as error:
        await instance.query("GET", "/users/1", [], {})
    assert error.value.code == "credential_error"
    assert "PRIVATE_PATH" not in str(error.value)


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    # No AstrBot dependency for transport tests. Real framework import is checked
    # separately in tools/smoke_server.py on the user's existing installation.
    for name in (
        "astrbot",
        "astrbot.api",
        "astrbot.api.star",
        "astrbot.api.event",
        "astrbot.core",
        "astrbot.core.utils",
        "astrbot.core.utils.astrbot_path",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["astrbot.api"].AstrBotConfig = dict
    event = sys.modules["astrbot.api.event"]
    event.AstrMessageEvent = object

    def decorator(*args, **kwargs):
        def apply(fn):
            if "name" in kwargs:
                fn.tool_name = kwargs["name"]
            return fn

        return apply

    event.filter = types.SimpleNamespace(
        llm_tool=decorator,
        command=decorator,
        permission_type=decorator,
        PermissionType=types.SimpleNamespace(ADMIN="admin"),
    )
    # This suite covers transport and tool schemas. The command adapter itself
    # is exercised against the real AstrBot framework by test_command_case.py.
    command_adapter = types.ModuleType("astrbot_plugin_osu_tools.command_filter")
    command_adapter.command = decorator
    monkeypatch.setitem(sys.modules,command_adapter.__name__,command_adapter)
    star = sys.modules["astrbot.api.star"]

    class Star:
        def __init__(self, context):
            self.context = context

    star.Star, star.Context = Star, object
    sys.modules["astrbot.core.utils.astrbot_path"].get_astrbot_data_path = lambda: str(
        tmp_path
    )
    monkeypatch.delitem(sys.modules, "astrbot_plugin_osu_tools.main", raising=False)
    module = importlib.import_module("astrbot_plugin_osu_tools.main")
    return module.OsuTools(None, {})


def test_tool_docstrings_schema(plugin):
    tools = [
        fn
        for _, fn in inspect.getmembers(plugin, inspect.ismethod)
        if hasattr(fn, "tool_name")
    ]
    assert len(tools) == 9
    for fn in tools:
        doc = docstring_parser.parse(fn.__doc__)
        args = set(inspect.signature(fn).parameters) - {"event"}
        assert {p.arg_name for p in doc.params} == args
        assert all(
            p.type_name in {"string", "number", "object", "boolean"} for p in doc.params
        )


@pytest.mark.asyncio
async def test_player_summary_uses_total_pp_and_team(plugin):
    plugin.client.query = AsyncMock(
        return_value=(
            {
                "id": 3,
                "username": "Alice",
                "avatar_url": "https://a.ppy.sh/3",
                "statistics": {"pp": 9486},
                "team": {"id": 2, "name": "Team"},
            },
            False,
        )
    )
    result = json.loads(await plugin.user(None, "Alice", "mania"))
    assert result["ok"]
    assert result["data"]["statistics"]["pp"] == 9486
    assert result["data"]["team"]["id"] == 2
    assert plugin.client.query.call_args.args[1] == "/users/%40Alice/mania"


@pytest.mark.asyncio
async def test_score_type_and_attribute_wrapper(plugin):
    plugin.client.query = AsyncMock(
        return_value=({"attributes": {"star_rating": 11.07}}, False)
    )
    result = json.loads(await plugin.attributes(None, "5111622", '["DT"]', "mania"))
    assert result["data"]["attributes"]["star_rating"] == 11.07
    assert plugin.client.query.call_args.args[3] == {"mods": ["DT"], "ruleset": "mania"}
    invalid = json.loads(await plugin.user_scores(None, "1", "all"))
    assert invalid["error"] == "invalid_argument"


@pytest.mark.asyncio
async def test_ranking_wrapper_encodes_page(plugin):
    plugin.client.query = AsyncMock(return_value=({"ranking": []}, False))
    assert json.loads(await plugin.rankings(None, page=2))["ok"]
    assert plugin.client.query.call_args.args[2] == [("cursor[page]", "2")]


def test_official_url_id_parsing(plugin):
    resource = sys.modules[plugin.__module__].resource
    assert (
        resource("https://osu.ppy.sh/beatmapsets/123#mania/4550525", "beatmaps")
        == "4550525"
    )
    assert resource("https://osu.ppy.sh/users/Alice", "users") == "@Alice"
    assert resource("@123", "users") == "@123"
    with pytest.raises(catalog.InputError):
        resource("https://osu.ppy.sh.evil.test/users/1", "users")
