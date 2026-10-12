"""Where things live. The simulator points ROOT and SD at a sandbox."""

ROOT = "/"          # internal flash (LittleFS)
SD = "/sd"          # microSD mount point


def data(name):
    """A file in the internal filesystem root."""
    return ROOT.rstrip("/") + "/" + name


def sd(name=""):
    return SD.rstrip("/") + ("/" + name if name else "")
