import re

with open('static/js/app.js', 'r') as f:
    content = f.read()

old = "if (i === 4 || i === 8 || i === 12 || i === 16) f += '-';"
new = "if (i === 3 || i === 7 || i === 11 || i === 15) f += '-';"

if old in content:
    content = content.replace(old, new)
    with open('static/js/app.js', 'w') as f:
        f.write(content)
    print("FIXED: dash positions 4,8,12,16 -> 3,7,11,15")
else:
    print("Pattern not found, checking actual code...")
    for i, line in enumerate(content.split('\n'), 1):
        if 'i === 4' in line and 'i === 8' in line:
            print(f"Line {i}: {line.strip()}")
