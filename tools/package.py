"""Build a deterministic source archive from an explicit publication allowlist."""
import ast
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
metadata = json.loads((root / "project.json").read_text())
module = metadata["module"]
syntax = ast.parse((root / module).read_text())
versions = [ast.literal_eval(node.value) for node in syntax.body
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)]
if versions != [metadata["version"]]:
    raise ValueError("Project and module versions must match.")
files = [module, "project.json", "README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
         ".gitignore", ".github/workflows/ci.yml", ".github/workflows/release.yml",
         ".github/ISSUE_TEMPLATE/bug_report.md", "docs/DE.md", "tools/package.py"] + metadata["examples"]
output = root / "dist"
output.mkdir(exist_ok=True)
name = metadata["slug"] + "-" + metadata["version"] + ".zip"
path = output / name
with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
    for relative in sorted(files):
        source = root / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError("Release file must exist and must not be a symlink: " + relative)
        entry = ZipInfo(metadata["slug"] + "/" + relative, date_time=(2026, 10, 7, 0, 0, 0))
        entry.compress_type = ZIP_DEFLATED
        entry.external_attr = 0o100644 << 16
        archive.writestr(entry, source.read_bytes())
digest = hashlib.sha256(path.read_bytes()).hexdigest()
(output / (name + ".sha256")).write_text(digest + "  " + name + "\n")
print("Built", name, "with", len(files), "allowlisted files.")
