"""Mamestagram public API, preserving native Stable/Lazer score fields."""
import json
import urllib.error
import urllib.parse
import urllib.request

import osu_api

BASE = 'https://api.mamesosu.net/lazer/api/v2'


def normalize_score(score):
    result = dict(score, server='mames')
    result['client'] = ('Lazer' if score.get('build_id') is not None
                        or score.get('legacy_score_id') is None else 'Stable')
    if not result.get('beatmapset'):
        result['beatmapset'] = (result.get('beatmap') or {}).get('beatmapset') or {}
    return result


class MamesApi:
    def __init__(self, proxy=''):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler(osu_api.effective_proxies(proxy)))

    def get(self, endpoint, params=None):
        url = BASE + endpoint
        if params:
            url += '?' + urllib.parse.urlencode(params)
        try:
            request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'mania-render/0.1'})
            with self.opener.open(request, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Mamesosu API HTTP {exc.code}') from None
        except (ValueError, OSError):
            raise RuntimeError('Mamesosu API 暂时无法访问') from None
        if isinstance(data, dict) and data.get('error'):
            raise RuntimeError('Mamesosu 没有找到玩家或成绩')
        return data

    def user_by_name(self, user, ruleset):
        key = urllib.parse.quote(' '.join(str(user).split()), safe='')
        data = self.get(f'/users/{key}/{ruleset}')
        if not isinstance(data, dict) or not data.get('id'):
            raise RuntimeError('Mamesosu 没有找到这个玩家')
        return data

    def recent_scores(self, user, ruleset, include_fails=True, limit=100):
        uid = user if str(user).isdigit() else self.user_by_name(user, ruleset)['id']
        rows = self.get(f'/users/{int(uid)}/scores/recent', {
            'mode': ruleset, 'include_fails': int(include_fails), 'limit': limit,
            'legacy_only': 0})
        if not isinstance(rows, list):
            raise RuntimeError('Mamesosu 最近成绩响应格式异常')
        return [normalize_score(s) for s in rows if include_fails or s.get('passed') is True]

    def beatmap_user_scores(self, bid, uid, ruleset):
        recent = self.recent_scores(uid, ruleset)
        rows = [s for s in recent if int(s.get('beatmap_id') or (s.get('beatmap') or {}).get('id') or 0) == int(bid)]
        if rows:
            return rows
        data = self.get(f'/beatmaps/{int(bid)}/scores/users/{int(uid)}', {'mode': ruleset, 'legacy_only': 0})
        score = data.get('score') if isinstance(data, dict) else None
        return [normalize_score(score)] if score else []
