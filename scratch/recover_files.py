import json
import os

log_path = "/Users/santhoshpatel/.gemini/antigravity-ide/brain/1d4e96b0-f6b1-4a25-aae3-948548deb2a2/.system_generated/logs/transcript.jsonl"
dest_dir = "/Users/santhoshpatel/Desktop/teamsbot-v3/Enzo-admin/src/pages"
os.makedirs(dest_dir, exist_ok=True)

last_dashboard = None
last_tasks = None

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            step = json.loads(line)
            tool_calls = step.get("tool_calls", [])
            for call in tool_calls:
                args = call.get("args", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except:
                        pass
                
                if isinstance(args, dict):
                    target = args.get("TargetFile") or args.get("AbsolutePath")
                    if target:
                        content = args.get("CodeContent") or args.get("content")
                        if content and content != "None":
                            if "Dashboard.tsx" in target:
                                last_dashboard = content
                            elif "Tasks.tsx" in target:
                                last_tasks = content
        except Exception as e:
            pass

if last_dashboard:
    with open(os.path.join(dest_dir, "Dashboard.tsx"), "w", encoding="utf-8") as f:
        f.write(last_dashboard)
    print("Recovered Dashboard.tsx successfully!")
else:
    print("Dashboard.tsx NOT found in logs!")

if last_tasks:
    with open(os.path.join(dest_dir, "Tasks.tsx"), "w", encoding="utf-8") as f:
        f.write(last_tasks)
    print("Recovered Tasks.tsx successfully!")
else:
    print("Tasks.tsx NOT found in logs!")
