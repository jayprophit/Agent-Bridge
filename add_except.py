#!/usr/bin/env python3
with open('C:\\Users\\jpowe\\Desktop\\Agent-Bridge\\runtime.py', 'r') as f:
    lines = f.readlines()

except_block = '''        except Exception as e:  # noqa: BLE001
            rec.status = FAILED
            rec.error = f"{type(e).__name__}: {e}"
            rec.result = {"session_id": self.session_id, "task_id": task_id,
                          "status": FAILED, "finished_reason": rec.error}
            self.runtime.metrics["tasks_failed"] += 1

'''

for i, line in enumerate(lines):
    if line.strip() == 'finally:' and i > 300:
        lines.insert(i, except_block)
        print(f'Inserted except block before line {i+1}')
        break

with open('C:\\Users\\jpowe\\Desktop\\Agent-Bridge\\runtime.py', 'w') as f:
    f.writelines(lines)

print('Added except block before finally')