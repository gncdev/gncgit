from dataclasses import dataclass, field


@dataclass
class Commit:
    id: str
    message: str
    parent: str | None
    files: dict[str, str] = field(default_factory=dict)


@dataclass
class Branch:
    name: str
    last_commit: str | None = None


@dataclass
class Index:
    branches: dict[str, dict[str, str]] = field(default_factory=dict)
    def add_file(self, branch_name: str, file_name: str, file_hash: str):
        if branch_name not in self.branches:
            self.branches[branch_name] = {}
        self.branches[branch_name][file_name] = file_hash
    def pop_file(self, branch_name: str, file_name: str):
        self.branches[branch_name].pop(file_name)
    def clear_branch(self, branch_name: str):
        self.branches[branch_name] = {}
    def get_branch_files(self, branch_name: str) -> dict[str, str]:
        return self.branches.get(branch_name, {})
    def to_dict(self) -> dict[str, dict[str, str]]:
        return self.branches
    @classmethod
    def from_dict(cls, data: dict[str, dict[str, str]]):
        return cls(branches=data)