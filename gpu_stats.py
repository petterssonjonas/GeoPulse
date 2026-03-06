"""AMD GPU stats via sysfs (no external deps). CPU/RAM when no GPU."""
import time
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


def get_cpu_ram_stats() -> dict | None:
    """Return {'cpu_pct': int, 'ram_used_gb': float, 'ram_total_gb': float} or None."""
    try:
        # CPU: two samples
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        if parts[0] != "cpu" or len(parts) < 5:
            return None
        user = int(parts[1])
        nice = int(parts[2])
        system = int(parts[3])
        idle = int(parts[4])
        iowait = int(parts[5]) if len(parts) > 5 else 0
        irq = int(parts[6]) if len(parts) > 6 else 0
        softirq = int(parts[7]) if len(parts) > 7 else 0
        total0 = user + nice + system + idle + iowait + irq + softirq
        idle0 = idle
        time.sleep(0.15)
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        if parts[0] != "cpu" or len(parts) < 5:
            return None
        user = int(parts[1])
        nice = int(parts[2])
        system = int(parts[3])
        idle = int(parts[4])
        iowait = int(parts[5]) if len(parts) > 5 else 0
        irq = int(parts[6]) if len(parts) > 6 else 0
        softirq = int(parts[7]) if len(parts) > 7 else 0
        total1 = user + nice + system + idle + iowait + irq + softirq
        idle1 = idle
        if total1 <= total0:
            cpu_pct = 0
        else:
            cpu_pct = int(100 * (1 - (idle1 - idle0) / (total1 - total0)))
            cpu_pct = max(0, min(100, cpu_pct))

        # RAM from /proc/meminfo
        mem = {}
        with open("/proc/meminfo") as f:
            for ln in f:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    mem[k.strip()] = int(v.strip().split()[0])
        total_kb = mem.get("MemTotal") or 0
        avail_kb = mem.get("MemAvailable") or mem.get("MemFree") or 0
        used_kb = total_kb - avail_kb
        if total_kb <= 0:
            return None
        ram_total_gb = total_kb / (1024 * 1024)
        ram_used_gb = used_kb / (1024 * 1024)
        return {"cpu_pct": cpu_pct, "ram_used_gb": round(ram_used_gb, 1), "ram_total_gb": round(ram_total_gb, 1)}
    except (OSError, ValueError, KeyError):
        return None
