"""AMD GPU stats via sysfs (no external deps)."""
from pathlib import Path


def _find_best_amd_card() -> Path | None:
    """Return the AMD card device path with the largest VRAM (the discrete GPU)."""
    best_path = None
    best_vram = 0
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
        dev = card / "device"
        try:
            if (dev / "vendor").read_text().strip() != "0x1002":
                continue
            vram = int((dev / "mem_info_vram_total").read_text().strip())
            if vram > best_vram:
                best_vram = vram
                best_path = dev
        except OSError:
            continue
    return best_path


_device: Path | None = _find_best_amd_card()


def get_gpu_stats() -> dict | None:
    """Return {'compute_pct': int, 'vram_used_mb': int, 'vram_total_mb': int} or None."""
    if _device is None:
        return None
    try:
        compute    = int((_device / "gpu_busy_percent").read_text().strip())
        vram_used  = int((_device / "mem_info_vram_used").read_text().strip()) // (1024 * 1024)
        vram_total = int((_device / "mem_info_vram_total").read_text().strip()) // (1024 * 1024)
        return {"compute_pct": compute, "vram_used_mb": vram_used, "vram_total_mb": vram_total}
    except OSError:
        return None
