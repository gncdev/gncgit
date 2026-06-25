import argparse
import fnmatch
from dataclasses import asdict
from functools import wraps
from pathlib import Path
import hashlib
import json

from gncgit.models import Branch, Commit, Index

GNCGIT_TREE = {
    ".gncgit": {
        "index.json": "f",
        "commits": {},
        "objects": {},
        "refs": {
            "heads": {
                "main": "f"
            }
        },
        "HEAD": "f"
    }
}


def requires_repo(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        self.ensure_repo()
        return method(self, *args, **kwargs)

    return wrapper


class GNCGIT:
    def __init__(self, root="."):
        self.root = Path(root).resolve()
        self.base_path = self.root / ".gncgit"
        self.head_file = self.base_path / "HEAD"
        self.index_file = self.base_path / "index.json"
        self.commits_dir = self.base_path / "commits"
        self.objects_dir = self.base_path / "objects"
        self.refs_dir = self.base_path / "refs"
        self.heads_dir = self.refs_dir / "heads"

    def calculate_commit_id(self):
        existing_commits = []
        for commit_file in self.commits_dir.glob("*.json"):
            try:
                existing_commits.append(int(commit_file.stem))
            except ValueError:
                continue
        if not existing_commits:
            return "0001"
        return f"{max(existing_commits) + 1:04d}"

    def ensure_repo(self):
        if not self.base_path.exists():
            raise RuntimeError("Run 'init' first")
        required_paths = [
            self.head_file,
            self.index_file,
            self.commits_dir,
            self.objects_dir,
            self.refs_dir,
            self.heads_dir,
        ]
        for path in required_paths:
            if not path.exists():
                raise RuntimeError(f"Invalid repository. Missing: {path}")

    @requires_repo
    def get_commit(self, commit_id=None) -> Commit | None:
        if not commit_id:
            commit_id = self.get_branch().last_commit
        if not commit_id:
            return None
        commit_path = self.commits_dir / f"{commit_id}.json"
        if not commit_path.exists():
            raise RuntimeError(f"Invalid commit id: {commit_id}")
        data = json.loads(commit_path.read_text(encoding="utf-8"))
        return Commit(**data)

    @requires_repo
    def get_branch(self, branch=None) -> Branch:
        if not branch:
            branch = self.head_file.read_text(encoding="utf-8").strip()
        branch_file = self.heads_dir / branch
        if not branch_file.exists():
            raise RuntimeError(f"Branch not found: {branch}")
        last_commit = branch_file.read_text(encoding="utf-8").strip()
        if last_commit == "":
            last_commit = None
        return Branch(branch, last_commit)

    @requires_repo
    def load_index(self) -> Index:
        content = self.index_file.read_text(encoding="utf-8").strip()
        if not content:
            return Index()
        return Index.from_dict(json.loads(content))

    def walk_git_tree(self, base_path, tree):
        if isinstance(tree, str) and tree == "f":
            (self.root / base_path).touch(exist_ok=True)
        elif isinstance(tree, dict) and len(tree) == 0:
            (self.root / base_path).mkdir(parents=True, exist_ok=True)
        else:
            for _base_path, _tree in tree.items():
                if base_path:
                    (self.root / base_path).mkdir(parents=True, exist_ok=True)
                    self.walk_git_tree(Path(base_path) / _base_path, _tree)
                else:
                    self.walk_git_tree(_base_path, _tree)

    def init(self):
        if self.base_path.exists():
            raise RuntimeError("repository already exists.")
        self.walk_git_tree(None, GNCGIT_TREE)
        self.head_file.write_text("main", encoding="utf-8")
        self.index_file.write_text(json.dumps({"main": {}}, indent=2), encoding="utf-8")

    @requires_repo
    def add(self, file_name):
        file = (self.root / file_name).resolve()
        if not file.is_file():
            raise FileNotFoundError(f"File not found: {file_name}")
        patterns = self.load_gitignore_patterns()
        if self.check_gitignore(file, patterns):
            print(f"Ignored: {file_name}")
            return
        content = file.read_bytes()
        hashed_content = hashlib.sha1(content).hexdigest()
        hashed_file = self.objects_dir / hashed_content
        if not hashed_file.exists():
            hashed_file.write_bytes(content)
        current_branch = self.get_branch()
        index = self.load_index()
        relative_file = file.relative_to(self.root).as_posix()
        index.add_file(current_branch.name, relative_file, hashed_content)
        self.index_file.write_text(json.dumps(index.to_dict(), indent=4), encoding="utf-8")
        print(f"Added {file_name}")

    @requires_repo
    def commit(self, message):
        index = self.load_index()
        current_branch = self.get_branch()
        staged_files = index.get_branch_files(current_branch.name)
        if len(staged_files) == 0:
            print("Nothing to commit.")
            return
        new_commit_id = self.calculate_commit_id()
        parent_commit = self.get_commit()
        parent_commit_id = parent_commit.id if parent_commit else None
        parent_files = parent_commit.files if parent_commit else {}
        files = parent_files.copy()
        files.update(staged_files)
        commit = Commit(new_commit_id, message, parent_commit_id, files)
        commit_path = self.commits_dir / f"{commit.id}.json"
        commit_path.write_text(json.dumps(asdict(commit), indent=2), encoding="utf-8")
        (self.heads_dir / current_branch.name).write_text(new_commit_id, encoding="utf-8")
        index.clear_branch(current_branch.name)
        self.index_file.write_text(json.dumps(index.to_dict(), indent=2), encoding="utf-8")
        print(f"Committed as {new_commit_id}")

    @requires_repo
    def checkout(self, branch_name: str):
        if branch_name == self.get_branch().name:
            print("Branch already checked out.")
            return
        branch_file = self.heads_dir / branch_name
        if not branch_file.exists():
            branch_file.write_text(
                self.get_branch().last_commit or "",
                encoding="utf-8"
            )
            print(f"Created branch: {branch_name}")
        branch = self.get_branch(branch_name)
        self.head_file.write_text(branch.name, encoding="utf-8")
        target_commit = self.get_commit(branch.last_commit)
        if target_commit is None:
            print("Nothing to checkout.")
            return
        for filename, object_hash in target_commit.files.items():
            if not (self.objects_dir / object_hash).exists():
                raise FileNotFoundError(f"Missing file object: {object_hash}")
            filename_path = self.root / filename
            filename_path.parent.mkdir(parents=True, exist_ok=True)
            filename_path.write_bytes((self.objects_dir / object_hash).read_bytes())

    def load_gitignore_patterns(self):
        patterns = []
        gitignore_file = self.root / ".gitignore"
        if gitignore_file.exists():
            content = gitignore_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                patterns.append(line)
        patterns.append(".gncgit")
        patterns.append(".gncgit/*")
        patterns.append(".gncgit/**")
        return patterns

    def check_gitignore(self, path, patterns):
        path = Path(path).resolve()
        try:
            relative_path = path.relative_to(self.root)
        except ValueError:
            raise RuntimeError("Cannot add files outside repository.")
        if ".gncgit" in path.parts:
            return True
        path_text = relative_path.as_posix()
        for pattern in patterns:
            if fnmatch.fnmatch(path_text, pattern):
                return True
        return False


def create_argparser():
    parser = argparse.ArgumentParser(prog="gncgit")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("file_name")
    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("-m", "--message", required=True)
    checkout_parser = subparsers.add_parser("checkout")
    checkout_parser.add_argument("branch")
    return parser


if __name__ == "__main__":
    parser = create_argparser()
    args = parser.parse_args()
    gncgit = GNCGIT()
    try:
        if args.command == "init":
            gncgit.init()
        elif args.command == "add":
            gncgit.add(args.file_name)
        elif args.command == "commit":
            gncgit.commit(args.message)
        elif args.command == "checkout":
            gncgit.checkout(args.branch)

    except (FileNotFoundError, RuntimeError, json.JSONDecodeError) as error:
        parser.error(str(error))
