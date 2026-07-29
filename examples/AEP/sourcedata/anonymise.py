#!/usr/bin/env python3
import json
import os
import sys

if len(sys.argv) != 3:
    sys.stderr.write("Usage: anonymise.py <dir> <textfile>\n")
    sys.exit(1)

with open(sys.argv[2], "r", encoding="utf-8") as f:
    changes = json.load(f)

for root, dirs, files in os.walk(sys.argv[1]):
    for filename in files:
        if not filename.endswith(".json"):
            continue
        fullpath = os.path.join(root, filename)
        with open(fullpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        new_data = {}
        for key, value in data.items():
            if key in changes:
                if changes[key]:
                    new_data[key] = changes[key]
            else:
                new_data[key] = value
        with open(fullpath, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=4)
