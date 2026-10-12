"""Regression tests against an installed AstrBot context manager."""

import argparse
import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True, type=Path)
parser.add_argument("--source", type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.root))

from astrbot.core.agent.context import compressor, manager  # noqa: E402
from astrbot.core.agent.context.config import ContextConfig  # noqa: E402
from astrbot.core.agent.message import ImageURLPart, Message, TextPart  # noqa: E402

if args.source:
    spec = importlib.util.spec_from_file_location(
        "astrbot.core.agent.context.context_fix_candidate", args.source
    )
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    manager.ContextTruncator = candidate.ContextTruncator
    compressor.ContextTruncator = candidate.ContextTruncator


def tool_round(number, parallel=1):
    """Build a real model tool-call/result chain.

    Args:
        number: Unique round identifier.
        parallel: Number of calls in the assistant message.

    Returns:
        An assistant message followed by matching tool results.
    """
    calls = [
        {
            "id": f"call_{number}_{i}",
            "type": "function",
            "function": {"name": "lookup", "arguments": "{}"},
        }
        for i in range(parallel)
    ]
    return [
        Message(role="assistant", content=None, tool_calls=calls),
        *[
            Message(role="tool", tool_call_id=c["id"], content="Lookup result")
            for c in calls
        ],
    ]


class ContextTurnTests(unittest.TestCase):
    def setUp(self):
        self.truncator = manager.ContextTruncator()
        self.system = Message(role="system", content="Answer the current request.")
        self.examples = [
            Message(role="user", content="Keep internal scores private."),
            Message(role="assistant", content="Understood."),
        ]
        for message in self.examples:
            message._no_save = True

    def test_original_questions_survive_every_tool_iteration(self):
        for prompt in (
            "我要渲染回放，有什么皮肤可以选择",
            "查看一下我最近游玩通过中，名叫reflec的谱面",
        ):
            with self.subTest(prompt=prompt):
                current = Message(role="user", content=[TextPart(text=prompt)])
                messages = [self.system, *self.examples, current]
                context = manager.ContextManager(
                    ContextConfig(
                        enforce_max_turns=12,
                        truncate_turns=20,
                        max_context_tokens=1_000_000,
                    )
                )
                expected = messages.copy()
                for i in range(15):
                    chain = tool_round(i, parallel=3)
                    messages.extend(chain)
                    expected.extend(chain)
                    messages = asyncio.run(context.process(messages))
                    self.assertIn(current, messages, f"lost request at iteration {i}")
                    self.assertEqual(messages, expected)

    def test_keeps_exactly_twelve_requests_including_current(self):
        messages = [self.system, *self.examples]
        starts = []
        for i in range(25):
            request = Message(role="user", content=f"Question {i}")
            starts.append(len(messages))
            messages.extend([request, *tool_round(i, i % 3 + 1)])
            if i != 24:
                messages.append(Message(role="assistant", content=f"Answer {i}"))
        result = self.truncator.truncate_by_turns(messages, 12, drop_turns=20)
        self.assertEqual(
            result, [self.system, *self.examples, *messages[starts[-12] :]]
        )
        users = [m for m in result if m.role == "user" and not m._no_save]
        self.assertEqual(len(users), 12)
        self.assertEqual(users[0].content, "Question 13")
        self.assertEqual(users[-1].content, "Question 24")

    def test_persona_examples_do_not_consume_request_limit(self):
        messages = [self.system, *self.examples]
        for i in range(12):
            messages.extend(
                [
                    Message(role="user", content=f"Q{i}"),
                    Message(role="assistant", content="A"),
                ]
            )
        self.assertEqual(self.truncator.truncate_by_turns(messages, 12), messages)

    def test_token_overflow_drops_whole_old_requests(self):
        old = [Message(role="user", content="Old"), *tool_round(0)]
        old.append(Message(role="assistant", content="Finished"))
        current = [Message(role="user", content="Current"), *tool_round(1, 3)]
        messages = [self.system, *self.examples, *old, *current]
        for count in (1, 20, 999):
            with self.subTest(drop=count):
                result = self.truncator.truncate_by_dropping_oldest_turns(
                    messages, count
                )
                self.assertEqual(result, [self.system, *self.examples, *current])

    def test_halving_keeps_complete_latest_request(self):
        messages = [self.system, *self.examples]
        rounds = []
        for i in range(7):
            group = [Message(role="user", content=f"Q{i}"), *tool_round(i, 2)]
            if i != 6:
                group.append(Message(role="assistant", content="Done"))
            rounds.append(group)
            messages.extend(group)
        result = self.truncator.truncate_by_halving(messages)
        expected = [self.system, *self.examples, *[m for r in rounds[3:] for m in r]]
        self.assertEqual(result, expected)

    def test_tool_images_and_final_notice_stay_in_current_request(self):
        current = Message(role="user", content="Inspect these tool images.")
        messages = [self.system, *self.examples, current]
        for i in range(15):
            messages.extend(tool_round(i))
            messages.append(
                Message(
                    role="user",
                    content=[
                        ImageURLPart(
                            image_url=ImageURLPart.ImageURL(
                                url="data:image/png;base64,AA=="
                            )
                        )
                    ],
                )
            )
        messages.append(Message(role="user", content="Stop using tools and summarize."))
        result = self.truncator.truncate_by_turns(messages, 12, 20)
        self.assertEqual(result, messages)

    def test_consecutive_user_requests_count_separately(self):
        messages = [
            self.system,
            *[Message(role="user", content=f"Q{i}") for i in range(15)],
        ]
        result = self.truncator.truncate_by_turns(messages, 12, 20)
        self.assertEqual(result, [self.system, *messages[-12:]])

    def test_single_active_request_cannot_be_removed_by_token_fallback(self):
        messages = [
            self.system,
            *self.examples,
            Message(role="user", content="Current"),
        ]
        for i in range(20):
            messages.extend(tool_round(i, 3))
        self.assertEqual(self.truncator.truncate_by_halving(messages), messages)
        self.assertEqual(
            self.truncator.truncate_by_dropping_oldest_turns(messages, 20), messages
        )

    def test_empty_system_only_and_disabled_limit(self):
        self.assertEqual(self.truncator.truncate_by_turns([], 12, 20), [])
        self.assertEqual(
            self.truncator.truncate_by_halving([self.system]), [self.system]
        )
        self.assertEqual(
            self.truncator.truncate_by_dropping_oldest_turns([self.system], 20),
            [self.system],
        )
        messages = [
            self.system,
            Message(role="user", content="Current"),
            *tool_round(1),
        ]
        self.assertIs(self.truncator.truncate_by_turns(messages, -1, 20), messages)

    def test_zero_limit_still_keeps_current_request(self):
        old = [
            Message(role="user", content="Old"),
            Message(role="assistant", content="Done"),
        ]
        current = [Message(role="user", content="Current"), *tool_round(2)]
        messages = [self.system, *old, *current]
        self.assertEqual(
            self.truncator.truncate_by_turns(messages, 0, 20), [self.system, *current]
        )

    def test_token_limit_remains_enabled_and_reduces_old_history(self):
        old = [
            Message(role="user", content="old" * 1000),
            Message(role="assistant", content="answer" * 1000),
        ]
        current = [Message(role="user", content="Current"), *tool_round(3)]
        context = manager.ContextManager(
            ContextConfig(
                max_context_tokens=500, enforce_max_turns=12, truncate_turns=20
            )
        )
        result = asyncio.run(context.process([self.system, *old, *current]))
        self.assertEqual(result, [self.system, *current])
        self.assertLess(context.token_counter.count_tokens(result), 500)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
