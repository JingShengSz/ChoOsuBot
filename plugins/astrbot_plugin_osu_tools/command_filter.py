"""Case-insensitive command names, preserving argument text and wake rules."""

import re

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.register.star_handler import (
    get_handler_full_name,
    register_command,
    star_handlers_registry,
)


class _CommandEvent:
    def __init__(self, event, text):
        self.event = event
        self.text = text

    def get_message_str(self):
        return self.text

    def __getattr__(self, name):
        return getattr(self.event, name)


class CaseInsensitiveCommandFilter(CommandFilter):
    def equals(self, message_str):
        return any(
            message_str.casefold() == name.casefold()
            for name in self.get_complete_command_names()
        )

    def filter(self, event, cfg):
        text = re.sub(r"\s+", " ", event.get_message_str().strip())
        folded = text.casefold()
        for name in sorted(self.get_complete_command_names(), key=len, reverse=True):
            if folded == name.casefold() or folded.startswith(name.casefold() + " "):
                # Only replace the command. Usernames, URLs and option values keep
                # their original case, and AstrBot handles wake/permission checks.
                return super().filter(
                    _CommandEvent(event, name + text[len(name) :]), cfg
                )
        return False


def command(name, alias=None, **kwargs):
    def decorate(handler):
        handler = register_command(name, alias=alias, **kwargs)(handler)
        md = star_handlers_registry.get_handler_by_full_name(
            get_handler_full_name(handler)
        )
        for index, item in enumerate(md.event_filters):
            if type(item) is CommandFilter and item.command_name == name:
                replacement = CaseInsensitiveCommandFilter(
                    name, item.alias, md, item.parent_command_names
                )
                replacement.custom_filter_list = item.custom_filter_list
                md.event_filters[index] = replacement
        return handler

    return decorate
