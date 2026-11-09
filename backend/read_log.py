
import sys
import io

# Force utf-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    with open("session.log", "r", encoding="utf-16le") as f:
        lines = f.readlines()
        # Show last 200 lines
        for i in range(max(0, len(lines)-200), len(lines)):
            line = lines[i].strip()
            if line:
                print(f"LINE {i}: {line}")
        
        # Also print keyword matches from anywhere
        keywords = ["healing", "fetched", "fetch window", "no complete", "traceback", "error", "critical"]
        for i, line in enumerate(lines):
            l_line = line.lower()
            if i >= 200 and any(k in l_line for k in keywords):
                print(f"LINE {i}: {line.strip()}")
        
        # Also print last 100 ticks count
        ticks = [l for l in lines if "TICK" in l]
        print(f"Total ticks in log: {len(ticks)}")
except Exception as e:
    print(f"Error: {e}")
