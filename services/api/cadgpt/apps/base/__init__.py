"""Shared kernel: the abstractions every other app inherits, and nothing domain-specific.

Nothing in this package may import another app. It is the lowest layer of the import
contract in the repository root, which means a change here can break anything and a change
anywhere else can never break this.
"""
