import time
from typing import Dict, Any

class RuleProfiler:
    def __init__(self):
        self.timings = {}
    
    def start(self, rule_id: int):
        self.timings[rule_id] = {"start": time.time()}
    
    def end(self, rule_id: int):
        if rule_id in self.timings and "start" in self.timings[rule_id]:
            elapsed = time.time() - self.timings[rule_id]["start"]
            self.timings[rule_id]["elapsed"] = elapsed
            return elapsed
        return 0
    
    def get_stats(self) -> Dict[int, float]:
        return {rule_id: data.get("elapsed", 0) for rule_id, data in self.timings.items()}
    
    def reset(self):
        self.timings = {}