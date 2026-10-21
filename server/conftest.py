"""Pytest kurulumu: testler sunucuya ihtiyaç duymadan (TestClient) çalışır.

App import edilmeden önce DATA_DIR'i geçici klasöre alır; böylece testler
gerçek veritabanına dokunmaz.
"""
from __future__ import annotations

import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="tashih-test-")
os.environ.setdefault("DATA_DIR", _tmpdir)
os.environ["LLM_API_KEY"] = ""  # testler kural tabanlı analizle çalışır
os.environ["LANG"] = "tr"
