"""Basit metrik collector — Prometheus benzeri."""
import time
import threading
from typing import List, Tuple, Optional, Dict
from collections import defaultdict

class MetricsCollector:
    """Thread-safe basit metrik toplama."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._start_time = time.time()
    
    def inc(self, name: str, value: int = 1, labels: Optional[Dict] = None):
        """Counter artır."""
        key = f"{name}" + (f"{{{','.join(f'{k}=\"{v}\"' for k,v in sorted(labels.items()))}}}" if labels else "")
        with self._lock:
            self._counters[key] += value
    
    def get_all(self) -> List[Tuple[str, int, str, str]]:
        """Tüm metrikleri döndür."""
        results = []
        with self._lock:
            for key, value in self._counters.items():
                name = key.split("{")[0] if "{" in key else key
                results.append((name, value, "Toplam sayım", "counter"))
        
        uptime = time.time() - self._start_time
        results.append(("bot_uptime_seconds", int(uptime), "Bot çalışma süresi", "gauge"))
        return results

_metrics = MetricsCollector()

def get_metrics() -> MetricsCollector:
    return _metrics

def inc_counter(name: str, value: int = 1, labels: Dict = None):
    _metrics.inc(name, value, labels)
