#!/usr/bin/env python3
"""
检查系统中未使用的函数（排除测试用例中的调用）
"""

import ast
import os
from pathlib import Path
from typing import Dict, Set, List, Tuple
from collections import defaultdict


class FunctionUsageChecker(ast.NodeVisitor):
    """AST访问器，用于收集函数定义和调用"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.defined_functions: Set[str] = set()
        self.defined_methods: Dict[str, Set[str]] = defaultdict(
            set
        )  # class_name -> methods
        self.called_functions: Set[str] = set()
        self.called_methods: Dict[str, Set[str]] = defaultdict(
            set
        )  # class_name -> methods
        self.current_class: str = None
        self.imports: Dict[str, str] = {}  # imported_name -> module_name
        self.variable_types: Dict[str, str] = (
            {}
        )  # variable_name -> class_name (用于追踪实例类型)
        self.defined_classes: Set[str] = set()  # 定义的类名

    def visit_FunctionDef(self, node):
        """收集函数定义"""
        if self.current_class:
            # 类方法
            self.defined_methods[self.current_class].add(node.name)
            # 私有方法（以_开头）通常不检查
            if node.name.startswith("_") and not node.name.startswith("__"):
                pass
        else:
            # 模块级函数
            self.defined_functions.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        """收集异步函数定义"""
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        """处理类定义"""
        self.defined_classes.add(node.name)
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_Call(self, node):
        """收集函数调用"""
        if isinstance(node.func, ast.Name):
            # 直接函数调用
            self.called_functions.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            # 方法调用或模块.函数调用
            if isinstance(node.func.value, ast.Name):
                # obj.method() 或 module.function()
                obj_name = node.func.value.id
                method_name = node.func.attr

                # 检查是否是类方法调用
                if obj_name in self.defined_methods:
                    self.called_methods[obj_name].add(method_name)
                # 检查是否是已知类型的实例变量
                elif obj_name in self.variable_types:
                    class_name = self.variable_types[obj_name]
                    self.called_methods[class_name].add(method_name)
                # 也可能是导入的模块
                elif obj_name in self.imports:
                    self.called_functions.add(f"{obj_name}.{method_name}")
                else:
                    # 可能是实例方法调用，记录方法名（用于匹配任何类的方法）
                    self.called_functions.add(method_name)
            elif isinstance(node.func.value, ast.Attribute):
                # obj.attr.method() - 链式调用
                if isinstance(node.func.value.value, ast.Name):
                    obj_name = node.func.value.value.id
                    method_name = node.func.attr
                    if obj_name in self.defined_methods:
                        self.called_methods[obj_name].add(method_name)
                    elif obj_name in self.variable_types:
                        class_name = self.variable_types[obj_name]
                        self.called_methods[class_name].add(method_name)
        self.generic_visit(node)

    def visit_Assign(self, node):
        """追踪变量赋值，识别实例创建"""
        # 检查是否是类实例化：var = ClassName() 或 var = module.ClassName()
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                # var = ClassName()
                class_name = node.value.func.id
                if class_name in self.defined_classes or class_name in self.imports:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.variable_types[target.id] = class_name
            elif isinstance(node.value.func, ast.Attribute):
                # var = module.ClassName() 或 var = obj.ClassName()
                if isinstance(node.value.func.value, ast.Name):
                    module_or_obj = node.value.func.value.id
                    class_name = node.value.func.attr
                    # 如果是导入的模块
                    if module_or_obj in self.imports:
                        full_class_name = f"{self.imports[module_or_obj]}.{class_name}"
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                self.variable_types[target.id] = class_name
                    else:
                        # 可能是 obj.ClassName()，记录类名
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                self.variable_types[target.id] = class_name
        self.generic_visit(node)

    def visit_Import(self, node):
        """收集导入"""
        for alias in node.names:
            if alias.asname:
                self.imports[alias.asname] = alias.name
            else:
                self.imports[alias.name] = alias.name

    def visit_ImportFrom(self, node):
        """收集from导入"""
        module = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = f"{module}.{alias.name}"
            # 如果导入的是实例变量（如 template_manager），需要追踪其类型
            # 这需要在后续分析中处理


def get_python_files(root_dir: Path, exclude_tests: bool = True) -> List[Path]:
    """获取所有Python文件"""
    python_files = []
    exclude_dirs = {
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".git",
        "htmlcov",
        "node_modules",
    }

    for path in root_dir.rglob("*.py"):
        # 排除虚拟环境和第三方库
        if any(exclude_dir in path.parts for exclude_dir in exclude_dirs):
            continue
        # 排除测试文件
        if exclude_tests and ("test" in path.parts or path.name.startswith("test_")):
            continue
        # 排除__pycache__
        if "__pycache__" in path.parts:
            continue
        python_files.append(path)
    return python_files


def analyze_file(file_path: Path) -> FunctionUsageChecker:
    """分析单个文件"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content, filename=str(file_path))
        checker = FunctionUsageChecker(str(file_path))
        checker.visit(tree)
        return checker
    except Exception as e:
        print(f"分析文件 {file_path} 时出错: {e}")
        return None


def get_function_qualname(
    file_path: Path, func_name: str, class_name: str = None, base_dir: Path = None
) -> str:
    """获取函数的完整限定名"""
    # 计算相对于基础目录的模块路径
    if base_dir:
        rel_path = file_path.relative_to(base_dir)
    else:
        rel_path = file_path.relative_to(Path.cwd())
    module_parts = list(rel_path.parts[:-1]) + [rel_path.stem]
    module_path = ".".join(module_parts)

    if class_name:
        return f"{module_path}.{class_name}.{func_name}"
    return f"{module_path}.{func_name}"


def check_unused_functions():
    """主检查函数"""
    root_dir = Path.cwd()
    # 只检查 jjz_alert 目录
    target_dir = root_dir / "jjz_alert"

    if not target_dir.exists():
        print(f"错误: {target_dir} 目录不存在")
        return

    print(f"正在扫描 {target_dir} 目录下的Python文件...")
    python_files = get_python_files(target_dir, exclude_tests=True)
    print(f"找到 {len(python_files)} 个非测试Python文件\n")

    # 分析所有文件
    all_checkers: Dict[Path, FunctionUsageChecker] = {}
    all_defined_functions: Dict[str, Tuple[Path, str, str]] = (
        {}
    )  # qualname -> (file, func_name, class_name)
    all_called_functions: Set[str] = set()
    all_called_methods: Dict[str, Set[str]] = defaultdict(set)  # class_name -> methods

    # 第一遍：收集所有定义
    print("正在分析文件（第一遍：收集定义）...")
    for file_path in python_files:
        checker = analyze_file(file_path)
        if checker:
            all_checkers[file_path] = checker

            # 收集所有定义的函数
            for func_name in checker.defined_functions:
                qualname = get_function_qualname(
                    file_path, func_name, base_dir=target_dir
                )
                all_defined_functions[qualname] = (file_path, func_name, None)

            # 收集所有定义的类方法
            for class_name, methods in checker.defined_methods.items():
                for method_name in methods:
                    qualname = get_function_qualname(
                        file_path, method_name, class_name, base_dir=target_dir
                    )
                    all_defined_functions[qualname] = (
                        file_path,
                        method_name,
                        class_name,
                    )

    # 构建全局变量类型映射（跨文件）
    global_variable_types: Dict[str, Dict[str, str]] = (
        {}
    )  # file_path -> {var_name -> class_name}

    # 第二遍：收集所有调用和跨文件的变量类型
    print("正在分析文件（第二遍：收集调用和变量类型）...")
    for file_path in python_files:
        checker = all_checkers[file_path]
        if checker:
            global_variable_types[file_path] = checker.variable_types.copy()

            # 收集所有调用的函数（简单名称，用于匹配）
            all_called_functions.update(checker.called_functions)
            # 收集通过类名调用的方法
            for class_name, methods in checker.called_methods.items():
                all_called_methods[class_name].update(methods)

            # 处理通过实例变量调用的方法
            for var_name, var_class in checker.variable_types.items():
                # 在所有文件中查找这个类
                for other_file, other_checker in all_checkers.items():
                    if var_class in other_checker.defined_classes:
                        # 找到了类定义，记录该类的方法调用
                        # 检查是否有通过这个变量调用的方法
                        if var_name in checker.called_methods:
                            all_called_methods[var_class].update(
                                checker.called_methods[var_name]
                            )

    # 第三遍：处理跨文件的实例变量（如从其他模块导入的 template_manager）
    print("正在分析文件（第三遍：处理跨文件导入的实例）...")
    # 构建模块路径到文件的映射（支持多种路径格式）
    module_to_file: Dict[str, Path] = {}
    for file_path in python_files:
        rel_path = file_path.relative_to(target_dir)
        module_parts = list(rel_path.parts[:-1]) + [rel_path.stem]
        # 相对路径（如 base.message_templates）
        module_path = ".".join(module_parts)
        module_to_file[module_path] = file_path
        # 完整路径（如 jjz_alert.base.message_templates）
        full_module_path = f"jjz_alert.{module_path}"
        module_to_file[full_module_path] = file_path

    for file_path in python_files:
        checker = all_checkers[file_path]
        if checker:
            # 检查导入的变量，看是否是其他文件中定义的实例
            for imported_name, import_path in checker.imports.items():
                # 查找导入路径对应的文件（支持完整路径和相对路径）
                other_file = None
                other_checker = None

                if import_path in module_to_file:
                    other_file = module_to_file[import_path]
                    other_checker = all_checkers[other_file]
                else:
                    # 尝试匹配部分路径（如 jjz_alert.base.message_templates -> base.message_templates）
                    for mod_path, mod_file in module_to_file.items():
                        if import_path.endswith(mod_path) or mod_path in import_path:
                            other_file = mod_file
                            other_checker = all_checkers[other_file]
                            break

                if other_file and other_checker:
                    # 检查该文件中是否有这个变量（模块级变量）
                    if imported_name in other_checker.variable_types:
                        var_class = other_checker.variable_types[imported_name]
                        # 记录这个导入变量的类型
                        checker.variable_types[imported_name] = var_class
                        # 如果当前文件通过这个导入的变量调用了方法，记录到对应类
                        if imported_name in checker.called_methods:
                            all_called_methods[var_class].update(
                                checker.called_methods[imported_name]
                            )

                        # 重新检查调用：遍历文件内容，查找通过这个变量调用的方法
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                            # 查找 imported_name.method_name( 的模式
                            import re

                            pattern = rf"{re.escape(imported_name)}\.(\w+)\s*\("
                            matches = re.findall(pattern, content)
                            for method_name in matches:
                                all_called_methods[var_class].add(method_name)
                        except:
                            pass

    print(f"找到 {len(all_defined_functions)} 个函数定义\n")

    # 检查未使用的函数
    unused_functions = []

    for qualname, (file_path, func_name, class_name) in all_defined_functions.items():
        # 跳过特殊方法（__init__, __str__等）
        if func_name.startswith("__") and func_name.endswith("__"):
            continue

        # 跳过私有方法（以_开头但不是__开头）
        if func_name.startswith("_") and not func_name.startswith("__"):
            continue

        # 检查是否被调用
        is_used = False

        # 1. 检查直接函数名调用
        if func_name in all_called_functions:
            is_used = True

        # 2. 如果是类方法，检查是否通过类名被调用
        if not is_used and class_name:
            if (
                class_name in all_called_methods
                and func_name in all_called_methods[class_name]
            ):
                is_used = True

        # 3. 检查是否在__all__中导出（通常意味着会被外部使用）
        if not is_used:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if f'"{func_name}"' in content or f"'{func_name}'" in content:
                        # 检查是否在__all__中
                        if "__all__" in content:
                            # 简单检查，可能不够精确
                            lines = content.split("\n")
                            in_all = False
                            for i, line in enumerate(lines):
                                if "__all__" in line:
                                    # 检查后续几行
                                    for j in range(i, min(i + 20, len(lines))):
                                        if func_name in lines[j] and (
                                            '"' in lines[j] or "'" in lines[j]
                                        ):
                                            in_all = True
                                            break
                                    break
                            if in_all:
                                is_used = True  # 在__all__中，可能被外部使用
            except:
                pass

        # 4. 检查是否在导入语句中被导入（从其他文件）
        if not is_used:
            for other_file, other_checker in all_checkers.items():
                if other_file != file_path:
                    # 检查是否导入了这个模块
                    module_name = file_path.stem
                    if module_name in other_checker.imports.values():
                        # 可能通过模块访问，标记为已使用
                        is_used = True
                        break

        if not is_used:
            unused_functions.append((qualname, file_path, func_name, class_name))

    # 输出结果
    print("=" * 80)
    print("未使用的函数列表（排除测试用例中的调用）")
    print("=" * 80)

    if not unused_functions:
        print("\n✅ 未发现未使用的函数！")
        return

    # 按文件分组
    by_file = defaultdict(list)
    for qualname, file_path, func_name, class_name in unused_functions:
        by_file[file_path].append((qualname, func_name, class_name))

    for file_path in sorted(by_file.keys()):
        print(f"\n📄 {file_path.relative_to(target_dir)}")
        for qualname, func_name, class_name in sorted(by_file[file_path]):
            if class_name:
                print(f"  - {class_name}.{func_name} ({qualname})")
            else:
                print(f"  - {func_name} ({qualname})")

    print(f"\n总计: {len(unused_functions)} 个未使用的函数")


if __name__ == "__main__":
    check_unused_functions()
