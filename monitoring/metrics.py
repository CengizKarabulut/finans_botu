"""Prometheus-style metrics collector."""
import time
import threading
from typing import List, Tuple
from collections import defaultdict

class MetricsCollector:
    """Thread-safe metrics collector."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict = defaultdict(int)
        self._gauges: dict = {}
        self._histograms: dict = defaultdict(list)
        self._start_time = time.time()
    
    def inc(self, name: str, value: int = 1, labels: dict = None):
        """Counter artır."""
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] += value
    
    def set_gauge(self, name: str, value: float, labels: dict = None):
        """Gauge değerini ayarla."""
        key = self._make_key(name, labels)
        with self._lock:
            self._gauges[key] = value
    
    def observe(self, name: str, value: float, labels: dict = None):
        """Histogram observation ekle."""
        key = self._make_key(name, labels)
        with self._lock:
            self._histograms[key].append(value)
            # Son 1000 değeri tut
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]
    
    def _make_key(self, name: str, labels: dict = None) -> str:
        """Metric key oluştur."""
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_all(self) -> List[Tuple[str, float, str, str]]:
        """Tüm metrikleri Prometheus formatında döndür."""
        results = []
        with self._lock:
            # Counters
            for key, value in self._counters.items():
                name = key.split("{")[0] if "{" in key else key
                results.append((name, value, "Toplam sayım", "counter"))
            
            # Gauges
            for key, value in self._gauges.items():
                name = key.split("{")[0] if "{" in key else key
                results.append((name, value, "Anlık değer", "gauge"))
            
            # Histograms (ortalama)
            for key, values in self._histograms.items():
                if values:
                    name = key.split("{")[0] if "{" in key else key
                    avg = sum(values) / len(values)
                    results.append((f"{name}_avg", avg, "Ortalama değer", "gauge"))
                    results.append((f"{name}_count", len(values), "Gözlem sayısı", "counter"))
        
        # Bot uptime
        uptime = time.time() - self._start_time
        results.append(("bot_uptime_seconds", uptime, "Bot çalışma süresi", "gauge"))
        
        return results

# Global instance
_metrics = MetricsCollector()

def get_metrics() -> MetricsCollector:
    """Global metrics collector instance döndür."""
    return _metrics

# Convenience functions
def inc_counter(name: str, value: int = 1, labels: dict = None):
    _metrics.inc(name, value, labels)

def set_gauge(name: str, value: float, labels: dict = None):
    _metrics.set_gauge(name, value, labels)

def observe_histogram(name: str, value: float, labels: dict = None):
    _metrics.observe(name, value, labels)
