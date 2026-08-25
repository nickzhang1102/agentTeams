import ast
from pathlib import Path


UNSAFE_OPERATIONS = {
    'add_column',
    'create_foreign_key',
    'create_index',
    'create_table',
    'create_unique_constraint',
}


class UnsafeOperationVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.unsafe_calls: list[str] = []
        self._inside_upgrade = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        was_inside_upgrade = self._inside_upgrade
        self._inside_upgrade = node.name == 'upgrade'
        self.generic_visit(node)
        self._inside_upgrade = was_inside_upgrade

    def visit_Call(self, node: ast.Call) -> None:
        if self._inside_upgrade and isinstance(node.func, ast.Attribute):
            if node.func.attr in UNSAFE_OPERATIONS and _is_op_name(node.func.value):
                self.unsafe_calls.append(node.func.attr)
        self.generic_visit(node)


def _is_op_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == 'op'


def test_upgrade_scripts_use_safe_operations_for_schema_creation() -> None:
    versions_dir = Path(__file__).resolve().parents[1] / 'migrations' / 'versions'

    unsafe_by_file: dict[str, list[str]] = {}
    for path in versions_dir.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        visitor = UnsafeOperationVisitor()
        visitor.visit(tree)
        if visitor.unsafe_calls:
            unsafe_by_file[path.name] = visitor.unsafe_calls

    assert unsafe_by_file == {}
