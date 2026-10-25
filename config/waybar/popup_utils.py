import json
import subprocess


def cursor_position():
    try:
        output = subprocess.check_output(
            ("hyprctl", "cursorpos"), text=True, timeout=1
        ).strip()
        x, y = output.split(",")
        return int(x.strip()), int(y.strip())
    except Exception:
        return None


def layer_rect(namespace):
    try:
        output = subprocess.check_output(
            ("hyprctl", "-j", "layers"), text=True, timeout=2
        )
        data = json.loads(output)
    except Exception:
        return None

    for monitor in data.values():
        for layers in monitor.get("levels", {}).values():
            for layer in layers:
                if layer.get("namespace") == namespace:
                    return (
                        layer.get("x", 0),
                        layer.get("y", 0),
                        layer.get("w", 0),
                        layer.get("h", 0),
                    )
    return None


def pointer_inside(rect, position=None):
    if rect is None:
        return None
    if position is None:
        position = cursor_position()
    if position is None:
        return None
    x, y, width, height = rect
    return x <= position[0] < x + width and y <= position[1] < y + height
