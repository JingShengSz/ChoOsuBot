"""Method replacements for AstrBot's turn truncator.

The patch builder copies these methods into the installed ContextTruncator.
"""

from typing import Any

Message = Any


class RequestTurnMethods:
    def _split_request_rounds(
        self, messages: list[Message]
    ) -> tuple[list[Message], list[list[Message]]]:
        """Group requests without splitting their tool-call trajectories.

        Args:
            messages: Runtime messages, including temporary persona examples.

        Returns:
            The system/example prefix and whole user request rounds.
        """
        prefix: list[Message] = []
        rounds: list[list[Message]] = []
        in_prefix = True
        awaiting_tool_completion = False
        for message in messages:
            if in_prefix and (
                message.role == "system" or getattr(message, "_no_save", False)
            ):
                prefix.append(message)
                continue
            in_prefix = False
            if message.role == "user" and not awaiting_tool_completion:
                rounds.append([])
            if not rounds:
                # A saved orphan tool result is not a real user request.
                continue
            rounds[-1].append(message)
            if self._has_tool_calls(message):
                awaiting_tool_completion = True
            elif message.role == "assistant":
                awaiting_tool_completion = False
            # Cached tool images and the final-step notice use role=user too.
            # They remain in the open tool trajectory until its final answer.
        return prefix, rounds

    def truncate_by_turns(
        self,
        messages: list[Message],
        keep_most_recent_turns: int,
        drop_turns: int = 1,
    ) -> list[Message]:
        """Keep the newest complete request rounds, including the active one.

        Args:
            messages: Runtime conversation messages.
            keep_most_recent_turns: Request limit; -1 disables this limit.
            drop_turns: Kept for API compatibility; applies to token overflow only.

        Returns:
            System/examples followed by at most the requested number of rounds.
        """
        if keep_most_recent_turns == -1:
            return messages
        prefix, rounds = self._split_request_rounds(messages)
        limit = max(1, keep_most_recent_turns)
        if len(rounds) <= limit:
            return messages
        retained = [message for group in rounds[-limit:] for message in group]
        return self.fix_messages(prefix + retained)

    def truncate_by_dropping_oldest_turns(
        self, messages: list[Message], drop_turns: int = 1
    ) -> list[Message]:
        """Drop whole old requests while always retaining the latest request.

        Args:
            messages: Runtime conversation messages.
            drop_turns: Number of old requests to discard.

        Returns:
            The remaining complete requests and original system/example prefix.
        """
        if drop_turns <= 0:
            return messages
        prefix, rounds = self._split_request_rounds(messages)
        if len(rounds) <= 1:
            return messages
        drop_count = min(drop_turns, len(rounds) - 1)
        retained = [message for group in rounds[drop_count:] for message in group]
        return self.fix_messages(prefix + retained)

    def truncate_by_halving(self, messages: list[Message]) -> list[Message]:
        """Remove half the old request rounds without splitting the latest one.

        Args:
            messages: Runtime conversation messages.

        Returns:
            The newest complete rounds and original system/example prefix.
        """
        prefix, rounds = self._split_request_rounds(messages)
        if len(rounds) <= 1:
            return messages
        retained = [
            message for group in rounds[len(rounds) // 2 :] for message in group
        ]
        return self.fix_messages(prefix + retained)
