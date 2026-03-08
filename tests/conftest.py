"""
tests/conftest.py — Pytest yapılandırması ve ortak fixture'lar.
"""
import os
import pytest

# Test için .env değerleri
os.environ.setdefault("BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")
os.environ.setdefault("DB_PATH", "/tmp/test_finans_bot.db")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
