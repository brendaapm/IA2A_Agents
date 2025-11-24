# executor sandbox (sem internet), timeout, captura stdout/figuras
import io
import base64
import contextlib
import sys
import matplotlib
matplotlib.use("Agg")  # backend não interativo
import matplotlib.pyplot as plt


def fig_to_base64_png() -> str:
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def capture_stdout(fn, *args, **kwargs):
    """Captura stdout de uma função (para logs curtos)."""
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return result, stream.getvalue()