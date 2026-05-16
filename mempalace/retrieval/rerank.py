"""Rerank plugin scaffold."""

from typing import Protocol


class RerankPlugin(Protocol):
    def rerank(self, candidates: list) -> list:
        ...


def no_op_rerank(candidates: list) -> list:
    return list(candidates)
