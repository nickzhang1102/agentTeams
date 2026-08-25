"""批量更新 Agent YAML frontmatter，添加 priority 字段"""
import os
import re

agents_dir = '.claude/agents'

def get_default_priority(agent_id, name):
    """根据 Agent 类型推断默认 priority"""
    # 审核类: 90
    if 'critic' in agent_id.lower() or '审核' in name or 'reviewer' in agent_id.lower():
        return 90
    # 前置类: 40
    if any(k in name for k in ['检验', '放射', '病理']):
        return 40
    # 默认: 50
    return 50

updated_count = 0
skipped_count = 0

for filename in os.listdir(agents_dir):
    if not filename.endswith('.md'):
        continue

    filepath = os.path.join(agents_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析 frontmatter
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        skipped_count += 1
        continue

    frontmatter = match.group(1)
    lines = frontmatter.split('\n')

    # 检查是否已有 priority
    has_priority = any(line.strip().startswith('priority:') for line in lines)

    if has_priority:
        skipped_count += 1
        continue

    # 提取 name
    name = ''
    for line in lines:
        if line.strip().startswith('name:'):
            name = line.split(':', 1)[1].strip().strip('"').strip("'")
            break

    agent_id = filename[:-3]
    priority = get_default_priority(agent_id, name)

    # 添加 priority 字段（在 model 行之后）
    new_frontmatter_lines = []
    inserted = False
    for line in lines:
        new_frontmatter_lines.append(line)
        if not inserted and line.strip().startswith('model:'):
            new_frontmatter_lines.append(f'priority: {priority}')
            inserted = True

    # 如果没有 model 行，在末尾添加
    if not inserted:
        new_frontmatter_lines.append(f'priority: {priority}')

    new_frontmatter = '\n'.join(new_frontmatter_lines)
    new_content = f'---\n{new_frontmatter}\n---\n{content[match.end():]}'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    updated_count += 1
    print(f'{filename}: priority={priority}')

print(f'\nTotal: Updated {updated_count}, Skipped {skipped_count}')