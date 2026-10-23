import os

# O Qt precisa estar em modo offscreen para rodar em CI/headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
