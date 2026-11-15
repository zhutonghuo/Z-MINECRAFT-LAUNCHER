import os
import json
import time
import shutil

INSTANCE_FILE = 'instance.json'

ICONS = ['grass', 'diamond', 'creeper', 'tnt', 'apple', 'sword', 'book', 'ender']


def instances_dir(data_root):
    return os.path.join(data_root, 'instances')


def list_instances(data_root):
    d = instances_dir(data_root)
    out = []
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name, INSTANCE_FILE)
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    inst = json.load(f)
                inst['_dir'] = os.path.join(d, name)
                out.append(inst)
            except Exception:
                pass
    return out


def get_instance(data_root, name):
    p = os.path.join(instances_dir(data_root), name, INSTANCE_FILE)
    if not os.path.isfile(p):
        return None
    with open(p, 'r', encoding='utf-8') as f:
        inst = json.load(f)
    inst['_dir'] = os.path.join(instances_dir(data_root), name)
    return inst


def save_instance(data_root, inst):
    name = inst['name']
    base = os.path.join(instances_dir(data_root), name)
    os.makedirs(base, exist_ok=True)
    os.makedirs(os.path.join(base, '.minecraft'), exist_ok=True)
    inst = dict(inst)
    inst.pop('_dir', None)
    with open(os.path.join(base, INSTANCE_FILE), 'w', encoding='utf-8') as f:
        json.dump(inst, f, ensure_ascii=False, indent=2)
    inst['_dir'] = base
    return inst


def create_instance(data_root, name, version_id, mod_loader='vanilla', icon='grass', notes=''):
    inst = {
        'name': name,
        'versionId': version_id,
        'gameDir': os.path.join(instances_dir(data_root), name, '.minecraft'),
        'modLoader': mod_loader,
        'createdAt': int(time.time() * 1000),
        'notes': notes,
        'icon': icon,
        'javaArgs': '',
        'gameArgs': '',
        'resolution': None,
    }
    return save_instance(data_root, inst)


def delete_instance(data_root, name):
    base = os.path.join(instances_dir(data_root), name)
    if os.path.isdir(base):
        shutil.rmtree(base)
