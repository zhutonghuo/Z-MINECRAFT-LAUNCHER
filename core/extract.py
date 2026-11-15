import os
import zipfile


def extract_natives(data_root, version_id):
    ndir = os.path.join(data_root, 'versions', version_id, 'natives')
    os.makedirs(ndir, exist_ok=True)
    for fn in os.listdir(ndir):
        if fn.endswith('.jar'):
            try:
                with zipfile.ZipFile(os.path.join(ndir, fn)) as z:
                    for name in z.namelist():
                        if name.endswith(('.dll', '.dylib', '.so', '.jnilib')):
                            z.extract(name, ndir)
            except Exception:
                pass
