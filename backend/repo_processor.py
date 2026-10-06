"""Clone a repository and select useful, safe text files for analysis."""

import os
import re
import ast
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from git import Repo


IGNORED_FOLDERS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "__pycache__",
    ".cache",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}

SUPPORTED_EXTENSIONS = {
    ".avi",
    ".bmp",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".dll",
    ".docx",
    ".env",
    ".exe",
    ".gif",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".jpeg",
    ".jpg",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".md",
    ".mov",
    ".mp4",
    ".pdf",
    ".pbix",
    ".php",
    ".png",
    ".pptx",
    ".py",
    ".rb",
    ".rar",
    ".rs",
    ".rst",
    ".scss",
    ".sql",
    ".svg",
    ".swift",
    ".tar",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".webm",
    ".xlsx",
    ".xml",
    ".yaml",
    ".yml",
    ".zip",
}

SOURCE_CODE_EXTENSIONS = {
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
}

IMPORTANT_FILENAMES = {
    ".gitignore",
    "build.gradle",
    "cargo.toml",
    "dockerfile",
    "go.mod",
    "gradle.build",
    "makefile",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}

MAX_DISCOVERED_FILES = 3000
MAX_ANALYZED_FILES = 10
MAX_FILE_BYTES = 500_000
MAX_FILE_CHARACTERS = 600
MAX_LOCAL_SCAN_BYTES = 20_000_000
MAX_TREE_ENTRIES = 80
MAX_PDF_BYTES = 8_000_000
MAX_PDF_CHARACTERS = 3_000
MAX_REPOSITORY_CONTEXT_CHARACTERS = 8_500
MAX_CONTENT_ITEMS = 14

DOCUMENT_EXTENSIONS = {".md", ".txt", ".rst"}
DATA_EXTENSIONS = {".csv", ".json", ".xml", ".yaml", ".yml"}
PDF_EXTENSIONS = {".pdf"}
KNOWN_TEXT_NAMES = {
    ".gitignore",
    "dockerfile",
    "makefile",
    "license",
    "license.txt",
    "notice",
    "readme",
}
NON_CONTENT_BINARY_EXTENSIONS = {
    ".7z",
    ".avi",
    ".bmp",
    ".dll",
    ".exe",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mp4",
    ".png",
    ".pbix",
    ".pdf",
    ".rar",
    ".so",
    ".tar",
    ".webm",
    ".xlsx",
    ".zip",
}

SECRET_PATTERNS = [
    re.compile(
        r"""(?i)(\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key)\b"""
        r"""\s*["']?\s*[:=]\s*["']?)([^"'\s,;}]+)"""
    ),
    re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
]
HIDDEN_SECRET_TEXT = "Secret/configuration value detected and hidden."


def validate_github_url(github_url):
    """Allow public GitHub repository URLs without assuming a specific checkout."""
    parsed_url = urlparse(str(github_url))
    hostname = (parsed_url.hostname or "").lower()
    path_parts = [part for part in parsed_url.path.strip("/").split("/") if part]

    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError(
            "Enter a public GitHub URL in the form "
            "https://github.com/username/repository."
        )

    if hostname not in {"github.com", "www.github.com"} or len(path_parts) != 2:
        raise ValueError(
            "Enter a public GitHub URL in the form "
            "https://github.com/username/repository."
        )


def clone_repository(github_url, destination_path):
    """Clone Git objects without checking files out onto the local filesystem."""
    validate_github_url(github_url)
    return Repo.clone_from(
        github_url,
        destination_path,
        depth=1,
        no_checkout=True,
    )


def list_repository_files(repository):
    """List tracked Git blobs by their repository paths without checking them out."""
    file_entries = []
    ignored_directories = IGNORED_FOLDERS | {
        ".next",
        ".tox",
        "vendor",
    }

    for blob in repository.head.commit.tree.traverse():
        if not blob.type == "blob":
            continue

        repository_path = blob.path.replace("\\", "/")
        path_parts = repository_path.split("/")
        if any(part.lower() in ignored_directories for part in path_parts[:-1]):
            continue

        file_entries.append(
            {
                "path": repository_path,
                "name": path_parts[-1],
                "extension": Path(path_parts[-1]).suffix.lower(),
                "size_bytes": blob.size,
                "blob": blob,
            }
        )
        if len(file_entries) >= MAX_DISCOVERED_FILES:
            break

    return file_entries


def file_category(file_entry):
    """Classify a tracked file using its extension and filename."""
    extension = file_entry["extension"]
    name = file_entry["name"].lower()

    if extension in PDF_EXTENSIONS:
        return "pdf"
    if extension == ".pbix":
        return "power_bi_binary"
    if extension in SOURCE_CODE_EXTENSIONS:
        return "source_code"
    if extension in DOCUMENT_EXTENSIONS or name.startswith("readme"):
        return "documentation"
    if extension in DATA_EXTENSIONS:
        return "data_or_configuration"
    if name in IMPORTANT_FILENAMES or name in KNOWN_TEXT_NAMES:
        return "project_configuration"
    if extension in NON_CONTENT_BINARY_EXTENSIONS:
        return "unsupported_binary"
    return "other"


def repository_file_importance(file_entry):
    """Rank README files and project content ahead of tests and binary files."""
    path = file_entry["path"].lower()
    name = file_entry["name"].lower()
    category = file_category(file_entry)
    path_parts = set(path.split("/"))

    score = {
        "documentation": 100,
        "source_code": 50,
        "project_configuration": 45,
        "data_or_configuration": 40,
        "pdf": 30,
        "other": 5,
        "power_bi_binary": -20,
        "unsupported_binary": -50,
    }[category]
    if name.startswith("readme"):
        score += 200
    if name in IMPORTANT_FILENAMES or name in {"dockerfile", ".gitignore"}:
        score += 70
    if path_parts.intersection({"src", "app", "backend", "frontend", "lib", "pkg"}):
        score += 25
    if path_parts.intersection({"test", "tests", "vendor", "examples", "fixtures"}):
        score -= 50
    return score


def extract_pdf_text(pdf_bytes):
    """Extract a small text sample from a PDF, when pypdf is installed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "PDF text extraction is unavailable because pypdf is not installed."

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        page_text = []
        total_characters = 0
        for page in reader.pages[:8]:
            text = page.extract_text() or ""
            remaining = MAX_PDF_CHARACTERS - total_characters
            if remaining <= 0:
                break
            page_text.append(text[:remaining])
            total_characters += min(len(text), remaining)
        extracted_text = "\n".join(page_text).strip()
        if not extracted_text:
            return "", "PDF exists, but no extractable text was found."
        if len(reader.pages) > 8 or total_characters >= MAX_PDF_CHARACTERS:
            return extracted_text, "PDF text was limited to the first 8 pages or 3,000 characters."
        return extracted_text, ""
    except Exception as error:
        return "", f"PDF exists, but text extraction failed: {error}"


def read_git_blob(blob, maximum_bytes):
    """Read a bounded amount of blob data from the local Git object database."""
    return blob.data_stream.read(maximum_bytes + 1)


def inspect_repository_files(file_entries):
    """Summarize repository content locally and retain bounded model context."""
    structures = {}
    content_items = []
    analysis_notes = []
    scanned_bytes = 0
    ordered_entries = sorted(
        file_entries,
        key=repository_file_importance,
        reverse=True,
    )

    for file_entry in ordered_entries:
        path = file_entry["path"]
        category = file_category(file_entry)
        file_entry["category"] = category
        if category in {"power_bi_binary", "unsupported_binary", "other"}:
            if category != "other":
                analysis_notes.append(
                    f"{path} was identified as {category.replace('_', ' ')}; "
                    "its binary contents were not inspected."
                )
            continue

        maximum_read = (
            MAX_PDF_BYTES
            if category == "pdf"
            else min(MAX_FILE_BYTES, MAX_LOCAL_SCAN_BYTES - scanned_bytes)
        )
        if maximum_read <= 0:
            analysis_notes.append(
                "The local content scan reached its 20 MB safety limit."
            )
            break
        if file_entry["size_bytes"] > maximum_read and category != "pdf":
            analysis_notes.append(
                f"{path} is large; only its first {maximum_read} bytes were scanned."
            )

        try:
            raw_content = read_git_blob(file_entry["blob"], maximum_read)
        except Exception as error:
            analysis_notes.append(f"{path} could not be read from Git: {error}")
            continue

        scanned_bytes += len(raw_content)
        if b"\0" in raw_content and category != "pdf":
            file_entry["category"] = "unsupported_binary"
            analysis_notes.append(
                f"{path} appears to be binary; its contents were not inspected."
            )
            continue

        if category == "pdf":
            if file_entry["size_bytes"] > MAX_PDF_BYTES:
                analysis_notes.append(
                    f"{path} exceeds the 8 MB PDF extraction limit; contents were not analyzed."
                )
                continue
            text, pdf_note = extract_pdf_text(raw_content)
            if pdf_note:
                analysis_notes.append(f"{path}: {pdf_note}")
            if not text:
                continue
            file_entry["category"] = "pdf_with_text"
        else:
            text = raw_content.decode("utf-8", errors="replace")
            if len(raw_content) > maximum_read:
                text = text[:MAX_FILE_CHARACTERS] + "\n... file content truncated ..."
            if category == "data_or_configuration":
                text = "\n".join(text.splitlines()[:40])
            if category == "source_code":
                structures[path] = extract_file_structure(path, text)

        text = hide_secrets(text)
        content_items.append(
            {
                "path": path,
                "category": file_entry["category"],
                "size_bytes": file_entry["size_bytes"],
                "text": text,
                "importance": repository_file_importance(file_entry),
            }
        )

    content_items.sort(key=lambda item: item["importance"], reverse=True)
    return structures, content_items, analysis_notes


def build_model_context(file_entries, content_items, structures):
    """Build a bounded context with README, documents, source, and binary inventory."""
    lines = [
        f"Repository file inventory ({len(file_entries)} tracked files):",
    ]
    ranked_entries = sorted(
        file_entries,
        key=repository_file_importance,
        reverse=True,
    )
    for file_entry in ranked_entries[:MAX_TREE_ENTRIES]:
        lines.append(
            f"- {file_entry['path']} [{file_entry.get('category', file_category(file_entry))}, "
            f"{file_entry['size_bytes']} bytes]"
        )
    if len(file_entries) > MAX_TREE_ENTRIES:
        lines.append(f"- ... {len(file_entries) - MAX_TREE_ENTRIES} additional files")

    lines.append("\nExtracted repository content:")
    remaining_characters = MAX_REPOSITORY_CONTEXT_CHARACTERS - sum(len(line) for line in lines)
    included_paths = set()
    content_item_limit = min(MAX_CONTENT_ITEMS, len(content_items))
    for item in content_items[:content_item_limit]:
        if item["category"] in {"documentation", "pdf_with_text"}:
            per_item_limit = 1_200
        elif item["category"] == "source_code":
            per_item_limit = 650
        else:
            per_item_limit = 700
        if Path(item["path"]).name.lower().startswith("readme"):
            per_item_limit = 1_600
        excerpt = item["text"][:per_item_limit]
        section = (
            f"\n--- {item['category']}: {item['path']} "
            f"({item['size_bytes']} bytes) ---\n{excerpt}"
        )
        if len(section) > remaining_characters:
            break
        lines.append(section)
        remaining_characters -= len(section)
        included_paths.add(item["path"])

    for path, structure in structures.items():
        if path in included_paths or remaining_characters < 100:
            continue
        summary = (
            f"\nLocal code structure for {path}: "
            f"imports={', '.join(structure['imports']) or 'none'}; "
            f"classes={', '.join(structure['classes']) or 'none'}; "
            f"functions={', '.join(structure['functions']) or 'none'}; "
            f"constants={', '.join(structure['constants']) or 'none'}"
        )
        if len(summary) <= remaining_characters:
            lines.append(summary)
            remaining_characters -= len(summary)

    return "".join(lines), included_paths


def get_binary_inventory(file_entries):
    """Describe binary files by name and type without attempting to decode them."""
    return [
        {
            "path": entry["path"],
            "type": entry.get("category", file_category(entry)),
            "size_bytes": entry["size_bytes"],
        }
        for entry in file_entries
        if entry.get("category", file_category(entry))
        in {"power_bi_binary", "unsupported_binary"}
    ]


def get_repository_tree(file_entries):
    """Create a readable path list directly from Git tree entries."""
    paths = [entry["path"] for entry in file_entries[:MAX_TREE_ENTRIES]]
    tree = "\n".join(f"- {path}" for path in paths)
    if len(file_entries) > MAX_TREE_ENTRIES:
        tree += f"\n- ... {len(file_entries) - MAX_TREE_ENTRIES} more files"
    return tree or "The repository contains no tracked files."


def summarize_file_types(file_entries):
    """Count repository files by their detected content category."""
    summary = {}
    for file_entry in file_entries:
        category = file_entry.get("category", file_category(file_entry))
        summary[category] = summary.get(category, 0) + 1
    return summary


def detect_repository_type(file_entries, content_items):
    """Suggest a project type from its tracked files and extracted text."""
    names = {entry["name"].lower() for entry in file_entries}
    extensions = {entry["extension"] for entry in file_entries}
    documentation_text = "\n".join(
        item["text"]
        for item in content_items
        if item["category"] in {"documentation", "pdf_with_text"}
    ).lower()

    if ".pbix" in extensions or re.search(r"\bpower\s*bi\b", documentation_text):
        return "Power BI / Business Analytics"
    if "package.json" in names or extensions.intersection({".js", ".jsx", ".ts", ".tsx"}):
        return "JavaScript/Node or Web project"
    if "pyproject.toml" in names or "requirements.txt" in names or ".py" in extensions:
        return "Python project"
    if "pom.xml" in names or "build.gradle" in names or ".java" in extensions:
        return "Java project"
    if content_items and all(
        item["category"] in {"documentation", "pdf_with_text"}
        for item in content_items
    ):
        return "Documentation-focused repository"
    return "Mixed or other repository"


def is_supported_file(file_path):
    """Return whether a path is a source, documentation, or project manifest."""
    lower_name = file_path.name.lower()
    if lower_name in IMPORTANT_FILENAMES or lower_name in KNOWN_TEXT_NAMES:
        return True
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def find_source_files(repository_path):
    """Find supported files, skipping generated folders and symbolic links."""
    source_files = []
    visited_folders = 0

    def raise_walk_error(error):
        raise error

    for current_folder, folder_names, file_names in os.walk(
        repository_path, onerror=raise_walk_error
    ):
        visited_folders += 1
        folder_names[:] = sorted(
            folder_name
            for folder_name in folder_names
            if folder_name.lower() not in IGNORED_FOLDERS
            and not (Path(current_folder) / folder_name).is_symlink()
        )

        for file_name in sorted(file_names):
            file_path = Path(current_folder) / file_name
            if is_supported_file(file_path) and not file_path.is_symlink():
                source_files.append(file_path)
                if len(source_files) >= MAX_DISCOVERED_FILES:
                    return source_files

        if visited_folders >= MAX_DISCOVERED_FILES:
            return source_files

    return source_files


def file_importance(file_path, repository_path):
    """Give core application files priority over tests and generated examples."""
    relative_path = Path(file_path).relative_to(repository_path)
    lower_path = str(relative_path).lower()
    lower_name = relative_path.name.lower()
    parts = {part.lower() for part in relative_path.parts}

    is_source_code = relative_path.suffix.lower() in SOURCE_CODE_EXTENSIONS
    score = 40 if is_source_code else 15
    if len(relative_path.parts) == 1:
        score += 10 if is_source_code else 5
    if parts.intersection({"src", "app", "backend", "frontend", "lib", "pkg"}):
        score += 20
    if lower_name in IMPORTANT_FILENAMES:
        score += 30
    if lower_name.startswith("readme"):
        score += 20

    core_signals = (
        "main",
        "app",
        "server",
        "index",
        "api",
        "controller",
        "service",
        "model",
        "database",
        "route",
        "router",
        "component",
    )
    support_signals = ("config", "helper", "util")
    lower_stem = relative_path.stem.lower()
    if any(signal in lower_stem for signal in core_signals):
        score += 35
    elif any(signal in lower_stem for signal in support_signals):
        score += 12

    if ".github" in parts or ".devcontainer" in parts:
        score -= 15
    if (
        "test" in parts
        or "tests" in parts
        or lower_name.startswith("test_")
        or lower_name.endswith("_test.py")
    ):
        score -= 35
    if parts.intersection({"examples", "fixtures", "generated", "vendor"}):
        score -= 25

    return score, lower_path


def select_important_files(repository_path, source_files):
    """Select the highest-priority files within the per-request analysis limit."""
    return sorted(
        source_files,
        key=lambda file_path: file_importance(file_path, repository_path),
        reverse=True,
    )[:MAX_ANALYZED_FILES]


def extract_file_structure(file_path, file_text):
    """Extract imports and code names locally without using the language model."""
    suffix = Path(file_path).suffix.lower()
    structure = {
        "imports": [],
        "classes": [],
        "functions": [],
        "constants": [],
        "dependencies": [],
    }

    if suffix == ".py":
        try:
            syntax_tree = ast.parse(file_text)
        except SyntaxError:
            syntax_tree = None

        if syntax_tree is not None:
            for node in syntax_tree.body:
                if isinstance(node, ast.Import):
                    structure["imports"].extend(
                        alias.name for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    structure["imports"].append(
                        f"from {module} import "
                        + ", ".join(alias.name for alias in node.names[:4])
                    )
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    parameters = [
                        argument.arg
                        for argument in node.args.args
                    ]
                    structure["functions"].append(
                        f"{node.name}({', '.join(parameters)})"
                    )
                elif isinstance(node, ast.ClassDef):
                    structure["classes"].append(node.name)
                    for class_item in node.body:
                        if isinstance(
                            class_item,
                            (ast.FunctionDef, ast.AsyncFunctionDef),
                        ):
                            parameters = [
                                argument.arg for argument in class_item.args.args
                            ]
                            structure["functions"].append(
                                f"{node.name}.{class_item.name}"
                                f"({', '.join(parameters)})"
                            )
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            structure["constants"].append(target.id)
    else:
        import_patterns = (
            r"(?m)^\s*import\s+[^;\n]+",
            r"(?m)^\s*from\s+[\w.]+\s+import\s+[^;\n]+",
            r"(?m)^\s*#include\s+[<\"].+[>\"]",
            r"(?m)^\s*use\s+[\w:{},* ]+;",
            r"(?m)^\s*require\s*\(?\s*[\"'][^\"']+[\"']",
        )
        for pattern in import_patterns:
            structure["imports"].extend(re.findall(pattern, file_text))

        structure["classes"].extend(
            re.findall(
                r"(?m)^\s*(?:export\s+)?(?:abstract\s+)?"
                r"(?:class|interface|struct|enum|trait)\s+([A-Za-z_]\w*)",
                file_text,
            )
        )
        structure["functions"].extend(
            re.findall(
                r"(?m)^\s*(?:export\s+)?(?:async\s+)?"
                r"(?:def|function|fn|func)\s+([A-Za-z_]\w*)\s*"
                r"\(([^)\n]*)\)",
                file_text,
            )
        )
        structure["functions"] = [
            f"{name}({', '.join(parameter.strip().split('=')[0] for parameter in parameters.split(',') if parameter.strip())})"
            for name, parameters in structure["functions"]
        ]
        if suffix in {".c", ".cpp", ".h", ".java", ".cs", ".kt", ".swift"}:
            function_matches = re.findall(
                r"(?m)^\s*(?:static\s+|inline\s+|public\s+|private\s+|protected\s+|"
                r"virtual\s+|extern\s+|final\s+|const\s+)*"
                r"[\w:<>,\[\].?]+\s*[*&]?\s*([A-Za-z_]\w*)\s*"
                r"\(([^;{}]*)\)\s*(?:const\s*)?(?:\{|;|$)",
                file_text,
            )
            for function_name, parameters in function_matches:
                parameter_names = []
                for parameter in parameters.split(","):
                    names = re.findall(r"([A-Za-z_]\w*)\s*(?:=.*)?$", parameter.strip())
                    if names:
                        parameter_names.append(names[-1])
                structure["functions"].append(
                    f"{function_name}({', '.join(parameter_names)})"
                )
        structure["constants"].extend(
            re.findall(
                r"(?m)^\s*(?:export\s+)?(?:const|let|var)?\s*"
                r"([A-Z][A-Z0-9_]{2,})\s*(?::[^=]+)?=",
                file_text,
            )
        )

    if Path(file_path).name.lower() == "requirements.txt":
        structure["dependencies"].extend(
            re.findall(
                r"(?m)^\s*([A-Za-z0-9_.-]+)\s*(?:[<>=!~].*)?$",
                "\n".join(
                    line.split("#", 1)[0]
                    for line in file_text.splitlines()
                    if not line.lstrip().startswith("#")
                ),
            )
        )
    elif suffix == ".toml":
        project_section = re.search(
            r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)",
            file_text,
        )
        if project_section:
            dependency_blocks = re.findall(
                r"(?ms)^\s*(?:dependencies|optional-dependencies)\s*=\s*\[(.*?)\]",
                project_section.group(1),
            )
            dependency_lines = []
            for dependency_block in dependency_blocks:
                dependency_lines.extend(
                    re.findall(
                        r"""["']([A-Za-z0-9_.-]+)\s*(?:[<>=!~].*)?["']""",
                        dependency_block,
                    )
                )
            structure["dependencies"].extend(dependency_lines)
    elif Path(file_path).name.lower() == "package.json":
        try:
            package_data = json.loads(file_text)
        except json.JSONDecodeError:
            package_data = {}
        for dependency_group in ("dependencies", "devDependencies", "optionalDependencies"):
            dependency_values = package_data.get(dependency_group, {})
            if isinstance(dependency_values, dict):
                structure["dependencies"].extend(dependency_values.keys())

    for key in structure:
        structure[key] = list(dict.fromkeys(structure[key]))[:12]
    return structure


def scan_file_structures(repository_path, source_files):
    """Build compact local structure summaries for all discovered files."""
    structures = {}
    analysis_notes = []
    scanned_bytes = 0
    repository_path = Path(repository_path)

    for file_path in source_files:
        file_path = Path(file_path)
        relative_path = file_path.relative_to(repository_path).as_posix()

        try:
            file_size = file_path.stat().st_size
            if scanned_bytes + min(file_size, MAX_FILE_BYTES) > MAX_LOCAL_SCAN_BYTES:
                analysis_notes.append(
                    "Local structure scanning reached its 20 MB safety limit; "
                    "some lower-priority files were not summarized."
                )
                break

            with file_path.open("rb") as source_file:
                raw_content = source_file.read(min(file_size, MAX_FILE_BYTES))
        except OSError as error:
            analysis_notes.append(f"{relative_path} could not be scanned: {error}")
            continue

        scanned_bytes += len(raw_content)
        if b"\0" in raw_content:
            analysis_notes.append(f"{relative_path} was skipped because it is binary.")
            continue

        file_text = raw_content.decode("utf-8", errors="replace")
        structure = extract_file_structure(relative_path, file_text)
        structures[relative_path] = {
            "path": relative_path,
            "size_bytes": file_size,
            "structure": structure,
            "large": file_size > MAX_FILE_BYTES,
        }

    return structures, analysis_notes


def select_deep_analysis_files(repository_path, source_files, structures):
    """Choose up to ten source files, avoiding tests when product code exists."""
    source_files = [
        file_path
        for file_path in source_files
        if Path(file_path).suffix.lower() in SOURCE_CODE_EXTENSIONS
        and Path(file_path).relative_to(repository_path).as_posix() in structures
    ]
    non_test_files = [
        file_path
        for file_path in source_files
        if file_importance(file_path, repository_path)[0] >= 40
        and not any(
            part.lower() in {"test", "tests"}
            for part in Path(file_path).relative_to(repository_path).parts
        )
        and not Path(file_path).name.lower().startswith("test_")
    ]
    preferred_files = non_test_files or source_files
    return select_important_files(repository_path, preferred_files)


def hide_secrets(file_content):
    """Mask common secret assignments before repository text reaches the LLM."""
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            file_content = pattern.sub(
                lambda match: match.group(1) + HIDDEN_SECRET_TEXT,
                file_content,
            )
        else:
            file_content = pattern.sub(HIDDEN_SECRET_TEXT, file_content)
    return file_content


def read_source_files(repository_path, source_files):
    """Read selected text files for Qwen and report any truncation."""
    code_by_file = {}
    analysis_notes = []
    repository_path = Path(repository_path)

    for file_path in source_files:
        file_path = Path(file_path)
        relative_path = file_path.relative_to(repository_path).as_posix()

        try:
            file_size = file_path.stat().st_size
            with file_path.open("rb") as source_file:
                if file_size <= MAX_FILE_BYTES:
                    raw_content = source_file.read(MAX_FILE_BYTES + 1)
                else:
                    beginning = source_file.read(MAX_FILE_CHARACTERS * 2)
                    source_file.seek(max(0, file_size - 1500))
                    ending = source_file.read(1500)
                    raw_content = beginning + b"\n\n... middle of large file omitted ...\n\n" + ending
        except OSError as error:
            analysis_notes.append(f"{relative_path} could not be read: {error}")
            continue

        if b"\0" in raw_content:
            analysis_notes.append(f"{relative_path} was skipped because it is binary.")
            continue

        file_content = raw_content.decode("utf-8", errors="replace")
        truncated = file_size > MAX_FILE_BYTES or len(file_content) > MAX_FILE_CHARACTERS
        if len(file_content) > MAX_FILE_CHARACTERS:
            marker = "\n\n... middle of large file omitted ...\n\n"
            first_part_size = (MAX_FILE_CHARACTERS - len(marker)) * 3 // 4
            last_part_size = MAX_FILE_CHARACTERS - len(marker) - first_part_size
            file_content = (
                file_content[:first_part_size]
                + marker
                + file_content[-last_part_size:]
            )
        elif truncated:
            file_content = file_content[:MAX_FILE_CHARACTERS]

        if truncated:
            analysis_notes.append(
                f"{relative_path} is large; only selected portions were analyzed."
            )

        code_by_file[relative_path] = hide_secrets(file_content)

    return code_by_file, analysis_notes


def format_repository_tree(source_files, repository_path):
    """Create a compact tree-like list from discovered project files."""
    paths = sorted(
        str(Path(file_path).relative_to(repository_path)).replace("\\", "/")
        for file_path in source_files[:MAX_TREE_ENTRIES]
    )
    tree = "\n".join(f"- {path}" for path in paths)
    if len(source_files) > MAX_TREE_ENTRIES:
        tree += f"\n- ... {len(source_files) - MAX_TREE_ENTRIES} more supported files"
    return tree or "No supported text files were found."
